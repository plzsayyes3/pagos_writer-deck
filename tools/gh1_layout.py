#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GH1-specific e-paper layout launcher.

Keeps zen_editor.py unchanged and replaces only the e-paper text renderer and
push_to_epaper method at runtime. The GH1 is 416x240, so the writer uses nine
text rows plus one compact status row at the bottom.

Status row is fixed into three zones:
    left   : character count
    center : filename or 未保存
    right  : HH:MM
"""

def apply(zen_editor):
    from PIL import Image, ImageDraw, ImageFont
    from datetime import datetime
    import os

    original_init_epd = zen_editor.EPaperWriter._init_epd

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

            # 9本文行。最下段をステータスバーとして確保する。
            max_width_px = max(canvas_w - 20, 10)
            body_rows = []
            for line in lines:
                body_rows.extend(self._wrap_for_epaper(line, draw, max_width_px))

            body_rows = body_rows[-9:]
            y = 4
            for line in body_rows:
                draw.text((10, y), line, font=font, fill=self.epd.BLACK)
                y += 23

            editor = getattr(self, "_layout_editor", None)
            if editor is not None:
                text = "\n".join(editor.lines)
                char_count = len(text.replace("\n", ""))
                if editor.filename:
                    filename = os.path.basename(editor.filename)
                else:
                    filename = "未保存"
            else:
                char_count = sum(len(line) for line in lines)
                filename = "未保存"

            # 固定3分割: 左=文字数 / 中央=ファイル名または未保存 / 右=時刻
            draw.rectangle((0, 218, canvas_w - 1, canvas_h - 1), fill=self.epd.BLACK)
            footer_y = 221
            left = f"{char_count}字"
            right = datetime.now().strftime("%H:%M")

            draw.text((10, footer_y), left, font=footer_font, fill=self.epd.WHITE)

            filename_bbox = draw.textbbox((0, 0), filename, font=footer_font)
            filename_w = filename_bbox[2] - filename_bbox[0]
            filename_x = max(10, (canvas_w - filename_w) // 2)
            draw.text((filename_x, footer_y), filename, font=footer_font, fill=self.epd.WHITE)

            right_bbox = draw.textbbox((0, 0), right, font=footer_font)
            right_w = right_bbox[2] - right_bbox[0]
            right_x = max(10, canvas_w - right_w - 10)
            draw.text((right_x, footer_y), right, font=footer_font, fill=self.epd.WHITE)

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
        self.epaper._layout_editor = self
        self.epaper.request(chunk)

    zen_editor.EPaperWriter._init_epd = _init_epd
    zen_editor.EPaperWriter._draw = _draw
    zen_editor.ZenEditor.push_to_epaper = _push


def main():
    raise SystemExit("Import and call apply(zen_editor) from the Fast writer launcher.")


if __name__ == "__main__":
    main()
