#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detect how the Pi's physical keyboard reports keys such as かな/英数.

Run this on tty1 with the physical keyboard connected to the Pi:
    python3 tools/keycode_test.py

Press かな, 英数, Ctrl+K, and a few ordinary keys. Press q to quit.
The script records curses/get_wch() results so we can map the keys without
changing zen_editor.py yet.
"""
import curses
import os
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "keycode_test.log")


def main(stdscr):
    curses.raw()
    stdscr.keypad(True)
    stdscr.nodelay(False)
    curses.noecho()

    events = []
    stdscr.erase()
    stdscr.addstr(0, 0, "PAGOS Writer Deck - keycode test")
    stdscr.addstr(1, 0, "Press: かな / 英数 / Ctrl+K / A / Enter")
    stdscr.addstr(2, 0, "Press q to finish.")
    stdscr.refresh()

    while True:
        ch = stdscr.get_wch()
        code = ord(ch) if isinstance(ch, str) and len(ch) == 1 else None
        record = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "repr": repr(ch),
            "type": type(ch).__name__,
            "ord": code,
        }
        events.append(record)

        if ch == "q":
            break

        row = 4 + min(len(events) - 1, 14)
        line = f"{len(events):2d}: repr={record['repr']!s:<12} type={record['type']:<7} ord={str(code):<4}"
        try:
            stdscr.addstr(row, 0, line[: max(1, stdscr.getmaxyx()[1] - 1)])
            stdscr.refresh()
        except curses.error:
            pass

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        for event in events:
            f.write(f"{event}\n")

    stdscr.erase()
    stdscr.addstr(0, 0, f"Saved: {LOG_PATH}")
    stdscr.addstr(1, 0, "Press Enter to exit.")
    stdscr.refresh()
    stdscr.get_wch()


if __name__ == "__main__":
    curses.wrapper(main)
