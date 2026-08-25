#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Render a simple Writer Deck UI image and show it on OSOYOO /dev/fb1 via fbi."""
import os
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 480, 320
FONT_CANDIDATES = [
    os.path.expanduser("~/e-Paper/E-paper_Separate_Program/3in7_e-Paper_G/RaspberryPi_JetsonNano/python/pic/Font.ttc"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
if not font_path:
    raise SystemExit("No usable font found")

img = Image.new("RGB", (WIDTH, HEIGHT), "white")
draw = ImageDraw.Draw(img)
font = ImageFont.truetype(font_path, 22)
small = ImageFont.truetype(font_path, 14)

lines = [
    "PAGOS Writer",
    "",
    "今日は少し寒い。",
    "LCD版の表示テストです。",
    "",
    "リアルタイム描画へ進めます。",
]

y = 16
for line in lines:
    draw.text((16, y), line, font=font, fill="black")
    y += 34

# Status bar: white background, black text, yellow separator.
draw.rectangle((0, HEIGHT - 30, WIDTH, HEIGHT), fill="white")
draw.line((0, HEIGHT - 31, WIDTH, HEIGHT - 31), fill=(230, 190, 0), width=2)
draw.text((12, HEIGHT - 24), "000字", font=small, fill="black")
draw.text((WIDTH // 2 - 45, HEIGHT - 24), "未保存", font=small, fill="black")
clock = "23:59"
bbox = draw.textbbox((0, 0), clock, font=small)
draw.text((WIDTH - 12 - (bbox[2] - bbox[0]), HEIGHT - 24), clock, font=small, fill="black")

fd, path = tempfile.mkstemp(prefix="pagos_lcd_", suffix=".png")
os.close(fd)
img.save(path)
print(path)

try:
    subprocess.run(["sudo", "fbi", "-T", "1", "-d", "/dev/fb1", "--noverbose", "--once", path], check=True)
finally:
    try:
        os.unlink(path)
    except OSError:
        pass
