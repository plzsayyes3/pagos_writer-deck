# another: GH1 partial-refresh investigation

This branch is for Raspberry Pi 3 + Waveshare 3.7inch e-Paper HAT+ (G).

## Current state

`zen_editor.py` currently calls `epd.display(...)`, which is a full-screen update.
It does **not** perform partial refresh.

The official Waveshare Python driver currently installed by the project is the
2025 `epd3in7g.py`. Its public API contains `display()` and `init_Fast()`, but no
`displayPartial()` / `display_part()` / `display_Partial()` method. The official C
driver likewise exposes full display and fast initialization, but no partial-display
function.

The Pi-side probe confirmed this on the actual machine:

```text
driver: /home/pagos/e-Paper/E-paper_Separate_Program/3in7_e-Paper_G/RaspberryPi_JetsonNano/python/lib/waveshare_epd/epd3in7g.py
EPD_WIDTH: 240
EPD_HEIGHT: 416
display: YES
displayPartial: NO
display_part: NO
display_Partial: NO
init: YES
init_Fast: YES
```

## What the official Waveshare documentation says

The current Waveshare product comparison lists the 3.7inch e-Paper HAT+ (G) as:

- 416x240
- red/yellow/black/white
- 20 s refresh
- **not marked as Partial Refresh supported**

The same comparison explicitly marks the monochrome 3.7inch e-Paper HAT (480x280)
as supporting partial refresh.

The GH1 manual contains FAQ text about partial refresh and ghosting, but the same
manual also states that **only some black-and-white e-Paper products support partial
refresh** and instructs users to check the product page. Therefore the FAQ must not
be treated as proof that this specific four-color GH1 panel supports partial refresh.

## New research: controller family

There is a separate 3.7inch 416x240 tri-color panel, Good Display GDEY037Z03,
using UC8253. Its published material contains explicit `PARTIAL IN (R91h)` and
`PARTIAL OUT (R92h)` commands, and Good Display lists a 1.5 s partial-refresh mode
for that panel family.

However, that does **not** establish that the Waveshare GH1 uses the same panel /
controller revision / waveform. The Waveshare GH1 is four-color (red/yellow/black/white)
and its public Waveshare driver uses a different command initialization sequence.
We must not copy the UC8253 sequence into GH1 blindly.

## Safe implementation rule

Do **not** implement partial refresh in `zen_editor.py` yet.

Only enable true partial refresh after identifying the controller and waveform for
the exact Waveshare 416x240 RYBW panel, preferably from the supplied panel datasheet,
controller datasheet, or a working driver for the exact panel.

Until then:

- `Ctrl+D` remains a full update.
- `main` remains untouched.
- `another` is the experimental branch.

## Practical Writer Deck direction

Even without partial refresh, the GH1 remains usable as the Writer Deck display.
The current editor already avoids updating the e-paper on every keystroke; the e-paper
is explicitly refreshed with `Ctrl+D`. This is appropriate for a display whose fast
refresh is about 12 s and full refresh is about 20 s.

## Sources

- Waveshare GH1 manual/product documentation
- Waveshare 2025 `epd3in7g.py` and C driver
- Good Display GDEY037Z03 / UC8253 documentation for comparison only
