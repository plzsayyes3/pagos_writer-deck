#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal real-time Writer Deck for the OSOYOO /dev/fb1 LCD.

This is an LCD-only experiment on the `lcd` branch. It renders directly to
/dev/fb1 using the Linux framebuffer and keeps the keyboard on tty1.

Controls in this first prototype:
- Ctrl+Q: quit
- Enter: new line
- Backspace: delete previous character

The renderer queries the framebuffer geometry and pixel format at runtime.
"""
import array
import curses
import fcntl
import mmap
import os
import struct
import sys
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


def first_existing(paths):
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def screen_info(fd):
    var = bytearray(160)
    fix = bytearray(80)
    fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var, True)
    fcntl.ioctl(fd, FBIOGET_FSCREENINFO, fix, True)
    # fb_var_screeninfo: xres,yres,xres_virtual,yres_virtual,xoffset,yoffset,bits_per_pixel
    xres, yres, xvirt, yvirt, xoff, yoff, bpp = struct.unpack_from("7I", var, 0)
    # fb_fix_screeninfo: line_length at offset 44
    line_length = struct.unpack_from("I", fix, 44)[0]
    # color bitfields start at offset 72 in fb_var_screeninfo
    red_off, red_len = struct.unpack_from("2I", var, 72)
    green_off, green_len = struct.unpack_from("2I", var, 80)
    blue_off, blue_len = struct.unpack_from("2I", var, 88)
    return {
        "width": xres,
        "height": yres,
        "xvirt": xvirt,
        "yvirt": yvirt,
        "bpp": bpp,
        "line_length": line_length,
        "red_off": red_off,
        "red_len": red_len,
        "green_off": green_off,
        "green_len": green_len,
        "blue_off": blue_off,
        "blue_len": blue_len,
    }


def pack_pixel(r, g, b, info):
    bpp = info["bpp"]
    if bpp == 16:
        rv = (r * ((1 << info["red_len"]) - 1) // 255) << info["red_off"]
        gv = (g * ((1 << info["green_len"]) - 1) // 255) << info["green_off"]
        bv = (b * ((1 << info["blue_len"]) - 1) // 255) << info["blue_off"]
        return struct.pack("<H", rv | gv | bv)
    if bpp == 24:
        rv = (r * ((1 << info["red_len"]) - 1) // 255) << info["red_off"]
        gv = (g * ((1 << info["green_len"]) - 1) // 255) << info["green_off"]
        bv = (b * ((1 << info["blue_len"]) - 1) // 255) << info["blue_off"]
        word = rv | gv | bv
        return bytes((word & 0xFF, (word >> 8) & 0xFF, (word >> 16) & 0xFF))
    if bpp == 32:
        rv = (r * ((1 << info["red_len"]) - 1) // 255) << info["red_off"]
        gv = (g * ((1 << info["green_len"]) - 1) // 255) << info["green_off"]
        bv = (b * ((1 << info["blue_len"]) - 1) // 255) << info["blue_off"]
        return struct.pack("<I", rv | gv | bv)
    raise RuntimeError(f"Unsupported framebuffer bpp: {bpp}")


def fit_text_lines(text, font, width_px):
    rows = []
    for logical in text.split("\n"):
        if logical == "":
            rows.append("")
            continue
        current = ""
        for ch in logical:
            test = current + ch
            if font.getlength(test) > width_px and current:
                rows.append(current)
                current = ch
            else:
                current = test
        rows.append(current)
    return rows


class LCDWriter:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.fd = os.open(FB, os.O_RDWR)
        self.info = screen_info(self.fd)
        self.width = self.info["width"]
        self.height = self.info["height"]
        self.map_len = self.info["line_length"] * self.info["yvirt"]
        self.fb = mmap.mmap(self.fd, self.map_len, mmap.MAP_SHARED, mmap.PROT_WRITE | mmap.PROT_READ)
        self.font_path = first_existing(FONT_CANDIDATES)
        if not self.font_path:
            raise RuntimeError("No usable font found")
        self.font = ImageFont.truetype(self.font_path, 24)
        self.small = ImageFont.truetype(self.font_path, 15)
        self.lines = [""]
        self.dirty = True

    def close(self):
        try:
            self.fb.close()
        finally:
            os.close(self.fd)

    def draw(self):
        img = Image.new("RGB", (self.width, self.height), "white")
        draw = ImageDraw.Draw(img)
        rows = fit_text_lines("\n".join(self.lines), self.font, self.width - 20)
        status_h = 30
        max_rows = max(1, (self.height - status_h - 10) // 30)
        rows = rows[-max_rows:]
        y = 6
        for row in rows:
            draw.text((10, y), row, font=self.font, fill="black")
            y += 30

        sep_y = self.height - status_h - 1
        draw.line((0, sep_y, self.width, sep_y), fill=(230, 190, 0), width=2)
        draw.text((10, self.height - 24), f"{sum(len(x) for x in self.lines)}字", font=self.small, fill="black")
        mid = "未保存"
        draw.text((self.width // 2 - 25, self.height - 24), mid, font=self.small, fill="black")
        clock = datetime.now().strftime("%H:%M")
        bbox = draw.textbbox((0, 0), clock, font=self.small)
        draw.text((self.width - 10 - (bbox[2] - bbox[0]), self.height - 24), clock, font=self.small, fill="black")

        raw = img.tobytes()
        if self.info["bpp"] == 16:
            out = bytearray(self.map_len)
            stride = self.info["line_length"]
            for y0 in range(self.height):
                for x0 in range(self.width):
                    r, g, b = img.getpixel((x0, y0))
                    p = (y0 * stride) + (x0 * 2)
                    rv = (r * ((1 << self.info["red_len"]) - 1) // 255) << self.info["red_off"]
                    gv = (g * ((1 << self.info["green_len"]) - 1) // 255) << self.info["green_off"]
                    bv = (b * ((1 << self.info["blue_len"]) - 1) // 255) << self.info["blue_off"]
                    struct.pack_into("<H", out, p, rv | gv | bv)
            self.fb.seek(0)
            self.fb.write(out)
        else:
            raise RuntimeError(f"LCD prototype currently expects 16bpp, detected {self.info['bpp']}bpp")
        self.fb.flush()
        self.dirty = False


def main(stdscr):
    curses.raw()
    curses.noecho()
    stdscr.nodelay(False)
    writer = LCDWriter(stdscr)
    try:
        writer.draw()
        while True:
            ch = stdscr.get_wch()
            if isinstance(ch, str):
                if ch == "\x11":  # Ctrl+Q
                    break
                if ch in ("\n", "\r"):
                    writer.lines.append("")
                elif ch in ("\x7f", "\b"):
                    if writer.lines[-1]:
                        writer.lines[-1] = writer.lines[-1][:-1]
                    elif len(writer.lines) > 1:
                        writer.lines.pop()
                elif unicodedata.category(ch[:1]) != "Cc":
                    writer.lines[-1] += ch
                writer.draw()
            else:
                # Ignore non-character function keys in the minimal prototype.
                pass
    finally:
        writer.close()


if __name__ == "__main__":
    curses.wrapper(main)
