#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V3(OSOYOO 3.5インチSPI LCD, 480x320)用の起動スプラッシュ画像を生成する。
電子ペーパー版と違いフルカラー・即時描画が可能なので、e-paper版の
シャットダウンロゴ(zen_editor.py の draw_shutdown_image)と同じ亀モチーフを
フルカラーで描き直す。

生成した splash.png を、起動時に fbi 等でフレームバッファに表示し、
何かキーが押されたら消してX11(mousepad+fcitx5-mozc)を起動する運用を想定。

使い方:
    python3 make_splash.py
    → 同じディレクトリに splash.png (480x320) が生成される
"""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 480, 320
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/vlgothic/VL-PGothic-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def main():
    img = Image.new("RGB", (W, H), (250, 248, 240))  # 生成り色の背景
    draw = ImageDraw.Draw(img)

    cx, cy = W // 2, H // 2 - 20
    shell_r = 78

    # 甲羅: 8分割の扇形をグリーン系2色で交互に(ガラパゴスをイメージした配色)
    n = 8
    colors = [(46, 125, 50), (129, 199, 132)]  # 濃い緑 / 明るい緑
    for i in range(n):
        start = i * (360 / n) - 90
        end = start + (360 / n)
        color = colors[i % 2]
        draw.pieslice(
            [cx - shell_r, cy - shell_r, cx + shell_r, cy + shell_r],
            start, end, fill=color, outline=(27, 60, 28),
        )
    draw.ellipse(
        [cx - shell_r, cy - shell_r, cx + shell_r, cy + shell_r],
        outline=(27, 60, 28), width=3,
    )

    # 中心の白丸+羽根ペン(オレンジ系のアクセント)
    inner_r = 40
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill=(255, 253, 245), outline=(27, 60, 28), width=2,
    )
    draw.line([cx - 17, cy + 21, cx + 17, cy - 21], fill=(230, 126, 34), width=4)
    draw.polygon(
        [(cx + 17, cy - 21), (cx + 2, cy - 9),
         (cx - 6, cy - 2), (cx + 6, cy - 6), (cx + 17, cy - 21)],
        fill=(211, 84, 0),
    )

    # 頭・4本足(甲羅と同系色)
    head_r = 15
    draw.ellipse(
        [cx - head_r, cy - shell_r - int(head_r * 1.5),
         cx + head_r, cy - shell_r + int(head_r * 0.3)],
        fill=(129, 199, 132), outline=(27, 60, 28), width=2,
    )
    leg_r = 14
    offs = int(shell_r * 0.75)
    for dx, dy in [(-offs, -offs), (offs, -offs), (-offs, offs), (offs, offs)]:
        draw.ellipse(
            [cx + dx - leg_r, cy + dy - leg_r, cx + dx + leg_r, cy + dy + leg_r],
            fill=(129, 199, 132), outline=(27, 60, 28), width=2,
        )

    font_path = find_font()
    title_font = ImageFont.truetype(font_path, 40) if font_path else ImageFont.load_default()
    sub_font = ImageFont.truetype(font_path, 18) if font_path else ImageFont.load_default()

    title = "パゴス"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    draw.text(
        (cx - (bbox[2] - bbox[0]) // 2, cy + shell_r + 22),
        title, font=title_font, fill=(27, 60, 28),
    )

    sub = "Enterで書き始める"
    bbox2 = draw.textbbox((0, 0), sub, font=sub_font)
    draw.text(
        (cx - (bbox2[2] - bbox2[0]) // 2, H - 32),
        sub, font=sub_font, fill=(90, 90, 90),
    )

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "splash.png")
    img.save(out_path)
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
