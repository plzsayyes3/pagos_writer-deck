# パゴス V2 (GUI + fcitx5-mozc版)

これはメインの`zen_editor.py`(AI一括変換方式)とは別の、**比較実験用の第2形態**。
X11 + openbox(最小ウィンドウマネージャ) + fcitx5-mozc(ローカルの伝統的なライブ変換IME)
を使い、「打った内容がその場で見える」編集体験が可能かどうかを検証した。

別のSDカード(ホスト名`pagos-writer-gui`)で構築。メインの`pagos-writer`カードとは
物理的に別カードで、同じRaspberry Pi 3 A+本体に挿し替えて使う想定。

**結論: 技術的には成立する。** fcitx5-mozcでの日本語変換、Ctrl+Gでのgit送信まで
一通り動作確認済み(2026-08-23)。ただし今回はテレビ(HDMI)接続での検証であり、
最終的にe-paper版に組み込むかどうかは別途判断が必要(e-paperの低速・全画面書き換え
という制約に、ライブ変換のUI(候補選択メニュー等)がそもそも向かないという理由で
当初SKK辞書方式を放棄した経緯があるため、GUI版はあくまで「概念実証」の位置づけ)。

## 構成

- OS: Raspberry Pi OS Lite (32bit, trixie)、ホスト名`pagos-writer-gui`
- X11 + openbox + fcitx5 + fcitx5-mozc (フルデスクトップ環境ではなく最小構成)
- エディタ: `mousepad`(GTKベースの軽量テキストエディタ)
- 固定ファイル`~/pagos_gui_draft.md`を常に開いた状態で運用
- **Ctrl+G**でopenboxのグローバルキーバインドから`git_sync.sh`を実行し、
  保存→`mynotebook`リポジトリの`00_inbox/`にタイムスタンプ付きで送信→
  mousepadを再起動して空の状態に戻す、という一連の流れを実現
- git送信先は本命端末と同じ`plzsayyes3/mynotebook`(この機体専用のデプロイ鍵で接続)

## ファイル一覧(このフォルダ)

- `xinitrc` → `~/.xinitrc` として配置
- `xprofile` → `~/.xprofile` として配置
- `git_sync.sh` → `~/git_sync.sh` として配置(`chmod +x`必要)
- `fcitx5_profile` → `~/.config/fcitx5/profile` として配置
- `fcitx5_conf_wayland.conf` → `~/.config/fcitx5/conf/wayland.conf` として配置
- `openbox_rc.xml` → `~/.config/openbox/rc.xml` として配置(標準からの変更点は
  下記「ハマった点」参照。`<chainQuitKey>`をEscapeに変更し、C-gのkeybindを追加している)

## セットアップ手順(このSDカードを再現する場合)

```bash
sudo apt install -y xserver-xorg xinit openbox dbus-x11 mousepad \
  fcitx5 fcitx5-mozc fcitx5-frontend-gtk3 x11-xserver-utils git xdotool

# キーボードレイアウトを物理キーボードに合わせる(下記「ハマった点」参照)
sudo sed -i 's/^XKBLAYOUT=.*/XKBLAYOUT="jp"/' /etc/default/keyboard
sudo setupcon --force

# /boot/firmware/config.txt: dtoverlay=vc4-kms-v3d を vc4-fkms-v3d に変更
# (下記「ハマった点」参照)

mkdir -p ~/.config/fcitx5/conf ~/.config/openbox
cp gui-version-v2/xinitrc ~/.xinitrc
cp gui-version-v2/xprofile ~/.xprofile
cp gui-version-v2/git_sync.sh ~/git_sync.sh && chmod +x ~/git_sync.sh
cp gui-version-v2/fcitx5_profile ~/.config/fcitx5/profile
cp gui-version-v2/fcitx5_conf_wayland.conf ~/.config/fcitx5/conf/wayland.conf
cp gui-version-v2/openbox_rc.xml ~/.config/openbox/rc.xml
touch ~/pagos_gui_draft.md

# git送信用のデプロイ鍵(この機体専用、mynotebookリポジトリにWrite権限で追加)
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_mynotebook -N ''
# 公開鍵をGitHubのmynotebookリポジトリのDeploy keysに追加(Allow write access)
# ~/.ssh/config に以下を追加:
#   Host github-mynotebook
#     HostName github.com
#     User git
#     IdentityFile ~/.ssh/id_ed25519_mynotebook
#     IdentitiesOnly yes
git clone github-mynotebook:plzsayyes3/mynotebook.git ~/mynotebook
git config --global user.email "plzsayyes3@gmail.com"
git config --global user.name "pagos"

# startxは必ず物理コンソール(SSH越しではない)から実行すること
startx
```

