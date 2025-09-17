#include "message.h"


#include <stdlib.h>
#include <string.h>
#include <wctype.h>
#include <unistd.h>

#include <sys/stat.h>
#include <fcntl.h>

#define LOG_MODULE "message"
#define LOG_ENABLE_DBG 0
#include "log.h"
#include "char32.h"
#include "key-binding.h"
#include "quirks.h"
#include "render.h"
#include "terminal.h"
#include "util.h"
#include "xmalloc.h"


static bool
execute_binding(struct seat *seat, struct terminal *term,
                const struct key_binding *binding, uint32_t serial)
{
    const enum bind_action_close_message action = binding->action;

    switch (action) {
    case BIND_ACTION_CLOSE_MESSAGE_NONE:
        return false;

    case BIND_ACTION_CLOSE_MESSAGE_CANCEL:
        msgs_reset(term);
        return true;

    case BIND_ACTION_CLOSE_MESSAGE_ACCEPT:
        term_shutdown(term);
        return true;

    case BIND_ACTION_MESSAGE_COUNT:
        return false;
    }
    return true;
}

void
msgs_input(struct seat *seat, struct terminal *term,
           const struct key_binding_set *bindings, uint32_t key,
           xkb_keysym_t sym, xkb_mod_mask_t mods, xkb_mod_mask_t consumed,
           const xkb_keysym_t *raw_syms, size_t raw_count,
           uint32_t serial)
{

    tll_foreach(bindings->msg, it) {
        const struct key_binding *bind = &it->item;
        if (bind->mods != mods || bind->mods == 0)
            continue;

        for (size_t i = 0; i < raw_count; i++) {
            if (bind->k.sym == raw_syms[i]) {
                execute_binding(seat, term, bind, serial);
                return;
            }
        }
    }

    /* Match translated symbol */
    tll_foreach(bindings->msg, it) {
        const struct key_binding *bind = &it->item;

        if (bind->k.sym == sym &&
            bind->mods == (mods & ~consumed))
        {
            execute_binding(seat, term, bind, serial);
            return;
        }

    }

    /* Match raw key code */
    tll_foreach(bindings->msg, it) {
        const struct key_binding *bind = &it->item;
        if (bind->mods != mods || bind->mods == 0)
            continue;

        /* Match raw key code */
        tll_foreach(bind->k.key_codes, code) {
            if (code->item == key) {
                execute_binding(seat, term, bind, serial);
                return;
            }
        }
    }

}

void
close_message(struct terminal *term)
{
    char *strs[] = {"Do you want to close this client?", "Confirm or cancel."};
    for (int i=0; i<2; i++){
        tll_push_back(term->msgs, ((struct msg){
                          .id = (uint64_t)rand() << 32 | rand(),
                          .text = ambstoc32(strs[i]),
                      }));
    }
}

void
msgs_render(struct terminal *term)
{
    struct wl_window *win = term->window;

    if (tll_length(win->term->msgs) == 0)
        return;

    if (term_ime_is_enabled(term)) {
        term->ime_reenable_after_msg_mode = true;
        term_ime_disable(term);
    }

    /* Dirty the last cursor, to ensure it is erased */
    {
        struct row *cursor_row = term->render.last_cursor.row;
        if (cursor_row != NULL) {
            struct cell *cell = &cursor_row->cells[term->render.last_cursor.col];
            cell->attrs.clean = 0;
            cursor_row->dirty = true;
        }
    }
    term->render.last_cursor.row = NULL;

    /* Clear scroll damage, to ensure we don't apply it twice (once on
     * the snapshot:ed grid, and then later again on the real grid) */
    tll_free(term->grid->scroll_damage);

    term_damage_view(term);


    xassert(tll_length(win->msgs) == 0);
    tll_foreach(win->term->msgs, it) {
        struct wl_msg msg = {.msg = &it->item};
        wayl_win_subsurface_new(win, &msg.surf, false);

        tll_push_back(win->msgs, msg);
    }

    render_refresh_msgs(term);
    render_refresh(term);
}


static void
msg_destroy(struct msg *msg)
{
    free(msg->text);
}

void
msgs_reset(struct terminal *term)
{
    term->render.last_cursor.row = NULL;

    if (term->window != NULL) {
        tll_foreach(term->window->msgs, it) {
            wayl_win_subsurface_destroy(&it->item.surf);
            tll_remove(term->window->msgs, it);
        }
    }

    tll_foreach(term->msgs, it) {
        msg_destroy(&it->item);
        tll_remove(term->msgs, it);
    }

    /* Re-enable IME, if it was enabled before we entered URL-mode */
    if (term->ime_reenable_after_msg_mode) {
        term->ime_reenable_after_msg_mode = false;
        term_ime_enable(term);
    }

    render_refresh(term);
}
