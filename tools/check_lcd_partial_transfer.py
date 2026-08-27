#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
「小さい範囲だけ書き換えると、実際にSPI転送も短時間で終わるのか」を
実機で検証するためのツール。

【なぜこれが必要か】
lcd_zen_editor_fast.py の lcd_perf.log は、Python側で mmap(/dev/fb1) に
write()する時間(render/pack/write)は測れるが、これは実際のSPI転送とは
別物。fbtftのdeferred I/Oは、mmapされたページへの書き込みをページフォルト
経由で検知し、write()自体は即座に返る一方、実際にSPI経由でパネルへ
転送するのは後から非同期にカーネル側のワーカーが行う。つまり
「write()呼び出しが速かった」は「パネルへの転送が実際に短時間で
終わった」ことの証明にはならない。

【このツールでやること】
プログラム的な計測(補助データとして表示はする)に頼りきらず、
実際にパネルを目で見て体感速度を比較できるよう、
1. 画面全体を白→黒→白と交互に塗り替える(フル画面更新)を5回
2. 画面の隅の小さな正方形(60x60px)だけを黒→白と交互に塗り替える
   (部分更新)を20回
を順番に行う。理論値では、20MHzのSPIなら480x320の全画面転送
(307200byte)には最低でも約120ms以上かかるはずなので、
「本当に部分転送されているか」は目視でもはっきり分かるはず。

使い方:
    python3 tools/check_lcd_partial_transfer.py

実行中、実機の画面を直接見ながら:
  - フェーズ1(全画面)の白黒切り替えが、パッと切り替わるか、
    それとも一瞬「塗られていく」ような遅延が見えるか
  - フェーズ2(隅の小さい四角)の切り替えが、フェーズ1より
    明らかに速く(ほぼ瞬時に)見えるか
を確認してほしい。同じくらいの速さに見えるなら、部分転送は
機能していない(=フル画面転送が毎回走っている)という結論になる。
"""
import ctypes
import fcntl
import mmap
import os
import struct
import sys
import time

FB = "/dev/fb1"
FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602


def fb_info(fd):
    var = bytearray(160)
    fix = bytearray(80)
    fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var, True)
    fcntl.ioctl(fd, FBIOGET_FSCREENINFO, fix, True)
    x, y, xv, yv, _xo, _yo, bpp, _ = struct.unpack_from("8I", var, 0)
    stride = struct.unpack_from("I", fix, 44)[0]
    return dict(w=x, h=y, bpp=bpp, stride=stride)


WHITE = 0xFFFF
BLACK = 0x0000


def fill_rect(mm, info, x0, y0, x1, y1, color):
    stride = info["stride"]
    row = struct.pack("<" + "H" * (x1 - x0), *([color] * (x1 - x0)))
    for y in range(y0, y1):
        mm.seek(y * stride + x0 * 2)
        mm.write(row)
    mm.flush()


def main():
    if not os.path.exists(FB):
        print(f"{FB} が見つかりません。LCD用のSDカード/設定で起動しているか確認してください")
        sys.exit(1)

    fd = os.open(FB, os.O_RDWR)
    info = fb_info(fd)
    w, h = info["w"], info["h"]
    size = info["stride"] * h
    mm = mmap.mmap(fd, size)

    print(f"フレームバッファ: {w}x{h}, stride={info['stride']}")
    print()
    print("=== フェーズ1: 全画面の白黒切り替え(5回)===")
    print("実機の画面を見ていてください。今から開始します。3秒後...")
    time.sleep(3)

    full_times = []
    for i in range(5):
        color = BLACK if i % 2 == 0 else WHITE
        t0 = time.perf_counter()
        fill_rect(mm, info, 0, 0, w, h, color)
        elapsed = (time.perf_counter() - t0) * 1000
        full_times.append(elapsed)
        print(f"  全画面 塗り替え{i+1}: write()呼び出し {elapsed:.1f}ms")
        time.sleep(0.6)

    print()
    print("=== フェーズ2: 画面隅の小さい四角(60x60px)の切り替え(20回)===")
    print("同じく画面(特に左上の隅)を見ていてください。3秒後...")
    time.sleep(3)

    sq = 60
    partial_times = []
    for i in range(20):
        color = BLACK if i % 2 == 0 else WHITE
        t0 = time.perf_counter()
        fill_rect(mm, info, 0, 0, sq, sq, color)
        elapsed = (time.perf_counter() - t0) * 1000
        partial_times.append(elapsed)
        print(f"  小四角 塗り替え{i+1}: write()呼び出し {elapsed:.1f}ms")
        time.sleep(0.3)

    # 後片付け: 画面を白に戻す
    fill_rect(mm, info, 0, 0, w, h, WHITE)

    mm.close()
    os.close(fd)

    avg_full = sum(full_times) / len(full_times)
    avg_partial = sum(partial_times) / len(partial_times)

    print()
    print("=== 結果(あくまでwrite()呼び出し自体の時間、参考値) ===")
    print(f"全画面   平均: {avg_full:.1f}ms")
    print(f"小四角   平均: {avg_partial:.1f}ms")
    print()
    print("【重要】上の数字はPython側の書き込み時間で、実際のSPI転送")
    print("時間ではありません。判断材料は主に、実機を見ていた時の体感です:")
    print("  - フェーズ2(小四角)が、フェーズ1(全画面)よりはっきり")
    print("    速く・パッと切り替わって見えたなら → 部分転送は機能している")
    print("  - 両方とも同じくらいの遅さ・同じような『塗られていく』感じ")
    print("    だったなら → 毎回フル画面分の転送が走っている(部分転送は")
    print("    効いていない)可能性が高い")


if __name__ == "__main__":
    main()
