#pragma once

/*
 * Self-contained software rasterizers for the vector graphics protocol
 * (see graphics.c). Kept dependency-free (no terminal/pixman/fcft) so the
 * pixel math can be unit tested in isolation (see tests/).
 *
 * The canvas is premultiplied ARGB8888. All drawing is clipped to the
 * canvas' clip rectangle. Source colours are premultiplied.
 */

#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

struct canvas {
    uint32_t *data;       /* premultiplied ARGB8888, w*h pixels */
    int w, h;             /* pixels */
    int clip_x, clip_y, clip_w, clip_h;
};

static inline int gfx_imin(int a, int b) { return a < b ? a : b; }
static inline int gfx_imax(int a, int b) { return a > b ? a : b; }

/* Premultiply straight RGBA into premultiplied ARGB8888 */
static inline uint32_t
premul(uint8_t a, uint8_t r, uint8_t g, uint8_t b)
{
    r = (r * a + 127) / 255;
    g = (g * a + 127) / 255;
    b = (b * a + 127) / 255;
    return (uint32_t)a << 24 | (uint32_t)r << 16 | (uint32_t)g << 8 | b;
}

static inline bool
in_clip(const struct canvas *c, int x, int y)
{
    return x >= c->clip_x && x < c->clip_x + c->clip_w &&
           y >= c->clip_y && y < c->clip_y + c->clip_h;
}

/* Source-over blend of premultiplied src onto premultiplied dst */
static inline void
blend(struct canvas *c, int x, int y, uint32_t src)
{
    if (!in_clip(c, x, y))
        return;

    uint8_t sa = src >> 24;
    if (sa == 0)
        return;

    uint32_t *dp = &c->data[y * c->w + x];

    if (sa == 0xff) {
        *dp = src;
        return;
    }

    uint32_t dst = *dp;
    uint32_t inv = 255 - sa;

    uint8_t da = dst >> 24;
    uint8_t dr = dst >> 16;
    uint8_t dg = dst >> 8;
    uint8_t db = dst;

    uint8_t oa = sa + (da * inv + 127) / 255;
    uint8_t orr = ((src >> 16) & 0xff) + (dr * inv + 127) / 255;
    uint8_t og = ((src >> 8) & 0xff) + (dg * inv + 127) / 255;
    uint8_t ob = (src & 0xff) + (db * inv + 127) / 255;

    *dp = (uint32_t)oa << 24 | (uint32_t)orr << 16 | (uint32_t)og << 8 | ob;
}

/* Source-over blend scaling premultiplied src by a coverage in [0,1].
 * Scaling all four premultiplied channels (alpha included) yields the correct
 * partially-covered premultiplied colour — the basis for anti-aliased edges. */
static inline void
blend_cov(struct canvas *c, int x, int y, uint32_t src, double cov)
{
    if (cov <= 0.0)
        return;
    if (cov >= 1.0) {
        blend(c, x, y, src);
        return;
    }

    uint32_t a = (uint32_t)((src >> 24 & 0xff) * cov + 0.5);
    uint32_t r = (uint32_t)((src >> 16 & 0xff) * cov + 0.5);
    uint32_t g = (uint32_t)((src >>  8 & 0xff) * cov + 0.5);
    uint32_t b = (uint32_t)((src       & 0xff) * cov + 0.5);
    blend(c, x, y, a << 24 | r << 16 | g << 8 | b);
}

static inline void
hspan(struct canvas *c, int x, int y, int len, uint32_t src)
{
    for (int i = 0; i < len; i++)
        blend(c, x + i, y, src);
}

/* Plot a point honoring thickness (filled square centered on x,y) */
static inline void
plot(struct canvas *c, int x, int y, int thickness, uint32_t src)
{
    if (thickness <= 1) {
        blend(c, x, y, src);
        return;
    }

    int half = thickness / 2;
    for (int dy = -half; dy < thickness - half; dy++)
        hspan(c, x - half, y + dy, thickness, src);
}

