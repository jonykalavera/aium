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

    if (provider.peak === false)
        detail += ' · 🔥 discounted';

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

// Severity ramp shared by health dots and sparklines: good, warn, critical.
export const LEVEL_COLORS = [[0.3, 0.85, 0.5], [1.0, 0.7, 0.2], [1.0, 0.3, 0.3]];

// 0 (good) | 1 (warn) | 2 (critical) | null (no color). Quota health wins
// (about to hit a rate limit), prepaid balance health comes second.
export function healthLevel(provider, warnThreshold = 10, criticalThreshold = 1) {
    if (provider.quota?.length) {
        const peak = Math.max(...provider.quota.map(w => w.utilization_pct));
        if (peak >= 90)
            return 2;
        if (peak >= 70)
            return 1;
        return 0;
    }
    if (provider.balance && provider.balance_kind === 'prepaid') {
        const available = provider.balance.available;
        if (available < criticalThreshold)
            return 2;
        if (available < warnThreshold)
            return 1;
        return 0;
    }
    return null;
}

export function healthColor(provider, warnThreshold = 10, criticalThreshold = 1) {
    const level = healthLevel(provider, warnThreshold, criticalThreshold);
    return level === null ? null : LEVEL_COLORS[level];
}

export function severityColor(pct) {
    if (pct >= 90)
        return LEVEL_COLORS[2];
    if (pct >= 70)
        return LEVEL_COLORS[1];
    return LEVEL_COLORS[0];
}

export function tooltipText(status) {
    if (!status)
        return 'No data';
    const totals = status.totals ?? {};
    return [
        `Spent this month: ${money(totals.spend_this_month, totals.currency)}`,
        `Spent today: ${money(totals.spend_today, totals.currency)}`,
        `Balance: ${money(totals.balance, totals.currency)}`,
    ].join('\n');
}

export function statsSummary(totals) {
    const daily = totals?.spend_daily ?? [];
    const avgDay = daily.length
        ? daily.reduce((a, b) => a + b, 0) / daily.length
        : 0;
    return {
        month: totals?.spend_this_month ?? 0,
        today: totals?.spend_today ?? 0,
        balance: totals?.balance ?? 0,
        avgDay,
        maxDay: daily.length ? Math.max(...daily) : 0,
        minDay: daily.length ? Math.min(...daily) : 0,
    };
}

export function summaryText(totals) {
    const s = statsSummary(totals);
    const currency = totals?.currency;
    return (
        `This month ${moneyShort(s.month, currency)} · Today ${moneyShort(s.today, currency)} · Balance ${moneyShort(s.balance, currency)}\n` +
        `Avg/day ${moneyShort(s.avgDay, currency)} · Max ${moneyShort(s.maxDay, currency)} · Min ${moneyShort(s.minDay, currency)}`
    );
}

export function isRelevant(provider) {
    if (provider.type === 'manual')
        return true;
    if (!provider.ok)
        return true;
    if (provider.plan)
        return true;
    if (provider.quota?.length)
        return true;
    const balance = provider.balance?.available ?? 0;
    const spent = provider.spend_this_month ?? 0;
    return balance > 0 || spent > 0;
}