## ハマった点・教訓

- **`startx`はSSH越しには実行できない**(`Only console users are allowed to run
  the X server`)。必ず物理キーボード+モニター直結のコンソールから実行すること
- **物理キーボードの配列(JP/US)とOS側の`/etc/default/keyboard`の設定が
  合っていないと、`~`や`-`などの記号が別のキーに化ける。** `xkb_layout`が
  ログにどう出ているか(`Xorg.0.log`)で確認できる。物理キーボードの製品名に
  ヒントがあることも(例: 製品名に"JP"とあるのに設定は"us"のままだった)
- **画面が真っ暗になる問題**は複数の原因が重なっていた:
  1. openboxはデフォルトで壁紙もパネルも無いため、ウィンドウが無ければ本当に
     何も表示されない(`xsetroot -solid`でルートウィンドウを塗ると診断しやすい)
  2. ウィンドウが画面の隅(0,0)付近にあると、テレビのオーバースキャンで
     見えなくなることがある(`-geometry`で中央寄りに配置する)
  3. **`dtoverlay=vc4-kms-v3d`(フルKMS)がテレビとの相性で映像出力自体が
     出ないことがある。`vc4-fkms-v3d`(fake KMS)に変えたら直った。**
     コンソールのテキストは正常に表示されるのに、Xに切り替わった瞬間だけ
     真っ暗になる、という症状が特徴的
  4. スクリーンショット(`scrot`)はXサーバー内部の framebuffer を直接読むため、
     たとえ実際のHDMI出力が死んでいても「正常な画面」が撮れてしまう。
     見た目の異常の切り分けには過信しないこと
- **`scrot`をSSH越しに実行すると`XAUTHORITY`が正しく通らず
  `Authorization required`エラーになることがある**(`/tmp/serverauth.*`を
  動的に指定しても解決しないことがあった)。確実なのは、Xセッション自身の
  中(xterm等)から直接`scrot`を実行すること
- **fcitx5が起動しても日本語に変換されない場合、`.xprofile`が実際に
  読み込まれているか確認すること。** `.xinitrc`の中で`source ~/.xprofile`と
  書いていたが、`/bin/sh`(Debianでは`dash`)は`source`をサポートしておらず、
  エラーを出しつつスクリプト全体は止めずに次の行に進んでしまうため、
  `.xprofile`だけが静かにスキップされ続けていた。**POSIX互換の`.`
  (ドットコマンド)を使うこと**: `. ~/.xprofile`
- **fcitx5の`wayland`アドオンが、X11オンリーの環境でも読み込み時にハングする
  ことがあった。** `~/.config/fcitx5/conf/wayland.conf`に`[Addon]\nEnabled=False`
  を書いて明示的に無効化することで回避
- **openboxのデフォルト設定には`<chainQuitKey>C-g</chainQuitKey>`という
  予約キーがあり、これが自分で割り当てたC-gのカスタムキーバインドを
  握りつぶしてしまう。** `<chainQuitKey>`を別のキー(`Escape`)に変更することで
  C-gを本来の用途(git送信)に使えるようになった
- **mousepad(GTKアプリ)を`xdotool`で外部操作してクリアしようとする際、
  `ctrl+a`+`Delete`のキー送信だけでは選択・削除が反映されないことがあった。**
  ファイルを直接シェルから書き換える(`: > file`)と、mousepadの内部状態との
  ズレで「外部で変更されました」という警告ダイアログが出てしまう。
  最終的に、**mousepadのウィンドウを`xdotool windowkill`で閉じてから、
  空のファイルで新しいmousepadを開き直す**方式が最も確実だった
- `ssh host "sudo ..."` は擬似端末が無いためパスワード入力に失敗する
  (`sudo: a terminal is required`)。`ssh -t host "sudo ..."`が必要
- zshは二重引用符の中でも`!`を履歴展開しようとしてエラーになることがある
  (`event not found`)。ヒアドキュメントを含む複雑なリモートコマンドは
  単一引用符で丸ごと囲むと安全