/* Anti-aliased stroke of the segment p0->p1, in floating-point coordinates.
 * The stroke is the set of points within `thickness/2` of the segment (a
 * capsule with round caps); each pixel's coverage is its signed distance to
 * that edge, clamped to a one-pixel-wide fringe. Pixel centres sit on integer
 * coordinates, matching the rest of this header. */
static inline void
draw_line_f(struct canvas *c, double x0, double y0, double x1, double y1,
            int thickness, uint32_t src)
{
    double radius = (thickness < 1 ? 1 : thickness) / 2.0;
    double dx = x1 - x0, dy = y1 - y0;
    double len2 = dx * dx + dy * dy;

    int pad = (int)ceil(radius) + 1;
    int minx = gfx_imax(c->clip_x, (int)floor(gfx_imin(x0, x1)) - pad);
    int maxx = gfx_imin(c->clip_x + c->clip_w - 1,
                        (int)ceil(gfx_imax(x0, x1)) + pad);
    int miny = gfx_imax(c->clip_y, (int)floor(gfx_imin(y0, y1)) - pad);
    int maxy = gfx_imin(c->clip_y + c->clip_h - 1,
                        (int)ceil(gfx_imax(y0, y1)) + pad);

    for (int py = miny; py <= maxy; py++) {
        for (int px = minx; px <= maxx; px++) {
            /* nearest point on the segment to the pixel centre */
            double t = 0.0;
            if (len2 > 0.0) {
                t = ((px - x0) * dx + (py - y0) * dy) / len2;
                t = t < 0.0 ? 0.0 : (t > 1.0 ? 1.0 : t);
            }
            double qx = x0 + t * dx, qy = y0 + t * dy;
            double ex = px - qx, ey = py - qy;
            double dist = sqrt(ex * ex + ey * ey);

            double cov = radius + 0.5 - dist;
            if (cov <= 0.0)
                continue;
            blend_cov(c, px, py, src, cov > 1.0 ? 1.0 : cov);
        }
    }
}

static inline void
draw_line(struct canvas *c, int x0, int y0, int x1, int y1, int thickness,
          uint32_t src)
{
    draw_line_f(c, x0, y0, x1, y1, thickness, src);
}

static inline void
fill_rect(struct canvas *c, int x, int y, int w, int h, uint32_t src)
{
    for (int row = 0; row < h; row++)
        hspan(c, x, y + row, w, src);
}

static inline void
outline_rect(struct canvas *c, int x, int y, int w, int h, int thickness,
             uint32_t src)
{
    if (w <= 0 || h <= 0)
        return;
    draw_line(c, x, y, x + w - 1, y, thickness, src);
    draw_line(c, x, y + h - 1, x + w - 1, y + h - 1, thickness, src);
    draw_line(c, x, y, x, y + h - 1, thickness, src);
    draw_line(c, x + w - 1, y, x + w - 1, y + h - 1, thickness, src);
}

static inline void
fill_circle(struct canvas *c, int cx, int cy, int r, uint32_t src)
{
    if (r < 0)
        return;

    int ox = r, oy = 0, err = -r;
    while (ox >= oy) {
        int last_oy = oy;
        err += oy; oy++; err += oy;

        hspan(c, cx - ox, cy + last_oy, ox * 2 + 1, src);
        if (last_oy != 0)
            hspan(c, cx - ox, cy - last_oy, ox * 2 + 1, src);

        if (err >= 0 && ox != last_oy) {
            hspan(c, cx - last_oy, cy + ox, last_oy * 2 + 1, src);
            if (ox != 0)
                hspan(c, cx - last_oy, cy - ox, last_oy * 2 + 1, src);
            err -= ox; ox--; err -= ox;
        }
    }
}

static inline void
draw_arc(struct canvas *c, int cx, int cy, int r, double a0, double a1,
         int thickness, uint32_t src);

