#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GH1 fast-refresh mode smoke test.

This uses the official Waveshare epd3in7g.init_Fast() mode and then performs
one normal display() operation. It does NOT attempt partial refresh.

Run from the repository root on the Raspberry Pi while zen_editor.py is stopped:
    python3 tools/gh1_fast_display_test.py
"""
import os
import sys
import time

HOME = os.path.expanduser("~")
EPD_LIB_DIR = os.path.join(
    HOME, "e-Paper", "E-paper_Separate_Program", "3in7_e-Paper_G",
    "RaspberryPi_JetsonNano", "python", "lib"
)
FONT_PATH = os.path.join(
    HOME, "e-Paper", "E-paper_Separate_Program", "3in7_e-Paper_G",
    "RaspberryPi_JetsonNano", "python", "pic", "Font.ttc"
)
sys.path.append(EPD_LIB_DIR)

from waveshare_epd import epd3in7g
from PIL import Image, ImageDraw, ImageFont


def main():
    epd = epd3in7g.EPD()
    print("Initializing GH1 with init_Fast()...")
    t0 = time.monotonic()
    epd.init_Fast()
    print(f"init_Fast: {time.monotonic() - t0:.2f} s")

    img = Image.new("RGB", (epd.height, epd.width), epd.WHITE)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 24)
    small = ImageFont.truetype(FONT_PATH, 18)

    draw.text((10, 10), "PAGOS Writer Deck", font=font, fill=epd.BLACK)
    draw.text((10, 55), "GH1 fast-refresh test", font=small, fill=epd.BLACK)
    draw.text((10, 90), "init_Fast() + display()", font=small, fill=epd.BLACK)
    draw.text((10, 125), "Partial refresh: not enabled", font=small, fill=epd.BLACK)
    draw.text((10, 170), "Pi 3 / 416x240", font=small, fill=epd.BLACK)

    print("Displaying test image...")
    t0 = time.monotonic()
    epd.display(epd.getbuffer(img))
    elapsed = time.monotonic() - t0
    print(f"display_after_init_Fast: {elapsed:.2f} s")
    print("The image should now be visible on the e-paper.")
    print("Press Enter after checking the display to put the panel to sleep.")
    input()

    epd.sleep()
    print("GH1 is sleeping. Fast-refresh test complete.")


if __name__ == "__main__":
    main()
