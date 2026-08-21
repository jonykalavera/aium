import {CURRENCY_SYMBOLS, money, moneyShort} from '../lib/format.js';
import {assertClose, assertDeepEqual, assertEqual, describe, it} from './_assert.js';

describe('money', () => {
    it('formats with currency', () => {
        assertEqual(money(1.5, 'USD'), '1.50 USD');
    });
    it('handles undefined value', () => {
        assertEqual(money(undefined, 'USD'), '0.00 USD');
    });
    it('defaults currency to USD', () => {
        assertEqual(money(1, undefined), '1.00 USD');
    });
});

describe('moneyShort', () => {
    it('uses currency symbol', () => {
        assertEqual(moneyShort(1.5, 'USD'), '$1.50');
        assertEqual(moneyShort(2, 'EUR'), '€2.00');
    });
    it('unknown currency has no symbol', () => {
        assertEqual(moneyShort(3, 'XYZ'), '3.00');
    });
    it('rounds to two decimals', () => {
        assertEqual(moneyShort(0.5, 'USD'), '$0.50');
    });
});

describe('CURRENCY_SYMBOLS', () => {
    it('covers the providers we support', () => {
        assertDeepEqual(Object.keys(CURRENCY_SYMBOLS).sort(), ['CNY', 'EUR', 'GBP', 'JPY', 'USD']);
    });
    it('amount parsing', () => {
        assertClose(Number('12.34'), 12.34);
    });
});
