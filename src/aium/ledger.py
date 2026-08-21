"""Ledger: derive monthly spend from balance snapshots (top-up aware)."""

from __future__ import annotations

from datetime import UTC, datetime


def month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        nxt = start.replace(year=now.year + 1, month=1)
    else:
        nxt = start.replace(month=now.month + 1)
    return start, nxt


def monthly_spend(snapshots: list[tuple[datetime, float]], now: datetime | None = None) -> float:
    """Total spend this month = opening balance + deposits - closing balance.

    Positive balance jumps are treated as top-ups (deposits) so recharges do not
    inflate the computed spend. The opening balance is the last snapshot before
    the month when available (the balance carried into the month); otherwise it
    is the first snapshot of the month. Providers without any snapshot this
    month return 0.
    """
    start, end = month_bounds(now)
    prev = [b for ts, b in snapshots if ts < start]
    month = [(ts, b) for ts, b in snapshots if start <= ts < end]
    if not month:
        return 0.0

    opening = prev[-1] if prev else month[0][1]
    closing = month[-1][1]
    deposits = 0.0
    for (_, prev_b), (_, cur_b) in zip(month, month[1:], strict=False):
        delta = cur_b - prev_b
        if delta > 0:
            deposits += delta

    spend = opening + deposits - closing
    return max(0.0, round(spend, 6))


def usage_monthly_spend(
    history: list[tuple[datetime, float]], now: datetime | None = None
) -> float:
    """Monthly spend from a cumulative-usage history.

    `history` is a list of (timestamp, cumulative usage) pairs, ascending. Spend
    this month = closing cumulative usage minus the cumulative usage carried
    into the month (the last record before the month start, or the first record
    of the month). Robust to cumulative counters and monthly resets.
    """
    start, end = month_bounds(now)
    prev = [u for ts, u in history if ts < start]
    month = [(ts, u) for ts, u in history if start <= ts < end]
    if not month:
        return 0.0

    opening = prev[-1] if prev else month[0][1]
    closing = month[-1][1]
    return max(0.0, round(closing - opening, 4))


def in_utc_window(now: datetime, window: str | None) -> bool:
    """Return True if `now` (UTC-aware) falls within a 'HH:MM-HH:MM' UTC window.

    The window may wrap across midnight (e.g. '16:30-00:30'). Malformed or
    missing windows return False.
    """
    if not window:
        return False
    try:
        start_s, end_s = window.split("-")
        start_min = _parse_hhmm(start_s)
        end_min = _parse_hhmm(end_s)
    except ValueError, IndexError:
        return False
    now_min = now.hour * 60 + now.minute
    if start_min <= end_min:
        return start_min <= now_min < end_min
    return now_min >= start_min or now_min < end_min


def _parse_hhmm(value: str) -> int:
    hour_s, _, minute_s = value.partition(":")
    hour, minute = int(hour_s), int(minute_s)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError
    return hour * 60 + minute
