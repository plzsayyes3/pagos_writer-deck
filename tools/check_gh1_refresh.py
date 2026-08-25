#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect the installed Waveshare GH1 driver before enabling partial refresh.

Run this on the Raspberry Pi 3 from the writer-deck checkout.
It deliberately performs NO display update, so it is safe to run while
investigating the driver API.
"""
import os
import sys

EPD_LIB_DIR = os.path.join(
    os.path.expanduser("~"),
    "e-Paper", "E-paper_Separate_Program", "3in7_e-Paper_G",
    "RaspberryPi_JetsonNano", "python", "lib",
)
sys.path.append(EPD_LIB_DIR)

try:
    from waveshare_epd import epd3in7g
except Exception as exc:
    print(f"IMPORT_ERROR: {type(exc).__name__}: {exc}")
    raise SystemExit(2)

print("driver:", getattr(epd3in7g, "__file__", "unknown"))
print("EPD_WIDTH:", getattr(epd3in7g, "EPD_WIDTH", "unknown"))
print("EPD_HEIGHT:", getattr(epd3in7g, "EPD_HEIGHT", "unknown"))

methods = [
    "display",
    "displayPartial",
    "display_part",
    "display_Partial",
    "init",
    "init_Fast",
]

epd = epd3in7g.EPD()
for name in methods:
    print(f"{name}: {'YES' if callable(getattr(epd, name, None)) else 'NO'}")

print("\nNo display operation was performed.")
print("If displayPartial/display_part/display_Partial is NO, the installed official")
print("2025 Waveshare Python driver is full-refresh-only and zen_editor must not")
print("pretend that Ctrl+D is a partial refresh.")
