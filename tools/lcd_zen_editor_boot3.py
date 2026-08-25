#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LCD boot UI: logo -> Enter -> Writer -> power-off message."""
import curses
import os
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from tools import lcd_zen_editor_boot2 as base

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO = os.path.join(ROOT, "logo.png")


def _font(editor, size=22):
    return ImageFont.truetype(editor.font.path if hasattr(editor.font, "path") else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)


def _write_image(editor, img):
    info = editor.fb_info
    w, h = info["w"], info["h"]
    img = img.convert("RGB").resize((w, h))
    img = img.rotate(180)
    rgb = np.asarray(img, dtype=np.uint16)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    packed = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
    raw = packed.astype("<u2").tobytes(order="C")
    row_bytes = w * 2
    stride = info["stride"]
    if stride == row_bytes:
        editor.mm.seek(0)
        editor.mm.write(raw)
    else:
        for y in range(h):
            src = y * row_bytes
            editor.mm.seek(y * stride)
            editor.mm.write(raw[src:src + row_bytes])
    editor.mm.flush()


def show_splash(self):
    w, h = self.fb_info["w"], self.fb_info["h"]
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)

    if os.path.exists(LOGO):
        try:
            logo = Image.open(LOGO).convert("RGB")
            max_w, max_h = int(w * 0.82), int(h * 0.68)
            scale = min(max_w / logo.width, max_h / logo.height, 1.0)
            logo = logo.resize((max(1, int(logo.width * scale)), max(1, int(logo.height * scale))))
            x = (w - logo.width) // 2
            y = 22 + (max_h - logo.height) // 2
            img.paste(logo, (x, y))
        except Exception:
            d.text((w // 2 - 65, 105), "ぱゴス", font=self.font, fill="black")
    else:
        d.text((w // 2 - 65, 105), "ぱゴス", font=self.font, fill="black")

    prompt = "Enterで開始"
    bbox = d.textbbox((0, 0), prompt, font=self.small)
    d.text(((w - (bbox[2] - bbox[0])) // 2, h - 42), prompt, font=self.small, fill="black")
    _write_image(self, img)

    while True:
        ch = self.stdscr.getch()
        if ch in (10, 13, curses.KEY_ENTER):
            self.status = "新しい原稿を書き始めてください"
            self.render()
            return
        if ch in (ord("q"), ord("Q")):
            self.want_poweroff = True
            return


def shutdown_image(self):
    w, h = self.fb_info["w"], self.fb_info["h"]
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    msg = "電源を切ってください"
    bbox = d.textbbox((0, 0), msg, font=self.font)
    d.text(((w - (bbox[2] - bbox[0])) // 2, (h - (bbox[3] - bbox[1])) // 2 - 12), msg, font=self.font, fill="black")
    sub = datetime.now().strftime("%H:%M")
    sb = d.textbbox((0, 0), sub, font=self.small)
    d.text(((w - (sb[2] - sb[0])) // 2, h - 38), sub, font=self.small, fill=(110, 110, 110))
    _write_image(self, img)


base.LCDZenEditor.show_splash = show_splash
base.LCDZenEditor.draw_shutdown_image = shutdown_image


if __name__ == "__main__":
    want_poweroff = curses.wrapper(base.lcd_zen_editor.main)
    if want_poweroff:
        os.system("sudo /usr/sbin/shutdown -h now")
