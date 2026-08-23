#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mozc_emacs_helper を GUI 無しで直接操作し、ひらがな文字列を「変換候補の
先頭(=第一候補)」で機械的に確定させて漢字仮名交じり文に変換するモジュール。

背景: GUI(X11+openbox+fcitx5-mozc)実験で、mozcのローカル変換エンジンが
このRaspberry Pi上で実際に動くことは確認できた。ただしfcitx5の候補選択UI
そのものは電子ペーパーには乗せられない(全画面書き換え・低速のため)。
そこで、候補選択UIを介さず、mozcの変換エンジンだけを「常に第一候補で
確定する」設定で直接叩くことで、Gemini API(クラウド・要ネット・要APIキー)
の代わりにローカル・オフラインで漢字変換を行うことを狙う。

【重要】このファイルは実機(Raspberry Pi)上で動作検証できていない状態で
書かれた。mozc_emacs_helperとのS式通信プロトコルは、以下の一次情報を
もとに実装している:
  - mozc本体のsrc/unix/emacs/mozc.el (Emacs用のフロントエンド実装)
  - コマンド例: (EVENT_ID CreateSession) / (EVENT_ID SendKey SESSION_ID KEY)
    / (EVENT_ID DeleteSession SESSION_ID)
  - 応答はS式のalist形式で、output以下にpreedit/candidates/resultが入る
ただし応答の正確なネスト構造(alistのキー名・階層)までは一次情報から
確認しきれなかったため、パース部分は「木構造のどこにあっても目的のタグを
探し出す」形の防御的な実装にしてある(find_first関数)。

このファイル単体でCLIテストできるようにしてある(下のif __name__ブロック)。
実機で以下を試して、動くか・ログに何が出るか確認してほしい:

    python3 mozc_convert.py "きょうはいいてんきですね"

失敗する場合は mozc_convert.log に生の送受信内容が全て記録されるので、
それを見ればどこがズレているか(応答の構造など)が分かり、パース部分
(find_firstで探しているタグ名)だけ直せば動くようにしてある。

前提: emacs-mozc-bin (または mozc_emacs_helper を含むパッケージ) が
インストールされていること。
    sudo apt install -y emacs-mozc-bin
または
    sudo apt search mozc
