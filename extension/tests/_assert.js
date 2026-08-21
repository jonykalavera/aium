// Minimal dependency-free assert framework for GJS (run via `gjs -m run.js`).

import system from 'system';

let _passes = 0;
let _failures = 0;
let _describe = '';

export function describe(name, fn) {
    const prev = _describe;
    _describe = prev ? `${prev} > ${name}` : name;
    try {
        fn();
    } finally {
        _describe = prev;
    }
}

export function it(name, fn) {
    const full = _describe ? `${_describe} > ${name}` : name;
    try {
        fn();
        _passes++;
        print(`PASS ${full}`);
    } catch (e) {
        _failures++;
        print(`FAIL ${full}`);
        print(`  ${e?.message ?? e}`);
        if (e?.stack)
            print(`  ${e.stack.split('\n').slice(0, 5).join('\n  ')}`);
    }
}

export function assertEqual(actual, expected, msg) {
    if (actual !== expected) {
        throw new Error(
            msg ?? `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
        );
    }
}

export function assertDeepEqual(actual, expected, msg) {
    const a = JSON.stringify(actual);
    const b = JSON.stringify(expected);
    if (a !== b)
        throw new Error(msg ?? `expected ${b}, got ${a}`);
}

export function assertTrue(value, msg) {
    if (!value)
        throw new Error(msg ?? `expected truthy, got ${JSON.stringify(value)}`);
}

export function assertClose(actual, expected, eps = 1e-6, msg) {
    if (Math.abs(actual - expected) > eps)
        throw new Error(msg ?? `expected ~${expected}, got ${actual}`);
}

export function summary() {
    print('');
    print(`${_passes} passed, ${_failures} failed`);
    system.exit(_failures ? 1 : 0);
}
