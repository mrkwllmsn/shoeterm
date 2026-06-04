#include "graphics.h"

#include <stdlib.h>
#include <string.h>

#include <fcft/fcft.h>

#define LOG_MODULE "graphics"
#define LOG_ENABLE_DBG 0
#include "log.h"
#include "debug.h"
#include "graphics_draw.h"
#include "sixel.h"
#include "util.h"
#include "xmalloc.h"

/*
 * Vector graphics protocol.
 *
 *   ESC P > g <body> ESC \
 *
 * <body> is a list of commands separated by newlines or commas (a comma
 * lets a whole drawing fit on one line). '#' starts a line comment, and
 * 'text' takes the rest of its line as a string — both ignore commas.
 * Coordinates are pixels, origin top-left of the canvas.
 * Colours are '#rrggbb', '#rrggbbaa' or 'none'.
 *
 *   size <cols> <rows>          canvas size, in terminal CELLS (required first)
 *   bg   <colour>               fill canvas background (default: none)
 *   pen  <colour>               current draw colour
 *   thickness <n>               line/outline thickness (default 1)
 *   clear                       reset canvas to background
 *   clip <x> <y> <w> <h>        clip subsequent drawing
 *   noclip                      remove clip
 *   pixel <x> <y>
 *   line  <x0> <y0> <x1> <y1>
 *   rect  <x> <y> <w> <h>       outline
 *   rectf <x> <y> <w> <h>       filled
 *   circ  <cx> <cy> <r>         outline
 *   circf <cx> <cy> <r>         filled
 *   tri   <x0> <y0> <x1> <y1> <x2> <y2>     outline
 *   trif  <x0> <y0> <x1> <y1> <x2> <y2>     filled
 *   poly  <x0> <y0> <x1> <y1> ...           closed outline
 *   polyf <x0> <y0> <x1> <y1> ...           filled
 *   text  <x> <y> <utf-8 string...>         (string = rest of line)
 *
 * All state (canvas, pen, clip, ...) is local to graphics_unhook(): the
 * raw body bytes are accumulated by graphics_put() and parsed in one
 * pass. The finished ARGB canvas is handed to the sixel image pipeline
 * via sixel_emit_image().
 */

/* Limits (struct canvas + rasterizers live in graphics_draw.h) */
#define GFX_MAX_DIM 10000          /* max canvas width/height, pixels */
#define GFX_MAX_THICKNESS 256

/* ------------------------------------------------------------------ */
/* Colour helpers                                                      */
/* ------------------------------------------------------------------ */

