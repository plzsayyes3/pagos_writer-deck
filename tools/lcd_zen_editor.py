#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Full LCD Writer Deck.

Reuses zen_editor's document, saving, Git, AI conversion, undo, search and
Ctrl-key behavior, while replacing only the e-paper/curses display with the
OSOYOO /dev/fb1 LCD.  Physical かな/英数 keys are handled directly here.
"""
import curses
import ctypes
import fcntl
import mmap
import os
import struct
import sys
import threading
import time
import unicodedata
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import zen_editor

FB = "/dev/fb1"
FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602
FONT_CANDIDATES = [
    os.path.expanduser("~/e-Paper/E-paper_Separate_Program/3in7_e-Paper_G/RaspberryPi_JetsonNano/python/pic/Font.ttc"),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def fb_info(fd):
    var = bytearray(160)
    fix = bytearray(80)
    fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var, True)
    fcntl.ioctl(fd, FBIOGET_FSCREENINFO, fix, True)
    x, y, xv, yv, _xo, _yo, bpp, _ = struct.unpack_from("8I", var, 0)
    ro, rl, _ = struct.unpack_from("3I", var, 32)
    go, gl, _ = struct.unpack_from("3I", var, 44)
    bo, bl, _ = struct.unpack_from("3I", var, 56)
    stride = struct.unpack_from("I", fix, 44)[0]
    return dict(w=x, h=y, xv=xv, yv=yv, bpp=bpp, stride=stride,
                ro=ro, rl=rl, go=go, gl=gl, bo=bo, bl=bl)


def noop_epaper_init(self):
    self.enabled = False
    self.error = "LCD mode"
    self.ready = False


class LCDNoopEPaper:
    def __init__(self):
        self.enabled = False
        self.error = "LCD mode"
        self.ready = False
        self.busy = False
    def request(self, lines):
        return None
    def request_custom(self, draw_fn):
        return None
    def shutdown(self):
        return None


# Prevent ZenEditor from touching the e-paper GPIO/SPI path.
zen_editor.EPaperWriter = LCDNoopEPaper


def convert_current_line(self):
    if self.skk_enabled:
        self.flush_romaji_buf()
    source = self.lines[self.cy]
    if not source.strip():
        self.status = "変換する文字がありません"
        return
    self.status = "変換中..."
    self.render()
    try:
        converted = zen_editor.ai_convert.convert_to_kanji(source)
        self.snapshot()
        self.lines[self.cy] = converted
        self.cx = len(converted)
        self.dirty = True
        self.status = "現在行を漢字変換しました"
    except zen_editor.ai_convert.AiConvertError as e:
        self.status = f"変換失敗: {e}"
    except Exception as e:
        self.status = f"変換失敗: {e}"


# Ctrl+K = current-line kanji conversion.
zen_editor.ZenEditor.skk_toggle = convert_current_line


class LCDZenEditor(zen_editor.ZenEditor):
    def __init__(self, stdscr):
        super().__init__(stdscr)
        self.fd = os.open(FB, os.O_RDWR)
        self.fb_info = fb_info(self.fd)
        if self.fb_info["bpp"] != 16:
            raise RuntimeError(f"LCD must be 16bpp, got {self.fb_info['bpp']}bpp")
        self.mm = mmap.mmap(
            self.fd,
            self.fb_info["stride"] * self.fb_info["yv"],
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
        )
        font_path = next((p for p in FONT_CANDIDATES if os.path.exists(p)), None)
        if not font_path:
            raise RuntimeError("No usable font found")
        self.font = ImageFont.truetype(font_path, 24)
        self.small = ImageFont.truetype(font_path, 15)
        self._render_lock = threading.Lock()

    def shutdown(self):
        try:
            self.mm.close()
        finally:
            os.close(self.fd)
        self.epaper.shutdown()

    def push_to_epaper(self):
        return None

    def draw_shutdown_image(self):
        return None

    @staticmethod
    def _wrap(text, font, width):
        rows = []
        cur = ""
        for ch in text:
            test = cur + ch
            if font.getlength(test) > width and cur:
                rows.append(cur)
                cur = ch
            else:
                cur = test
        rows.append(cur)
        return rows

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
            current_logical = self.cy
            # Keep cursor line visible; otherwise show the newest lines.
            start = max(0, len(rows) - max_rows)
            for pos, (idx, text) in enumerate(rows):
                if idx == current_logical:
                    first = pos
                    start = min(max(0, first), max(0, len(rows) - max_rows))
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
                # Thin vertical cursor; no block to minimize visual noise.
                d.rectangle((cursor_x, cursor_y + 2, cursor_x + 2, cursor_y + 25), fill="black")

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

            # Rotate to match the physical LCD orientation.
            img = img.rotate(180)

            # Vectorized RGB888 -> RGB565 little-endian.
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


def physical_lang_listener(editor):
    """Use the verified Mac JIS keys directly from /dev/input/event0.
    122=かな, 123=英数.  Fail-soft so LCD editor remains usable."""
    stop = threading.Event()
    device = "/dev/input/event0"
    def event_size():
        return 16 if ctypes.sizeof(ctypes.c_long) == 4 else 24
    size = event_size()

    def worker():
        try:
            fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            return
        fmt = "@llHHI"
        try:
            while not stop.is_set():
                try:
                    data = os.read(fd, size * 32)
                except BlockingIOError:
                    time.sleep(0.02); continue
                except OSError:
                    break
                if not data:
                    time.sleep(0.02); continue
                usable = len(data) - len(data) % size
                for off in range(0, usable, size):
                    _sec, _usec, typ, code, value = struct.unpack(fmt, data[off:off+size])
                    if typ != 1 or value != 1:
                        continue
                    if code == 122:
                        editor.skk_enabled = True
                        editor.romaji_buf = ""
                        editor.status = "日本語入力: ON"
                    elif code == 123:
                        editor.flush_romaji_buf()
                        editor.skk_enabled = False
                        editor.status = "日本語入力: OFF"
                        editor.render()
        finally:
            os.close(fd)
    th = threading.Thread(target=worker, daemon=True, name="lcd-lang-keys")
    th.start()
    return stop, th


def main(stdscr):
    curses.raw()
    curses.noecho()
    curses.curs_set(0)
    stdscr.keypad(True)
    stdscr.nodelay(False)
    editor = LCDZenEditor(stdscr)
    stop, th = physical_lang_listener(editor)
    try:
        editor.run()
        return editor.want_poweroff
    finally:
        stop.set()
        th.join(timeout=1)
        editor.shutdown()


if __name__ == "__main__":
    want_poweroff = curses.wrapper(main)
    if want_poweroff:
        os.system("sudo /usr/sbin/shutdown -h now")
