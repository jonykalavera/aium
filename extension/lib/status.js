// Pure status/display logic (no gi:// or shell resource imports).

import {money} from './format.js';

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
        ? money(provider.balance.available, provider.balance.currency)
        : '—';
    const spent = provider.spend_this_month != null
        ? ` · ${money(provider.spend_this_month, provider.currency)} spent`
        : '';
    let detail = `${balance}${spent}`;

    if (provider.peak != null)
        detail += provider.peak ? ' · peak' : ' · off-peak';

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
