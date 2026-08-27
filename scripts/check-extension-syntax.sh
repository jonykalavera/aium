#!/usr/bin/env bash
# Syntax-check the shell-loaded extension modules.
#
# `gjs -m` reports parse-time early errors (e.g. `const` redeclaration) BEFORE
# trying to resolve the shell-only `resource://` imports, so a SyntaxError here
# means the module is broken even though `node --check` may pass. Any other
# failure (missing shell resources) is expected and ignored.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
for f in extension/extension.js extension/prefs.js; do
    if gjs -m "$f" 2>&1 | grep -q "SyntaxError"; then
        echo "FAIL: $f has a SyntaxError:"
        gjs -m "$f" 2>&1 | grep "SyntaxError" | sed 's/^/  /'
        fail=1
    fi
done
if [ "$fail" -eq 0 ]; then
    echo "extension syntax OK"
fi
exit "$fail"
