#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Listen for the physical Mac JIS かな/英数 keys at Linux input level.

Verified on the real Writer Deck keyboard with evtest:
  かな -> EV_KEY code 122 (KEY_HANGUEL), scan 70090
  英数 -> EV_KEY code 123 (KEY_HANJA),  scan 70091

The listener is best-effort. If the input device cannot be opened, the writer
continues to work with its normal JP mode instead of failing to start.
"""
import os
import struct
import threading
import time
import ctypes

DEVICE = "/dev/input/event0"
EV_KEY = 0x01
KEY_HANGUEL = 122
KEY_HANJA = 123
KEY_RELEASE = 0


def _event_size():
    # struct input_event is timeval + type(u16) + code(u16) + value(u32).
    # Raspbian on Pi 3 is armv7/32-bit, where timeval uses 32-bit longs.
    long_size = ctypes.sizeof(ctypes.c_long)
    return 16 if long_size == 4 else 24


def start(editor, device=DEVICE):
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_run,
        args=(editor, device, stop_event),
        daemon=True,
        name="physical-lang-keys",
    )
    thread.start()
    return stop_event, thread


def _run(editor, device, stop_event):
    size = _event_size()
    fmt = "@llHHI" if size == 16 else "@llHHI"
    try:
        fd = os.open(device, os.O_RDONLY | os.O_NONBLOCK)
    except OSError as e:
        editor.status = f"物理かな/英数キー監視無効: {e}"
        return

    try:
        while not stop_event.is_set():
            try:
                data = os.read(fd, size * 32)
            except BlockingIOError:
                time.sleep(0.02)
                continue
            except OSError as e:
                editor.status = f"キー監視停止: {e}"
                break

            if not data:
                time.sleep(0.02)
                continue

            usable = len(data) - (len(data) % size)
            for offset in range(0, usable, size):
                sec, usec, event_type, code, value = struct.unpack(
                    fmt, data[offset:offset + size]
                )
                if event_type != EV_KEY or value != 1:
                    continue
                if code == KEY_HANGUEL:
                    editor.skk_enabled = True
                    editor.romaji_buf = ""
                    editor.status = "日本語入力: ON"
                elif code == KEY_HANJA:
                    editor.flush_romaji_buf()
                    editor.skk_enabled = False
                    editor.status = "日本語入力: OFF"
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
