/* Unit tests for the vector graphics rasterizers (graphics_draw.h). */

#include <stdio.h>
#include <stdlib.h>

#include "../graphics_draw.h"

static struct canvas
mk(int w, int h)
{
    struct canvas c = {
        .data = calloc((size_t)w * h, sizeof(uint32_t)),
        .w = w, .h = h,
        .clip_x = 0, .clip_y = 0, .clip_w = w, .clip_h = h,
    };
    return c;
}

static int failures = 0;

static void
expect(struct canvas *c, int x, int y, uint32_t want, const char *what)
{
    uint32_t got = c->data[y * c->w + x];
    if (got != want) {
        fprintf(stderr, "FAIL %s at (%d,%d): got %08x want %08x\n",
                what, x, y, got, want);
        failures++;
    }
}

/* Anti-aliased strokes don't land exact opaque colours on every pixel; this
 * checks a pixel was covered and is dominated by the expected channel. */
enum chan { CH_R, CH_G, CH_B };

static void
expect_stroke(struct canvas *c, int x, int y, enum chan dom, const char *what)
{
    uint32_t got = c->data[y * c->w + x];
    uint8_t a = got >> 24, r = got >> 16, g = got >> 8, b = got;
    uint8_t v[3] = { r, g, b };
    bool ok = a >= 64 && v[dom] >= v[(dom + 1) % 3] && v[dom] >= v[(dom + 2) % 3];
    if (!ok) {
        fprintf(stderr, "FAIL %s at (%d,%d): got %08x (expected covered stroke)\n",
                what, x, y, got);
        failures++;
    }
}

int
main(void)
{
    struct canvas c = mk(360, 200);

    const uint32_t bg    = premul(255, 16, 16, 40);
    const uint32_t red   = premul(255, 255, 80, 80);
    const uint32_t cyan  = premul(255, 80, 208, 255);
    const uint32_t green = premul(255, 128, 255, 128);

    for (int i = 0; i < c.w * c.h; i++)
        c.data[i] = bg;

    /* premultiplication: opaque colours are unchanged */
    if (premul(255, 255, 80, 80) != 0xffff5050u) { failures++; }
    /* 50% alpha halves the channels */
    if (premul(128, 255, 0, 0) != 0x80800000u) { failures++; }

    fill_rect(&c, 12, 12, 150, 70, red);
    expect(&c, 80, 40, red, "rect interior");
    expect(&c, 5, 195, bg, "rect leaves rest untouched");

    fill_circle(&c, 250, 55, 38, cyan);
    expect(&c, 250, 55, cyan, "circle center");
    expect(&c, 215, 55, cyan, "circle interior near edge");
    expect(&c, 205, 55, bg, "outside circle radius");

    int tri[6] = {60, 110, 150, 199, 30, 199};
    fill_triangle(&c, tri[0], tri[1], tri[2], tri[3], tri[4], tri[5], green);
    expect(&c, 60, 130, green, "triangle interior");
    expect(&c, 0, 199, bg, "outside triangle");

    /* Filled polygon (rectangle) with 50% alpha must blend, not overwrite */
    int poly[8] = {200, 110, 350, 110, 350, 180, 200, 180};
    fill_polygon(&c, poly, 4, premul(128, 255, 128, 255));
    uint32_t blended = c.data[150 * c.w + 275];
    if (blended == bg || blended == premul(128, 255, 128, 255)) {
        fprintf(stderr, "FAIL polygon alpha blend: %08x\n", blended);
        failures++;
    }

    /* Rounded rect: center filled, true corner pixel left empty */
    struct canvas rr = mk(100, 100);
    fill_round_rect(&rr, 10, 10, 80, 80, 20, red);
    expect(&rr, 50, 50, red, "rrect center filled");
    expect(&rr, 10, 10, 0, "rrect corner rounded away");
    expect(&rr, 50, 10, red, "rrect top edge filled");
    free(rr.data);

    /* Arc: a point on the arc is drawn, off-arc stays empty.
     * East (0 deg) of center (50,50) r=30 -> (80,50). */
    struct canvas ar = mk(100, 100);
    draw_arc(&ar, 50, 50, 30, -10, 10, 1, green);
    expect_stroke(&ar, 80, 50, CH_G, "arc east point");
    expect(&ar, 20, 50, 0, "arc west point not drawn");
    free(ar.data);

    /* Bezier: endpoints must be on the curve */
    struct canvas bz = mk(100, 100);
    draw_bezier(&bz, 5, 5, 30, 90, 70, 90, 95, 5, 1, cyan);
    expect(&bz, 5, 5, cyan, "bezier start endpoint");
    expect(&bz, 95, 5, cyan, "bezier end endpoint");
    free(bz.data);

    /* Clipping: drawing outside the clip rect must be a no-op */
    struct canvas cc = mk(50, 50);
    cc.clip_x = 10; cc.clip_y = 10; cc.clip_w = 20; cc.clip_h = 20;
    fill_rect(&cc, 0, 0, 50, 50, red);
    expect(&cc, 5, 5, 0, "clip rejects outside");
    expect(&cc, 15, 15, red, "clip accepts inside");
    free(cc.data);

    free(c.data);

    if (failures > 0) {
        fprintf(stderr, "%d failures\n", failures);
        return 1;
    }
    printf("all graphics rasterizer tests passed\n");
    return 0;
}
