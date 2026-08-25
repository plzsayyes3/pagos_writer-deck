#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime patch for Ctrl+K: convert only the current editor line.

Ctrl+G remains the existing whole-document conversion + Git send operation.
Ctrl+K is intentionally local to the current logical line.
"""


def apply(zen_editor):
    original = zen_editor.ZenEditor.skk_toggle

    def convert_current_line(self):
        # Ctrl+K must no longer toggle JP/EN mode.
        if self.skk_enabled:
            self.flush_romaji_buf()

        source = self.lines[self.cy]
        if not source.strip():
            self.status = "変換する文字がありません"
            return

        self.status = "変換中..."
        self.render()
        try:
            converted = zen_editor.ai_convert.convert_to_kanji(source)
            self.snapshot()
            self.lines[self.cy] = converted
            self.cx = len(converted)
            self.dirty = True
            self.status = "現在行を漢字変換しました"
        except zen_editor.ai_convert.AiConvertError as e:
            self.status = f"変換失敗: {e}"
        except Exception as e:
            self.status = f"変換失敗: {e}"

    zen_editor.ZenEditor.skk_toggle = convert_current_line


def main():
    raise SystemExit("Import and call apply(zen_editor) from the Fast writer launcher.")


if __name__ == "__main__":
    main()
