"""Tests for `aium report` (bounds generators, build_report, CLI)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from typer.testing import CliRunner

from aium import ledger, storage
from aium.cli import app
from aium.config import save_providers
from aium.models import BalanceProviderConfig, ManualProviderConfig, ProviderType
from aium.report import build_report

runner = CliRunner()

NOW = datetime(2026, 8, 27, 15, 0, tzinfo=UTC)


def test_day_bounds_range():
    days = ledger.day_bounds_range(NOW, 3)
    assert len(days) == 3
    # oldest → newest
    assert all(days[i][0] < days[i + 1][0] for i in range(2))
    assert days[-1][0] == NOW.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    # half-open local midnights
    assert all((e - s) == timedelta(days=1) for s, e in days)
    assert all(s.tzinfo is not None for s, _ in days)


def test_week_bounds_iso():
    weeks = ledger.week_bounds(NOW, 3)
    assert len(weeks) == 3
    # every week starts on a Monday, half-open, oldest → newest
    assert all(s.weekday() == 0 for s, _ in weeks)
    assert all((e - s) == timedelta(days=7) for s, e in weeks)
    assert all(weeks[i][0] < weeks[i + 1][0] for i in range(2))
    # the newest week is the one containing `now`
    assert weeks[-1][0] <= NOW.astimezone() < weeks[-1][1]


def test_month_bounds_range():
    months = ledger.month_bounds_range(NOW, 2)
    assert len(months) == 2
    assert months[0][0].month == 7 and months[0][0].year == 2026
    assert months[1][0].month == 8 and months[1][0].year == 2026
    # every period starts on the 1st, oldest → newest
    assert all(s.day == 1 for s, _ in months)
    assert months[0][1] == months[1][0]
    # July has 31 days
    assert (months[0][1] - months[0][0]) == timedelta(days=31)


def test_month_bounds_range_year_rollover():
    dec = datetime(2026, 12, 15, 12, 0, tzinfo=UTC)
    months = ledger.month_bounds_range(dec, 3)
    assert len(months) == 3
    assert months[0][0].month == 10
    assert months[2][0].month == 12 and months[2][0].year == 2026
    assert months[2][1].month == 1 and months[2][1].year == 2027
    assert (months[2][1] - months[2][0]) == timedelta(days=31)


def test_month_bounds_range_leap_feb():
    mar = datetime(2026, 3, 10, tzinfo=UTC)
    months = ledger.month_bounds_range(mar, 3)
    # [Jan, Feb, Mar 2026]; Feb 2026 is not a leap year
    assert (months[1][1] - months[1][0]) == timedelta(days=28)


def _seed_history():
    """Two providers: balance-only 'ds' and usage 'or' with known daily spend."""
    storage.init_db()
    bounds = ledger.day_bounds_range(NOW, 3)
    d0, d1, d2 = bounds

    # balance provider: spends 1.0 on day0 and 3.0 on day1
    storage.record_snapshot("ds", 10.0, "USD", ts=d0[0] + timedelta(hours=1))
    storage.record_snapshot("ds", 9.0, "USD", ts=d0[0] + timedelta(hours=2))
    storage.record_snapshot("ds", 6.0, "USD", ts=d1[0] + timedelta(hours=2))
    storage.record_snapshot("ds", 6.0, "USD", ts=d2[0] + timedelta(hours=2))

    # usage provider: cumulative usage grows 2.0 on day0 and 2.0 on day1
    storage.record_usage("or", 0.0, ts=d0[0] + timedelta(hours=1))
    storage.record_usage("or", 2.0, ts=d0[0] + timedelta(hours=2))
    storage.record_usage("or", 4.0, ts=d1[0] + timedelta(hours=2))
    storage.record_usage("or", 4.0, ts=d2[0] + timedelta(hours=2))

    save_providers(
        [
            BalanceProviderConfig(
                id="ds", name="DeepSeek", type=ProviderType.balance, kind="deepseek"
            ),
            BalanceProviderConfig(
                id="or", name="OpenRouter", type=ProviderType.balance, kind="openrouter"
            ),
        ]
    )
    return bounds


def test_build_report_day_week_month():
    days = _seed_history()

    rows = build_report("day", 3, now=NOW)
    assert len(rows) == 3
    assert [r["total"] for r in rows] == [3.0, 5.0, 0.0]
    assert rows[0]["providers"] == {"ds": 1.0, "or": 2.0}
    assert rows[1]["providers"] == {"ds": 3.0, "or": 2.0}
    assert rows[2]["providers"] == {}
    # labels and iso bounds match the ledger range helpers
    assert [r["label"] for r in rows] == [s.strftime("%Y-%m-%d") for s, _ in days]
    assert rows[0]["start"] == days[0][0].isoformat()
    assert rows[0]["end"] == days[0][1].isoformat()
    assert datetime.fromisoformat(rows[0]["start"]).tzinfo is not None

    # weeks: current week holds all three days (today is a Thursday), previous is empty
    weeks = ledger.week_bounds(NOW, 2)
    rows = build_report("week", 2, now=NOW)
    assert len(rows) == 2
    assert rows[0]["total"] == 0.0
    assert rows[1]["total"] == 8.0
    iso = weeks[-1][0].isocalendar()
    assert rows[1]["label"] == f"{iso[0]}-W{iso[1]:02d}"
    assert rows[1]["providers"] == {"ds": 4.0, "or": 4.0}

    # months: everything lands in August; July is empty
    rows = build_report("month", 2, now=NOW)
    assert len(rows) == 2
    assert rows[0]["label"] == "2026-07"
    assert rows[0]["total"] == 0.0
    assert rows[1]["label"] == "2026-08"
    assert rows[1]["total"] == 8.0


def test_build_report_unknown_group_raises():
    with pytest.raises(ValueError, match="unknown group"):
        build_report("year", 1)


def test_build_report_provider_filter():
    _seed_history()
    rows = build_report("day", 3, provider_id="ds", now=NOW)
    assert len(rows) == 3
    assert rows[0]["providers"] == {"ds": 1.0}
    assert rows[0]["total"] == 1.0
    # only 'ds' ever appears, and only on days where it actually spent
    assert all(set(r["providers"]) <= {"ds"} for r in rows)
    assert rows[2]["providers"] == {}  # zero-spend day, key omitted

    # unknown provider: periods still render with empty breakdowns
    rows = build_report("day", 3, provider_id="nope", now=NOW)
    assert len(rows) == 3
    assert all(r["providers"] == {} for r in rows)
    assert all(r["total"] == 0.0 for r in rows)


def test_build_report_manual_provider_spreads_nothing():
    storage.init_db()
    save_providers(
        [ManualProviderConfig(id="plus", name="Plus", type=ProviderType.manual, cost=20.0)]
    )
    rows = build_report("day", 3, now=NOW)
    assert len(rows) == 3
    assert all(r["providers"] == {} for r in rows)
    assert all(r["total"] == 0.0 for r in rows)


def test_report_cli_week():
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["report", "--group", "week", "--periods", "2"])
    assert result.exit_code == 0, result.output
    assert "period" in result.output
    assert "total" in result.output


def test_report_cli_unknown_group():
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["report", "--group", "bogus"])
    assert result.exit_code == 1
    assert "Unknown group" in result.output


def test_report_cli_json():
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["report", "--group", "day", "--periods", "2", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert len(payload) == 2
    assert set(payload[0]) == {"label", "start", "end", "total", "providers"}
