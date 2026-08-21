import {isRelevant, providerDetail, severityColor, tooltipText} from '../lib/status.js';
import {assertClose, assertDeepEqual, assertEqual, describe, it} from './_assert.js';

const balanceProvider = {
    id: 'deepseek',
    name: 'DeepSeek',
    type: 'balance',
    currency: 'USD',
    ok: true,
    balance: {available: 10, currency: 'USD'},
    spend_this_month: 2.5,
};

describe('providerDetail', () => {
    it('balance + spend', () => {
        assertEqual(
            providerDetail(balanceProvider),
            '10.00 USD · 2.50 USD spent',
        );
    });
    it('peak marker', () => {
        assertEqual(providerDetail({...balanceProvider, peak: true}), '10.00 USD · 2.50 USD spent · peak');
        assertEqual(providerDetail({...balanceProvider, peak: false}), '10.00 USD · 2.50 USD spent · off-peak');
    });
    it('plan', () => {
        assertEqual(
            providerDetail({...balanceProvider, plan: 'Antigravity (free-tier)'}),
            '10.00 USD · 2.50 USD spent · Antigravity (free-tier)',
        );
    });
    it('quota windows', () => {
        const withQuota = {
            ...balanceProvider,
            quota: [
                {label: '5h', utilization_pct: 40},
                {label: '7d', utilization_pct: 10},
            ],
        };
        assertEqual(providerDetail(withQuota), '10.00 USD · 2.50 USD spent · 5h 40% · 7d 10%');
    });
    it('manual subscription', () => {
        const manual = {
            id: 'chatgpt',
            name: 'ChatGPT Plus',
            type: 'manual',
            currency: 'USD',
            ok: true,
            subscription: {cost: 20, cycle: 'monthly', currency: 'USD'},
            days_until_renewal: 15,
        };
        assertEqual(providerDetail(manual), '20.00 USD/monthly · 15d');
    });
    it('error provider', () => {
        assertEqual(providerDetail({...balanceProvider, ok: false, error: 'boom'}), 'boom');
    });
    it('no balance uses dash', () => {
        assertEqual(
            providerDetail({...balanceProvider, balance: null, spend_this_month: null}),
            '—',
        );
    });
});

describe('severityColor', () => {
    it('thresholds', () => {
        assertDeepEqual(severityColor(95), [1.0, 0.3, 0.3]);
        assertDeepEqual(severityColor(80), [1.0, 0.7, 0.2]);
        assertDeepEqual(severityColor(50), [0.3, 0.85, 0.5]);
    });
});

describe('tooltipText', () => {
    it('totals only', () => {
        assertEqual(
            tooltipText({totals: {spend_this_month: 1.5, balance: 20, currency: 'USD'}}),
            'Spent this month: 1.50 USD\nBalance: 20.00 USD',
        );
    });
    it('no data', () => {
        assertEqual(tooltipText(null), 'No data');
    });
});

describe('isRelevant', () => {
    it('manual always relevant', () => {
        assertEqual(isRelevant({type: 'manual'}), true);
    });
    it('error provider relevant', () => {
        assertEqual(isRelevant({type: 'balance', ok: false, balance: null, spend_this_month: null}), true);
    });
    it('zero balance and spend not relevant', () => {
        assertEqual(
            isRelevant({type: 'balance', ok: true, balance: {available: 0}, spend_this_month: 0}),
            false,
        );
    });
    it('positive balance relevant', () => {
        assertEqual(
            isRelevant({type: 'balance', ok: true, balance: {available: 5}, spend_this_month: 0}),
            true,
        );
    });
    it('assertClose sanity', () => {
        assertClose(0.1 + 0.2, 0.3);
    });
});