static int
hexval(char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

/* Parse "#rrggbb", "#rrggbbaa" or "none". Returns premultiplied ARGB. */
static bool
parse_color(const char *s, size_t n, uint32_t *out)
{
    if (n == 4 && memcmp(s, "none", 4) == 0) {
        *out = 0;
        return true;
    }

    if (n != 7 && n != 9)
        return false;
    if (s[0] != '#')
        return false;

    int v[8];
    for (size_t i = 1; i < n; i++) {
        v[i - 1] = hexval(s[i]);
        if (v[i - 1] < 0)
            return false;
    }

    uint8_t r = v[0] << 4 | v[1];
    uint8_t g = v[2] << 4 | v[3];
    uint8_t b = v[4] << 4 | v[5];
    uint8_t a = n == 9 ? (v[6] << 4 | v[7]) : 0xff;

    *out = premul(a, r, g, b);
    return true;
}

/* ------------------------------------------------------------------ */
/* Tokenizing                                                          */
/* ------------------------------------------------------------------ */

static void
skip_spaces(const char **p, const char *end)
{
    while (*p < end && (**p == ' ' || **p == '\t' || **p == '\r'))
        (*p)++;
}

/* Next whitespace-delimited word. Returns false if none left. */
static bool
next_word(const char **p, const char *end, const char **wstart, size_t *wlen)
{
    skip_spaces(p, end);
    if (*p >= end)
        return false;

    const char *start = *p;
    while (*p < end && **p != ' ' && **p != '\t' && **p != '\r')
        (*p)++;

    *wstart = start;
    *wlen = *p - start;
    return true;
}

/* Next integer. Returns false if the next word is not a valid integer. */
static bool
next_int(const char **p, const char *end, int *out)
{
    const char *w;
    size_t wlen;
    if (!next_word(p, end, &w, &wlen))
        return false;

    bool neg = false;
    size_t i = 0;
    if (i < wlen && (w[i] == '-' || w[i] == '+')) {
        neg = w[i] == '-';
        i++;
    }
    if (i >= wlen)
        return false;

    long val = 0;
    for (; i < wlen; i++) {
        if (w[i] < '0' || w[i] > '9')
            return false;
        val = val * 10 + (w[i] - '0');
        if (val > GFX_MAX_DIM * 4)
            val = GFX_MAX_DIM * 4;   /* clamp, avoid overflow */
    }

    *out = neg ? -(int)val : (int)val;
    return true;
}

/* ------------------------------------------------------------------ */
/* UTF-8 + text                                                        */
/* ------------------------------------------------------------------ */

/* Decode one codepoint. Returns bytes consumed (>=1). */
static size_t
utf8_next(const char *s, size_t len, char32_t *cp)
{
    uint8_t b0 = s[0];

    if (b0 < 0x80) { *cp = b0; return 1; }

    int n;
    char32_t c;
    if ((b0 & 0xe0) == 0xc0) { n = 1; c = b0 & 0x1f; }
    else if ((b0 & 0xf0) == 0xe0) { n = 2; c = b0 & 0x0f; }
    else if ((b0 & 0xf8) == 0xf0) { n = 3; c = b0 & 0x07; }
    else { *cp = 0xfffd; return 1; }

    if (len < (size_t)(n + 1)) { *cp = 0xfffd; return 1; }

    for (int i = 1; i <= n; i++) {
        if ((s[i] & 0xc0) != 0x80) { *cp = 0xfffd; return 1; }
        c = c << 6 | (s[i] & 0x3f);
    }

    *cp = c;
    return n + 1;
}

/*
 * Is `cp` a grapheme "extender" — a codepoint that combines with the
 * preceding base rather than starting a new cluster? This lets `text`
 * group e.g. an emoji and its variation selector (🌦️ = U+1F326 U+FE0F),
 * skin-tone modifiers, ZWJ sequences and combining marks into a single
 * grapheme, so fcft can shape them into one (color) glyph — mirroring
 * foot's normal text path. Without this, the bare base codepoint is
 * rasterized on its own and the emoji presentation is lost.
 */
static bool
is_grapheme_extender(char32_t cp)
{
    return
        cp == 0x200d ||                       /* ZWJ                       */
        cp == 0xfe0e || cp == 0xfe0f ||       /* variation selectors 15/16 */
        (cp >= 0x1f3fb && cp <= 0x1f3ff) ||   /* emoji skin-tone modifiers */
        (cp >= 0x0300 && cp <= 0x036f) ||     /* combining diacritical marks */
        (cp >= 0x1ab0 && cp <= 0x1aff) ||     /* combining diacritical ext */
        (cp >= 0x1dc0 && cp <= 0x1dff) ||     /* combining diacritical supp */
        (cp >= 0x20d0 && cp <= 0x20ff) ||     /* combining marks for symbols */
        (cp >= 0xfe20 && cp <= 0xfe2f);       /* combining half marks      */
}

static bool
is_regional_indicator(char32_t cp)
{
    return cp >= 0x1f1e6 && cp <= 0x1f1ff;
}

/* Composite one already-rasterized glyph at the pen, advancing pen_x. */
static void
blit_glyph(pixman_image_t *dst, pixman_image_t *clr,
           const struct fcft_glyph *g, int *pen_x, int baseline)
{
    if (g == NULL)
        return;

    if (g->is_color_glyph) {
        pixman_image_composite32(
            PIXMAN_OP_OVER, g->pix, NULL, dst, 0, 0, 0, 0,
            *pen_x + g->x, baseline - g->y, g->width, g->height);
    } else {
        pixman_image_composite32(
            PIXMAN_OP_OVER, clr, g->pix, dst, 0, 0, 0, 0,
            *pen_x + g->x, baseline - g->y, g->width, g->height);
    }

    *pen_x += g->advance.x;
}

static void
draw_text(struct terminal *term, struct canvas *c, uint32_t pen,
          int x, int baseline, const char *str, size_t slen)
{
    struct fcft_font *font = term->fonts[0];
    if (font == NULL)
        return;

    pixman_image_t *dst = pixman_image_create_bits_no_clear(
        PIXMAN_a8r8g8b8, c->w, c->h, c->data, c->w * sizeof(uint32_t));
    if (dst == NULL)
        return;

    pixman_region32_t clip;
    pixman_region32_init_rect(&clip, c->clip_x, c->clip_y, c->clip_w, c->clip_h);
    pixman_image_set_clip_region32(dst, &clip);

    /* pen is premultiplied ARGB; pixman_color_t is premultiplied too */
    pixman_color_t pc = {
        .alpha = (uint16_t)((pen >> 24) & 0xff) * 0x101,
        .red   = (uint16_t)((pen >> 16) & 0xff) * 0x101,
        .green = (uint16_t)((pen >> 8) & 0xff) * 0x101,
        .blue  = (uint16_t)((pen >> 0) & 0xff) * 0x101,
    };
    pixman_image_t *clr = pixman_image_create_solid_fill(&pc);

    /* A space's advance, for expanding tabs */
    const struct fcft_glyph *space =
        fcft_rasterize_char_utf32(font, ' ', FCFT_SUBPIXEL_NONE);
    const int space_adv = space != NULL ? space->advance.x : 0;

    /*
     * Decode the whole run to codepoints first (dropping control chars,
     * expanding tabs), so we can look ahead and group grapheme clusters.
     * One byte yields at most one codepoint, so `slen` is a safe bound.
     */
    char32_t *cps = xmalloc((slen + 1) * sizeof(cps[0]));
    size_t n = 0;
    int pen_x = x;

    /* Sentinel marking a tab stop in the decoded stream */
    const char32_t TAB = 0xffffffff;

    {
        size_t i = 0;
        while (i < slen) {
            char32_t cp;
            i += utf8_next(str + i, slen - i, &cp);
            if (cp == '\t')      { cps[n++] = TAB; continue; }
            if (cp < 0x20 || cp == 0x7f)
                continue;        /* drop other controls */
            cps[n++] = cp;
        }
    }

    const bool can_shape = term->conf->can_shape_grapheme;

    size_t i = 0;
    while (i < n) {
        if (cps[i] == TAB) {
            int stop = space_adv * 4;
            if (stop > 0)
                pen_x = x + ((pen_x - x) / stop + 1) * stop;
            i++;
            continue;
        }

        /* Build a grapheme cluster: base + trailing extenders. */
        size_t start = i++;

        /* Regional-indicator (flag) pair */
        if (is_regional_indicator(cps[start]) &&
            i < n && is_regional_indicator(cps[i]))
            i++;

        while (i < n && cps[i] != TAB) {
            if (is_grapheme_extender(cps[i]))
                i++;
            else if (cps[i - 1] == 0x200d)   /* codepoint joined by a ZWJ */
                i++;
            else
                break;
        }

        size_t len = i - start;

        if (len > 1 && can_shape) {
            const struct fcft_grapheme *grapheme =
                fcft_rasterize_grapheme_utf32(font, len, &cps[start],
                                              FCFT_SUBPIXEL_NONE);
            if (grapheme != NULL) {
                for (size_t j = 0; j < grapheme->count; j++)
                    blit_glyph(dst, clr, grapheme->glyphs[j], &pen_x, baseline);
                continue;
            }
            /* fall through: shape the base on its own */
        }

        blit_glyph(dst, clr,
                   fcft_rasterize_char_utf32(font, cps[start], FCFT_SUBPIXEL_NONE),
                   &pen_x, baseline);
    }

    free(cps);
    pixman_image_unref(clr);
    pixman_image_unref(dst);
    pixman_region32_fini(&clip);
}

/* ------------------------------------------------------------------ */
/* DCS handlers                                                        */
/* ------------------------------------------------------------------ */

void
graphics_put(struct terminal *term, uint8_t c)
{
    struct vt *vt = &term->vt;

    /* Grow buffer exponentially (mirrors xtgettcap_put) */
    if (vt->dcs.idx >= vt->dcs.size) {
        size_t new_size = vt->dcs.size * 2;
        if (new_size == 0)
            new_size = 1024;

        uint8_t *new_data = realloc(vt->dcs.data, new_size);
        if (new_data == NULL) {
            LOG_ERRNO("failed to grow graphics DCS buffer");
            return;
        }
        vt->dcs.data = new_data;
        vt->dcs.size = new_size;
    }

    vt->dcs.data[vt->dcs.idx++] = c;
}

static void
set_clip_full(struct canvas *c)
{
    c->clip_x = 0;
    c->clip_y = 0;
    c->clip_w = c->w;
    c->clip_h = c->h;
}

void
graphics_unhook(struct terminal *term)
{
    const char *p = (const char *)term->vt.dcs.data;
    size_t total = term->vt.dcs.idx;
    if (p == NULL || total == 0)
        return;

    const char *end = p + total;

    struct canvas c = {0};
    uint32_t pen = 0xffffffff;   /* opaque white */
    uint32_t bg = 0;             /* premultiplied; 0 => transparent */
    bool transparent_bg = true;
    int thickness = 1;

    while (p < end) {
        const char *nl = memchr(p, '\n', end - p);
        const char *line_end = nl != NULL ? nl : end;
        const char *next_line = nl != NULL ? nl + 1 : end;

        /* Commands are separated by newlines OR commas, so a whole drawing
         * can fit on one line (e.g. a single printf). The 'text' command and
         * '#' comments are exempt — they run to end of line, commas and all
         * (handled below). */
        const char *comma = memchr(p, ',', line_end - p);
        const char *lend = comma != NULL ? comma : line_end;
        const char *lp = p;
        p = comma != NULL ? comma + 1 : next_line;

        /* The terminal line discipline turns each '\n' the client prints
         * into '\r\n', so lines arrive with a trailing CR. Trim it (this
         * matters for 'text', whose argument is the rest of the line). */
        if (lend > lp && lend[-1] == '\r')
            lend--;

        const char *cmd;
        size_t cmdlen;
        if (!next_word(&lp, lend, &cmd, &cmdlen))
            continue;
        if (cmd[0] == '#') {
            p = next_line;   /* a comment runs to end of line, commas included */
            continue;
        }

        #define CMD(s) (cmdlen == sizeof(s) - 1 && memcmp(cmd, s, cmdlen) == 0)

        if (CMD("size")) {
            int cols, rows;
            if (!next_int(&lp, lend, &cols) || !next_int(&lp, lend, &rows))
                continue;
            if (cols < 1 || rows < 1)
                continue;

            int64_t w = (int64_t)cols * term->cell_width;
            int64_t h = (int64_t)rows * term->cell_height;
            if (w < 1 || h < 1 || w > GFX_MAX_DIM || h > GFX_MAX_DIM) {
                LOG_WARN("graphics: canvas %dx%d cells too large", cols, rows);
                continue;
            }

            free(c.data);
            c.w = w;
            c.h = h;
            c.data = xcalloc((size_t)w * h, sizeof(uint32_t));
            set_clip_full(&c);
            bg = 0;
            transparent_bg = true;
        }

        else if (CMD("bg")) {
            const char *w;
            size_t wlen;
            uint32_t col;
            if (!next_word(&lp, lend, &w, &wlen) || !parse_color(w, wlen, &col))
                continue;
            bg = col;
            transparent_bg = (col >> 24) == 0;
            if (c.data != NULL) {
                for (size_t i = 0; i < (size_t)c.w * c.h; i++)
                    c.data[i] = bg;
            }
        }

        else if (CMD("pen")) {
            const char *w;
            size_t wlen;
            uint32_t col;
            if (next_word(&lp, lend, &w, &wlen) && parse_color(w, wlen, &col))
                pen = col;
        }

        else if (CMD("thickness")) {
            int t;
            if (next_int(&lp, lend, &t))
                thickness = t < 1 ? 1 : (t > GFX_MAX_THICKNESS ? GFX_MAX_THICKNESS : t);
        }

        else if (CMD("clear")) {
            if (c.data != NULL)
                for (size_t i = 0; i < (size_t)c.w * c.h; i++)
                    c.data[i] = bg;
        }

        else if (CMD("noclip")) {
            if (c.data != NULL)
                set_clip_full(&c);
        }

        else if (c.data == NULL) {
            /* All remaining commands need a canvas */
            continue;
        }

        else if (CMD("clip")) {
            int x, y, w, h;
            if (!next_int(&lp, lend, &x) || !next_int(&lp, lend, &y) ||
                !next_int(&lp, lend, &w) || !next_int(&lp, lend, &h))
                continue;
            int x0 = max(0, x), y0 = max(0, y);
            int x1 = min(c.w, x + w), y1 = min(c.h, y + h);
            c.clip_x = x0;
            c.clip_y = y0;
            c.clip_w = max(0, x1 - x0);
            c.clip_h = max(0, y1 - y0);
        }

        else if (CMD("pixel")) {
            int x, y;
            if (next_int(&lp, lend, &x) && next_int(&lp, lend, &y))
                plot(&c, x, y, thickness, pen);
        }

        else if (CMD("line")) {
            int x0, y0, x1, y1;
            if (next_int(&lp, lend, &x0) && next_int(&lp, lend, &y0) &&
                next_int(&lp, lend, &x1) && next_int(&lp, lend, &y1))
                draw_line(&c, x0, y0, x1, y1, thickness, pen);
        }

        else if (CMD("rect")) {
            int x, y, w, h;
            if (next_int(&lp, lend, &x) && next_int(&lp, lend, &y) &&
                next_int(&lp, lend, &w) && next_int(&lp, lend, &h))
                outline_rect(&c, x, y, w, h, thickness, pen);
        }

        else if (CMD("rectf")) {
            int x, y, w, h;
            if (next_int(&lp, lend, &x) && next_int(&lp, lend, &y) &&
                next_int(&lp, lend, &w) && next_int(&lp, lend, &h))
                fill_rect(&c, x, y, w, h, pen);
        }

        else if (CMD("circ")) {
            int cx, cy, r;
            if (next_int(&lp, lend, &cx) && next_int(&lp, lend, &cy) &&
                next_int(&lp, lend, &r))
                outline_circle(&c, cx, cy, r, thickness, pen);
        }

        else if (CMD("circf")) {
            int cx, cy, r;
            if (next_int(&lp, lend, &cx) && next_int(&lp, lend, &cy) &&
                next_int(&lp, lend, &r))
                fill_circle(&c, cx, cy, r, pen);
        }

        else if (CMD("arc")) {
            int cx, cy, r, a0, a1;
            if (next_int(&lp, lend, &cx) && next_int(&lp, lend, &cy) &&
                next_int(&lp, lend, &r) && next_int(&lp, lend, &a0) &&
                next_int(&lp, lend, &a1))
                draw_arc(&c, cx, cy, r, a0, a1, thickness, pen);
        }

        else if (CMD("rrect")) {
            int x, y, w, h, r;
            if (next_int(&lp, lend, &x) && next_int(&lp, lend, &y) &&
                next_int(&lp, lend, &w) && next_int(&lp, lend, &h) &&
                next_int(&lp, lend, &r))
                outline_round_rect(&c, x, y, w, h, r, thickness, pen);
        }

        else if (CMD("rrectf")) {
            int x, y, w, h, r;
            if (next_int(&lp, lend, &x) && next_int(&lp, lend, &y) &&
                next_int(&lp, lend, &w) && next_int(&lp, lend, &h) &&
                next_int(&lp, lend, &r))
                fill_round_rect(&c, x, y, w, h, r, pen);
        }

        else if (CMD("bezier")) {
            int x0, y0, x1, y1, x2, y2, x3, y3;
            if (next_int(&lp, lend, &x0) && next_int(&lp, lend, &y0) &&
                next_int(&lp, lend, &x1) && next_int(&lp, lend, &y1) &&
                next_int(&lp, lend, &x2) && next_int(&lp, lend, &y2) &&
                next_int(&lp, lend, &x3) && next_int(&lp, lend, &y3))
                draw_bezier(&c, x0, y0, x1, y1, x2, y2, x3, y3, thickness, pen);
        }

        else if (CMD("tri")) {
            int x0, y0, x1, y1, x2, y2;
            if (next_int(&lp, lend, &x0) && next_int(&lp, lend, &y0) &&
                next_int(&lp, lend, &x1) && next_int(&lp, lend, &y1) &&
                next_int(&lp, lend, &x2) && next_int(&lp, lend, &y2)) {
                draw_line(&c, x0, y0, x1, y1, thickness, pen);
                draw_line(&c, x1, y1, x2, y2, thickness, pen);
                draw_line(&c, x2, y2, x0, y0, thickness, pen);
            }
        }

        else if (CMD("trif")) {
            int x0, y0, x1, y1, x2, y2;
            if (next_int(&lp, lend, &x0) && next_int(&lp, lend, &y0) &&
                next_int(&lp, lend, &x1) && next_int(&lp, lend, &y1) &&
                next_int(&lp, lend, &x2) && next_int(&lp, lend, &y2))
                fill_triangle(&c, x0, y0, x1, y1, x2, y2, pen);
        }

        else if (CMD("poly") || CMD("polyf")) {
            int pts[GFX_MAX_POLY_POINTS * 2];
            int n = 0;
            int v;
            while (n < GFX_MAX_POLY_POINTS * 2 && next_int(&lp, lend, &v))
                pts[n++] = v;
            n /= 2;   /* point count */
            if (n < 2)
                continue;

            if (CMD("polyf"))
                fill_polygon(&c, pts, n, pen);
            else {
                for (int i = 0; i < n; i++) {
                    int j = (i + 1) % n;
                    draw_line(&c, pts[i * 2], pts[i * 2 + 1],
                              pts[j * 2], pts[j * 2 + 1], thickness, pen);
                }
            }
        }

        else if (CMD("text")) {
            /* text takes the rest of the line as its string, so commas in
             * the string are literal (not command separators). Extend past
             * any comma the splitter stopped at and skip to the next line. */
            lend = line_end;
            if (lend > lp && lend[-1] == '\r')
                lend--;
            p = next_line;
            int x, y;
            if (!next_int(&lp, lend, &x) || !next_int(&lp, lend, &y))
                continue;
            skip_spaces(&lp, lend);
            if (lp < lend)
                draw_text(term, &c, pen, x, y, lp, lend - lp);
        }

        #undef CMD
    }

    if (c.data == NULL)
        return;

    /* Stage the canvas in the sixel image slot and emit through the
     * shared sixel pipeline (handles placement, scrolling, damage). */
    term->sixel.image.data = c.data;
    term->sixel.image.p = NULL;
    term->sixel.image.width = c.w;
    term->sixel.image.height = c.h;
    term->sixel.image.alloc_height = c.h;
    term->sixel.image.bottom_pixel = 0;
    term->sixel.pos = (struct coord){.col = 0, .row = c.h};
    term->sixel.transparent_bg = transparent_bg;
    term->sixel.pixman_fmt = PIXMAN_a8r8g8b8;

    sixel_emit_image(term);   /* takes ownership of c.data */
}
