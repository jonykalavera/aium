#!/usr/bin/env bash
# Fast iteration on Wayland: run a nested GNOME Shell in a window.
#
# Usage: scripts/dev-nested.sh
#   - Installs the extension files first, then launches a nested session.
#   - The nested shell re-imports the extension fresh on startup, so you see
#     code changes immediately.
#   - Logs: journalctl -f -o cat GNOME_SHELL_EXTENSION_UUID=aium@jonykalavera
#   - Exit with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/dev-install.sh

echo "Launching nested GNOME Shell (Ctrl+C to exit)…"
# `--devkit` switches mutter into nested mode (a throwaway X11/Wayland display).
# The optional `mutter-devkit` binary (a DevTools console) is not required.
exec dbus-run-session -- gnome-shell --wayland --devkit
