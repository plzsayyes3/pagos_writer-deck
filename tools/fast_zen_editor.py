#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launch zen_editor.py using the GH1 Fast initialization and layout modes.

This keeps zen_editor.py unchanged. It applies four runtime adaptations:
1. GH1 init_Fast() for the experimentally measured ~14.6 s full refresh.
2. GH1-specific text layout from gh1_layout.py.
3. Physical かな/英数 key mode control from physical_lang_keys.py.
4. Ctrl+K current-line Kanji conversion from kanji_shortcut.py.

Ctrl+K converts only the current logical line. Ctrl+G remains the existing
whole-document conversion + Git send operation.
"""
import curses
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import zen_editor
from tools import gh1_layout, physical_lang_keys, kanji_shortcut

if not zen_editor.EPAPER_OK:
    raise SystemExit(f"e-paper driver unavailable: {zen_editor.EPAPER_ERR}")

from waveshare_epd import epd3in7g


def _fast_init(self):
    return self.init_Fast()


# Use the experimentally verified GH1 fast initialization path.
epd3in7g.EPD.init = _fast_init

# Apply the GH1-specific 416x240 text layout without modifying zen_editor.py.
gh1_layout.apply(zen_editor)

# JP/EN is selected by the physical かな/英数 keys.
# Replace the old Ctrl+K JP/EN toggle with current-line Kanji conversion.
kanji_shortcut.apply(zen_editor)


def main(stdscr):
    curses.raw()
    zen_editor.disable_flow_control()
    editor = zen_editor.ZenEditor(stdscr)
    lang_stop, lang_thread = physical_lang_keys.start(editor)
    try:
        editor.run()
    finally:
        lang_stop.set()
        lang_thread.join(timeout=1)
        editor.shutdown()
    return editor.want_poweroff


if __name__ == "__main__":
    want_poweroff = False
    try:
        want_poweroff = curses.wrapper(main)
    except Exception:
        raise

    if want_poweroff:
        subprocess.run(["sudo", "/usr/sbin/shutdown", "-h", "now"])