でパッケージ名を確認すること(ディストリのバージョンにより名前が違うことがある)。
"""
import subprocess
import os
import shutil
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mozc_convert.log")
HELPER_BIN = "mozc_emacs_helper"
RECV_TIMEOUT_SEC = 5


def _log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


class MozcConvertError(Exception):
    pass


# ---------------------------------------------------------------------------
# S式(S-expression)の最小限のパーサー。
# mozc_emacs_helperとの通信はLisp形式のS式で行われるため自前で実装している。
# ローカルでの単体テスト(sexp_test.py相当のロジック)で動作確認済み。
# ---------------------------------------------------------------------------

def _tokenize(s):
    tokens = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
            continue
        if c in "()":
            tokens.append(c)
            i += 1
            continue
        if c == "'":
            tokens.append("'")
            i += 1
            continue
        if c == '"':
            j = i + 1
            buf = []
            while j < n and s[j] != '"':
                if s[j] == "\\" and j + 1 < n:
                    buf.append(s[j + 1])
                    j += 2
                else:
                    buf.append(s[j])
                    j += 1
            tokens.append(("str", "".join(buf)))
            i = j + 1
            continue
        j = i
        while j < n and s[j] not in " \t\r\n()\"'":
            j += 1
        tokens.append(("atom", s[i:j]))
        i = j
    return tokens


def _parse(tokens):
    def _p(pos):
        if pos >= len(tokens):
            raise MozcConvertError("S式のパースに失敗(トークン不足)")
        tok = tokens[pos]
        if tok == "(":
            lst = []
            pos += 1
            while pos < len(tokens) and tokens[pos] != ")":
                val, pos = _p(pos)
                lst.append(val)
            return lst, pos + 1
        elif tok == "'":
            return _p(pos + 1)
        elif isinstance(tok, tuple) and tok[0] == "str":
            return tok[1], pos + 1
        elif isinstance(tok, tuple) and tok[0] == "atom":
            a = tok[1]
            if a == "nil":
                return [], pos + 1
            try:
                return int(a), pos + 1
            except ValueError:
                return a, pos + 1
        raise MozcConvertError(f"S式のパースに失敗(想定外トークン): {tok}")

    val, _ = _p(0)
    return val


def parse_sexp(s):
    return _parse(_tokenize(s))


def find_first(tree, tag):
    """treeの中を再帰的に探索し、先頭要素がtagに一致する最初の部分リストを
    見つけて値を返す。(tag . value)、(tag value)、(tag v1 v2...)いずれの
    形にも対応する。応答の正確なネスト構造が分からなくても動くための保険。"""
    if isinstance(tree, list):
        if len(tree) >= 1 and tree[0] == tag:
            rest = tree[1:]
            if len(rest) == 2 and rest[0] == ".":
                return rest[1]
            if len(rest) == 1:
                return rest[0]
            return rest if rest else None
        for item in tree:
            found = find_first(item, tag)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------------------
# mozc_emacs_helper とのやり取り
# ---------------------------------------------------------------------------

class MozcSession:
    """mozc_emacs_helperプロセスを1つ起動し、複数行の変換をまとめて処理する。
    with文で使う(終了時に必ずプロセスを閉じる)。"""

    def __init__(self):
        self.proc = None
        self.event_id = 0

    def __enter__(self):
        if shutil.which(HELPER_BIN) is None:
            raise MozcConvertError(
                f"{HELPER_BIN} が見つかりません。"
                "emacs-mozc-bin等のパッケージがインストールされているか確認してください"
            )
        self.proc = subprocess.Popen(
            [HELPER_BIN],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self

    def __exit__(self, *exc):
        if self.proc:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
            try:
                self.proc.terminate()
                self.proc.wait(timeout=3)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    def _next_event_id(self):
        self.event_id += 1
        return self.event_id

    @staticmethod
    def _format_arg(a):
        # space/enter等のシンボル、セッションID(int)はそのまま。
        # それ以外の文字列(ひらがな1文字など)はダブルクオートで囲む。
        if isinstance(a, str) and a not in ("space", "enter", "nil"):
            escaped = a.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return str(a)

    def _send(self, *args):
        eid = self._next_event_id()
        formatted = " ".join(self._format_arg(a) for a in args)
        line = f"({eid} {formatted})"
        _log(f"送信: {line}")
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        return eid

    def _recv(self):
        line = self.proc.stdout.readline()
        _log(f"受信: {line.strip()!r}")
        if not line:
            stderr = ""
            try:
                stderr = self.proc.stderr.read(2000)
            except Exception:
                pass
            raise MozcConvertError(
                f"mozc_emacs_helperから応答がありません(プロセス終了の可能性)。"
                f" stderr: {stderr}"
            )
        return parse_sexp(line)

    def create_session(self):
        self._send("CreateSession")
        resp = self._recv()
        session_id = find_first(resp, "emacs-session-id")
        if session_id is None:
            raise MozcConvertError(f"セッションIDが取得できませんでした: {resp}")
        return session_id

    def send_key(self, session_id, key):
        self._send("SendKey", session_id, key)
        return self._recv()

    def delete_session(self, session_id):
        try:
            self._send("DeleteSession", session_id)
            self._recv()
        except Exception:
            pass

    def convert_line(self, hiragana_line):
        """1行分のひらがな文字列を、mozcの第一候補選択で漢字仮名交じり文に
        変換する。ドキュメント化されている通信例に忠実に、1文字ずつ
        SendKeyする(複数文字を1回のSendKeyで送れるかは未確認のため)。"""
        if not hiragana_line.strip():
            return hiragana_line

        session_id = self.create_session()
        try:
            for ch in hiragana_line:
                self.send_key(session_id, ch)
            self.send_key(session_id, "space")  # 変換(第一候補がハイライトされる想定)
            resp = self.send_key(session_id, "enter")  # 確定

            result = find_first(resp, "result")
            if isinstance(result, list):
                # (result (type . string) (value . "...")) のような
                # ネストになっている場合、その中からvalueを探す
                value = find_first(result, "value")
                if value is not None:
                    result = value
            if not isinstance(result, str) or not result:
                # resultで取れなければpreeditも試す(保険)
                pre = find_first(resp, "preedit")
                if isinstance(pre, str) and pre:
                    result = pre
                else:
                    raise MozcConvertError(f"変換結果を取得できませんでした。応答: {resp}")
            return result
        finally:
            self.delete_session(session_id)


def convert_to_kanji_via_mozc(text):
    """textを行ごとに分割し、各行をmozc_emacs_helper経由で第一候補選択方式
    で漢字仮名交じり文に変換する。1行でも失敗したら例外を投げ、呼び出し側
    (ai_convert.py)で他方式へのフォールバックを促す。"""
    lines = text.split("\n")
    converted_lines = []
    _log(f"=== 変換開始: {len(lines)}行 ===")
    with MozcSession() as sess:
        for line in lines:
            try:
                converted_lines.append(sess.convert_line(line))
            except Exception as e:
                _log(f"行変換失敗: {line!r}: {e}")
                raise MozcConvertError(f"mozc変換中にエラー: {e}")
    result = "\n".join(converted_lines)
    _log(f"=== 変換完了: {result[:80]!r} ===")
    return result


if __name__ == "__main__":
    # 実機での動作確認用の簡易CLIテスト。
    # 使い方: python3 mozc_convert.py "きょうはいいてんきですね"
    import sys

    test_text = sys.argv[1] if len(sys.argv) > 1 else "きょうはいいてんきですね"
    print(f"入力: {test_text}")
    try:
        result = convert_to_kanji_via_mozc(test_text)
        print(f"結果: {result}")
    except MozcConvertError as e:
        print(f"失敗: {e}")
        print(f"詳細は {LOG_PATH} を確認してください")
