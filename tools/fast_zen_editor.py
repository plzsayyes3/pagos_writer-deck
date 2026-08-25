#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Launch zen_editor.py using the GH1 Fast initialization mode.

This intentionally leaves zen_editor.py unchanged. It monkey-patches the
Waveshare EPD object's init() call to init_Fast(), then runs the existing
editor unchanged. Ctrl+D and all existing editor behavior remain the same;
only the panel initialization waveform is changed.

Run only while zen_editor.py is not already running:
    python3 tools/fast_zen_editor.py
"""
import curses
import subprocess

import zen_editor


if not zen_editor.EPAPER_OK:
    raise SystemExit(f"e-paper driver unavailable: {zen_editor.EPAPER_ERR}")

# The official GH1 driver exposes init_Fast() and our hardware test showed
# that it reduces the subsequent full refresh from ~19.4 s to ~14.6 s.
from waveshare_epd import epd3in7g

_original_init = epd3in7g.EPD.init


def _fast_init(self):
    return self.init_Fast()


epd3in7g.EPD.init = _fast_init


def main(stdscr):
    curses.raw()
    zen_editor.disable_flow_control()
    editor = zen_editor.ZenEditor(stdscr)
    try:
        editor.run()
    finally:
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
