#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ひらがな主体の文章を、自然な漢字仮名交じり文に変換してもらう。

2つのバックエンドを切り替え可能:
- "ollama": Mac上に常駐しているローカルLLM。プライベートな内容でも外部に
  送らず、同じLAN内だけで完結する。ただし7Bクラスのモデルでは変換精度に
  限界があり、稀に単語自体を書き換えてしまう(ハルシネーション)ことがある。
- "gemini": Google Gemini API(クラウド)。精度は高いが、文章がGoogleの
  サーバーに送信される。**本当にプライベートな内容を書く時は使わないこと。**

AI_BACKENDの値を書き換えるだけで切り替えられる。
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime

# モニター無しの実機でも、後からSSHで原因を確認できるよう、
# 変換の成功/失敗をこのログファイルに必ず記録する。
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_convert.log")


def _log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass

AI_BACKEND = "gemini"  # "ollama" または "gemini"

# ---- Ollama(ローカルLLM)設定 ----
OLLAMA_HOST = "192.168.1.139"
OLLAMA_PORT = 11434
OLLAMA_MODEL = "qwen2.5:7b"

# ---- Gemini(クラウドAPI)設定 ----
# APIキーは公開リポジトリにコミットされるこのファイルには書かず、
# 環境変数から読む(~/.bashrc に export GEMINI_API_KEY="..." を追加すること)。
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-3.5-flash"

TIMEOUT_SEC = 45

# Qwen系モデルは中国語にも強いため、単に「漢字に変換して」とだけ指示すると
# 簡体字(中国語)が混ざることがある。また、モデルによっては「自然にする」
# という指示だけだと、数字や単語そのものを別の内容に書き換えてしまう
# (ハルシネーション)ことがある。system側で「表記変換以外は一切禁止」と
# 強く縛る。
SYSTEM_PROMPT = (
    "あなたは日本語の文章の表記だけを変換する機械的な変換ツールです。文章の意味や"
    "内容を理解したり、書き直したり、要約したりしてはいけません。あなたの仕事は"
    "「ひらがなで書かれた単語を、対応する常用漢字に置き換える」ことだけです。\n"
    "厳守事項:\n"
    "- 単語・数字・固有名詞は一切変更しないでください。元の文章にある数字や単語を"
    "別の数字・単語に書き換えることは絶対に禁止です(例: 「4色」を「4週間」にする"
    "ような変更は重大な誤りです)。\n"
    "- 出力は日本語(常用漢字・ひらがな・カタカナ)のみです。中国語(簡体字・繁体字)"
    "の字体や単語は一切使用しないでください(例: 「台風」であり「台风」ではない)。\n"
    "- 文の順番、改行位置、句読点、言い回しは元の文章から一切変えないでください。\n"
    "- 変換後の文章だけを出力し、説明・前置き・引用符・コードブロックは一切"
    "つけないでください。"
)


class AiConvertError(Exception):
    pass


def convert_to_kanji(text):
    """textをAIで漢字仮名交じり文に変換する。
    失敗した場合はAiConvertErrorを投げる(呼び出し側でtry/exceptすること)。"""
    if not text.strip():
        return text

    _log(f"開始 backend={AI_BACKEND} 入力{len(text)}文字: {text[:50]!r}")
    try:
        if AI_BACKEND == "gemini":
            result = _convert_via_gemini(text)
        else:
            result = _convert_via_ollama(text)
        cleaned = _sanity_check_and_clean(text, result)
        _log(f"成功 出力{len(cleaned)}文字: {cleaned[:50]!r}")
        return cleaned
    except AiConvertError as e:
        _log(f"失敗: {e}")
        raise
    except Exception as e:
        _log(f"想定外の例外: {type(e).__name__}: {e}")
        raise AiConvertError(f"想定外のエラー: {e}")


def _sanity_check_and_clean(text, result):
    if not result:
        raise AiConvertError("AIから空の応答が返ってきました")

    # 漢字化すると文字数は減る方向(ひらがな複数文字→漢字1文字)なのが普通。
    # 逆に大きく増えていたり、極端に短くなっていたりする場合は、意味不明な
    # 単語を創作した(ハルシネーション)可能性が高いので、変換前の文章に戻す。
    if len(result) > len(text) * 1.5 or len(result) < len(text) * 0.4:
        raise AiConvertError(
            f"AIの出力が不自然な長さでした(元{len(text)}文字→AI後{len(result)}文字)。"
            "内容がおかしい可能性があるため未変換のまま送信します"
        )

    # AIが前置きの引用符やコードフェンスを付けてしまった場合の簡易クリーンアップ
    if result.startswith("```"):
        result = result.strip("`").strip()
    if len(result) >= 2 and result[0] in "「\"" and result[-1] in "」\"":
        result = result[1:-1].strip()

    return result


def _convert_via_ollama(text):
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "stream": False,
        # temperatureが高い(Ollamaのデフォルトは0.8)と、変換のはずなのに
        # 無関係な単語を創作してしまうことがあったため大きく下げる。
        "options": {"temperature": 0.1, "top_p": 0.9},
    }).encode("utf-8")

    url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        raise AiConvertError(f"Ollamaに接続できません({OLLAMA_HOST}:{OLLAMA_PORT}): {e}")
    except Exception as e:
        raise AiConvertError(f"Ollama変換中にエラー: {e}")

    return body.get("message", {}).get("content", "").strip()


def _convert_via_gemini(text):
    if not GEMINI_API_KEY:
        raise AiConvertError(
            "GEMINI_API_KEYが設定されていません。~/.bashrcに"
            'export GEMINI_API_KEY="..." を追加してください'
        )

    payload = json.dumps({
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "temperature": 0.1,
            # このモデルは内部で「思考」してから答えるが、単純な表記変換には
            # 不要なうえ、応答の構造が複雑になって取り出しにくくなるため無効化する。
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode("utf-8")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise AiConvertError(f"Gemini APIエラー({e.code}): {detail[:200]}")
    except urllib.error.URLError as e:
        raise AiConvertError(f"Geminiに接続できません: {e}")
    except Exception as e:
        raise AiConvertError(f"Gemini変換中にエラー: {e}")

    try:
        parts = body["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        raise AiConvertError(f"Geminiの応答形式が想定外でした: {body}")

    # partsが複数ある場合、"thought": true の部分(思考過程)は答えではないので
    # 飛ばし、実際のテキストが入っている部分だけをつなげる。
    texts = [
        p["text"] for p in parts
        if isinstance(p, dict) and p.get("text") and not p.get("thought")
    ]
    if not texts:
        raise AiConvertError(f"Geminiの応答にテキストが含まれていませんでした: {body}")
    return "".join(texts).strip()
