from datetime import UTC, datetime

import pytest

from aium.ledger import (
    in_utc_window,
    local_day_bounds,
    month_bounds,
    monthly_spend,
    period_spend,
    period_usage_spend,
)


def _ts(day: int) -> datetime:
    return datetime(2026, 8, day, tzinfo=UTC)


def test_no_snapshots():
    assert monthly_spend([]) == 0.0


def test_simple_spend():
    snaps = [(_ts(1), 100.0), (_ts(10), 70.0)]
    assert monthly_spend(snaps, _ts(15)) == 30.0


def test_topup_is_not_counted_as_spend():
    snaps = [
        (_ts(1), 100.0),
        (_ts(5), 60.0),  # spent 40
        (_ts(6), 160.0),  # top-up +100
        (_ts(12), 120.0),  # spent 40
    ]
    assert monthly_spend(snaps, _ts(15)) == 80.0


def test_ignores_snapshots_from_previous_month():
    prev_month = datetime(2026, 7, 31, tzinfo=UTC)
    snaps = [(prev_month, 100.0), (_ts(10), 90.0)]
    assert monthly_spend(snaps, _ts(15)) == 10.0


def test_month_bounds_december():
    dec = datetime(2026, 12, 10, tzinfo=UTC)
    start, end = month_bounds(dec)
    assert start.month == 12
    assert end.month == 1 and end.year == 2027


def _utc(h: int, m: int = 0) -> datetime:
    return datetime(2026, 8, 21, h, m, tzinfo=UTC)


def test_in_window_normal():
    # peak 00:30-16:30 UTC
    assert in_utc_window(_utc(10, 0), "00:30-16:30") is True
    assert in_utc_window(_utc(0, 15), "00:30-16:30") is False
    assert in_utc_window(_utc(20, 0), "00:30-16:30") is False


def test_in_window_wraps_midnight():
    # off-peak 16:30-00:30 UTC (wraps across midnight)
    assert in_utc_window(_utc(23, 0), "16:30-00:30") is True
    assert in_utc_window(_utc(0, 15), "16:30-00:30") is True
    assert in_utc_window(_utc(2, 0), "16:30-00:30") is False
    assert in_utc_window(_utc(12, 0), "16:30-00:30") is False


def test_in_window_none_or_malformed():
    assert in_utc_window(_utc(10, 0), None) is False
    assert in_utc_window(_utc(10, 0), "garbage") is False
    assert in_utc_window(_utc(10, 0), "25:99-16:30") is False


def test_period_spend_within_day():
    day_start = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    day_end = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)
    snaps = [
        (datetime(2026, 8, 20, 23, 0, tzinfo=UTC), 100.0),  # carried in
        (datetime(2026, 8, 21, 9, 0, tzinfo=UTC), 95.0),
        (datetime(2026, 8, 21, 15, 0, tzinfo=UTC), 90.0),  # spent 5 then 5
    ]
    assert period_spend(snaps, day_start, day_end) == 10.0


def test_period_usage_spend():
    day_start = datetime(2026, 8, 21, 0, 0, tzinfo=UTC)
    day_end = datetime(2026, 8, 22, 0, 0, tzinfo=UTC)
    hist = [
        (datetime(2026, 8, 20, 23, 0, tzinfo=UTC), 6.28),
        (datetime(2026, 8, 21, 9, 0, tzinfo=UTC), 6.40),
        (datetime(2026, 8, 21, 18, 0, tzinfo=UTC), 7.10),
    ]
    assert period_usage_spend(hist, day_start, day_end) == pytest.approx(0.82, rel=1e-3)


def test_local_day_bounds_is_midnight():
    start, end = local_day_bounds()
    assert start.hour == 0 and start.minute == 0
    assert (end - start).days == 1
