#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
電源電圧・スロットリング監視ログスクリプト。
vcgencmd get_throttled と measure_temp を定期的にサンプリングして
~/power_log.csv に記録する。

throttledのビット意味:
  bit0  : 現在電圧不足
  bit1  : 現在ARM周波数が制限されている
  bit2  : 現在スロットリング中
  bit3  : 現在ソフト温度制限が働いている
  bit16 : 起動後、電圧不足が一度でも発生した
  bit17 : 起動後、周波数制限が一度でも発生した
  bit18 : 起動後、スロットリングが一度でも発生した
  bit19 : 起動後、ソフト温度制限が一度でも発生した
"""
import subprocess
import time
import os
from datetime import datetime

LOG_PATH = os.path.expanduser("~/power_log.csv")
INTERVAL_SEC = 10

FLAG_BITS = {
    0: "under_voltage_now",
    1: "freq_capped_now",
    2: "throttled_now",
    3: "temp_limit_now",
    16: "under_voltage_occurred",
    17: "freq_capped_occurred",
    18: "throttled_occurred",
    19: "temp_limit_occurred",
}


def get_throttled():
    try:
        out = subprocess.run(
            ["vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        # 例: "throttled=0x50005"
        return int(out.split("=")[1], 16)
    except Exception:
        return None


def get_temp():
    try:
        out = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        # 例: "temp=45.0'C"
        return out.split("=")[1].replace("'C", "")
    except Exception:
        return ""


def decode(value):
    if value is None:
        return {name: "" for name in FLAG_BITS.values()}
    return {name: str(int(bool(value & (1 << bit)))) for bit, name in FLAG_BITS.items()}


def main():
    is_new = not os.path.exists(LOG_PATH)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        if is_new:
            header = ["timestamp", "raw_hex", "temp_c"] + list(FLAG_BITS.values())
            f.write(",".join(header) + "\n")
            f.flush()

        prev_value = None
        while True:
            value = get_throttled()
            temp = get_temp()
            flags = decode(value)
            raw_hex = hex(value) if value is not None else ""
            row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), raw_hex, temp] + \
                  [flags[n] for n in FLAG_BITS.values()]
            f.write(",".join(row) + "\n")
            f.flush()

            # 状態が変化した瞬間だけ分かりやすく標準出力にも出す(systemdのjournalログ用)
            if value != prev_value:
                active = [n for n in FLAG_BITS.values() if flags[n] == "1"]
                print(f"[{row[0]}] throttled={raw_hex} temp={temp}C -> "
                      f"{', '.join(active) if active else 'normal'}")
            prev_value = value

            time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    main()
