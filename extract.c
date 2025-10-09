#include "extract.h"
#include "terminal.h"
#include <string.h>

#define LOG_MODULE "extract"
#define LOG_ENABLE_DBG 0
#include "log.h"
#include "char32.h"

struct extraction_context {
    char32_t *buf;
    size_t size;
    size_t idx;
    size_t tab_spaces_left;
    size_t empty_count;
    size_t newline_count;
    bool strip_trailing_empty;
    bool failed;
    const struct row *last_row;
    const struct cell *last_cell;
    enum selection_kind selection_kind;

    bool rich;
    bool bold;                            // 0
    bool dim;                             // 1
    bool italic;                          // 2
    bool underline;                       // 3
    bool blink;                           // 4
    bool reverse;                         // 5
    bool conceal;                         // 6
    bool strikethrough;                   // 7
    uint32_t fg;                          // 8
    uint32_t bg;                          // 9
    uint32_t un;                          // 3
    enum color_source fg_src;             // 8
    enum color_source bg_src;             // 9
    enum color_source un_src;             // 3
    enum underline_style underline_style; // 3
    uint64_t url_id;                      // 10
};

uint16_t
compare_attrs(struct extraction_context *ctx, struct attributes attrs, const struct row *row, int col) {
    uint16_t diff = 0;
    uint8_t idx;

    const struct row_data *extra = row->extra;

    idx = 0;
    if (ctx->bold != attrs.bold)
        diff |= 1 << idx;

    idx = 1;
    if (ctx->dim != attrs.dim)
        diff |= 1 << idx;

    idx = 2;
    if (ctx->italic != attrs.italic)
        diff |= 1 << idx;

    idx = 3;
    if (ctx->underline != attrs.underline)
        diff |= 1 << idx;
    if (extra != NULL){
        for (size_t i = 0; i < extra->underline_ranges.count; i++){
            const struct row_range *range = &extra->underline_ranges.v[i];
            if (range->start <= col && col <= range->end){
                if (ctx->underline_style != range->underline.style){
                    diff |= 1 << idx;
                    break;
                }
                if (ctx->un_src != range->underline.color_src){
                    diff |= 1 << idx;
                    break;
                }
                if ((range->underline.color_src != COLOR_DEFAULT) && ctx->un != range->underline.color){
                    diff |= 1 << idx;
                    break;
                }
                break;
            }
        }
    }

    idx = 4;
    if (ctx->blink != attrs.blink)
        diff |= 1 << idx;

    idx = 5;
    if (ctx->reverse != attrs.reverse)
        diff |= 1 << idx;

    idx = 6;
    if (ctx->conceal != attrs.conceal)
        diff |= 1 << idx;

    idx = 7;
    if (ctx->strikethrough != attrs.strikethrough)
        diff |= 1 << idx;

    idx = 8;
    if (ctx->fg_src != attrs.fg_src)
        diff |= 1 << idx;
    if ((attrs.fg_src != COLOR_DEFAULT) && ctx->fg != attrs.fg)
        diff |= 1 << idx;

    idx = 9;
    if (ctx->bg_src != attrs.bg_src)
        diff |= 1 << idx;
    if ((attrs.bg_src != COLOR_DEFAULT) && ctx->bg != attrs.bg)
        diff |= 1 << idx;

    idx = 10;

    if (extra != NULL){
        bool found_one = false;
        for (size_t i = 0; i < extra->uri_ranges.count; i++){
            const struct row_range *range = &extra->uri_ranges.v[i];
            if (range->start <= col && col <= range->end){
                found_one = true;
                if (ctx->url_id != range->uri.id)
                    diff |= 1 << idx;
                break;
            }
        }
        if (!found_one && ctx->url_id)
            diff |= 1 << idx;
    } else if (ctx->url_id) {
        diff |= 1 << idx;
    }

    return diff;
}


static bool
ensure_size(struct extraction_context *ctx, size_t additional_chars) {
    while (ctx->size < ctx->idx + additional_chars) {
        size_t new_size = ctx->size == 0 ? 512 : ctx->size * 2;
        char32_t *new_buf = realloc(ctx->buf, new_size * sizeof(new_buf[0]));

        if (new_buf == NULL)
            return false;

        ctx->buf = new_buf;
        ctx->size = new_size;
    }

    xassert(ctx->size >= ctx->idx + additional_chars);
    return true;
}


