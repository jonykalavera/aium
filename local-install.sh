#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

EXT_UUID="aium@jonykalavera"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"

echo "==> Installing aium CLI via uv tool"
uv tool install --force --no-cache .

echo "==> Installing systemd user units"
mkdir -p ~/.config/systemd/user
cp systemd/aium-poll.service ~/.config/systemd/user/
cp systemd/aium-poll.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now aium-poll.timer

echo "==> Installing GNOME Shell extension"
rm -rf "$EXT_DIR"
mkdir -p "$EXT_DIR"
cp -r extension/lib "$EXT_DIR/"
cp -r extension/icons "$EXT_DIR/"
cp extension/metadata.json extension/extension.js extension/prefs.js extension/stylesheet.css "$EXT_DIR/"
mkdir -p "$EXT_DIR/schemas"
glib-compile-schemas extension/schemas --targetdir="$EXT_DIR/schemas"

echo "==> Done"
echo "Restart GNOME Shell to enable the extension (Alt+F2, type 'r', Enter) or log out/in."
echo "Then: gnome-extensions enable $EXT_UUID"
