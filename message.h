#pragma once

#include <stdbool.h>
#include <xkbcommon/xkbcommon.h>
#include <tllist.h>

#include "config.h"
#include "key-binding.h"
#include "terminal.h"

static inline bool msgs_mode_is_active(const struct terminal *term)
{
    return tll_length(term->msgs) > 0;
}

void close_message(struct terminal *term);
void msgs_reset(struct terminal *term);
void msgs_render(struct terminal *term);

void
msgs_input(struct seat *seat, struct terminal *term,
           const struct key_binding_set *bindings, uint32_t key,
           xkb_keysym_t sym, xkb_mod_mask_t mods, xkb_mod_mask_t consumed,
           const xkb_keysym_t *raw_syms, size_t raw_count,
           uint32_t serial);