bool
clear_rich_ctx(struct extraction_context *ctx) {
    if (ctx->url_id){
        if (!ensure_size(ctx, 7))
            return false;
        ctx->buf[ctx->idx++] = U'\x1b';
        ctx->buf[ctx->idx++] = U']';
        ctx->buf[ctx->idx++] = U'8';
        ctx->buf[ctx->idx++] = U';';
        ctx->buf[ctx->idx++] = U';';
        ctx->buf[ctx->idx++] = U'\x1b';
        ctx->buf[ctx->idx++] = U'\\';
    }

    if (ctx->bold +
        ctx->dim +
        ctx->italic +
        ctx->underline +
        ctx->blink +
        ctx->reverse +
        ctx->conceal +
        ctx->strikethrough +
        ctx->fg_src +
        ctx->bg_src +
        ctx->un_src +
        ctx->underline_style
        )
    {
        if (!ensure_size(ctx, 4))
            return false;
        ctx->buf[ctx->idx++] = U'\x1b';
        ctx->buf[ctx->idx++] = U'[';
        ctx->buf[ctx->idx++] = U'0';
        ctx->buf[ctx->idx++] = U'm';
    }

    ctx->bold = false;
    ctx->dim = false;
    ctx->italic = false;
    ctx->underline = false;
    ctx->blink = false;
    ctx->reverse = false;
    ctx->conceal = false;
    ctx->strikethrough = false;
    ctx->fg = 0;
    ctx->bg = 0;
    ctx->un = 0;
    ctx->fg_src = 0;
    ctx->bg_src = 0;
    ctx->un_src = 0;
    ctx->underline_style = 0;
    ctx->url_id = 0;

    return true;
}

bool
init_x1b(bool *x1b, struct extraction_context *ctx) {
    if (!(*x1b)) {
        if (!ensure_size(ctx, 2))
            return false;

        ctx->buf[ctx->idx++] = U'\x1b';
        ctx->buf[ctx->idx++] = U'[';
    } else {
        if (!ensure_size(ctx, 1))
            return false;

        ctx->buf[ctx->idx++] = U';';
    }
    *x1b = true;
    return true;
}

bool
change_color_rich(enum color_source colour_src, uint32_t colour, struct extraction_context *ctx, uint8_t domain)
{
    switch (colour_src) {
        case COLOR_DEFAULT:
            if (!ensure_size(ctx, 2))
                return false;
            ctx->buf[ctx->idx++] = U'0' + domain;
            ctx->buf[ctx->idx++] = U'9';
            break;
        case COLOR_BASE16:
            xassert(domain != 0);
            if (!ensure_size(ctx, 2 + (((domain + (6 * (colour > 7)))) > 9)))
                return false;
            if (((domain + (6 * (colour > 7)))) > 9)
                ctx->buf[ctx->idx++] = U'1';
            ctx->buf[ctx->idx++] = U'0' + domain + (6 * (colour > 7)) - 10 * (((domain + (6 * (colour > 7)))) > 9);
            ctx->buf[ctx->idx++] = U'0' + colour - (8 * (colour > 7));
            break;
        case COLOR_BASE256:
            if (!ensure_size(ctx, 6 + (colour > 9) + (colour > 99)))
                return false;
            ctx->buf[ctx->idx++] = U'0' + domain;
            ctx->buf[ctx->idx++] = U'8';
            ctx->buf[ctx->idx++] = U';';
            ctx->buf[ctx->idx++] = U'5';
            ctx->buf[ctx->idx++] = U';';
            if (colour > 99)
                ctx->buf[ctx->idx++] = U'0' + (colour / 100);
            if (colour > 9)
                ctx->buf[ctx->idx++] = U'0' + ((colour % 100) / 10);
            ctx->buf[ctx->idx++] = U'0' + (colour % 10);
            break;
        case COLOR_RGB:;
            uint8_t r = (colour >> 16) & 0xff;
            uint8_t g = (colour >> 8) & 0xff;
            uint8_t b = colour & 0xff;
            if (!ensure_size(ctx, 8 + (r > 9) + (r > 99) + (g > 9) + (g > 99) + (b > 9) + (b > 99)))
                return false;
            ctx->buf[ctx->idx++] = U'0' + domain;
            ctx->buf[ctx->idx++] = U'8';
            ctx->buf[ctx->idx++] = U';';
            ctx->buf[ctx->idx++] = U'2';
            ctx->buf[ctx->idx++] = U';';
            if (r > 99)
                ctx->buf[ctx->idx++] = U'0' + (r / 100);
            if (r > 9)
                ctx->buf[ctx->idx++] = U'0' + ((r % 100) / 10);
            ctx->buf[ctx->idx++] = U'0' + (r % 10);
            ctx->buf[ctx->idx++] = U';';
            if (g > 99)
                ctx->buf[ctx->idx++] = U'0' + (g / 100);
            if (g > 9)
                ctx->buf[ctx->idx++] = U'0' + ((g % 100) / 10);
            ctx->buf[ctx->idx++] = U'0' + (g % 10);
            ctx->buf[ctx->idx++] = U';';
            if (b > 99)
                ctx->buf[ctx->idx++] = U'0' + (b / 100);
            if (b > 9)
                ctx->buf[ctx->idx++] = U'0' + ((b % 100) / 10);
            ctx->buf[ctx->idx++] = U'0' + (b % 10);
            break;
    }
    return true;
}

