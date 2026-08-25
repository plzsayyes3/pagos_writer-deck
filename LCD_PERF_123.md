# LCD performance: 1-2-3

This branch is based on the known-good `lcd` branch.

## 1. Measure

The fast editor can record render / RGB565 packing / framebuffer-write timings.

```bash
PAGOS_LCD_PERF=1 python3 tools/lcd_zen_editor_fast.py
```

The log is written to:

```text
~/pagos_writer-deck/lcd_perf.log
```

A `full` frame is the initial screen. Subsequent frames should normally be
`partial`, with a much smaller `bytes=` value. `none` means the rendered
frame did not change.

## 2. Partial refresh

`tools/lcd_zen_editor_fast.py` keeps a shadow RGB565 framebuffer and calculates
the changed rectangle. Only that rectangle is written through `/dev/fb1`.

The existing fbtft framebuffer path is deliberately retained; no driver or
kernel migration is part of this change.

## 3. SPI 32 MHz

Change only the existing OSOYOO overlay speed on the Raspberry Pi:

```text
dtoverlay=osoyoo35b:speed=32000000
```

Do not change the other LCD settings at the same time.

Then reboot and verify:

```bash
dmesg | grep -iE 'fb_ili9486|spi0.0|osoyoo'
```

The driver should report `spi0.0 at 32 MHz` (or an equivalent speed line).

If the display is unstable, revert only this value to `20000000` and reboot.

## Safe rollout

1. Test the fast editor manually first.
2. Confirm the screen is correct and text input still works.
3. Enable `PAGOS_LCD_PERF=1` only while measuring; leave it off for normal use.
4. Change SPI from 20 MHz to 32 MHz separately.
5. Only after both tests are stable should the boot launcher be changed to
   `lcd_zen_editor_fast.py`.
