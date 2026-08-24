"""Polling service: collect provider state, persist history, produce status."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict, cast

import httpx

from . import ledger, storage
from .config import load_providers, load_settings
from .models import (
    ProviderConfig,
    ProviderStatus,
    ProviderType,
    StatusFile,
    Totals,
    utcnow,
)
from .providers import BalanceProvider, CloudProvider, ProviderError, build_provider
from .providers.manual import ManualSubscription
from .providers.registry import get_spec
from .secrets import SecretsStore


class _BaseKwargs(TypedDict, total=False):
    id: str
    name: str
    type: ProviderType
    currency: str
    usage_url: str | None
    peak: bool | None
    balance_kind: str | None
    balance_label: str | None


async def _collect(
    cfg: ProviderConfig,
    http: httpx.AsyncClient,
    secrets: SecretsStore,
    day: tuple[datetime, datetime],
) -> ProviderStatus:
    spec = get_spec(getattr(cfg, "kind", "manual")) if cfg.type != ProviderType.manual else None
    peak_window = cfg.peak_window or (spec.peak_window if spec else None)
    peak = ledger.in_utc_window(utcnow(), peak_window) if peak_window else None
    base: _BaseKwargs = {
        "id": cfg.id,
        "name": cfg.name,
        "type": cfg.type,
        "currency": cfg.currency,
        "usage_url": cfg.usage_url or (spec.usage_url if spec and spec.usage_url else None),
        "peak": peak,
        "balance_kind": spec.balance_kind if spec else None,
        "balance_label": spec.balance_label if spec else None,
    }

    if cfg.type == ProviderType.manual:
        sub = cast(ManualSubscription, build_provider(cfg))
        return ProviderStatus(
            **base,
            subscription=cfg,
            spend_this_month=sub.monthly_equivalent(),
            spend_today=0.0,
            days_until_renewal=sub.days_until_renewal(),
        )

    secret = secrets.get(cfg.id)
    try:
        provider = build_provider(cfg)
        if isinstance(provider, BalanceProvider):
            balance = await provider.fetch_balance(http, secret)
            usage = await provider.fetch_usage(http, secret)
            quota = await provider.fetch_quota(http, secret)
            plan = await provider.fetch_plan(http, secret)

            sparkline: list[float] | None = None
            quota_sparkline: list[float] | None = None
            spend: float | None = None
            day_start, day_end = day

            if usage is not None:
                storage.record_usage(cfg.id, usage.total)
                if getattr(provider, "usage_cumulative", False):
                    spend = ledger.usage_monthly_spend(storage.get_usage_history(cfg.id))
                else:
                    spend = usage.total
                spend_today = ledger.period_usage_spend(
                    storage.get_usage_history(cfg.id), day_start, day_end
                )
                sparkline = storage.get_usage_sparkline(cfg.id)
            else:
                spend_today = None

            if balance is not None:
                storage.record_snapshot(cfg.id, balance.available, balance.currency)
                if sparkline is None:
                    sparkline = storage.get_spend_sparkline(cfg.id)

            if spend is None and balance is not None:
                spend = ledger.monthly_spend(storage.get_snapshots(cfg.id))
            if spend_today is None and balance is not None:
                spend_today = ledger.period_spend(storage.get_snapshots(cfg.id), day_start, day_end)
            if spend_today is None:
                spend_today = 0.0

            if quota:
                quota_peak = max(w.utilization_pct for w in quota)
                storage.record_quota(cfg.id, quota_peak)
                quota_sparkline = storage.get_quota_history(cfg.id)

            return ProviderStatus(
                **base,
                ok=True,
                balance=balance,
                usage=usage,
                quota=quota,
                sparkline=sparkline,
                quota_sparkline=quota_sparkline,
                plan=plan,
                spend_this_month=spend,
                spend_today=spend_today,
                last_updated=utcnow(),
            )
        if isinstance(provider, CloudProvider):
            usage = await provider.fetch_cost_to_date(http, secret)
            return ProviderStatus(
                **base,
                ok=True,
                usage=usage,
                spend_this_month=usage.total,
                last_updated=utcnow(),
            )
        raise ProviderError(f"unsupported provider type: {type(provider).__name__}")
    except ProviderError as exc:
        return ProviderStatus(**base, ok=False, error=str(exc))
    except httpx.HTTPStatusError as exc:
        return ProviderStatus(**base, ok=False, error=f"HTTP {exc.response.status_code}")
    except Exception as exc:  # noqa: BLE001 - never let one provider crash the poll
        return ProviderStatus(**base, ok=False, error=str(exc))


def _aggregate(
    statuses: list[ProviderStatus],
    base_currency: str,
    spend_daily: list[float] | None = None,
) -> Totals:
    spend = round(sum(s.spend_this_month or 0.0 for s in statuses), 2)
    spend_today = round(sum(s.spend_today or 0.0 for s in statuses), 2)
    # Only prepaid credit balances are summed into the total; budget-style
    # balances (e.g. Anthropic's remaining monthly limit) are shown per-provider.
    balance = round(
        sum(s.balance.available for s in statuses if s.balance and s.balance_kind == "prepaid"),
        2,
    )
    return Totals(
        spend_this_month=spend,
        spend_today=spend_today,
        balance=balance,
        currency=base_currency,
        spend_daily=spend_daily or [],
    )


def _provider_daily_spend(
    cfg: ProviderConfig, bounds: list[tuple[datetime, datetime]]
) -> list[float]:
    """Spend per local day from history, mirroring the `_collect` attribution.

    Cumulative/usage providers derive days from `usage_history`; balance-only
    providers from `snapshots`. Manual subscriptions spread nothing (their flat
    cost already lands in `spend_this_month`).
    """
    if cfg.type == ProviderType.manual:
        return [0.0] * len(bounds)
    history = storage.get_usage_history(cfg.id)
    if history:
        return [round(ledger.period_usage_spend(history, s, e), 2) for s, e in bounds]
    snapshots = storage.get_snapshots(cfg.id)
    if snapshots:
        return [round(ledger.period_spend(snapshots, s, e), 2) for s, e in bounds]
    return [0.0] * len(bounds)


def _daily_series(
    providers: list[ProviderConfig], bounds: list[tuple[datetime, datetime]]
) -> list[float]:
    daily = [0.0] * len(bounds)
    for cfg in providers:
        if not cfg.enabled:
            continue
        series = _provider_daily_spend(cfg, bounds)
        daily = [round(d + v, 2) for d, v in zip(daily, series, strict=True)]
    return daily


async def poll(http: httpx.AsyncClient | None = None) -> StatusFile:
    settings = load_settings()
    providers = load_providers()
    secrets = SecretsStore()
    day = ledger.local_day_bounds()
    bounds = ledger.local_month_days()

    own_client = http is None
    if http is None:
        http = httpx.AsyncClient(timeout=30.0)

    try:
        statuses = [await _collect(cfg, http, secrets, day) for cfg in providers if cfg.enabled]
    finally:
        if own_client:
            await http.aclose()

    totals = _aggregate(statuses, settings.base_currency, _daily_series(providers, bounds))
    status = StatusFile(totals=totals, providers=statuses)
    storage.write_status(status)
    return status
