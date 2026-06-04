#pragma once

#include "terminal.h"

/*
 * Vector graphics protocol.
 *
 * Driven by a DCS sequence: ESC P > g <commands> ESC \
 *
 * The body is a newline/whitespace separated list of drawing commands
 * (see graphics.c for the grammar). The bytes are accumulated by
 * graphics_put() and the whole batch is parsed, rasterized into an ARGB
 * canvas, and placed on the grid by graphics_unhook(), reusing the sixel
 * image pipeline (sixel_emit_image()).
 */

void graphics_put(struct terminal *term, uint8_t c);
void graphics_unhook(struct terminal *term);
