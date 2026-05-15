#pragma once

#include "terminal.h"

#if defined(FOOT_HAVE_SCROLLBACK)
void cmd_scrollback_up(struct terminal *term, int rows);
void cmd_scrollback_down(struct terminal *term, int rows);
#endif /* FOOT_HAVE_SCROLLBACK */
