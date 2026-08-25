#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ローマ字 -> ひらがな 変換(SKK方式の名残の入力ロジックのみ)。

設計の経緯: 当初はSKK辞書(SKK-JISYO.L)を使った単語単位の候補選択方式を
実装していたが、電子ペーパー(全画面書き換え・低速)には向かないと判断し、
辞書引き・候補選択の仕組みは廃止した。今はローマ字のライブ変換のみを担当し、
実際の漢字変換はローカルLLM(ai_convert.py)にまとめて任せる方式に変更している。
"""

# ---------------------------------------------------------------------------
# ローマ字 -> ひらがな 変換テーブル
# ---------------------------------------------------------------------------
# 3文字(拗音・小書き文字)を先にマッチさせ、次に2文字、最後に1文字を試す。
ROMAJI_3 = {
    "kya": "きゃ", "kyu": "きゅ", "kyo": "きょ",
    "gya": "ぎゃ", "gyu": "ぎゅ", "gyo": "ぎょ",
    "sha": "しゃ", "shu": "しゅ", "sho": "しょ",
    "sya": "しゃ", "syu": "しゅ", "syo": "しょ",
    "zya": "じゃ", "zyu": "じゅ", "zyo": "じょ",
    "cha": "ちゃ", "chu": "ちゅ", "cho": "ちょ",
    "tya": "ちゃ", "tyu": "ちゅ", "tyo": "ちょ",
    "dya": "ぢゃ", "dyu": "ぢゅ", "dyo": "ぢょ",
    "nya": "にゃ", "nyu": "にゅ", "nyo": "にょ",
    "hya": "ひゃ", "hyu": "ひゅ", "hyo": "ひょ",
    "bya": "びゃ", "byu": "びゅ", "byo": "びょ",
    "pya": "ぴゃ", "pyu": "ぴゅ", "pyo": "ぴょ",
    "mya": "みゃ", "myu": "みゅ", "myo": "みょ",
    "rya": "りゃ", "ryu": "りゅ", "ryo": "りょ",
    "xtu": "っ", "ltu": "っ", "xtsu": "っ", "ltsu": "っ",
    "xya": "ゃ", "xyu": "ゅ", "xyo": "ょ",
    "lya": "ゃ", "lyu": "ゅ", "lyo": "ょ",
    "shi": "し", "chi": "ち", "tsu": "つ", "ji": "じ",
}
ROMAJI_2 = {
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "sa": "さ", "si": "し", "su": "す", "se": "せ", "so": "そ",
    "za": "ざ", "zi": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "ta": "た", "ti": "ち", "tu": "つ", "te": "て", "to": "と",
    "da": "だ", "di": "ぢ", "du": "づ", "de": "で", "do": "ど",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "hu": "ふ", "he": "へ", "ho": "ほ", "fu": "ふ",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "wa": "わ", "wo": "を",
    "ja": "じゃ", "ju": "じゅ", "jo": "じょ",
    "xa": "ぁ", "xi": "ぃ", "xu": "ぅ", "xe": "ぇ", "xo": "ぉ",
    "la": "ぁ", "li": "ぃ", "lu": "ぅ", "le": "ぇ", "lo": "ぉ",
    "n'": "ん",  # 明示的なアポストロフィ区切りは2文字消費でOK
}
ROMAJI_1 = {
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
}

VOWELS = set("aeiou")


def convert_romaji(buf):
    """bufを可能な限りひらがなに変換する。
    戻り値: (変換できた文字列, 変換しきれず残ったバッファ)
    """
    out = []
    i = 0
    n = len(buf)
    while i < n:
        chunk4 = buf[i:i + 4]
        if chunk4 in ROMAJI_3:  # xtsu/ltsu は4文字
            out.append(ROMAJI_3[chunk4])
            i += 4
            continue
        chunk3 = buf[i:i + 3]
        if chunk3 in ROMAJI_3:
            out.append(ROMAJI_3[chunk3])
            i += 3
            continue
        chunk2 = buf[i:i + 2]
        if chunk2 in ROMAJI_2:
            out.append(ROMAJI_2[chunk2])
            i += 2
            continue

        ch = buf[i]

        # 促音(っ): 子音の連続(nを除く)。例: kk, ss, tt, pp
        if ch not in VOWELS and ch != "n" and i + 1 < n and buf[i + 1] == ch:
            out.append("っ")
            i += 1
            continue

        # ん: "n" の次が母音でもyでもない場合に確定する。
        if ch == "n":
            if i + 1 < n and buf[i + 1] == "'":
                # 明示的なアポストロフィ区切り。2文字消費してOK。
                out.append("ん")
                i += 2
                continue
            if i + 1 < n and buf[i + 1] == "n":
                # "nn"は2通りの意味がありうる:
                #  (a) 3文字目が母音 → 1つ目のnで「ん」を確定させ、2つ目のnは
                #      次のループで後続の母音と結合させる(例: konnichiha -> こんにちは)
                #  (b) 3文字目が子音(または末尾) → 単に「ん」を強調して2回打っただけ
                #      なので、2つのnをまとめて「ん」1個として消費する
                #      (例: dennshi のつもりで打ったなら でんし、であって でんんし ではない)
                if i + 2 < n and buf[i + 2] in ("a", "i", "u", "e", "o"):
                    out.append("ん")
                    i += 1
                else:
                    out.append("ん")
                    i += 2
                continue
            if i + 1 < n and buf[i + 1] not in ("a", "i", "u", "e", "o", "y"):
                out.append("ん")
                i += 1
                continue
            # 次の文字がまだ来ていない/母音・y待ちの可能性があるので、ここで打ち切って
            # 残りは未変換のままバッファに残す(次のキー入力を待つ)
            break

        # 長音記号(ー): ハイフンを長音として扱う(例: peepa- -> ぺーぱー)
        if ch == "-":
            out.append("ー")
            i += 1
            continue

        chunk1 = ROMAJI_1.get(ch)
        if chunk1:
            out.append(chunk1)
            i += 1
            continue

        # 変換できない文字(記号など)。ここで打ち切り、残りはそのままにする。
        break

    return "".join(out), buf[i:]


def flush_trailing_n(buf):
    """Tab/Spaceなど区切りキーが押された時点で、バッファ末尾に残っている
    確定待ちの"n"を強制的に「ん」に変換する。"""
    if buf == "n":
        return "ん", ""
    return "", buf
