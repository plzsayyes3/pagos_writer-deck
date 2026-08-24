#!/bin/bash
exec > $HOME/git_sync.log 2>&1
echo "=== $(date) ==="
DRAFT=$HOME/pagos_gui_draft.md
REPO=$HOME/mynotebook
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="$REPO/00_inbox/${TIMESTAMP}.md"

WIN=$(xdotool search --name "Mousepad" | head -1)
echo "WIN=$WIN"
xdotool windowactivate --sync "$WIN"
sleep 0.3
xdotool key --window "$WIN" ctrl+s
sleep 1

echo "draft size:"
wc -c "$DRAFT"

if [ -s "$DRAFT" ]; then
  cp "$DRAFT" "$DEST"
  cd "$REPO" || exit 1
  git add "$DEST"
  git commit -m "GUI版から送信: ${TIMESTAMP}"
  git pull --no-edit --rebase=false
  git push
  : > "$DRAFT"
  xdotool windowkill "$WIN"
  sleep 0.5
  mousepad "$DRAFT" &
  echo "done"
else
  echo "draft empty, skipped"
fi
