# 朝の作業チェックリスト (2026-08-24未明作業分)

夜間に以下を実装・pushしました。実機での動作確認が必要な部分をまとめます。

## 1. `pagos-writer`(本命機)を最新化

```bash
ssh pagos@pagos-writer.local
cd ~/pagos_writer-deck
git pull
```

## 2. Ctrl+Dの動作確認(★確度高い、まず試してほしい)

**変更点**: これまで`Enter`を押すたびにe-paperが更新されていたが、これを
やめて`Ctrl+D`を押した時だけ更新するようにした(日本語入力でEnterが
増えることを見越して)。

```bash
python3 zen_editor.py
```
- 何行か打ってEnterを押しても、e-paperが更新**されない**ことを確認
- `Ctrl+D`を押したら、e-paperが更新される**こと**を確認
- 画面下のヘルプ表示に「Ctrl+D画面更新」が出ているか確認

もし「Enterでも更新されてしまう」「Ctrl+Dで何も起きない」場合は教えてください。

## 3. mozcローカル変換のテスト(★確度低い、未検証)

正直に言うと、これは一次情報(mozc.elのソース・ブログ記事)から protocol を
類推して実装したもので、**実機で試すまで本当に動くか分かりません。**

```bash
sudo apt install -y emacs-mozc-bin
# もし見つからなければ: apt search mozc | grep -i emacs
cd ~/pagos_writer-deck
python3 mozc_convert.py "きょうはいいてんきですね"
```

### 期待する結果
```
入力: きょうはいいてんきですね
結果: 今日はいい天気ですね
```
のように、ある程度自然な漢字混じり文が返ってくれば成功。

### うまくいかない場合
`mozc_convert.log` に生の送受信内容が全部記録されているので、それを
見せてもらえれば、応答のS式の実際の構造に合わせてパース部分
(`mozc_convert.py`内の`find_first`で探しているタグ名)を直します。

```bash
cat ~/pagos_writer-deck/mozc_convert.log
```

### 動作確認できたら
`ai_convert.py`の`AI_BACKEND = "gemini"`を`AI_BACKEND = "mozc_local"`に
書き換えれば、Ctrl+Gでもmozcのローカル変換が使われるようになる
(Gemini APIキー・ネット接続が不要になる)。

## 4. (優先度低) Ctrl+Q亀ロゴ

タイムアウトを25→60秒に伸ばす修正をしたが、テストでは変化なしとの
ことでした。これは一旦保留にする合意でしたが、気が向いたら
`zen_editor_crash.log`の有無や、e-paper側のログ(`_worker`内の例外を
どこかにログするコードは今は無い)を追加で見る必要があります。
急ぎではありません。

## 5. その他の背景情報

- APIキーがこのセッション中に一度チャットに露出しました。まだ
  ローテーション(再発行)していなければ、Google AI Studioで
  古いキーを無効化し、新しいキーを`~/.bashrc`に設定することを
  おすすめします
- `.bashrc`の`GEMINI_API_KEY`のexport順序バグ(自動起動より後に
  書かれていた)は修正済みです
