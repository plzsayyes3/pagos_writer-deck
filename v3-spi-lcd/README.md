# パゴス V3 (OSOYOO 3.5inch SPI LCD版)

V2(HDMIモニター+fcitx5-mozc)の実験で「mozcのライブ変換自体はこのPi上で
動く」ことを確認したが、電子ペーパーには候補選択UIが乗せられないという
結論だった。V3は、**電子ペーパーとは別に、リアルタイム描画が可能な小型
SPI液晶(OSOYOO 3.5インチタッチスクリーン、480×320)を使い、mozcのライブ
変換IMEをそのまま実用できるようにする**試み。

**正直な位置づけ**: ここに用意したファイル・手順は、OSOYOO公式の
Raspberry Pi OS Trixie向けセットアップガイド(2026-02-09版)と、V2実験で
得た知見を組み合わせて用意したもの。**私はSPI液晶の実機を持っておらず、
Dockerのようにソフトウェアだけで検証することもできない(GPIO/SPIという
物理ハードウェアが絡むため)。そのためV2のmozc_convert.pyのような
「一発で動作確認済み」という保証はできない。** 実機に届いたら、この
READMEの手順通りに進めて、うまくいかない箇所があれば教えてほしい。

## ハードウェア上の注意(要確認)

電子ペーパーHATとこのOSOYOO LCDは、どちらもGPIOヘッダーに直挿しする
HAT型で、どちらもSPIバスを使う。同時に両方を同じPiに物理的に接続する
場合、ピンの取り合いが起きる可能性がある。**基本方針は、電子ペーパー版
(pagos-writer)・GUI版V2(pagos-writer-gui)と同様に、別のSDカードを用意し
「使うときだけ挿し替える」運用を想定している**。同時接続したい場合は
配線から見直しが必要になる。

## セットアップ手順

### 1. config.txtの変更

`config_txt_snippet.txt`の内容を参照。既存の`dtoverlay=vc4-kms-v3d`
(V2で`vc4-fkms-v3d`に変えていた場合はそちらも)をコメントアウトし、
OSOYOO用の設定を追記する。**このLCDはKMS/DRMを使わない旧来の
fbtft方式のドライバなので、通常のHDMI出力とは共存しない**(想定通り、
このSDカードではHDMIは使わない前提)。

### 2. ドライバのインストール

```bash
sudo apt-get update
sudo apt-get install -y unzip cmake xserver-xorg-input-evdev xinput-calibrator fbi
cd ~
sudo wget https://osoyoo.com/driver/osoyoo35b.zip
sudo unzip ./osoyoo35b.zip
sudo cp osoyoo35b.dtbo /boot/overlays/
sudo reboot
```

再起動後、`/dev/fb1`が存在するか確認:
```bash
ls -la /dev/fb1
```

### 3. X11 + openbox + fcitx5-mozc(V2と同じ構成)

V2実験と同じパッケージ・同じ落とし穴対策を使う:

```bash
sudo apt install -y xserver-xorg xinit openbox dbus-x11 mousepad \
  fcitx5 fcitx5-mozc fcitx5-frontend-gtk3 x11-xserver-utils git xdotool \
  fonts-vlgothic
```

このディレクトリのファイルを配置:
```bash
mkdir -p ~/.config/fcitx5/conf ~/.config/openbox
cp xinitrc ~/.xinitrc
cp xprofile ~/.xprofile
cp fcitx5_profile ~/.config/fcitx5/profile
cp fcitx5_conf_wayland.conf ~/.config/fcitx5/conf/wayland.conf
cp openbox_rc.xml ~/.config/openbox/rc.xml
cp git_sync.sh ~/git_sync.sh && chmod +x ~/git_sync.sh
sudo cp 99-calibration.conf /usr/share/X11/xorg.conf.d/99-calibration.conf
touch ~/pagos_gui_draft.md
```

git送信用のデプロイ鍵はV2と同じ手順(この機体専用に新規発行し、
`mynotebook`リポジトリにWrite権限で追加)。

### 4. 起動スプラッシュ(パゴス+亀ロゴ)の生成

```bash
python3 make_splash.py
```
`splash.png`(480×320)がこのディレクトリに生成される。フォントは
`fonts-vlgothic`を前提にしている。

### 5. 自動起動の設定

`bashrc_snippet.txt`の内容を`~/.bashrc`に追記する(既存のCUI版
自動起動ブロックがあればコメントアウトすること。両方同時には
起動できない)。

**流れ**: 電源投入 → 自動ログイン(tty1) → `FRAMEBUFFER=/dev/fb1`設定
→ 亀ロゴのスプラッシュをフレームバッファに直接表示(X11起動を待たず
即座に出る) → 何かキー入力があるまで待機 → X11起動
(openbox + fcitx5-mozc + mousepad) → 執筆開始。

電子ペーパー版と違い、このLCDは通電が無いと表示を維持できないため、
「終了時に画面を表示しっぱなしにする」ことはできない
(shutdown時は単に画面が消えるだけになる想定)。

## 動作確認チェックリスト(実機到着後)

1. `ls /dev/fb1`が存在するか(ドライバが正しく読み込まれたか)
2. `sudo reboot`後、LCDに何か映るか(真っ暗なら`cat ~/xorg_errors.log`)
3. スプラッシュ画像(パゴス+亀ロゴ)が正しく表示され、キー入力で消えるか
4. mousepadが起動し、日本語入力(Ctrl+Space→ローマ字→変換)ができるか
   (V2で確認済みのfcitx5-mozc設定をそのまま流用しているので、ここは
   高確度で動くはず)
5. タッチ操作の座標がずれていないか(ずれていれば`xinput_calibrator`で
   再校正し、`99-calibration.conf`の値を更新)
6. `Ctrl+G`でgit送信できるか(V2と同じ`git_sync.sh`をそのまま使用)

## 既知の懸念・未検証事項

- OSOYOO公式ドライバ(`osoyoo35b`)がRaspberry Pi 3 A+(armhf)と
  今回のOS(trixie)の組み合わせで問題なく動くか(ガイド自体は対応を
  謳っているが未確認)
- タッチパネルのデバイス名が`ADS7846 Touchscreen`と一致するか
  (`xinput list`で確認要)
- `mousepad --geometry=470x290+3+3`のようなウィンドウサイズ指定が
  実際に効くか(効かない場合はopenboxのウィンドウ最大化キーバインドで
  代用: デフォルトでは`A-F5`など)
- `fbi`での起動スプラッシュ表示自体(パッケージ・フレームバッファの
  ピクセルフォーマットが噛み合うか)
