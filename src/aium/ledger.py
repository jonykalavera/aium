"""Ledger: derive monthly spend from balance snapshots (top-up aware)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def month_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    now = now or datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        nxt = start.replace(year=now.year + 1, month=1)
    else:
        nxt = start.replace(month=now.month + 1)
    return start, nxt


def local_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Start/end of the current **local** day (midnight to midnight, aware)."""
    now = now or datetime.now().astimezone()
    local = now.astimezone()
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    # Next local midnight (handles DST-free simple case; one day ahead).
    end = start + timedelta(days=1)
    # Convert to a stable timezone-free comparison by returning both as-is; the
    # caller compares against UTC-aware snapshots (Python handles aware vs aware).
    return start, end


def local_month_days(now: datetime | None = None) -> list[tuple[datetime, datetime]]:
    """Bounds for each local day of the current month up to today, inclusive."""
    now = now or datetime.now().astimezone()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    days: list[tuple[datetime, datetime]] = []
    day = start
    while day <= today:
        days.append((day, day + timedelta(days=1)))
        day += timedelta(days=1)
    return days


def period_spend(
    snapshots: list[tuple[datetime, float]],
    start: datetime,
    end: datetime,
) -> float:
    """Spend over `[start, end)` = opening balance + deposits - closing balance.

    Positive balance jumps are treated as top-ups (deposits). Opening balance is
    the last snapshot before `start` (carried in), else the first in-period.
    Returns 0 if there is no snapshot in the period.
    """
    prev = [b for ts, b in snapshots if ts < start]
    period = [(ts, b) for ts, b in snapshots if start <= ts < end]
    if not period:
        return 0.0

    opening = prev[-1] if prev else period[0][1]
    closing = period[-1][1]
    deposits = 0.0
    for (_, prev_b), (_, cur_b) in zip(period, period[1:], strict=False):
        delta = cur_b - prev_b
        if delta > 0:
            deposits += delta

    spend = opening + deposits - closing
    return max(0.0, round(spend, 6))


def monthly_spend(snapshots: list[tuple[datetime, float]], now: datetime | None = None) -> float:
    """Total spend this month = opening balance + deposits - closing balance."""
    start, end = month_bounds(now)
    return period_spend(snapshots, start, end)


def period_usage_spend(
    history: list[tuple[datetime, float]],
    start: datetime,
    end: datetime,
) -> float:
    """Spend over `[start, end)` from a cumulative-usage history.

    `history` is (timestamp, cumulative usage) ascending. Spend = closing usage
    minus the usage carried into the period (last record before `start`, or the
    first in-period). Robust to cumulative counters and resets.
    """
    prev = [u for ts, u in history if ts < start]
    period = [(ts, u) for ts, u in history if start <= ts < end]
    if not period:
        return 0.0

    opening = prev[-1] if prev else period[0][1]
    closing = period[-1][1]
    return max(0.0, round(closing - opening, 4))


def usage_monthly_spend(
    history: list[tuple[datetime, float]], now: datetime | None = None
) -> float:
    """Monthly spend from a cumulative-usage history."""
    start, end = month_bounds(now)
    return period_usage_spend(history, start, end)


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