bool
style_flip_rich(bool attr, uint8_t attr_idx, struct extraction_context *ctx) {
    if (attr) {
        if (!ensure_size(ctx, 1))
            return false;
        ctx->buf[ctx->idx++] = U'0' + attr_idx;
    } else {
        if (!ensure_size(ctx, 2))
            return false;
        ctx->buf[ctx->idx++] = U'2';
        ctx->buf[ctx->idx++] = U'0' + attr_idx;
    }
    return true;
}

bool
add_rich_diff(struct extraction_context *ctx, struct attributes attrs, const struct row *row, int col, uint16_t diff) {
    char idx;
    bool x1b = false;

    /* dim and bod */
    idx = 0;
    if (diff & 1 << idx || diff & 1 << (idx + 1)) {
        x1b = true;
        if (!ensure_size(ctx, 2))
            goto err;

        ctx->buf[ctx->idx++] = U'\x1b';
        ctx->buf[ctx->idx++] = U'[';

        if ((!attrs.bold && !attrs.dim) || (attrs.bold ^ attrs.dim)) {
            if (!ensure_size(ctx, 2 + (2 * (attrs.bold ^ attrs.dim))))
                goto err;

            ctx->buf[ctx->idx++] = U'2';
            ctx->buf[ctx->idx++] = U'2';
            if (attrs.bold ^ attrs.dim) {
                ctx->buf[ctx->idx++] = U';';
                if (attrs.dim) {
                    ctx->buf[ctx->idx++] = U'2';
                }
                else if (attrs.bold) {
                    ctx->buf[ctx->idx++] = U'1';
                }
            }
        }
        ctx->dim = attrs.dim;
        ctx->bold = attrs.bold;
    }

    /* italic */
    idx = 2;
    if (diff & 1 << idx) {
        if (!init_x1b(&x1b, ctx))
            goto err;
        if (!style_flip_rich(attrs.italic, 3, ctx))
            goto err;
        ctx->italic = attrs.italic;
    }

    /* underline */
    idx = 3;
    if (diff & 1 << idx) {
        if (attrs.underline) {
            const struct row_data *extra = row->extra;
            if (extra != NULL) {
                for (size_t i = 0; i < extra->underline_ranges.count; i++) {
                    const struct row_range *range = &extra->underline_ranges.v[i];
                    if (range->start <= col && col <= range->end) {
                        if (ctx->underline_style != range->underline.style) {
                            if (!init_x1b(&x1b, ctx))
                                goto err;
                            if (!ensure_size(ctx, 3))
                                goto err;
                            ctx->buf[ctx->idx++] = U'4';
                            ctx->buf[ctx->idx++] = U':';
                            ctx->buf[ctx->idx++] = U'0' + range->underline.style;
                        }

                        if ((ctx->un_src != range->underline.color_src) || ((range->underline.color_src != COLOR_DEFAULT) && ctx->un != range->underline.color)) {
                            if (!init_x1b(&x1b, ctx))
                                goto err;
                            if (!change_color_rich(range->underline.color_src, range->underline.color, ctx, 5))
                                goto err;
                        }
                        ctx->underline_style = range->underline.style;
                        ctx->un = range->underline.color;
                        ctx->un_src = range->underline.color_src;
                        break;
                    }
                }
            } else {
                if (!init_x1b(&x1b, ctx))
                    goto err;
                if (!ensure_size(ctx, 3))
                    goto err;
                ctx->buf[ctx->idx++] = U'4';
                ctx->buf[ctx->idx++] = U':';
                ctx->buf[ctx->idx++] = U'1';

                ctx->underline_style = 0;
                ctx->un = 0;
                ctx->un_src = 0;
            }
        } else {
            if (!init_x1b(&x1b, ctx))
                goto err;
            if (!ensure_size(ctx, 3))
                goto err;
            ctx->buf[ctx->idx++] = U'4';
            ctx->buf[ctx->idx++] = U':';
            ctx->buf[ctx->idx++] = U'0';
        }
        ctx->underline = attrs.underline;
    }

    /* blink */
    idx = 4;
    if (diff & 1 << idx) {
        if (!init_x1b(&x1b, ctx))
            goto err;
        if (!style_flip_rich(attrs.blink, 5, ctx))
            goto err;
        ctx->blink = attrs.blink;
    }

    /* reverse */
    idx = 5;
    if (diff & 1 << idx) {
        if (!init_x1b(&x1b, ctx))
            goto err;
        if (!style_flip_rich(attrs.reverse, 7, ctx))
            goto err;
        ctx->reverse = attrs.reverse;
    }

    /* conceal */
    idx = 6;
    if (diff & 1 << idx) {
        if (!init_x1b(&x1b, ctx))
            goto err;
        if (!style_flip_rich(attrs.conceal, 8, ctx))
            goto err;
        ctx->conceal = attrs.conceal;
    }

    /* strikethrough */
    idx = 7;
    if (diff & 1 << idx) {
        if (!init_x1b(&x1b, ctx))
            goto err;
        if (!style_flip_rich(attrs.strikethrough, 9, ctx))
            goto err;
        ctx->strikethrough = attrs.strikethrough;
    }

    /* foreground colour */
    idx = 8;
    if (diff & 1 << idx) {
        if (!init_x1b(&x1b, ctx))
            goto err;

        if (!change_color_rich(attrs.fg_src, attrs.fg, ctx, 3))
            goto err;

        ctx->fg = attrs.fg;
        ctx->fg_src = attrs.fg_src;
    }

    /* background colour */
    idx = 9;
    if (diff & 1 << idx) {
        if (!init_x1b(&x1b, ctx))
            goto err;

        if (!change_color_rich(attrs.bg_src, attrs.bg, ctx, 4))
            goto err;

        ctx->bg = attrs.bg;
        ctx->bg_src = attrs.bg_src;
    }

    if (x1b) {
        if (!ensure_size(ctx, 1))
            goto err;
        ctx->buf[ctx->idx++] = U'm';
    }

    idx = 10;
    if (diff & 1 << idx) {
        const struct row_data *extra = row->extra;
        if (extra != NULL) {
            char32_t *text;
            bool found_one = false;
            for (size_t i = 0; i < extra->uri_ranges.count; i++) {
                const struct row_range *range = &extra->uri_ranges.v[i];
                if (range->start <= col && col <= range->end) {
                    found_one = true;
                    ctx->url_id = range->uri.id;
                    text = ambstoc32(range->uri.uri);

                    if (!ensure_size(ctx, 7 + c32len(text)))
                        goto err;
                    ctx->buf[ctx->idx++] = U'\x1b';
                    ctx->buf[ctx->idx++] = U']';
                    ctx->buf[ctx->idx++] = U'8';
                    ctx->buf[ctx->idx++] = U';';
                    ctx->buf[ctx->idx++] = U';';

                    for (size_t j = 0; j < c32len(text); j++)
                        ctx->buf[ctx->idx++] = text[j];

                    ctx->buf[ctx->idx++] = U'\x1b';
                    ctx->buf[ctx->idx++] = U'\\';

                    free(text);
                    break;
                }
            }
            if (!found_one) {
                if (!ensure_size(ctx, 7))
                    goto err;
                ctx->buf[ctx->idx++] = U'\x1b';
                ctx->buf[ctx->idx++] = U']';
                ctx->buf[ctx->idx++] = U'8';
                ctx->buf[ctx->idx++] = U';';
                ctx->buf[ctx->idx++] = U';';
                ctx->buf[ctx->idx++] = U'\x1b';
                ctx->buf[ctx->idx++] = U'\\';

                ctx->url_id = 0;
            }
        } else {
            if (!ensure_size(ctx, 7))
                goto err;
            ctx->buf[ctx->idx++] = U'\x1b';
            ctx->buf[ctx->idx++] = U']';
            ctx->buf[ctx->idx++] = U'8';
            ctx->buf[ctx->idx++] = U';';
            ctx->buf[ctx->idx++] = U';';
            ctx->buf[ctx->idx++] = U'\x1b';
            ctx->buf[ctx->idx++] = U'\\';

            ctx->url_id = 0;
        }
    }
    return true;

err:
    free(ctx->buf);
    free(ctx);
    return false;
}

