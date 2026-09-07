#!/usr/bin/env python3
"""Sync the pure display logic from extension/lib (ESM, source of truth)
into omarchy/lib/status.js (QML script style for the Omarchy shell plugin).

Quickshell's JS engine (Qt QML V4) does not speak ES modules and does not
support `import` inside .js resources, so the copies are flattened and
rewritten mechanically:
  - module imports are removed (imported bindings are merged into the same
    file, dependency-first: format.js, then status.js)
  - `export const/function` becomes a plain declaration

The generated file is committed; CI re-runs this script and fails on drift
(`make omarchy-check`). Never edit omarchy/lib by hand.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "extension" / "lib"
DST = ROOT / "omarchy" / "lib"

# Merge order must put dependencies first (status.js uses format.js helpers).
MERGE_ORDER = ["format.js", "status.js"]
OUTPUT = "status.js"

HEADER = (
    "// GENERATED FILE — do not edit by hand.\n"
    "// Flattened from extension/lib (ESM source of truth) by `make omarchy-sync`.\n"
    "// Qt QML's JS engine does not support ES modules, so everything is merged\n"
    "// into this single script file.\n"
)

IMPORT_RE = re.compile(r"import\s*\{[^}]*\}\s*from\s*'[^']+';\n?")
EXPORT_RE = re.compile(r"^export ", re.MULTILINE)


def convert(text: str) -> str:
    body = IMPORT_RE.sub("", text)
    return EXPORT_RE.sub("", body).strip()


def main() -> int:
    if not SRC.is_dir():
        print(f"missing source dir: {SRC}", file=sys.stderr)
        return 1
    for name in MERGE_ORDER:
        if not (SRC / name).is_file():
            print(f"missing source file: {SRC / name}", file=sys.stderr)
            return 1

    sections = [HEADER]
    for name in MERGE_ORDER:
        sections.append(convert((SRC / name).read_text()))
    DST.mkdir(parents=True, exist_ok=True)
    (DST / OUTPUT).write_text("\n\n".join(sections) + "\n")

    # Drop files from previous sync layouts so stale copies can't linger.
    for stale in DST.glob("*.js"):
        if stale.name != OUTPUT:
            stale.unlink()
            print(f"removed stale {stale.name}")
    print(f"synced {OUTPUT} (from {' + '.join(MERGE_ORDER)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
