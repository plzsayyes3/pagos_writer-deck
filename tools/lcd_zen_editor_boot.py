#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boot wrapper for the LCD Writer Deck.

The shared ZenEditor.run() waits for Enter on its splash screen. On the
headless tty1 LCD appliance we want the editor visible immediately after boot.
The LCD renderer itself is unchanged.
"""
import curses
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools import lcd_zen_editor


def no_splash(self):
    self.status = "新しい原稿を書き始めてください"
    self.render()


lcd_zen_editor.LCDZenEditor.show_splash = no_splash


if __name__ == "__main__":
    want_poweroff = curses.wrapper(lcd_zen_editor.main)
    if want_poweroff:
        os.system("sudo /usr/sbin/shutdown -h now")
