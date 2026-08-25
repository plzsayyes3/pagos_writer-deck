#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LCD Writer prototype: render once, then update only changed LCD regions."""
import curses
import fcntl
import mmap
import os
import struct
import unicodedata
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

FB = "/dev/fb1"
FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602
FONT_CANDIDATES = [
    os.path.expanduser("~/e-Paper/E-paper_Separate_Program/3in7_e-Paper_G/RaspberryPi_JetsonNano/python/pic/Font.ttc"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

def info(fd):
    var = bytearray(160); fix = bytearray(80)
    fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var, True)
    fcntl.ioctl(fd, FBIOGET_FSCREENINFO, fix, True)
    x, y, xv, yv, xo, yo, bpp, _ = struct.unpack_from("8I", var, 0)
    ro, rl, _ = struct.unpack_from("3I", var, 32)
    go, gl, _ = struct.unpack_from("3I", var, 44)
    bo, bl, _ = struct.unpack_from("3I", var, 56)
    stride = struct.unpack_from("I", fix, 44)[0]
    return dict(w=x, h=y, xv=xv, yv=yv, bpp=bpp, stride=stride,
                ro=ro, rl=rl, go=go, gl=gl, bo=bo, bl=bl)

def pixel(r, g, b, inf):
    return ((r * ((1 << inf["rl"]) - 1) // 255) << inf["ro"]) | \
           ((g * ((1 << inf["gl"]) - 1) // 255) << inf["go"]) | \
           ((b * ((1 << inf["bl"]) - 1) // 255) << inf["bo"])

def crop_to_fb(img, x, y, w, h, inf, mm):
    """Copy only one rectangle to the framebuffer; the image is already rotated."""
    data = bytearray(w * h * 2)
    p = 0
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            struct.pack_into("<H", data, p, pixel(*img.getpixel((xx, yy)), inf))
            p += 2
    for row in range(h):
        mm.seek((y + row) * inf["stride"] + x * 2)
        mm.write(data[row * w * 2:(row + 1) * w * 2])

def make_frame(inf, font, small, lines):
    img = Image.new("RGB", (inf["w"], inf["h"]), "white")
    d = ImageDraw.Draw(img)
    y = 6
    line_boxes = []
    for logical in lines:
        cur = ""
        for ch in logical:
            test = cur + ch
            if d.textlength(test, font=font) > inf["w"] - 20 and cur:
                d.text((10, y), cur, font=font, fill="black")
                line_boxes.append(y); y += 30; cur = ch
            else:
                cur = test
        d.text((10, y), cur, font=font, fill="black")
        line_boxes.append(y); y += 30
        if y > inf["h"] - 42:
            break
    sy = inf["h"] - 31
    d.line((0, sy, inf["w"], sy), fill=(230, 190, 0), width=2)
    d.text((10, inf["h"] - 24), f"{sum(map(len, lines))}字", font=small, fill="black")
    d.text((inf["w"] // 2 - 25, inf["h"] - 24), "未保存", font=small, fill="black")
    clock = datetime.now().strftime("%H:%M")
    bb = d.textbbox((0, 0), clock, font=small)
    d.text((inf["w"] - 10 - (bb[2] - bb[0]), inf["h"] - 24), clock, font=small, fill="black")
    return img.rotate(180), line_boxes

def main(stdscr):
    curses.raw(); curses.noecho(); stdscr.nodelay(False)
    fd = os.open(FB, os.O_RDWR)
    inf = info(fd)
    if inf["bpp"] != 16:
        raise RuntimeError(f"expected 16bpp, got {inf['bpp']}bpp")
    mm = mmap.mmap(fd, inf["stride"] * inf["yv"], mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
    fontp = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
    if not fontp: raise RuntimeError("font not found")
    font = ImageFont.truetype(fontp, 24); small = ImageFont.truetype(fontp, 15)
    lines = [""]
    try:
        frame, boxes = make_frame(inf, font, small, lines)
        mm.seek(0); mm.write(frame_to_bytes(frame, inf)); mm.flush()
        while True:
            ch = stdscr.get_wch()
            if isinstance(ch, str):
                old_n = len(lines)
                if ch == "\x11": break
                if ch in ("\n", "\r"):
                    lines.append("")
                elif ch in ("\x7f", "\b"):
                    if lines[-1]: lines[-1] = lines[-1][:-1]
                    elif len(lines) > 1: lines.pop()
                elif ch and unicodedata.category(ch[0]) != "Cc":
                    lines[-1] += ch
                frame, boxes = make_frame(inf, font, small, lines)
                # Minimal prototype: update only the visible text area plus status bar.
                # This removes the large full-frame write that caused visible flicker.
                text_h = max(0, inf["h"] - 34)
                crop_to_fb(frame, 0, 0, inf["w"], text_h, inf, mm)
                crop_to_fb(frame, 0, inf["h"] - 34, inf["w"], 34, inf, mm)
                mm.flush()
    finally:
        mm.close(); os.close(fd)

def frame_to_bytes(img, inf):
    out = bytearray(inf["stride"] * inf["yv"])
    for yy in range(inf["h"]):
        base = yy * inf["stride"]
        for xx in range(inf["w"]):
            struct.pack_into("<H", out, base + xx * 2, pixel(*img.getpixel((xx, yy)), inf))
    return out

if __name__ == "__main__":
    curses.wrapper(main)
