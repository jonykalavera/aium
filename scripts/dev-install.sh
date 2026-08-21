#!/usr/bin/env bash
# Install the extension (code + lib + schema + icon) into the user's session.
#
# NOTE: GNOME Shell 45+ caches the extension module after the first import, so
# `gnome-extensions disable/enable` does NOT reload extension.js. On Wayland
# there is no hot restart (Alt+F2 -> r). To see code changes:
#   1. log out and back in, or
#   2. test in a nested shell: scripts/dev-nested.sh
set -euo pipefail
cd "$(dirname "$0")/.."

EXT_UUID="aium@jonykalavera"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"

rm -rf "$EXT_DIR"
mkdir -p "$EXT_DIR"
cp -r extension/lib "$EXT_DIR/"
cp -r extension/icons "$EXT_DIR/"
cp extension/metadata.json extension/extension.js extension/prefs.js extension/stylesheet.css "$EXT_DIR/"
mkdir -p "$EXT_DIR/schemas"
glib-compile-schemas extension/schemas --targetdir="$EXT_DIR/schemas"

echo "Installed files for $EXT_UUID"
if [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
    echo "Wayland: no hot reload. Log out/in, or test in a nested shell (scripts/dev-nested.sh)."
else
    echo "X11: reload with Alt+F2, then type 'r', Enter."
fi
