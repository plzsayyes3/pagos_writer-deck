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

**運用方針(2026-08-24確定)**: 新しいSDカードは用意せず、**V2実験で使った
`pagos-writer-gui`のSDカードをそのまま流用し、上書きしていく**。
X11・openbox・fcitx5-mozc・mousepad・xdotool・git deploy鍵は既に
セットアップ済みのはずなので、以下の手順は**差分だけ**適用すればよい
(パッケージの再インストールは基本不要、config.txtとX11設定ファイル
だけがV2(HDMI)からV3(SPI LCD)への変更点)。

## ハードウェア運用方針(確定)

電子ペーパーHATとこのOSOYOO LCDは、どちらもGPIOヘッダーに直挿しする
HAT型で、どちらもSPIバスを使うため同時接続はしない。
**`pagos-writer`(電子ペーパー版)のSDカードはそのまま温存し、
`pagos-writer-gui`(V2で使った予備SDカード)をV3用に上書きしていく**
運用で確定。使うときに応じてSDカードごと挿し替える。

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

### 3. X11 + openbox + fcitx5-mozc(`pagos-writer-gui`なら大部分は導入済み)

`pagos-writer-gui`のSDカードをそのまま使う場合、以下のパッケージは
V2実験で既にインストール済みのはずなので**このコマンドは基本不要**
(念のため、入っていなければ実行):
```bash
sudo apt install -y xserver-xorg xinit openbox dbus-x11 mousepad \
  fcitx5 fcitx5-mozc fcitx5-frontend-gtk3 x11-xserver-utils git xdotool \
  fonts-vlgothic
```

**設定ファイルはV2(HDMI用)からV3(SPI LCD用)に置き換える必要がある**
(`.xinitrc`が別物になる。geometryがHDMIの1920x1080基準だったものを
480x320基準に変更しているため):
```bash
mkdir -p ~/.config/fcitx5/conf ~/.config/openbox
cp xinitrc ~/.xinitrc
cp xprofile ~/.xprofile          # V2と同一内容なので上書きしても実質変化なし
cp fcitx5_profile ~/.config/fcitx5/profile
cp fcitx5_conf_wayland.conf ~/.config/fcitx5/conf/wayland.conf
cp openbox_rc.xml ~/.config/openbox/rc.xml   # V2と同一内容
cp git_sync.sh ~/git_sync.sh && chmod +x ~/git_sync.sh  # V2と同一内容
sudo cp 99-calibration.conf /usr/share/X11/xorg.conf.d/99-calibration.conf
touch ~/pagos_gui_draft.md   # 既にあれば不要
```

git送信用のデプロイ鍵・`~/mynotebook`のクローン・`~/.ssh/config`は
V2で既に設定済みのはず。`ls ~/mynotebook`と`git -C ~/mynotebook remote -v`
で生きているか確認するだけでよい(新規発行は不要)。

### 4. 起動スプラッシュ(パゴス+亀ロゴ)の生成

```bash
python3 make_splash.py
```
`splash.png`(480×320)がこのディレクトリに生成される。フォントは
`fonts-vlgothic`を前提にしている。

### 5. 自動起動の設定

`bashrc_snippet.txt`の内容を`~/.bashrc`に追記する。V2実験では
`startx`は毎回手動で実行していた(自動起動は無かった)ので、これは
V3で新規に追加する部分。

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