struct extraction_context *
extract_begin(enum selection_kind kind, bool strip_trailing_empty, bool rich) {
    struct extraction_context *ctx = malloc(sizeof(*ctx));
    if (unlikely(ctx == NULL)){
        LOG_ERRNO("malloc() failed");
        return NULL;
    }

    *ctx = (struct extraction_context){
        .selection_kind = kind,
        .strip_trailing_empty = strip_trailing_empty,
        .rich = rich,
    };
    return ctx;
}

bool
extract_finish_wide(struct extraction_context *ctx, char32_t **text, size_t *len)
{
    if (text == NULL)
        return false;

    *text = NULL;
    if (len != NULL)
        *len = 0;

    if (ctx->failed)
        goto err;

    if (!ctx->strip_trailing_empty) {
        /* Insert pending newlines, and replace empty cells with spaces */
        if (!ensure_size(ctx, ctx->newline_count + ctx->empty_count))
            goto err;

        for (size_t i = 0; i < ctx->newline_count; i++)
            ctx->buf[ctx->idx++] = U'\n';

        for (size_t i = 0; i < ctx->empty_count; i++)
            ctx->buf[ctx->idx++] = U' ';
    }

    if (ctx->idx == 0) {
        /* Selection of empty cells only */
        if (!ensure_size(ctx, 1))
            goto err;
        ctx->buf[ctx->idx++] = U'\0';
    } else {
        xassert(ctx->idx > 0);
        xassert(ctx->idx <= ctx->size);

        switch (ctx->selection_kind) {
        default:
            if (ctx->buf[ctx->idx - 1] == U'\n')
                ctx->buf[ctx->idx - 1] = U'\0';
            break;

        case SELECTION_LINE_WISE:
            if (ctx->buf[ctx->idx - 1] != U'\n') {
                if (!ensure_size(ctx, 1))
                    goto err;
                ctx->buf[ctx->idx++] = U'\n';
            }
            break;

        }

        if (ctx->buf[ctx->idx - 1] != U'\0') {
            if (!ensure_size(ctx, 1))
                goto err;
            ctx->buf[ctx->idx++] = U'\0';
        }
    }

    if (ctx->rich){
        ctx->idx = ctx->idx - 1;
        if (!clear_rich_ctx(ctx))
            goto err;
        if (!ensure_size(ctx, 1))
            goto err;
        ctx->buf[ctx->idx++] = U'\0';
    }

    *text = ctx->buf;
    if (len != NULL)
        *len = ctx->idx - 1;
    free(ctx);
    return true;

err:
    free(ctx->buf);
    free(ctx);
    return false;
}

