// Pure formatting helpers (no gi:// or shell resource imports).

export const CURRENCY_SYMBOLS = { USD: '$', EUR: '€', GBP: '£', JPY: '¥', CNY: '¥' };

export function money(value, currency) {
    const amount = Number(value ?? 0).toFixed(2);
    return `${amount} ${currency ?? 'USD'}`;
}

export function moneyShort(value, currency) {
    const amount = Number(value ?? 0).toFixed(2);
    return `${CURRENCY_SYMBOLS[currency ?? 'USD'] ?? ''}${amount}`;
}
