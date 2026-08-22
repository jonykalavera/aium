// Pure status/display logic (no gi:// or shell resource imports).

import {money, moneyShort} from './format.js';

const METRICS = {
    spend_month: totals => moneyShort(totals.spend_this_month, totals.currency),
    spend_today: totals => moneyShort(totals.spend_today, totals.currency),
    balance: totals => moneyShort(totals.balance, totals.currency),
    none: () => '',
};

export function panelMetric(total, metric) {
    return (METRICS[metric] ?? METRICS.none)(total ?? {});
}

export function panelLabel(totals, topMetric, bottomMetric) {
    return {
        top: panelMetric(totals, topMetric),
        bottom: panelMetric(totals, bottomMetric),
    };
}

export function providerDetail(provider) {
    if (!provider.ok)
        return provider.error ?? 'error';
    if (provider.type === 'manual') {
        const sub = provider.subscription;
        const days = provider.days_until_renewal;
        const renewal = days != null ? ` · ${days}d` : '';
        return `${money(sub.cost, sub.currency)}/${sub.cycle}${renewal}`;
    }
    const balance = provider.balance
        ? (provider.balance_label && provider.balance_label !== 'balance'
            ? `${provider.balance_label}: ${money(provider.balance.available, provider.balance.currency)}`
            : money(provider.balance.available, provider.balance.currency))
        : '—';
    const spent = provider.spend_this_month != null
        ? ` · ${money(provider.spend_this_month, provider.currency)} spent`
        : '';
    let detail = `${balance}${spent}`;

    if (provider.spend_today != null && provider.spend_today > 0)
        detail += ` · today ${moneyShort(provider.spend_today, provider.currency)}`;

    if (provider.peak != null)
        detail += provider.peak ? ' · peak' : ' · 🔥 offer';

    if (provider.plan)
        detail += ` · ${provider.plan}`;

    if (provider.quota?.length) {
        const windows = provider.quota
            .map(w => `${w.label} ${w.utilization_pct}%`)
            .join(' · ');
        detail += ` · ${windows}`;
    }
    return detail;
}

const GOOD = [0.3, 0.85, 0.5];
const WARN = [1.0, 0.7, 0.2];
const CRITICAL = [1.0, 0.3, 0.3];

export function healthColor(provider, warnThreshold = 10, criticalThreshold = 1) {
    // Quota health wins (about to hit a rate limit).
    if (provider.quota?.length) {
        const peak = Math.max(...provider.quota.map(w => w.utilization_pct));
        if (peak >= 90)
            return CRITICAL;
        if (peak >= 70)
            return WARN;
        return GOOD;
    }
    // Prepaid balance health.
    if (provider.balance && provider.balance_kind === 'prepaid') {
        const available = provider.balance.available;
        if (available < criticalThreshold)
            return CRITICAL;
        if (available < warnThreshold)
            return WARN;
        return GOOD;
    }
    return null;
}

export function severityColor(pct) {
    if (pct >= 90)
        return [1.0, 0.3, 0.3];
    if (pct >= 70)
        return [1.0, 0.7, 0.2];
    return [0.3, 0.85, 0.5];
}

export function tooltipText(status) {
    if (!status)
        return 'No data';
    const totals = status.totals ?? {};
    return [
        `Spent this month: ${money(totals.spend_this_month, totals.currency)}`,
        `Balance: ${money(totals.balance, totals.currency)}`,
    ].join('\n');
}

export function isRelevant(provider) {
    if (provider.type === 'manual')
        return true;
    if (!provider.ok)
        return true;
    const balance = provider.balance?.available ?? 0;
    const spent = provider.spend_this_month ?? 0;
    return balance > 0 || spent > 0;
}