static inline void
outline_circle(struct canvas *c, int cx, int cy, int r, int thickness,
               uint32_t src)
{
    if (r < 0)
        return;

    draw_arc(c, cx, cy, r, 0, 360, thickness, src);
}

/* Arc outline. Angles in degrees: 0=east, 90=south, 180=west, 270=north
 * (clockwise, since the y axis points down). */
static inline void
draw_arc(struct canvas *c, int cx, int cy, int r, double a0, double a1,
         int thickness, uint32_t src)
{
    if (r <= 0)
        return;

    double r0 = a0 * M_PI / 180.0;
    double r1 = a1 * M_PI / 180.0;
    if (r1 < r0) { double t = r0; r0 = r1; r1 = t; }

    double step = 1.0 / r;
    if (step > 0.1)
        step = 0.1;

    /* Walk the arc, joining consecutive samples with anti-aliased segments
     * (in floating point, so vertices aren't quantised to the pixel grid). */
    double px = cx + r * cos(r0), py = cy + r * sin(r0);
    for (double a = r0 + step; a < r1; a += step) {
        double nx = cx + r * cos(a), ny = cy + r * sin(a);
        draw_line_f(c, px, py, nx, ny, thickness, src);
        px = nx; py = ny;
    }

    /* exact endpoint */
    draw_line_f(c, px, py, cx + r * cos(r1), cy + r * sin(r1), thickness, src);
}

static inline void
fill_round_rect(struct canvas *c, int x, int y, int w, int h, int r,
                uint32_t src)
{
    if (w <= 0 || h <= 0)
        return;
    if (r < 0) r = 0;
    if (r > w / 2) r = w / 2;
    if (r > h / 2) r = h / 2;
    if (r == 0) { fill_rect(c, x, y, w, h, src); return; }

    fill_rect(c, x + r, y, w - 2 * r, h, src);          /* center band */
    fill_rect(c, x, y + r, r, h - 2 * r, src);          /* left band */
    fill_rect(c, x + w - r, y + r, r, h - 2 * r, src);  /* right band */

    fill_circle(c, x + r, y + r, r, src);
    fill_circle(c, x + w - r - 1, y + r, r, src);
    fill_circle(c, x + r, y + h - r - 1, r, src);
    fill_circle(c, x + w - r - 1, y + h - r - 1, r, src);
}

static inline void
outline_round_rect(struct canvas *c, int x, int y, int w, int h, int r,
                   int thickness, uint32_t src)
{
    if (w <= 0 || h <= 0)
        return;
    if (r < 0) r = 0;
    if (r > w / 2) r = w / 2;
    if (r > h / 2) r = h / 2;
    if (r == 0) { outline_rect(c, x, y, w, h, thickness, src); return; }

    draw_line(c, x + r, y, x + w - r - 1, y, thickness, src);
    draw_line(c, x + r, y + h - 1, x + w - r - 1, y + h - 1, thickness, src);
    draw_line(c, x, y + r, x, y + h - r - 1, thickness, src);
    draw_line(c, x + w - 1, y + r, x + w - 1, y + h - r - 1, thickness, src);

    draw_arc(c, x + r,         y + r,         r, 180, 270, thickness, src);
    draw_arc(c, x + w - r - 1, y + r,         r, 270, 360, thickness, src);
    draw_arc(c, x + w - r - 1, y + h - r - 1, r, 0,   90,  thickness, src);
    draw_arc(c, x + r,         y + h - r - 1, r, 90,  180, thickness, src);
}

