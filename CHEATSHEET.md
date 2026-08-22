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
終了は Ctrl+Q

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
