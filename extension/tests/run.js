// GJS test runner: discovers `*.test.js` under this directory, imports each,
// then prints a summary and exits non-zero on failure.
//
// Usage: gjs -m extension/tests/run.js

import GLib from 'gi://GLib';
import system from 'system';

import {summary} from './_assert.js';

function testsDir() {
    const url = import.meta.url;
    const path = url.startsWith('file://') ? url.slice('file://'.length) : url;
    return GLib.path_get_dirname(path);
}

function discover(dir) {
    const found = [];
    const d = GLib.Dir.open(dir, 0);
    let name;
    while ((name = d.read_name()) !== null) {
        const path = GLib.build_filenamev([dir, name]);
        if (GLib.file_test(path, GLib.FileTest.IS_DIR))
            found.push(...discover(path));
        else if (name.endsWith('.test.js'))
            found.push(path);
    }
    d.close();
    found.sort();
    return found;
}

async function main() {
    const files = discover(testsDir());
    for (const file of files) {
        await import(`file://${file}`);
    }
    summary();
}

main().catch(e => {
    print(`RUNNER ERROR: ${e?.stack ?? e}`);
    system.exit(1);
});
