#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zen Editor (prototype) - 自作執筆デック用 CLIエディタ
Python + curses、モードレス(Ctrl主体)キーバインド、e-paper自動反映。

入力はローマ字→ひらがなのライブ変換のみ(skk.py)。漢字変換はCtrl+Gで
ローカルLLM(ai_convert.py、Mac常駐のOllama)にまとめて任せ、そのままGit送信し、
完了後は画面をクリアして次の原稿に移る設計。
"""
import curses
import termios
import sys
import os
import subprocess
import threading
import time
import locale
import unicodedata
from datetime import datetime

import skk
import ai_convert

locale.setlocale(locale.LC_ALL, '')


def display_width(s):
    """日本語などの全角文字は端末上で2マス分の幅を占めるため、
    文字数ではなく実際の表示幅を計算する(カーソル位置合わせ用)。"""
    w = 0
    for ch in s:
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def wrap_line_with_offsets(text, width):
    """1つの論理行(text)を、画面幅(width、表示カラム数)に収まるよう
    複数の表示行に分割する。全角文字は2カラムとして計算する。
    戻り値: [(この表示行がtext内で始まる文字インデックス, 表示行の文字列), ...]
    (textが空文字列でも、必ず1要素は返す)"""
    if width <= 0:
        return [(0, text)]
    rows = []
    current = []
    current_w = 0
    start = 0
    for i, ch in enumerate(text):
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if current_w + cw > width and current:
            rows.append((start, "".join(current)))
            current = []
            current_w = 0
            start = i
        current.append(ch)
        current_w += cw
    rows.append((start, "".join(current)))
    return rows

# ---- パス設定 ----
HOME = os.path.expanduser("~")
INBOX_DIR = os.path.join(HOME, "mynotebook", "00_inbox")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

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
        self.pending_draw_fn = None
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
            self.pending_draw_fn = None

    def request_custom(self, draw_fn):
        """テキスト行ではなく、任意の描画(画像など)をしたい時に使う。
        draw_fn(epd, Image, ImageDraw, ImageFont) を渡すと、バックグラウンド
        スレッド側で呼び出される。draw_fn内で最終的にepd.display(...)まで
        自分で行うこと。"""
        if not self.enabled:
            return
        with self.lock:
            self.pending_draw_fn = draw_fn
            self.pending_lines = None

    def _worker(self):
        if self.enabled:
            self._init_epd()
        while not self.stop_flag:
            lines = None
            draw_fn = None
            with self.lock:
                if self.pending_draw_fn is not None:
                    draw_fn = self.pending_draw_fn
                    self.pending_draw_fn = None
                elif self.pending_lines is not None:
                    lines = self.pending_lines
                    self.pending_lines = None
            if draw_fn is not None:
                try:
                    self.busy = True
                    draw_fn(self.epd, Image, ImageDraw, ImageFont)
                except Exception as e:
                    self.error = str(e)
                finally:
                    self.busy = False
            elif lines is not None:
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
            # 4色パネルのフルカラー画像(シャットダウンロゴ等)の描画は
            # 25秒では終わらないことがあり、タイムアウトすると描画未完了の
            # まま epd.sleep() が呼ばれて亀ロゴが表示されずに終了してしまう。
            # 余裕を持って60秒待つ。
            self.thread.join(timeout=60)
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

            # 「今回実際に変化があったファイル数」を数える(00_inbox内の
            # 総ファイル数ではない)。git addした直後、コミット前の
            # ステージ済み差分がこれにあたる。
            diff = subprocess.run(
                ["git", "-C", inbox_dir, "diff", "--cached", "--name-only"],
                timeout=10, capture_output=True, text=True
            )
            changed_files = [f for f in diff.stdout.splitlines() if f]

            commit = subprocess.run(
                ["git", "-C", inbox_dir, "commit", "-m",
                 f"write: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"],
                timeout=15, capture_output=True, text=True
            )
            if commit.returncode != 0 and "nothing to commit" not in (commit.stdout + commit.stderr):
                detail = (commit.stderr or commit.stdout).strip().splitlines()
                status_cb(f"Git送信失敗(commit): {detail[-1] if detail else commit.returncode}")
                return False

            # 別の場所からの送信でリモートが進んでいることがあるため、
            # pushする前に必ず取り込んでおく(fast-forward失敗の予防)
            pull = subprocess.run(
                ["git", "-C", inbox_dir, "pull", "--no-edit", "--rebase=false"],
                timeout=30, capture_output=True, text=True
            )
            if pull.returncode != 0:
                detail = (pull.stderr or pull.stdout).strip().splitlines()
                status_cb(f"Git送信失敗(pull): {detail[-1] if detail else pull.returncode}")
                return False

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
        if changed_files:
            status_cb(f"Git送信成功: {len(changed_files)}件を新規送信しました")
        else:
            status_cb("Git送信成功(変更なし、リモートと同期済み)")
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

        # ---- 日本語入力(ローマ字→ひらがな)の状態 ----
        # 漢字変換はローカルLLM(ai_convert.py)にCtrl+Gでまとめて任せる方式のため、
        # ここではローマ字→ひらがなのライブ変換だけを担当する。
        self.skk_enabled = False       # Ctrl+Kで切り替え。ONの間はローマ字がその場でひらがなになる
        self.romaji_buf = ""           # 変換待ちのローマ字断片

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
            return True
        except Exception as e:
            self.status = f"保存失敗: {e}"
            return False

    def reset_document(self):
        """今書いている内容をまっさらにして、次の原稿を書き始められる状態にする。"""
        self.lines = [""]
        self.cy = 0
        self.cx = 0
        self.filename = None
        self.dirty = False
        self.undo_stack = []
        self.romaji_buf = ""

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

    # ---- 日本語入力(ローマ字→ひらがな) ----
    def skk_toggle(self):
        self.skk_enabled = not self.skk_enabled
        if not self.skk_enabled:
            self.flush_romaji_buf()
        self.status = f"日本語入力: {'ON' if self.skk_enabled else 'OFF'}"

    def skk_feed(self, ch):
        self.romaji_buf += ch
        kana, remaining = skk.convert_romaji(self.romaji_buf)
        self.romaji_buf = remaining
        if kana:
            self.snapshot()
            for k in kana:
                self.insert_char(k)

    def flush_romaji_buf(self):
        """Tab/Enterなど区切りキーが押された時、保留中のローマ字
        (末尾の確定待ち"n"など)を確定させて挿入する。"""
        if not self.romaji_buf:
            return
        kana, _ = skk.flush_trailing_n(self.romaji_buf)
        if kana:
            self.snapshot()
            self.insert_char(kana)
        self.romaji_buf = ""

    # ---- AI(ローカルLLM)による漢字変換 + Git送信 ----
    def finalize_and_send(self):
        """Ctrl+Gの本体処理。
        1. 保留中のローマ字を確定
        2. まず生の内容(未変換)を保存(AIが失敗しても何も失わないため)
        3. ローカルLLMに全文を渡して漢字仮名交じり文に変換
        4. 変換できたら内容を置き換えて保存し直す
        5. Gitへadd/commit/pull/push
        6. 完了したら画面をまっさらにして次の原稿へ
        """
        if self.skk_enabled:
            self.flush_romaji_buf()

        text = "\n".join(self.lines)
        if not text.strip():
            self.status = "本文が空です"
            return

        self.save(as_new=False)

        self.status = "変換中..."
        self.render()
        try:
            converted = ai_convert.convert_to_kanji(text)
            self.lines = converted.split("\n")
            self.cy = len(self.lines) - 1
            self.cx = len(self.lines[self.cy])
            self.dirty = True
            self.save(as_new=False)
            ai_status = "変換成功"
        except ai_convert.AiConvertError as e:
            ai_status = f"変換失敗(未変換のまま送信): {e}"

        # 変換結果をe-paperにも反映する。モニター無しの本番運用では、
        # これが送信前に内容を確認できる唯一の手段になる。
        self.push_to_epaper()

        self.status = f"{ai_status} / Git送信中..."
        self.render()

        result_holder = {}

        def cb(msg):
            result_holder["msg"] = msg

        GitSync.send(INBOX_DIR, cb)
        final_msg = f"{ai_status} / {result_holder.get('msg', '')}"
        self.status = final_msg
        self.render()
        self.epaper.request([final_msg])
        time.sleep(1.5)  # 結果をひと呼吸見せてから画面をリセットする

        self.reset_document()
        self.status = "新しい原稿を書き始めてください"

    # ---- e-paper反映 ----
    def push_to_epaper(self):
        # モニター無しの本番運用ではcurses側のステータスバーが見えないため、
        # 日本語入力のON/OFF状態だけはe-paper側にも先頭行として必ず含める。
        visible = 11
        start = max(0, self.cy - visible + 1)
        chunk = self.lines[start:self.cy + 1]
        header = f"[日本語入力:{'ON' if self.skk_enabled else 'off'}]"
        self.epaper.request([header] + chunk)

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

    # ---- 起動画面 ----
    def show_splash(self):
        """モニター無し運用でも「準備完了」がわかるよう、起動時に
        簡単なロゴ画面を出し、Enterが押されるまで編集を始めない。
        e-paper側にも同じ内容を一度出しておく。"""
        splash_lines = ["パゴス", "", "Enterで書き始める"]
        self.epaper.request(splash_lines)

        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        start_y = max(0, h // 2 - len(splash_lines) // 2)
        for i, text in enumerate(splash_lines):
            x = max(0, (w - display_width(text)) // 2)
            try:
                self.stdscr.addstr(start_y + i, x, text)
            except curses.error:
                pass
        self.stdscr.refresh()

        while True:
            try:
                ch = self.stdscr.get_wch()
            except curses.error:
                continue
            code = ord(ch) if isinstance(ch, str) and len(ch) == 1 else None
            if ch == curses.KEY_ENTER or code in (10, 13):
                return

    def draw_shutdown_image(self):
        """Ctrl+Qで終了する時、e-paperに亀のマーク入りの終了画面を描く。
        e-paperは双安定(bistable)なので、電源を切っても画像はそのまま
        残り続ける(OLEDの焼き付きとは違う仕組みで、劣化の心配はない)。
        実際の描画・SPI通信はバックグラウンドスレッド側(request_custom)に
        任せる。ここで完了を待つ必要はなく、後続のeditor.shutdown()が
        スレッドの終了(=描画完了)を待ってからepd.sleep()を呼ぶ。"""
        if not self.epaper.enabled:
            return

        def _draw(epd, Image, ImageDraw, ImageFont):
            w, h = epd.height, epd.width  # 描画キャンバスは(240, 416)想定
            img = Image.new('RGB', (w, h), epd.WHITE)
            draw = ImageDraw.Draw(img)
            cx, cy = w // 2, 150
            shell_r = 80

            # 甲羅: 8分割の扇形を赤/黄交互に塗る(4色パネルの色をそのまま活かす)
            n = 8
            for i in range(n):
                start = i * (360 / n) - 90
                end = start + (360 / n)
                color = epd.RED if i % 2 == 0 else epd.YELLOW
                draw.pieslice(
                    [cx - shell_r, cy - shell_r, cx + shell_r, cy + shell_r],
                    start, end, fill=color, outline=epd.BLACK,
                )
            draw.ellipse(
                [cx - shell_r, cy - shell_r, cx + shell_r, cy + shell_r],
                outline=epd.BLACK, width=4,
            )

            # 中心の白丸+羽根ペン
            inner_r = 42
            draw.ellipse(
                [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
                fill=epd.WHITE, outline=epd.BLACK, width=3,
            )
            draw.line([cx - 18, cy + 22, cx + 18, cy - 22], fill=epd.BLACK, width=4)
            draw.polygon(
                [(cx + 18, cy - 22), (cx + 2, cy - 10),
                 (cx - 6, cy - 2), (cx + 6, cy - 6), (cx + 18, cy - 22)],
                fill=epd.BLACK,
            )

            # 頭
            head_r = 16
            draw.ellipse(
                [cx - head_r, cy - shell_r - int(head_r * 1.5),
                 cx + head_r, cy - shell_r + int(head_r * 0.3)],
                fill=epd.WHITE, outline=epd.BLACK, width=3,
            )
            # 4本足
            leg_r = 16
            offs = int(shell_r * 0.75)
            for dx, dy in [(-offs, -offs), (offs, -offs), (-offs, offs), (offs, offs)]:
                draw.ellipse(
                    [cx + dx - leg_r, cy + dy - leg_r, cx + dx + leg_r, cy + dy + leg_r],
                    fill=epd.WHITE, outline=epd.BLACK, width=3,
                )

            # テキスト
            font = ImageFont.truetype(FONT_PATH, 36)
            text = "PAGOS"
            bbox = draw.textbbox((0, 0), text, font=font)
            draw.text(
                (cx - (bbox[2] - bbox[0]) // 2, cy + shell_r + 40),
                text, font=font, fill=epd.BLACK,
            )
            sub_font = ImageFont.truetype(FONT_PATH, 18)
            sub = "電源を切って大丈夫です"
            bbox2 = draw.textbbox((0, 0), sub, font=sub_font)
            draw.text(
                (cx - (bbox2[2] - bbox2[0]) // 2, cy + shell_r + 95),
                sub, font=sub_font, fill=epd.BLACK,
            )

            epd.display(epd.getbuffer(img))

        self.epaper.request_custom(_draw)

    # ---- メインループ ----
    def run(self):
        self.show_splash()
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
                self.draw_shutdown_image()
                break
            elif code == 19:  # Ctrl+S
                self.save(as_new=False)
            elif code == 4:  # Ctrl+D: e-paperの画面更新のみを明示的に行う
                # 通常の文字入力(Enter含む)からは独立させている。日本語入力で
                # Enterの頻度が上がっても、e-paperの重い描画を毎回走らせない
                # ようにするため。
                if self.skk_enabled:
                    self.flush_romaji_buf()
                self.push_to_epaper()
                self.status = "e-paperを更新しました"
            elif code == 14:  # Ctrl+N: 未保存なら保存してから、新規原稿へ(画面クリア)
                if self.skk_enabled:
                    self.flush_romaji_buf()
                if self.dirty:
                    self.save(as_new=False)
                self.reset_document()
                self.status = "新しい原稿を書き始めてください"
            elif code == 7:  # Ctrl+G: 変換 → 保存 → Git送信 → 新規原稿へ
                self.finalize_and_send()
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
            elif code == 11:  # Ctrl+K: 日本語入力(ローマ字→ひらがな)モードの切り替え
                self.skk_toggle()
            elif code == 9:  # Tab
                self.snapshot()
                self.insert_char("\t")
            elif ch == curses.KEY_BACKSPACE or code in (127, 8):
                if self.skk_enabled and self.romaji_buf:
                    self.romaji_buf = self.romaji_buf[:-1]
                else:
                    self.snapshot()
                    self.backspace()
            elif ch == curses.KEY_DC:
                self.snapshot()
                self.delete_forward()
            elif ch == curses.KEY_ENTER or code in (10, 13):
                if self.skk_enabled:
                    self.flush_romaji_buf()
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
            elif self.skk_enabled and isinstance(ch, str) and (
                (ch.isalpha() and ch.islower()) or ch in ("'", "-")
            ):
                self.skk_feed(ch)
            elif self.skk_enabled and ch in (",", "."):
                # 日本語入力中は半角カンマ/ピリオドを句読点に自動変換する
                self.flush_romaji_buf()
                self.snapshot()
                self.insert_char("、" if ch == "," else "。")
            elif isinstance(ch, str) and ch.isprintable():
                if self.skk_enabled and self.romaji_buf:
                    self.flush_romaji_buf()
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
        # e-paperの更新はここでは行わない(Ctrl+Dで明示的に行う)。
        # 日本語入力では変換確定のためにEnterを押す頻度が英語入力より
        # 高くなりがちで、毎回e-paperの重い描画が走ると実用に耐えない。

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
        width = max(1, w - 1)

        # 全論理行を画面幅で折り返し、「表示行」の一覧を作る。
        # 各要素: (元の行番号, その表示行がtext内で始まる文字位置, 表示テキスト)
        display_rows = []
        for li, line in enumerate(self.lines):
            for start, seg in wrap_line_with_offsets(line, width):
                display_rows.append((li, start, seg))

        # カーソルが属する表示行のインデックスを探す(折り返し境界で複数
        # マッチする場合は、後ろ側=次の表示行の先頭を優先する)
        cursor_display_index = 0
        for idx, (li, start, seg) in enumerate(display_rows):
            if li == self.cy and start <= self.cx <= start + len(seg):
                cursor_display_index = idx

        if self.typewriter:
            top = max(0, cursor_display_index - body_h // 2)
        else:
            top = max(0, cursor_display_index - body_h + 1)

        cursor_yx = None
        for i in range(body_h):
            ridx = top + i
            if ridx >= len(display_rows):
                break
            li, start, seg = display_rows[ridx]
            try:
                if ridx == cursor_display_index:
                    # カーソル行だけは「カーソルより前」「カーソルより後」を分けて描画し、
                    # 描画直後の実際の座標をcursesに直接教えてもらう。
                    # (全角文字の表示幅を自前計算すると、ncurses/端末の実際の
                    #  描画幅とズレることがあるため、自前計算より確実)
                    offset = self.cx - start
                    self.stdscr.move(i, 0)
                    self.stdscr.addstr(seg[:offset])
                    cursor_yx = self.stdscr.getyx()
                    self.stdscr.addstr(seg[offset:])
                else:
                    self.stdscr.addstr(i, 0, seg)
            except curses.error:
                pass

        fname = os.path.basename(self.filename) if self.filename else "(未保存)"
        dirty_mark = "*" if self.dirty else ""
        skk_tag = f"[日本語:{'ON' if self.skk_enabled else 'off'}]"
        if self.skk_enabled and self.romaji_buf:
            skk_tag += f"({self.romaji_buf})"
        info = f"{fname}{dirty_mark}  [{self.cy+1}:{self.cx+1}]  {skk_tag}  Ctrl+S保存 Ctrl+D画面更新 Ctrl+N新規原稿 Ctrl+G変換+送信 Ctrl+K日本語 Ctrl+Q終了"
        try:
            self.stdscr.addstr(h - 2, 0, info[:w - 1], curses.A_REVERSE)
            self.stdscr.addstr(h - 1, 0, self.status[:w - 1])
        except curses.error:
            pass

        if cursor_yx is not None:
            self.stdscr.move(*cursor_yx)
        else:
            # フォールバック(通常はここには来ない想定)
            cursor_col = display_width(self.lines[self.cy][:self.cx])
            self.stdscr.move(min(self.cy - top, body_h - 1), min(cursor_col, w - 1))
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
    # シェル側で標準出力をファイルにリダイレクトすると、cursesが端末に
    # 直接アクセスできなくなり初期化自体が失敗する(cbreak() returned ERR等)。
    # そのため出力先は変えず、クラッシュした場合だけこのスクリプト自身が
    # ログファイルに記録する。curses.wrapper()は例外発生時も端末の状態を
    # 元に戻してから例外を外に投げるので、ここで受け取っても画面は壊れない。
    try:
        curses.wrapper(main)
    except Exception:
        import traceback
        crash_log = os.path.join(SCRIPT_DIR, "zen_editor_crash.log")
        with open(crash_log, "a", encoding="utf-8") as f:
            f.write(f"\n--- crash at {datetime.now()} ---\n")
            traceback.print_exc(file=f)
        raise
