"""Terminal spend dashboard: braille sparklines of usage history."""

from __future__ import annotations

import asyncio
import os
import sys
import time

from rich.console import Console

from . import spark, storage
from .models import StatusFile
from .service import poll as run_poll

#: Console with rich's number highlighter disabled (labels are raw).
_console = Console(highlight=False)


def _money(value: float | None) -> str:
    return f"${value:,.2f}" if value is not None else "-"


def health_key(p) -> str | None:
    """The health dot color key for a provider (mirrors the extension's thresholds).

    Quota health wins; prepaid balance health follows ``balance-critical`` (1)
    / ``balance-warn`` (10). Budget balances and missing data get no signal.
    """
    if p.quota:
        peak = max((w.utilization_pct for w in p.quota), default=0)
        if peak >= 90:
            return "red"
        if peak >= 70:
            return "yellow"
        return "green"
    if p.balance and p.balance_kind == "prepaid":
        available = p.balance.available
        if available < 1:
            return "red"
        if available < 10:
            return "yellow"
        return "green"
    return None


def _header(status: StatusFile, totals) -> str:
    days = len(totals.spend_daily or [])
    rng = ""
    if days:
        month = status.generated_at.strftime("%b")
        rng = f" · {month} 01→{month} {days:02d}"
    return (
        f"aium › {_money(totals.spend_this_month)}/mo · "
        f"{_money(totals.spend_today)} today · {_money(totals.balance)} balance{rng}"
    )


def render_frame(
    status: StatusFile,
    *,
    height: int = 3,
    samples: int | None = None,
    provider_id: str | None = None,
    width: int = 80,
) -> list[str]:
    """The dashboard lines: header + one rounded box per series."""
    pal = spark.palette(os.environ.get("AIUM_THEME") == "light")
    inner = max(10, width - 2)
    totals = status.totals
    lines = [_header(status, totals)]

    daily = list(totals.spend_daily or [])
    if samples:
        daily = daily[-samples:]
    avg = sum(daily) / len(daily) if daily else 0.0
    label = f"{_money(avg)}/day · today {_money(totals.spend_today)}"
    lines += spark.box_lines(
        "daily", label, spark.render_sparkline(daily, height), pal["sky"], pal["border"], inner
    )

    for p in status.providers:
        if provider_id and p.id != provider_id:
            continue
        if not p.ok:
            blank = "\n".join([""] * height)
            lines += spark.box_lines(
                p.id, f"error: {p.error or 'error'}", blank, pal["red"], pal["border"], inner
            )
            continue
        if p.type == "manual":
            sub = p.subscription
            assert sub is not None
            label = f"{_money(sub.cost)}/{sub.cycle.value} · {p.days_until_renewal}d"
            # Fixed-cost subscription: no usage history to plot, keep it compact.
            lines += spark.box_lines(
                p.id, label, "\n".join([""] * 1), pal["sky"], pal["border"], inner
            )
            continue

        bal = ""
        if p.balance:
            if p.balance_label and p.balance_label != "balance":
                bal = f"{p.balance_label} {_money(p.balance.available)}"
            else:
                bal = _money(p.balance.available)
        spend = f"{_money(p.spend_this_month)}/mo" if p.spend_this_month is not None else "-"
        parts = [part for part in (bal, spend) if part]
        if p.quota:
            parts.append(" · ".join(f"{w.label} {w.utilization_pct}%" for w in p.quota))
        label = " · ".join(parts)

        series = (
            p.sparkline or storage.get_usage_level(p.id) or storage.get_spend_sparkline(p.id) or []
        )
        if samples:
            series = series[-samples:]
        spend_spark = spark.render_sparkline(series, height) if any(series) else None

        quota_spark = None
        if p.quota:
            qhist = storage.get_quota_history(p.id)
            if any(qhist):
                quota_spark = spark.render_sparkline(qhist, height, vmax=100)

        key = health_key(p)
        health = pal[key] if key else None
        lines += spark.provider_box_lines(
            p.id,
            label,
            spend_spark,
            pal["sky"],
            quota_spark,
            pal["mauve"],
            pal["border"],
            inner,
            health,
        )

    return lines


def run_stats(
    *,
    once: bool,
    poll: bool,
    interval: float,
    height: int,
    samples: int | None,
    provider_id: str | None,
    width: int,
    tty: bool,
) -> None:
    """Render the dashboard once or live (redraw on each refresh cycle)."""
    storage.init_db()
    eff_interval = interval or (60.0 if poll else 5.0)

    def frame() -> list[str]:
        status: StatusFile | None = asyncio.run(run_poll()) if poll else storage.read_status()
        if status is None:
            return ["No cached status. Run 'aium poll' first."]
        return render_frame(
            status, height=height, samples=samples, provider_id=provider_id, width=width
        )

    if once or not tty:
        _console.print("\n".join(frame()))
        return

    sys.stdout.write("\033[?25l")  # hide cursor while redrawing
    try:
        while True:
            # Full-screen clear: the block can be taller than the terminal, so
            # per-line clearing scrolls and leaves stale rows (header repeats).
            sys.stdout.write("\033[H\033[J")
            sys.stdout.flush()
            _console.print("\n".join(frame()))
            time.sleep(eff_interval)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write("\033[?25h")  # restore cursor
