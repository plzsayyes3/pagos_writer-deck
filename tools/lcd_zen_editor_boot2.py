#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LCD boot wrapper with polished pending-romaji rendering."""
import curses
import os
import sys
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tools import lcd_zen_editor


def no_splash(self):
    self.status = "新しい原稿を書き始めてください"
    self.render()


def render(self):
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
        start = max(0, len(rows) - max_rows)
        for pos, (idx, _text) in enumerate(rows):
            if idx == self.cy:
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
            # 未確定ローマ字は本文と同じサイズ、薄いグレー。
            # カーソルは未確定文字列の右側に置く。
            pending_x = cursor_x
            if self.skk_enabled and self.romaji_buf:
                d.text(
                    (pending_x, cursor_y),
                    self.romaji_buf,
                    font=self.font,
                    fill=(150, 150, 150),
                )
                pending_x += int(d.textlength(self.romaji_buf, font=self.font))
            d.rectangle((pending_x, cursor_y + 2, pending_x + 2, cursor_y + 27), fill="black")

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
        cx = (w - (cb[2] - cb[0])) // 2
        d.text((cx, h - 24), center, font=self.small, fill="black")
        rb = d.textbbox((0, 0), right, font=self.small)
        d.text((w - 8 - (rb[2] - rb[0]), h - 24), right, font=self.small, fill="black")

        img = img.rotate(180)
        rgb = np.asarray(img, dtype=np.uint16)
        r = rgb[:, :, 0]
        g = rgb[:, :, 1]
        b = rgb[:, :, 2]
        packed = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        raw = packed.astype("<u2").tobytes(order="C")

        row_bytes = w * 2
        stride = info["stride"]
        if stride == row_bytes:
            self.mm.seek(0)
            self.mm.write(raw)
        else:
            for yy in range(h):
                src = yy * row_bytes
                dst = yy * stride
                self.mm.seek(dst)
                self.mm.write(raw[src:src + row_bytes])
        self.mm.flush()


lcd_zen_editor.LCDZenEditor.show_splash = no_splash
lcd_zen_editor.LCDZenEditor.render = render


if __name__ == "__main__":
    want_poweroff = curses.wrapper(lcd_zen_editor.main)
    if want_poweroff:
        os.system("sudo /usr/sbin/shutdown -h now")