bool
extract_finish(struct extraction_context *ctx, char **text, size_t *len)
{
    if (text == NULL)
        return false;
    if (len != NULL)
        *len = 0;

    char32_t *wtext;
    if (!extract_finish_wide(ctx, &wtext, NULL))
        return false;

    bool ret = false;

    *text = ac32tombs(wtext);
    if (*text == NULL) {
        LOG_ERR("failed to convert selection to UTF-8");
        goto out;
    }

    if (len != NULL)
        *len = strlen(*text);
    ret = true;

out:
    free(wtext);
    return ret;
}

bool
extract_one(const struct terminal *term, const struct row *row,
            const struct cell *cell, int col, void *context)
{
    struct extraction_context *ctx = context;
    struct attributes attrs = cell->attrs;

    if (cell->wc >= CELL_SPACER)
        return true;

    if (ctx->last_row != NULL && row != ctx->last_row) {
        /* New row - determine if we should insert a newline or not */
        if (ctx->rich){
            if (!clear_rich_ctx(ctx))
                goto err;
        }

        if (ctx->selection_kind != SELECTION_BLOCK) {
            if (ctx->last_row->linebreak ||
                ctx->empty_count > 0 ||
                cell->wc == 0)
            {
                /* Row has a hard linebreak, or either last cell or
                 * current cell is empty */

                /* Don't emit newline just yet - only if there are
                 * non-empty cells following it */
                ctx->newline_count++;

                if (!ctx->strip_trailing_empty) {
                    if (!ensure_size(ctx, ctx->empty_count))
                        goto err;
                    for (size_t i = 0; i < ctx->empty_count; i++)
                        ctx->buf[ctx->idx++] = U' ';
                }
                ctx->empty_count = 0;
            }
        } else {
            /* Always insert a linebreak */
            if (!ensure_size(ctx, 1))
                goto err;

            ctx->buf[ctx->idx++] = U'\n';

            if (!ctx->strip_trailing_empty) {
                if (!ensure_size(ctx, ctx->empty_count))
                    goto err;
                for (size_t i = 0; i < ctx->empty_count; i++)
                    ctx->buf[ctx->idx++] = U' ';
            }
            ctx->empty_count = 0;
        }

        ctx->tab_spaces_left = 0;
    }

    if (cell->wc == U' ' && ctx->tab_spaces_left > 0) {
        ctx->tab_spaces_left--;
        return true;
    }

    ctx->tab_spaces_left = 0;

    if (cell->wc == 0) {
        ctx->empty_count++;
        ctx->last_row = row;
        ctx->last_cell = cell;
        return true;
    }

    /* Insert pending newlines, and replace empty cells with spaces */
    if (!ensure_size(ctx, ctx->newline_count + ctx->empty_count))
        goto err;

    for (size_t i = 0; i < ctx->newline_count; i++)
        ctx->buf[ctx->idx++] = U'\n';

    for (size_t i = 0; i < ctx->empty_count; i++)
        ctx->buf[ctx->idx++] = U' ';

    ctx->newline_count = 0;
    ctx->empty_count = 0;

    if (ctx->rich)
    {
        uint16_t rich_diff = compare_attrs(ctx, attrs, row, col);
        if (rich_diff)
            add_rich_diff(ctx, attrs, row, col, rich_diff);
    }

    if (cell->wc >= CELL_COMB_CHARS_LO && cell->wc <= CELL_COMB_CHARS_HI)
    {
        const struct composed *composed = composed_lookup(
            term->composed, cell->wc - CELL_COMB_CHARS_LO);

        if (!ensure_size(ctx, composed->count))
            goto err;

        for (size_t i = 0; i < composed->count; i++)
            ctx->buf[ctx->idx++] = composed->chars[i];
    }

    else {
        if (!ensure_size(ctx, 1))
            goto err;
        ctx->buf[ctx->idx++] = cell->wc;

        if (cell->wc == U'\t') {
            int next_tab_stop = term->cols - 1;
            tll_foreach(term->tab_stops, it) {
                if (it->item > col) {
                    next_tab_stop = it->item;
                    break;
                }
            }

            if (next_tab_stop > col)
                ctx->tab_spaces_left = next_tab_stop - col - 1;
        }
    }

    ctx->last_row = row;
    ctx->last_cell = cell;
    return true;

err:
    ctx->failed = true;
    return false;
}
