#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zen Editor (prototype) - 自作執筆デック用 CLIエディタ
Python + curses、モードレス(Ctrl主体)キーバインド、e-paper自動反映。
"""
import curses
import termios
import sys
import os
import subprocess
import threading
import time
import locale
from datetime import datetime

locale.setlocale(locale.LC_ALL, '')

# ---- パス設定 ----
HOME = os.path.expanduser("~")
INBOX_DIR = os.path.join(HOME, "mynotebook", "00_inbox")

EPD_LIB_DIR = os.path.join(
    HOME, "e-Paper", "E-paper_Separate_Program", "3in7_e-Paper_G",
    "RaspberryPi_JetsonNano", "python", "lib"
)
FONT_PATH = os.path.join(
    HOME, "e-Paper", "E-paper_Separate_Program", "3in7_e-Paper_G",
    "RaspberryPi_JetsonNano", "python", "pic", "Font.ttc"
)
sys.path.append(EPD_LIB_DIR)

os.makedirs(INBOX_DIR, exist_ok=True)

# ---- e-paper (壊れていても起動できるようフォールバック) ----
EPAPER_OK = True
try:
    from waveshare_epd import epd3in7g
    from PIL import Image, ImageDraw, ImageFont
except Exception as e:
    EPAPER_OK = False
    EPAPER_ERR = str(e)


class EPaperWriter:
    """e-paperへの描画をバックグラウンドスレッドで行うクラス。
    タイピングをブロックしないよう、更新要求をキューイングして
    1つ前の描画が終わってから最新の内容を描画する。"""

    def __init__(self):
        self.enabled = EPAPER_OK
        self.epd = None
        self.font = None
        self.lock = threading.Lock()
        self.pending_lines = None
        self.busy = False
        self.stop_flag = False
        self.ready = False
        self.error = None if EPAPER_OK else EPAPER_ERR

        # epd.init()/Clear()は数十秒かかることがあるため、
        # ここ(メインスレッド/起動処理)でやるとUIが起動直後フリーズして見える。
        # 必ずバックグラウンドスレッド側で初期化する。
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _init_epd(self):
        try:
            self.epd = epd3in7g.EPD()
            self.epd.init()
            self.epd.Clear()
            self.font = ImageFont.truetype(FONT_PATH, 24)
            self.ready = True
        except Exception as e:
            self.enabled = False
            self.error = str(e)

    def request(self, lines):
        """描画したい行のリストを渡す(非ブロッキング)。"""
        if not self.enabled:
            return
        with self.lock:
            self.pending_lines = list(lines)

    def _worker(self):
        if self.enabled:
            self._init_epd()
        while not self.stop_flag:
            lines = None
            with self.lock:
                if self.pending_lines is not None:
                    lines = self.pending_lines
                    self.pending_lines = None
            if lines is not None:
                self._draw(lines)
            else:
                time.sleep(0.2)

    def _draw(self, lines):
        try:
            self.busy = True
            img = Image.new('RGB', (self.epd.height, self.epd.width), self.epd.WHITE)
            draw = ImageDraw.Draw(img)
            y = 8
            for line in lines:
                draw.text((8, y), line, font=self.font, fill=self.epd.BLACK)
                y += 30
            self.epd.display(self.epd.getbuffer(img))
        except Exception as e:
            self.error = str(e)
        finally:
            self.busy = False

    def shutdown(self):
        self.stop_flag = True
        if self.thread.is_alive():
            self.thread.join(timeout=25)
        if self.enabled and self.epd:
            try:
                self.epd.sleep()
            except Exception:
                pass


class GitSync:
    @staticmethod
    def is_repo(path):
        try:
            r = subprocess.run(
                ["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=5
            )
            return r.returncode == 0
        except Exception:
            return False

    @staticmethod
    def send(inbox_dir, status_cb):
        if not GitSync.is_repo(inbox_dir):
            status_cb("Gitリポジトリ未設定: 送信スキップ (00_inboxはgit initされていません)")
            return False

        md_files = [f for f in os.listdir(inbox_dir) if f.endswith(".md")]
        if not md_files:
            status_cb("送信対象の.mdファイルがありません")
            return False

        try:
            subprocess.run(["git", "-C", inbox_dir, "add", "."],
                            check=True, timeout=15, capture_output=True, text=True)
            subprocess.run(
                ["git", "-C", inbox_dir, "commit", "-m",
                 f"write: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
                check=True, timeout=15, capture_output=True, text=True
            )
            subprocess.run(["git", "-C", inbox_dir, "push"],
                            check=True, timeout=30, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            detail = (e.stderr or e.stdout or str(e)).strip().splitlines()
            status_cb(f"Git送信失敗: {detail[-1] if detail else e}")
            return False
        except Exception as e:
            status_cb(f"Git送信失敗: {e}")
            return False

        # ファイルは00_inboxに置いたまま(既存のプラグインがデイリーノートへ移動する運用のため)
        status_cb(f"Git送信成功: {len(md_files)}件をpushしました")
        return True


class ZenEditor:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.lines = [""]
        self.cy = 0  # cursor row
        self.cx = 0  # cursor col
        self.filename = None
        self.dirty = False
        self.typewriter = True
        self.status = ""
        self.undo_stack = []
        self.epaper = EPaperWriter()

        curses.curs_set(1)
        stdscr.keypad(True)
        stdscr.nodelay(False)

        if not self.epaper.enabled:
            self.status = f"[e-paper無効: {self.epaper.error}]"

    # ---- 保存 ----
    def new_filename(self):
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        return os.path.join(INBOX_DIR, f"{ts}.md")

    def save(self, as_new=False):
        if self.filename is None or as_new:
            self.filename = self.new_filename()
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines))
            self.dirty = False
            self.status = f"保存しました: {os.path.basename(self.filename)}"
        except Exception as e:
            self.status = f"保存失敗: {e}"

    # ---- undo ----
    def snapshot(self):
        self.undo_stack.append((list(self.lines), self.cy, self.cx))
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            self.status = "これ以上戻れません"
            return
        self.lines, self.cy, self.cx = self.undo_stack.pop()
        self.dirty = True

    # ---- e-paper反映 ----
    def push_to_epaper(self):
        visible = 12
        start = max(0, self.cy - visible + 1)
        chunk = self.lines[start:self.cy + 1]
        self.epaper.request(chunk)

    # ---- 検索 ----
    def search(self):
        query = self.prompt("検索: ")
        if not query:
            return
        for i in range(self.cy, len(self.lines)):
            col = self.lines[i].find(query, self.cx + 1 if i == self.cy else 0)
            if col != -1:
                self.cy, self.cx = i, col
                self.status = f"見つかりました: {i+1}行目"
                return
        for i in range(0, self.cy + 1):
            col = self.lines[i].find(query)
            if col != -1:
                self.cy, self.cx = i, col
                self.status = f"見つかりました(先頭から): {i+1}行目"
                return
        self.status = "見つかりませんでした"

    def prompt(self, message):
        h, w = self.stdscr.getmaxyx()
        curses.echo()
        self.stdscr.move(h - 1, 0)
        self.stdscr.clrtoeol()
        self.stdscr.addstr(h - 1, 0, message)
        curses.curs_set(1)
        s = self.stdscr.getstr(h - 1, len(message)).decode("utf-8", "ignore")
        curses.noecho()
        return s

    # ---- メインループ ----
    def run(self):
        while True:
            self.render()
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                continue

            # get_wch()は制御文字を「int」ではなく「1文字の文字列」として返す
            # (例: Ctrl+Aは 1 ではなく '\x01')。特殊キー(矢印等)はintで返る。
            # そのため、比較用に「文字列なら文字コード、intならNone」を作る。
            code = ord(ch) if isinstance(ch, str) and len(ch) == 1 else None

            if code == 17:  # Ctrl+Q
                if self.dirty:
                    ans = self.prompt("未保存の変更があります。保存して終了しますか？(y/n): ")
                    if ans.lower() == "y":
                        self.save()
                break
            elif code == 19:  # Ctrl+S
                self.save(as_new=False)
            elif code == 14:  # Ctrl+N (新規保存)
                self.save(as_new=True)
            elif code == 7:  # Ctrl+G
                self.status = "Git送信中..."
                self.render()
                GitSync.send(INBOX_DIR, lambda m: setattr(self, "status", m))
            elif code == 6:  # Ctrl+F
                self.search()
            elif code == 20:  # Ctrl+T
                self.typewriter = not self.typewriter
                self.status = f"タイプライタースクロール: {'ON' if self.typewriter else 'OFF'}"
            elif code == 26:  # Ctrl+Z
                self.undo()
            elif code == 1:  # Ctrl+A
                self.cx = 0
            elif code == 5:  # Ctrl+E
                self.cx = len(self.lines[self.cy])
            elif code == 23:  # Ctrl+W
                self.snapshot()
                self.delete_word_backward()
            elif ch == curses.KEY_BACKSPACE or code in (127, 8):
                self.snapshot()
                self.backspace()
            elif ch == curses.KEY_DC:
                self.snapshot()
                self.delete_forward()
            elif ch == curses.KEY_ENTER or code in (10, 13):
                self.snapshot()
                self.newline()
            elif ch == curses.KEY_UP:
                self.move_up()
            elif ch == curses.KEY_DOWN:
                self.move_down()
            elif ch == curses.KEY_LEFT:
                self.move_left()
            elif ch == curses.KEY_RIGHT:
                self.move_right()
            elif isinstance(ch, str) and ch.isprintable():
                self.snapshot()
                self.insert_char(ch)

    # ---- 編集操作 ----
    def insert_char(self, ch):
        line = self.lines[self.cy]
        self.lines[self.cy] = line[:self.cx] + ch + line[self.cx:]
        self.cx += 1
        self.dirty = True

    def backspace(self):
        if self.cx > 0:
            line = self.lines[self.cy]
            self.lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
            self.cx -= 1
            self.dirty = True
        elif self.cy > 0:
            prev_len = len(self.lines[self.cy - 1])
            self.lines[self.cy - 1] += self.lines[self.cy]
            del self.lines[self.cy]
            self.cy -= 1
            self.cx = prev_len
            self.dirty = True

    def delete_forward(self):
        line = self.lines[self.cy]
        if self.cx < len(line):
            self.lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
            self.dirty = True
        elif self.cy < len(self.lines) - 1:
            self.lines[self.cy] += self.lines[self.cy + 1]
            del self.lines[self.cy + 1]
            self.dirty = True

    def delete_word_backward(self):
        line = self.lines[self.cy]
        i = self.cx
        while i > 0 and line[i - 1] == " ":
            i -= 1
        while i > 0 and line[i - 1] != " ":
            i -= 1
        self.lines[self.cy] = line[:i] + line[self.cx:]
        self.cx = i
        self.dirty = True

    def newline(self):
        line = self.lines[self.cy]
        rest = line[self.cx:]
        self.lines[self.cy] = line[:self.cx]
        self.lines.insert(self.cy + 1, rest)
        self.cy += 1
        self.cx = 0
        self.dirty = True
        self.push_to_epaper()

    def move_up(self):
        if self.cy > 0:
            self.cy -= 1
            self.cx = min(self.cx, len(self.lines[self.cy]))

    def move_down(self):
        if self.cy < len(self.lines) - 1:
            self.cy += 1
            self.cx = min(self.cx, len(self.lines[self.cy]))

    def move_left(self):
        if self.cx > 0:
            self.cx -= 1
        elif self.cy > 0:
            self.cy -= 1
            self.cx = len(self.lines[self.cy])

    def move_right(self):
        if self.cx < len(self.lines[self.cy]):
            self.cx += 1
        elif self.cy < len(self.lines) - 1:
            self.cy += 1
            self.cx = 0

    # ---- 画面描画 ----
    def render(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        body_h = h - 2

        if self.typewriter:
            top = max(0, self.cy - body_h // 2)
        else:
            top = max(0, self.cy - body_h + 1)

        for i in range(body_h):
            li = top + i
            if li >= len(self.lines):
                break
            try:
                self.stdscr.addstr(i, 0, self.lines[li][:w - 1])
            except curses.error:
                pass

        fname = os.path.basename(self.filename) if self.filename else "(未保存)"
        dirty_mark = "*" if self.dirty else ""
        info = f"{fname}{dirty_mark}  [{self.cy+1}:{self.cx+1}]  Ctrl+S保存 Ctrl+N新規 Ctrl+G送信 Ctrl+Q終了"
        try:
            self.stdscr.addstr(h - 2, 0, info[:w - 1], curses.A_REVERSE)
            self.stdscr.addstr(h - 1, 0, self.status[:w - 1])
        except curses.error:
            pass

        self.stdscr.move(min(self.cy - top, body_h - 1), min(self.cx, w - 1))
        self.stdscr.refresh()

    def shutdown(self):
        self.epaper.shutdown()


def disable_flow_control():
    """Ctrl+S / Ctrl+Q がXON/XOFFに奪われないようにする"""
    try:
        fd = sys.stdin.fileno()
        attrs = termios.tcgetattr(fd)
        attrs[0] = attrs[0] & ~termios.IXON & ~termios.IXOFF
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except Exception:
        pass


def main(stdscr):
    # 順序が重要: curses.raw()が内部でtermiosを上書きするため、
    # フロー制御(IXON/IXOFF)の無効化は必ずcurses.raw()の"後"に行う。
    # (先にやると、curses.raw()の内部処理で設定が巻き戻されてしまう)
    curses.raw()
    disable_flow_control()
    editor = ZenEditor(stdscr)
    try:
        editor.run()
    finally:
        editor.shutdown()


if __name__ == "__main__":
    curses.wrapper(main)
