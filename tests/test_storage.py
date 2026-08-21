"""Tests for history/sparkline storage helpers."""

from datetime import UTC, datetime

from aium import ledger, storage


def _ts(day: int) -> datetime:
    return datetime(2026, 8, day, 12, 0, tzinfo=UTC)


def test_quota_history_roundtrip(tmp_path):
    db = tmp_path / "h.db"
    storage.init_db(db)
    storage.record_quota("a", 10.0, ts=_ts(1), db=db)
    storage.record_quota("a", 62.0, ts=_ts(2), db=db)
    storage.record_quota("a", 90.0, ts=_ts(3), db=db)
    assert storage.get_quota_history("a", db=db) == [10.0, 62.0, 90.0]


def test_quota_history_limit(tmp_path):
    db = tmp_path / "h.db"
    storage.init_db(db)
    for i in range(1, 6):
        storage.record_quota("a", float(i), ts=_ts(i), db=db)
    assert storage.get_quota_history("a", limit=3, db=db) == [3.0, 4.0, 5.0]


def test_spend_sparkline_from_balance_deltas(tmp_path):
    db = tmp_path / "h.db"
    storage.init_db(db)
    storage.record_snapshot("p", 100.0, "USD", ts=_ts(1), db=db)
    storage.record_snapshot("p", 90.0, "USD", ts=_ts(2), db=db)
    storage.record_snapshot("p", 95.0, "USD", ts=_ts(3), db=db)  # top-up
    storage.record_snapshot("p", 80.0, "USD", ts=_ts(4), db=db)
    assert storage.get_spend_sparkline("p", db=db) == [10.0, 0.0, 15.0]


def test_usage_history_and_sparkline(tmp_path):
    db = tmp_path / "h.db"
    storage.init_db(db)
    storage.record_usage("or", 2.0, ts=_ts(1), db=db)
    storage.record_usage("or", 3.5, ts=_ts(2), db=db)
    storage.record_usage("or", 6.29, ts=_ts(3), db=db)
    history = storage.get_usage_history("or", db=db)
    assert [u for _, u in history] == [2.0, 3.5, 6.29]
    assert storage.get_usage_sparkline("or", db=db) == [1.5, 2.79]


def test_usage_monthly_spend(tmp_path):
    db = tmp_path / "h.db"
    storage.init_db(db)
    # usage before the month
    storage.record_usage("or", 2.0, ts=datetime(2026, 7, 31, 23, 0, tzinfo=UTC), db=db)
    # within August
    storage.record_usage("or", 3.0, ts=_ts(5), db=db)
    storage.record_usage("or", 6.29, ts=_ts(10), db=db)
    assert ledger.usage_monthly_spend(storage.get_usage_history("or", db=db), _ts(10)) == 4.29
