# another: GH1 partial-refresh investigation

This branch is for Raspberry Pi 3 + Waveshare 3.7inch e-Paper HAT+ (G).

## Current state

`zen_editor.py` currently calls `epd.display(...)`, which is a full-screen update.
It does **not** perform partial refresh.

The official Waveshare Python driver currently installed by the project is the
2025 `epd3in7g.py`. Its public API contains `display()` and `init_Fast()`, but no
`displayPartial()` method. The official C driver likewise exposes full display
and fast initialization, but no partial-display function.

Waveshare's current product page does not mark the 3.7inch HAT+ (G) as a
partial-refresh product, even though the GH1 manual/partner documentation
contains FAQ text discussing partial-refresh behavior. Therefore we should
not fake a partial-refresh implementation by simply renaming `display()`.

## Safe next step on the Pi

Run:

```bash
cd ~/pagos_writer-deck
git checkout another
git pull
python3 tools/check_gh1_refresh.py
```

The script performs no display update. It only reports which refresh methods
are actually present in the driver installed on the Pi.

## Implementation rule

Only enable true partial refresh after we have identified the controller
sequence/API for this exact 416x240 four-color panel. A partial-refresh
implementation must also keep track of when a full refresh is required.

Until then, `Ctrl+D` remains a full update. This keeps the hardware safe while
we experiment.
