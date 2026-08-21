from datetime import UTC, datetime

from aium.ledger import in_utc_window, month_bounds, monthly_spend


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
