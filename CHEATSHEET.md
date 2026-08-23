# よく使うコマンド

## 接続
~~~
ssh pagos@192.168.1.191
~~~

## ファイル転送(Macのローカルターミナルで実行)
~~~
scp ~/Downloads/<ファイル名> pagos@192.168.1.191:~/pagos_writer-deck/
~~~

## エディタ起動
~~~
cd ~/pagos_writer-deck
python3 zen_editor.py
~~~
Ctrl+S保存 / Ctrl+D e-paper更新 / Ctrl+N新規原稿 / Ctrl+G AI変換+送信 / Ctrl+K日本語入力 / Ctrl+Q終了
(2026-08-24: Ctrl+Dを新設。Enterキー押下では自動でe-paperを更新しなくなった。
必ずCtrl+Dを押すこと)

## mozcローカル変換のテスト(Docker上で動作検証済み、実機でも高確度で動く見込み)
~~~
sudo apt install -y emacs-mozc-bin
cd ~/pagos_writer-deck
python3 mozc_convert.py "きょうはいいてんきですね"
~~~
成功すれば「今日はいい天気ですね」のような漢字仮名交じり文が出力される。
失敗した場合は`mozc_convert.log`を確認すること。動作確認できたら
`ai_convert.py`の`AI_BACKEND`を`"mozc_local"`に変更するとCtrl+Gでも
使われるようになる(ネット接続・APIキー不要、完全ローカル)。

## 電源状態の確認
~~~
vcgencmd get_throttled
~~~
0x0 以外が出たら電圧不足あり

## 電源監視ログの確認
~~~
tail -20 ~/pagos_writer-deck/power_log.csv
systemctl status power-monitor.service
~~~

## シャットダウン・再起動
~~~
sudo shutdown -h now
sudo reboot
~~~

## Git関連
~~~
cd ~/pagos_writer-deck
git status
git log --oneline -5
git push
~~~

## 実機(自動起動)側のログ確認
~~~
cat ~/zen_editor.log
~~~

## トラブル時の確認
~~~
ps aux | grep zen_editor
dmesg | tail -30
journalctl -u power-monitor.service -n 30 --no-pager
~~~
