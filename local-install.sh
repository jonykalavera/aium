#!/usr/bin/env bash
# Dev install from this repo: the CLI + the systemd poll timer, plus the
# display outlets relevant to this machine. The GNOME Shell extension and the
# Omarchy shell plugin are auto-detected; override with --gnome/--no-gnome and
# --omarchy/--no-omarchy.
set -euo pipefail
cd "$(dirname "$0")"

EXT_UUID="aium@jonykalavera"
EXT_DIR="$HOME/.local/share/gnome-shell/extensions/$EXT_UUID"
PLUGIN_ID="jonykalavera.aium"

usage() {
  cat <<USAGE
Usage: ./local-install.sh [--gnome|--no-gnome] [--omarchy|--no-omarchy]

Installs the aium CLI (uv tool) and the aium-poll systemd user timer, then
sets up the display outlets this machine uses:
  - GNOME Shell extension  (auto: gnome-shell session or GNOME desktop)
  - Omarchy shell plugin   (auto: omarchy config/CLI present)
Auto-detection can be overridden per outlet.
USAGE
}

WANT_GNOME=""    # "" = auto, 1 = force install, 0 = skip
WANT_OMARCHY=""

for arg in "$@"; do
  case "$arg" in
    --gnome) WANT_GNOME=1 ;;
    --no-gnome) WANT_GNOME=0 ;;
    --omarchy) WANT_OMARCHY=1 ;;
    --no-omarchy) WANT_OMARCHY=0 ;;
    -h | --help) usage; exit 0 ;;
    *)
      echo "local-install.sh: unknown option: $arg" >&2
      usage >&2
      exit 1
      ;;
  esac
done

gnome_detected() {
  pgrep -x gnome-shell >/dev/null 2>&1 && return 0
  case "${XDG_CURRENT_DESKTOP:-}${DESKTOP_SESSION:-}" in
    *[Gg]nome*) return 0 ;;
  esac
  return 1
}

omarchy_detected() {
  [[ -d "$HOME/.config/omarchy" ]] && return 0
  command -v omarchy >/dev/null 2>&1 && return 0
  return 1
}

echo "==> Installing aium CLI via uv tool"
uv tool install --force --no-cache .

echo "==> Installing systemd user units"
mkdir -p ~/.config/systemd/user
cp systemd/aium-poll.service ~/.config/systemd/user/
cp systemd/aium-poll.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now aium-poll.timer

install_gnome_extension() {
  rm -rf "$EXT_DIR"
  mkdir -p "$EXT_DIR"
  cp -r extension/lib "$EXT_DIR/"
  cp -r extension/icons "$EXT_DIR/"
  cp extension/metadata.json extension/extension.js extension/prefs.js extension/stylesheet.css "$EXT_DIR/"
  mkdir -p "$EXT_DIR/schemas"
  glib-compile-schemas extension/schemas --targetdir="$EXT_DIR/schemas"
  echo "Restart GNOME Shell to enable the extension (Alt+F2, type 'r', Enter) or log out/in."
  echo "Then: gnome-extensions enable $EXT_UUID"
}

install_omarchy_plugin() {
  ./scripts/omarchy-install.sh
}

if [[ $WANT_GNOME == 1 ]]; then
  echo "==> Installing GNOME Shell extension (--gnome)"
  install_gnome_extension
elif [[ $WANT_GNOME == 0 ]]; then
  echo "==> Skipping GNOME Shell extension (--no-gnome)"
elif gnome_detected; then
  echo "==> Installing GNOME Shell extension"
  install_gnome_extension
else
  echo "==> Skipping GNOME Shell extension (no GNOME session detected; use --gnome to force)"
fi

if [[ $WANT_OMARCHY == 1 ]]; then
  echo "==> Installing Omarchy shell plugin (--omarchy)"
  install_omarchy_plugin
elif [[ $WANT_OMARCHY == 0 ]]; then
  echo "==> Skipping Omarchy shell plugin (--no-omarchy)"
elif omarchy_detected; then
  echo "==> Installing Omarchy shell plugin"
  install_omarchy_plugin
else
  echo "==> Skipping Omarchy shell plugin (no Omarchy detected; use --omarchy to force)"
fi

echo "==> Done"
