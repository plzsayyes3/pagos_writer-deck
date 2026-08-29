#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fast LCD Writer Deck.

Based on tools/lcd_zen_editor.py. This version keeps the known-good fbtft/
/dev/fb1 path, but only writes the changed framebuffer rectangle after the
first frame. It also records render/write timings when PAGOS_LCD_PERF=1.

SPI speed is intentionally NOT changed by this Python program. The safe
hardware-side change is documented separately as a config.txt edit to
32 MHz, so it can be reverted independently.
"""
import curses
import os
import sys
import time
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from lcd_zen_editor import LCDZenEditor as _BaseLCDZenEditor
from lcd_zen_editor import physical_lang_listener
import zen_editor

PERF = os.environ.get("PAGOS_LCD_PERF", "0") == "1"
# 診断用: PAGOS_LCD_FORCE_FULL=1 で部分更新を無効化し、毎回フル画面を
# 書き込む。表示が途中で切れる不具合が部分更新側のバグかどうかを
# 切り分けるためのもの。
FORCE_FULL = os.environ.get("PAGOS_LCD_FORCE_FULL", "0") == "1"
PERF_LOG = os.path.expanduser("~/pagos_writer-deck/lcd_perf.log")


class FastLCDZenEditor(_BaseLCDZenEditor):
    """Known-good LCD editor with dirty-rectangle framebuffer writes."""

    def __init__(self, stdscr):
        self._shadow = None
        self._frame_no = 0
        super().__init__(stdscr)

    def _perf_log(self, frame_no, render_ms, pack_ms, write_ms, total_ms,
                  mode, bbox, bytes_written):
        if not PERF:
            return
        line = (
            f"{datetime.now().isoformat(timespec='milliseconds')} "
            f"frame={frame_no} mode={mode} bbox={bbox} bytes={bytes_written} "
            f"render={render_ms:.2f}ms pack={pack_ms:.2f}ms "
            f"write={write_ms:.2f}ms total={total_ms:.2f}ms\n"
        )
        try:
            with open(PERF_LOG, "a", encoding="utf-8") as fp:
                fp.write(line)
        except OSError:
            pass

    def render(self):
        t0 = time.perf_counter()
        with self._render_lock:
            info = self.fb_info
            w, h = info["w"], info["h"]
            status_h = 32
            img = Image.new("RGB", (w, h), "white")
            d = ImageDraw.Draw(img)

            visible_h = h - status_h - 8
            rows = []
            for idx, logical in enumerate(self.lines):
                for part in self._wrap(logical, self.font, w - 24):
                    rows.append((idx, part))
            max_rows = max(1, visible_h // 30)
            current_logical = self.cy
            start = max(0, len(rows) - max_rows)
            for pos, (idx, _text) in enumerate(rows):
                if idx == current_logical:
                    start = min(max(0, pos), max(0, len(rows) - max_rows))
                    break
            visible = rows[start:start + max_rows]

            y = 5
            cursor_y = None
            cursor_x = 10
            for idx, text in visible:
                d.text((10, y), text, font=self.font, fill="black")
                if idx == self.cy:
                    cursor_y = y
                    prefix = self.lines[idx][:self.cx]
                    cursor_x = 10 + int(d.textlength(prefix, font=self.font))
                y += 30

            if cursor_y is not None:
                if self.skk_enabled and self.romaji_buf:
                    d.text(
                        (cursor_x, cursor_y + 2), self.romaji_buf,
                        font=self.small, fill=(110, 110, 110),
                    )
                d.rectangle(
                    (cursor_x, cursor_y + 2, cursor_x + 2, cursor_y + 25),
                    fill="black",
                )

            sep_y = h - status_h
            d.line((0, sep_y, w, sep_y), fill=(205, 180, 70), width=2)
            count = sum(len(x) for x in self.lines)
            left = f"{count}字"
            center = os.path.basename(self.filename) if self.filename and not self.dirty else "未保存"
            if self.filename and self.dirty:
                center = os.path.basename(self.filename) + "*"
            right = datetime.now().strftime("%H:%M")
            d.text((8, h - 24), left, font=self.small, fill="black")
            cb = d.textbbox((0, 0), center, font=self.small)
            d.text(((w - (cb[2] - cb[0])) // 2, h - 24), center,
                   font=self.small, fill="black")
            rb = d.textbbox((0, 0), right, font=self.small)
            d.text((w - 8 - (rb[2] - rb[0]), h - 24), right,
                   font=self.small, fill="black")

            img = img.rotate(180)
            render_ms = (time.perf_counter() - t0) * 1000.0

            t1 = time.perf_counter()
            rgb = np.asarray(img, dtype=np.uint16)
            r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
            packed = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            current = packed.astype("<u2")
            pack_ms = (time.perf_counter() - t1) * 1000.0

            if FORCE_FULL or self._shadow is None or self._shadow.shape != current.shape:
                y0, y1, x0, x1 = 0, h, 0, w
                mode = "full"
            else:
                changed = current != self._shadow
                ys, xs = np.nonzero(changed)
                if len(xs) == 0:
                    self._frame_no += 1
                    total_ms = (time.perf_counter() - t0) * 1000.0
                    self._perf_log(self._frame_no, render_ms, pack_ms, 0.0,
                                   total_ms, "none", None, 0)
                    return
                y0, y1 = int(ys.min()), int(ys.max()) + 1
                x0, x1 = int(xs.min()), int(xs.max()) + 1
                mode = "partial"

            row_bytes = w * 2
            stride = info["stride"]
            t2 = time.perf_counter()
            bytes_written = 0
            if x0 == 0 and x1 == w and stride == row_bytes:
                raw = current[y0:y1].tobytes(order="C")
                self.mm.seek(y0 * stride)
                self.mm.write(raw)
                bytes_written = len(raw)
            else:
                segment = current[:, x0:x1]
                seg_bytes = (x1 - x0) * 2
                for yy in range(y0, y1):
                    raw = segment[yy - y0].tobytes(order="C")
                    self.mm.seek(yy * stride + x0 * 2)
                    self.mm.write(raw)
                    bytes_written += seg_bytes
            self.mm.flush()
            write_ms = (time.perf_counter() - t2) * 1000.0

            self._shadow = current.copy()
            self._frame_no += 1
            total_ms = (time.perf_counter() - t0) * 1000.0
            self._perf_log(
                self._frame_no, render_ms, pack_ms, write_ms, total_ms,
                mode, (x0, y0, x1, y1), bytes_written,
            )


def main(stdscr):
    # 順序が重要: curses.raw()が内部でtermiosを上書きするため、
    # フロー制御(IXON/IXOFF)の無効化は必ずcurses.raw()の"後"に行う。
    # 電子ペーパー版(zen_editor.py)にはこの処理があるが、LCD版には
    # 無かった。物理コンソール(SSHのptyとは違う)では、これが無いと
    # 入力が正しく通らないことがある。
    curses.raw()
    zen_editor.disable_flow_control()
    curses.noecho()
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)
    editor = FastLCDZenEditor(stdscr)
    stop, th = physical_lang_listener(editor)
    try:
        editor.render()
        editor.run = lambda: zen_editor.ZenEditor.run(editor)
        return editor.run()
    finally:
        stop.set()
        th.join(timeout=1)
        editor.shutdown()


if __name__ == "__main__":
    want_poweroff = curses.wrapper(main)
    if want_poweroff:
        os.system("sudo /usr/sbin/shutdown -h now")
