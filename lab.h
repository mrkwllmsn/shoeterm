#pragma once

#include <stdint.h>

struct lab {
    float l;
    float a;
    float b;
};

struct lab lab_from_rgb(uint32_t rgb);
uint32_t lab_to_rgb(struct lab c);
struct lab lab_lerp(float t, struct lab a, struct lab b);
