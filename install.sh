#!/usr/bin/env bash
# aium installer for `curl ... | bash`.
#
#   curl -fsSL https://raw.githubusercontent.com/jonykalavera/aium/main/install.sh | bash
#   # pin a release:
#   curl -fsSL https://raw.githubusercontent.com/jonykalavera/aium/main/install.sh | AIUM_VERSION=v0.1.1 bash
#
# Installs, pinned to <owner>/<repo> and GitHub releases/main (HTTPS):
#   - the `aium` CLI from PyPI (aium-cli)
#   - the systemd user timer that polls every 60 min
#   - the GNOME Shell extension from the release asset
#
# Requires: curl, unzip, and one of uv / pipx / pip.
set -euo pipefail

AIUM_REPO="${AIUM_REPO:-jonykalavera/aium}"
AIUM_VERSION="${AIUM_VERSION:-}"

# Resolve the version to a release tag (e.g. v0.1.1).
if [ -z "$AIUM_VERSION" ]; then
    AIUM_VERSION="$(curl -fsSL "https://api.github.com/repos/$AIUM_REPO/releases/latest" \
        | sed -n 's/.*"tag_name": *"\([^"]*\)".*/\1/p' | head -1)"
fi
if [ -z "$AIUM_VERSION" ]; then
    echo "Could not determine the latest release. Set AIUM_VERSION (e.g. v0.1.1)." >&2
    exit 1
fi
PYPI_VERSION="${AIUM_VERSION#v}"

echo "==> Installing aium CLI ($AIUM_VERSION) from PyPI"
if command -v uv >/dev/null 2>&1; then
    uv tool install --force "aium-cli==$PYPI_VERSION"
elif command -v pipx >/dev/null 2>&1; then
    pipx install --force "aium-cli==$PYPI_VERSION"
elif command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
    P="$(command -v pip3 || command -v pip)"
    "$P" install --user "aium-cli==$PYPI_VERSION"
else
    echo "No Python package manager found (uv, pipx or pip). Install one and retry." >&2
    exit 1
fi

echo "==> Installing systemd user units"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
curl -fsSL "https://raw.githubusercontent.com/$AIUM_REPO/main/systemd/aium-poll.service" \
    -o "$UNIT_DIR/aium-poll.service"
curl -fsSL "https://raw.githubusercontent.com/$AIUM_REPO/main/systemd/aium-poll.timer" \
    -o "$UNIT_DIR/aium-poll.timer"
systemctl --user daemon-reload
systemctl --user enable --now aium-poll.timer

echo "==> Installing GNOME Shell extension"
EXT_UUID="aium@jonykalavera"
EXT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gnome-shell/extensions/$EXT_UUID"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
curl -fsSL "https://github.com/$AIUM_REPO/releases/download/$AIUM_VERSION/aium@jonykalavera.zip" \
    -o "$TMP"
rm -rf "$EXT_DIR"
mkdir -p "$EXT_DIR"
unzip -q "$TMP" -d "$EXT_DIR"
if command -v glib-compile-schemas >/dev/null 2>&1; then
    glib-compile-schemas "$EXT_DIR/schemas" 2>/dev/null || true
fi
if command -v gnome-extensions >/dev/null 2>&1; then
    gnome-extensions enable "$EXT_UUID" >/dev/null 2>&1 || true
fi

echo "==> Done"
echo "Restart GNOME Shell (logout/login) to load the extension."
