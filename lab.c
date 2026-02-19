#include "lab.h"

#include <math.h>

struct lab
lab_from_rgb(uint32_t rgb)
{
    /* Extract and normalize sRGB components */
    float r = ((rgb >> 16) & 0xff) / 255.0f;
    float g = ((rgb >> 8) & 0xff) / 255.0f;
    float b = (rgb & 0xff) / 255.0f;

    /* Linearize sRGB (inverse gamma) */
    r = r > 0.04045f ? powf((r + 0.055f) / 1.055f, 2.4f) : r / 12.92f;
    g = g > 0.04045f ? powf((g + 0.055f) / 1.055f, 2.4f) : g / 12.92f;
    b = b > 0.04045f ? powf((b + 0.055f) / 1.055f, 2.4f) : b / 12.92f;

    /* Linear RGB to XYZ (sRGB matrix, D65 illuminant) */
    float x = (r * 0.4124564f + g * 0.3575761f + b * 0.1804375f) / 0.95047f;
    float y = r * 0.2126729f + g * 0.7151522f + b * 0.0721750f;
    float z = (r * 0.0193339f + g * 0.1191920f + b * 0.9503041f) / 1.08883f;

    /* XYZ to LAB */
    x = x > 0.008856f ? cbrtf(x) : 7.787f * x + 16.0f / 116.0f;
    y = y > 0.008856f ? cbrtf(y) : 7.787f * y + 16.0f / 116.0f;
    z = z > 0.008856f ? cbrtf(z) : 7.787f * z + 16.0f / 116.0f;

    return (struct lab){
        .l = 116.0f * y - 16.0f,
        .a = 500.0f * (x - y),
        .b = 200.0f * (y - z),
    };
}

uint32_t
lab_to_rgb(struct lab c)
{
    /* LAB to XYZ */
    float y = (c.l + 16.0f) / 116.0f;
    float x = c.a / 500.0f + y;
    float z = y - c.b / 200.0f;

    float x3 = x * x * x;
    float y3 = y * y * y;
    float z3 = z * z * z;

    float xf = (x3 > 0.008856f ? x3 : (x - 16.0f / 116.0f) / 7.787f) * 0.95047f;
    float yf = y3 > 0.008856f ? y3 : (y - 16.0f / 116.0f) / 7.787f;
    float zf = (z3 > 0.008856f ? z3 : (z - 16.0f / 116.0f) / 7.787f) * 1.08883f;

    /* XYZ to linear RGB (inverse sRGB matrix) */
    float r = xf *  3.2404542f - yf * 1.5371385f - zf * 0.4985314f;
    float g = xf * -0.9692660f + yf * 1.8760108f + zf * 0.0415560f;
    float b = xf *  0.0556434f - yf * 0.2040259f + zf * 1.0572252f;

    /* Apply sRGB gamma */
    r = r > 0.0031308f ? 1.055f * powf(r, 1.0f / 2.4f) - 0.055f : 12.92f * r;
    g = g > 0.0031308f ? 1.055f * powf(g, 1.0f / 2.4f) - 0.055f : 12.92f * g;
    b = b > 0.0031308f ? 1.055f * powf(b, 1.0f / 2.4f) - 0.055f : 12.92f * b;

    /* Clamp and quantize */
    if (r < 0.0f) r = 0.0f; else if (r > 1.0f) r = 1.0f;
    if (g < 0.0f) g = 0.0f; else if (g > 1.0f) g = 1.0f;
    if (b < 0.0f) b = 0.0f; else if (b > 1.0f) b = 1.0f;

    return (uint32_t)((uint8_t)(r * 255.0f + 0.5f) << 16 |
                      (uint8_t)(g * 255.0f + 0.5f) << 8 |
                      (uint8_t)(b * 255.0f + 0.5f));
}

struct lab
lab_lerp(float t, struct lab a, struct lab b)
{
    return (struct lab){
        .l = a.l + t * (b.l - a.l),
        .a = a.a + t * (b.a - a.a),
        .b = a.b + t * (b.b - a.b),
    };
}
