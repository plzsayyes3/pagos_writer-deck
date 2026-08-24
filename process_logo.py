#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任意のロゴ画像を、電子ペーパー(4色パネル: 白/黒/赤/黄)用の logo.png に
加工するツール。logo.pngを別の画像に差し替えたくなった時に再利用できる。

1. 余白をトリミング
2. 240x416(縦長、e-paperの描画キャンバスサイズ)に収まるようリサイズ
3. 各ピクセルを4色パネルの実際の色のうち最も近い色に丸め込む
   (JPEG圧縮によるノイズ・アンチエイリアスのグラデーションを除去し、
   パネルで正しく発色するようにするため)

使い方:
    python3 process_logo.py 入力画像パス [出力パス=logo.png]
"""
from PIL import Image
import sys
import os

CANVAS_W, CANVAS_H = 240, 416

PALETTE = [
    (0, 0, 0),        # BLACK
    (255, 255, 255),  # WHITE
    (255, 0, 0),      # RED
    (255, 255, 0),    # YELLOW
]


def nearest_palette_color(px):
    r, g, b = px[:3]
    best = None
    best_dist = None
    for pr, pg, pb in PALETTE:
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if best_dist is None or d < best_dist:
            best_dist = d
            best = (pr, pg, pb)
    return best


def autocrop_white(img, threshold=245):
    """ほぼ白い外周部分を切り落とす。"""
    rgb = img.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    def row_is_white(y):
        return all(min(px[x, y][:3]) >= threshold for x in range(w))

    def col_is_white(x):
        return all(min(px[x, y][:3]) >= threshold for y in range(h))

    top = 0
    while top < h and row_is_white(top):
        top += 1
    bottom = h - 1
    while bottom > top and row_is_white(bottom):
        bottom -= 1
    left = 0
    while left < w and col_is_white(left):
        left += 1
    right = w - 1
    while right > left and col_is_white(right):
        right -= 1

    margin = 6
    top = max(0, top - margin)
    left = max(0, left - margin)
    bottom = min(h - 1, bottom + margin)
    right = min(w - 1, right + margin)
    return img.crop((left, top, right + 1, bottom + 1))


def main():
    in_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "logo.png"
    )

    img = Image.open(in_path).convert("RGB")
    img = autocrop_white(img)

    scale = min(CANVAS_W / img.width, CANVAS_H / img.height)
    new_w = max(1, int(img.width * scale))
    new_h = max(1, int(img.height * scale))
    resized = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), (255, 255, 255))
    ox = (CANVAS_W - new_w) // 2
    oy = (CANVAS_H - new_h) // 2
    canvas.paste(resized, (ox, oy))

    px = canvas.load()
    for y in range(CANVAS_H):
        for x in range(CANVAS_W):
            px[x, y] = nearest_palette_color(px[x, y])

    canvas.save(out_path)
    print(f"saved: {out_path} ({CANVAS_W}x{CANVAS_H})")


if __name__ == "__main__":
    main()