/* Cubic Bezier curve through control points p0..p3, stroked as line segments */
static inline void
draw_bezier(struct canvas *c, int x0, int y0, int x1, int y1,
            int x2, int y2, int x3, int y3, int thickness, uint32_t src)
{
    double d = fabs((double)x1 - x0) + fabs((double)y1 - y0) +
               fabs((double)x2 - x1) + fabs((double)y2 - y1) +
               fabs((double)x3 - x2) + fabs((double)y3 - y2);
    int seg = (int)(d / 3);
    if (seg < 8) seg = 8;
    if (seg > 1024) seg = 1024;

    double px = x0, py = y0;
    for (int i = 1; i <= seg; i++) {
        double t = (double)i / seg, u = 1.0 - t;
        double b0 = u*u*u, b1 = 3*u*u*t, b2 = 3*u*t*t, b3 = t*t*t;
        double nx = b0*x0 + b1*x1 + b2*x2 + b3*x3;
        double ny = b0*y0 + b1*y1 + b2*y2 + b3*y3;
        draw_line_f(c, px, py, nx, ny, thickness, src);
        px = nx; py = ny;
    }
}

static inline int
orient2d(int ax, int ay, int bx, int by, int cx, int cy)
{
    return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
}

static inline void
fill_triangle(struct canvas *c, int x0, int y0, int x1, int y1, int x2, int y2,
              uint32_t src)
{
    /* Ensure counter-clockwise winding so weights are non-negative inside */
    if (orient2d(x0, y0, x1, y1, x2, y2) < 0) {
        int tx = x1, ty = y1;
        x1 = x2; y1 = y2;
        x2 = tx; y2 = ty;
    }

    int minx = gfx_imax(c->clip_x, gfx_imin(x0, gfx_imin(x1, x2)));
    int miny = gfx_imax(c->clip_y, gfx_imin(y0, gfx_imin(y1, y2)));
    int maxx = gfx_imin(c->clip_x + c->clip_w - 1, gfx_imax(x0, gfx_imax(x1, x2)));
    int maxy = gfx_imin(c->clip_y + c->clip_h - 1, gfx_imax(y0, gfx_imax(y1, y2)));

    for (int y = miny; y <= maxy; y++) {
        for (int x = minx; x <= maxx; x++) {
            int w0 = orient2d(x1, y1, x2, y2, x, y);
            int w1 = orient2d(x2, y2, x0, y0, x, y);
            int w2 = orient2d(x0, y0, x1, y1, x, y);
            if (w0 >= 0 && w1 >= 0 && w2 >= 0)
                blend(c, x, y, src);
        }
    }
}

#define GFX_MAX_POLY_POINTS 256

/* Even-odd scanline polygon fill. pts = [x0,y0,x1,y1,...], n = point count */
static inline void
fill_polygon(struct canvas *c, const int *pts, int n, uint32_t src)
{
    if (n < 3)
        return;

    int miny = pts[1], maxy = pts[1];
    for (int i = 1; i < n; i++) {
        miny = gfx_imin(miny, pts[i * 2 + 1]);
        maxy = gfx_imax(maxy, pts[i * 2 + 1]);
    }
    miny = gfx_imax(miny, c->clip_y);
    maxy = gfx_imin(maxy, c->clip_y + c->clip_h - 1);

    int xs[GFX_MAX_POLY_POINTS];

    for (int y = miny; y <= maxy; y++) {
        int count = 0;
        float ys = y + 0.5f;

        for (int i = 0; i < n; i++) {
            int j = (i + 1) % n;
            float ay = pts[i * 2 + 1], by = pts[j * 2 + 1];
            float ax = pts[i * 2], bx = pts[j * 2];

            if ((ay <= ys && by > ys) || (by <= ys && ay > ys)) {
                float t = (ys - ay) / (by - ay);
                if (count < GFX_MAX_POLY_POINTS)
                    xs[count++] = (int)(ax + t * (bx - ax));
            }
        }

        for (int a = 0; a < count - 1; a++)
            for (int b = a + 1; b < count; b++)
                if (xs[b] < xs[a]) {
                    int t = xs[a]; xs[a] = xs[b]; xs[b] = t;
                }

        for (int a = 0; a + 1 < count; a += 2)
            hspan(c, xs[a], y, xs[a + 1] - xs[a] + 1, src);
    }
}
