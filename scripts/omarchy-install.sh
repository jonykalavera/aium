#!/usr/bin/env bash
# Dev install of the aium Omarchy shell plugin (the sibling of
# scripts/dev-install.sh for the GNOME extension). Copies manifest.json +
# omarchy/ into ~/.config/omarchy/plugins/jonykalavera.aium and enables the
# widget on the right of the bar. Saved files hot-reload in omarchy-shell.
set -euo pipefail

PLUGIN_ID="jonykalavera.aium"
PLUGINS_DIR="$HOME/.config/omarchy/plugins"
DEST="$PLUGINS_DIR/$PLUGIN_ID"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Refresh the shared display logic (extension/lib -> omarchy/lib) first.
python3 "$REPO_ROOT/scripts/sync-omarchy-lib.py"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/omarchy"
cp "$REPO_ROOT/manifest.json" "$STAGE/manifest.json"
rsync -a "$REPO_ROOT/omarchy/" "$STAGE/omarchy/"

mkdir -p "$PLUGINS_DIR"
rm -rf "$DEST"
mv "$STAGE" "$DEST"
echo "installed plugin at $DEST"

if ! command -v omarchy >/dev/null 2>&1; then
  echo "omarchy CLI not found — skipping validate/enable"
  exit 0
fi

if omarchy plugin validate "$DEST"; then
  omarchy plugin enable "$PLUGIN_ID" --section right 2>/dev/null \
    || echo "plugin already enabled (ok)"
  if pgrep -x omarchy-shell >/dev/null 2>&1; then
    echo "omarchy-shell running — hot reload should pick the change up"
  else
    echo "omarchy-shell is not running — start it to see the widget"
  fi
fi
