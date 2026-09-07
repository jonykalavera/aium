#!/usr/bin/env python3
"""Sanity checks for the Omarchy shell plugin (run in CI; no omarchy needed):

  1. omarchy/lib copies are in sync with extension/lib (the sync script is
     deterministic — re-running it must not produce a diff).
  2. manifest.json is valid: schemaVersion 1, kinds/entryPoints present,
     safe relative entry-point paths that exist, id outside the reserved
     omarchy.* namespace (mirrors `omarchy plugin validate`).

Run via `make omarchy-check` (which re-runs the sync first).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifest.json"
LIB = ROOT / "omarchy" / "lib"

REQUIRED_KIND_ENTRY = {"bar-widget": "barWidget"}


def check_qml_syntax() -> bool:
    """Parse each plugin QML file with qmlformat when available (local dev
    only; the omarchy binary isn't present in CI, so this is a soft check)."""
    qmlformat = shutil.which("qmlformat")
    if not qmlformat:
        return True
    ok = True
    for qml in sorted((ROOT / "omarchy").glob("*.qml")):
        result = subprocess.run(
            [qmlformat, str(qml)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"QML syntax error in {qml.name}:\n{result.stderr.strip()}")
            ok = False
    return ok


def check_lib_sync() -> bool:
    result = subprocess.run(
        ["git", "diff", "--exit-code", "--", "omarchy/lib"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("omarchy/lib is stale — run `make omarchy-sync` and commit the result")
        print(result.stdout)
        return False
    return True


def check_manifest() -> bool:
    ok = True
    try:
        manifest = json.loads(MANIFEST.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"manifest.json unreadable: {exc}")
        return False

    if manifest.get("schemaVersion") != 1:
        print("manifest.json: schemaVersion must be 1")
        ok = False

    plugin_id = manifest.get("id", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", plugin_id) or plugin_id.startswith("omarchy."):
        print(f"manifest.json: invalid or reserved plugin id '{plugin_id}'")
        ok = False

    for field in ("id", "name", "version", "kinds", "entryPoints"):
        if field not in manifest:
            print(f"manifest.json: missing field '{field}'")
            ok = False

    kinds = manifest.get("kinds") or []
    if not isinstance(kinds, list) or not kinds:
        print("manifest.json: 'kinds' must be a non-empty array")
        ok = False

    entry_points = manifest.get("entryPoints") or {}
    if not isinstance(entry_points, dict):
        print("manifest.json: 'entryPoints' must be an object")
        ok = False
        entry_points = {}

    for kind, key in REQUIRED_KIND_ENTRY.items():
        if kind in kinds and key not in entry_points:
            print(f"manifest.json: kind '{kind}' requires entryPoints.{key}")
            ok = False

    for key, value in entry_points.items():
        path = str(value)
        if path.startswith("/") or ".." in path:
            print(f"manifest.json: unsafe entryPoints.{key}: '{path}'")
            ok = False
        elif not (ROOT / path).is_file():
            print(f"manifest.json: entryPoints.{key} file not found: '{path}'")
            ok = False

    section = (manifest.get("barWidget") or {}).get("defaultSection")
    if section is not None and section not in ("left", "center", "right"):
        print(f"manifest.json: barWidget.defaultSection must be left, center or right (got '{section}')")
        ok = False

    return ok


def main() -> int:
    ok = check_lib_sync() and check_manifest() and check_qml_syntax()
    if ok:
        print("omarchy plugin checks passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
