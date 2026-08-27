"""Spend history reporting: aggregate provider spend into day/week/month periods."""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from . import ledger, storage
from .config import load_providers
from .models import ProviderConfig, ProviderType


def provider_series(cfg: ProviderConfig, bounds: list[tuple[datetime, datetime]]) -> list[float]:
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


def daily_series(
    providers: list[ProviderConfig], bounds: list[tuple[datetime, datetime]]
) -> list[float]:
    daily = [0.0] * len(bounds)
    for cfg in providers:
        if not cfg.enabled:
            continue
        series = provider_series(cfg, bounds)
        daily = [round(d + v, 2) for d, v in zip(daily, series, strict=True)]
    return daily


class PeriodRow(TypedDict):
    label: str
    start: str  # isoformat of start
    end: str  # isoformat of end
    total: float
    providers: dict[str, float]


def build_report(
    group: str, periods: int, provider_id: str | None = None, now: datetime | None = None
) -> list[PeriodRow]:
    """Aggregate spend per period across enabled providers, oldest→newest.

    `group` is "day" | "week" | "month". Returns one row per period with the
    total spend and a per-provider breakdown. Spend attribution mirrors
    `provider_series` (usage-cumulative → period_usage_spend; balance →
    period_spend; manual → flat 0).
    """
    if group == "day":
        bounds = ledger.day_bounds_range(now, periods)
    elif group == "week":
        bounds = ledger.week_bounds(now, periods)
    elif group == "month":
        bounds = ledger.month_bounds_range(now, periods)
    else:
        raise ValueError(f"unknown group: {group}")

    providers = [p for p in load_providers() if p.enabled]
    if provider_id is not None:
        providers = [p for p in providers if p.id == provider_id]

    series = [provider_series(p, bounds) for p in providers]
    rows: list[PeriodRow] = []
    for i, (start, end) in enumerate(bounds):
        breakdown: dict[str, float] = {}
        total = 0.0
        for p, p_series in zip(providers, series, strict=True):
            value = round(p_series[i], 2)
            if value != 0.0:
                breakdown[p.id] = value
            total += value
        rows.append(
            PeriodRow(
                label=_period_label(group, start),
                start=start.isoformat(),
                end=end.isoformat(),
                total=round(total, 2),
                providers=breakdown,
            )
        )
    return rows


def _period_label(group: str, start: datetime) -> str:
    if group == "day":
        return start.strftime("%Y-%m-%d")
    if group == "week":
        iso = start.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    return start.strftime("%Y-%m")
