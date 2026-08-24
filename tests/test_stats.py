"""Tests for the braille sparkline renderer and stats dashboard."""

from __future__ import annotations

import re
from datetime import UTC, datetime

import pytest

from aium import storage
from aium.models import Balance, ProviderStatus, ProviderType, QuotaWindow, StatusFile, Totals
from aium.spark import _display_width, box_lines, provider_box_lines, render_sparkline
from aium.stats import render_frame


def _plain(line: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", line)


def test_sparkline_empty_returns_blank_rows():
    lines = render_sparkline([], height=3).split("\n")
    assert len(lines) == 3
    assert all(line == "" for line in lines)


def test_sparkline_all_zero_keeps_height():
    lines = render_sparkline([0, 0, 0], height=3, vmax=100).split("\n")
    assert len(lines) == 3
    assert all(chr(0x2800) in line for line in lines)


def test_sparkline_nonzero_minimum_unit():
    # value 1 on a 0..100 scale (height 1 = 4 units) still renders one unit.
    line = render_sparkline([1], height=1, vmax=100)
    assert line and ord(line[0]) > 0x2800


def test_sparkline_caps_at_height():
    # value 100 vs vmax 10 would be 40 units; height 1 caps it at 4.
    line = render_sparkline([100], height=1, vmax=10)
    cell = ord(line) - 0x2800
    assert cell & 0x47 == 0x47  # left column fully filled


def test_sparkline_relative_scale():
    # [0, 2, 4] on relative scale: max 4 -> scaled [0, 2, 4] units (height 1).
    line = render_sparkline([0, 2, 4], height=1)
    assert len(line) == 2  # (3 + 1) // 2 cells
    cell0 = ord(line[0]) - 0x2800
    assert cell0 & 0x47 == 0  # first sample zero -> left column empty
    assert cell0 & 0xB8 == 0xA0  # second sample fills 2 of 4 right dots


def test_box_lines_count_and_label():
    spark = "\n".join(["a", "b", "c"])
    lines = box_lines("test", "1.00 USD", spark, "#89dceb", "#6c7086", inner_width=20)
    assert len(lines) == 5  # spark rows + top + bottom
    assert "TEST" in _plain(lines[0])
    assert "1.00 USD" in _plain(lines[0])


@pytest.fixture(autouse=True)
def _db():
    storage.init_db()


def _status() -> StatusFile:
    return StatusFile(
        generated_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        totals=Totals(
            spend_this_month=9.0,
            spend_today=3.0,
            balance=15.73,
            currency="USD",
            spend_daily=[0.0, 2.0, 4.0, 3.0],
        ),
        providers=[
            ProviderStatus(
                id="ds",
                name="DeepSeek",
                type=ProviderType.balance,
                currency="USD",
                balance=Balance(available=15.71),
                balance_kind="prepaid",
                spend_this_month=14.8,
                spend_today=1.0,
                sparkline=[1.0, 2.0, 3.0],
            ),
            ProviderStatus(
                id="an",
                name="Anthropic",
                type=ProviderType.balance,
                currency="USD",
                spend_this_month=0.0,
                quota=[
                    QuotaWindow(label="5h", utilization_pct=85),
                    QuotaWindow(label="7d", utilization_pct=10),
                ],
            ),
        ],
    )


def test_frame_header_and_daily_box():
    lines = render_frame(_status(), width=80)
    assert "aium › $9.00/mo · $3.00 today · $15.73 balance · Aug 01→Aug 04" in _plain(lines[0])
    daily_top = next(line for line in lines if _plain(line).startswith("╭─ DAILY"))
    assert "$2.25/day · today $3.00" in _plain(daily_top)


def test_frame_provider_boxes():
    lines = render_frame(_status(), width=80)
    text = "\n".join(_plain(line) for line in lines)
    assert "╭─ DS $15.71 · $14.80/mo" in text
    assert "╭─ AN $0.00/mo · 5h 85% · 7d 10%" in text
    assert any(_plain(line).startswith("│S") for line in lines)  # consumption section
    assert any(_plain(line).startswith("│Q") for line in lines)  # quota section


def test_frame_one_box_per_provider():
    lines = render_frame(_status(), width=80)
    text = "\n".join(_plain(line) for line in lines)
    assert text.count("╭─ AN") == 1
    assert text.count("╭─ DS") == 1
    assert "QUOTA" not in text  # no separate quota box anymore


def test_frame_quota_severity_colors():
    lines = render_frame(_status(), width=80)
    quota_row = next(line for line in lines if _plain(line).startswith("│Q"))
    assert "#f9e2af" in quota_row  # 85% -> amber


def _provider(available: float, quota_pct: int | None = None) -> ProviderStatus:
    return ProviderStatus(
        id="p",
        name="Provider",
        type=ProviderType.balance,
        currency="USD",
        balance=Balance(available=available),
        balance_kind="prepaid",
        spend_this_month=2.0,
        sparkline=[1.0, 2.0, 3.0],
        quota=(
            [QuotaWindow(label="5h", utilization_pct=quota_pct)] if quota_pct is not None else []
        ),
    )


def _frame_for(p: ProviderStatus) -> list[str]:
    status = StatusFile(
        generated_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
        totals=Totals(currency="USD"),
        providers=[p],
    )
    return render_frame(status, width=80)


def test_spend_box_color_follows_health():
    spend_top = next(line for line in _frame_for(_provider(25)) if _plain(line).startswith("╭─ P"))
    assert "#a6e3a1" in spend_top  # balance 25 -> green

    spend_top = next(line for line in _frame_for(_provider(5)) if _plain(line).startswith("╭─ P"))
    assert "#f9e2af" in spend_top  # balance 5 -> amber

    spend_top = next(line for line in _frame_for(_provider(0.5)) if _plain(line).startswith("╭─ P"))
    assert "#f38ba8" in spend_top  # balance 0.5 -> red


def test_spend_box_color_follows_quota_health():
    top = _frame_for(_provider(25, quota_pct=95))
    spend_top = next(line for line in top if _plain(line).startswith("╭─ P"))
    assert "#f38ba8" in spend_top  # quota 95% wins over healthy balance


def test_frame_provider_filter():
    lines = render_frame(_status(), width=80, provider_id="an")
    text = "\n".join(_plain(line) for line in lines)
    assert "DS" not in text
    assert "╭─ AN $0.00/mo · 5h 85% · 7d 10%" in text


def test_provider_box_sections_and_spacer():
    spend = render_sparkline([1.0, 2.0, 3.0], 3)
    quota = render_sparkline([40.0, 80.0, 90.0], 3, vmax=100)
    lines = provider_box_lines(
        "ds", "$15.71", spend, "#a6e3a1", quota, "#f38ba8", "#6c7086", inner_width=20
    )
    text = _plain("\n".join(lines))
    assert sum(1 for line in lines if _plain(line).startswith("│S")) == 3
    assert sum(1 for line in lines if _plain(line).startswith("│Q")) == 3
    assert "│" + " " * 20 + "│" in text  # spacer between sections
    assert len(lines) == 1 + 3 + 1 + 3 + 1


def test_provider_box_no_quota_has_no_gutter():
    spend = render_sparkline([1.0, 2.0, 3.0], 3)
    lines = provider_box_lines(
        "ds", "$15.71", spend, "#a6e3a1", None, "#6c7086", "#6c7086", inner_width=20
    )
    text = _plain("\n".join(lines))
    assert "│ S " not in text
    assert "│ Q " not in text
    assert len(lines) == 1 + 3 + 1


def test_box_lines_cjk_title_truncates_to_box_width():
    lines = box_lines(
        "glm", "error: 当前用户不存在coding plan", "\n", "#f38ba8", "#6c7086", inner_width=20
    )
    for line in lines:
        assert _display_width(_plain(line)) <= 22  # inner_width + 2 borders
