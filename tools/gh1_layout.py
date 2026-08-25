#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GH1-specific e-paper layout launcher.

Keeps zen_editor.py unchanged and replaces only the e-paper text renderer and
push_to_epaper method at runtime. The GH1 is 416x240, so this layout reserves
the bottom 22 pixels for a small status line and uses 9 text rows above it.

Run through fast_zen_editor.py after importing this module there, or execute
this file directly only as a development helper.
"""

def apply(zen_editor):
    from PIL import Image, ImageDraw, ImageFont
    from datetime import datetime

    original_init_epd = zen_editor.EPaperWriter._init_epd
    original_push = zen_editor.ZenEditor.push_to_epaper

    def _init_epd(self):
        original_init_epd(self)
        if self.ready:
            try:
                self.font = ImageFont.truetype(zen_editor.FONT_PATH, 22)
            except Exception:
                pass

    def _draw(self, lines):
        try:
            self.busy = True
            zen_editor._epaper_log("GH1 layout _draw開始")
            canvas_w, canvas_h = self.epd.height, self.epd.width
            img = Image.new("RGB", (canvas_w, canvas_h), self.epd.WHITE)
            draw = ImageDraw.Draw(img)
            font = self.font
            footer_font = ImageFont.truetype(zen_editor.FONT_PATH, 16)

            # 9本文行。幅は左右10px余白。
            max_width_px = max(canvas_w - 20, 10)
            body_rows = []
            for line in lines:
                body_rows.extend(self._wrap_for_epaper(line, draw, max_width_px))

            body_rows = body_rows[-9:]
            y = 4
            for line in body_rows:
                draw.text((10, y), line, font=font, fill=self.epd.BLACK)
                y += 23

            # 最下段は状態表示。黄色をアクセントにする。
            footer = f"JP {'ON' if getattr(self, '_layout_skk', True) else 'OFF'}  {datetime.now().strftime('%H:%M')}"
            draw.rectangle((0, 218, canvas_w - 1, canvas_h - 1), fill=self.epd.YELLOW)
            draw.text((10, 221), footer, font=footer_font, fill=self.epd.BLACK)

            self.epd.display(self.epd.getbuffer(img))
            zen_editor._epaper_log("GH1 layout _draw完了")
        except Exception as e:
            self.error = str(e)
            zen_editor._epaper_log(f"GH1 layout _draw失敗: {type(e).__name__}: {e}")
        finally:
            self.busy = False

    def _push(self):
        if not self.epaper.enabled:
            return
        visible = 9
        start = max(0, self.cy - visible + 1)
        chunk = self.lines[start:self.cy + 1]
        self.epaper._layout_skk = self.skk_enabled
        self.epaper.request(chunk)

    zen_editor.EPaperWriter._init_epd = _init_epd
    zen_editor.EPaperWriter._draw = _draw
    zen_editor.ZenEditor.push_to_epaper = _push


def main():
    raise SystemExit("Import and call apply(zen_editor) from the Fast writer launcher.")


if __name__ == "__main__":
    main()
