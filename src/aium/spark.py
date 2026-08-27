"""Minimal braille sparkline renderer (vendored, no dependencies)."""

from __future__ import annotations

import unicodedata

#: Left/right braille column dot bits, indexed by dot offset **from the bottom**
#: (offset 0 = lowest dot in the cell, 3 = top dot).
_LEFT = (0x40, 0x04, 0x02, 0x01)
_RIGHT = (0x80, 0x20, 0x10, 0x08)

#: Catppuccin Mocha (dark) and Latte (light) accents.
_PALETTES = {
    "dark": {
        "border": "#6c7086",
        "sky": "#89dceb",
        "green": "#a6e3a1",
        "yellow": "#f9e2af",
        "red": "#f38ba8",
        "mauve": "#cba6f7",
    },
    "light": {
        "border": "#6c6f85",
        "sky": "#04a5e5",
        "green": "#40a02b",
        "yellow": "#df8e1d",
        "red": "#d20f39",
        "mauve": "#8839ef",
    },
}


def palette(light: bool = False) -> dict[str, str]:
    """The color set for a theme (dark = Mocha, light = Latte)."""
    return _PALETTES["light" if light else "dark"]


def render_sparkline(values: list[float], height: int = 3, vmax: float | None = None) -> str:
    """A braille bar sparkline of ``values`` as a ``height``-line string.

    Bars grow upward from a bottom baseline (the last row). ``vmax`` pins the
    scale (e.g. ``100`` for a percentage); ``None`` uses the window's maximum.
    A non-zero value always renders at least one unit so small values stay
    visible on a fixed scale. Values beyond the cap never grow past ``height``.
    A **constant** relative series (all values equal) renders as a flat line on
    the baseline instead of "full" — it means "no change", not "at 100%".
    """
    if not values:
        return "\n".join([""] * height)
    top = vmax if vmax else max(values)
    if top <= 0:
        return "\n".join([""] * height)
    units = height * 4
    if vmax is None and min(values) == max(values):
        scaled = [1] * len(values)
    else:
        scaled = [min(units, max(1, round(v / top * units))) if v > 0 else 0 for v in values]
    return _render_bars(scaled, height)


def _render_bars(scaled: list[int], height: int) -> str:
    """Braille cells for per-sample unit heights, bottom-aligned."""
    cells = max(1, (len(scaled) + 1) // 2)
    grid = [[0] * cells for _ in range(height)]
    for i, value in enumerate(scaled):
        side = _RIGHT if i % 2 else _LEFT
        cell = i // 2
        for unit in range(value):
            row = unit // 4
            dot = unit % 4
            grid[row][cell] |= side[dot]
    lines = []
    for row in range(height - 1, -1, -1):
        lines.append("".join(chr(0x2800 | grid[row][c]) for c in range(cells)))
    return "\n".join(lines)


def _display_width(text: str) -> int:
    """Terminal display columns: CJK (wide/fullwidth) characters count as 2."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def _truncate_display(text: str, max_width: int) -> str:
    """Truncate ``text`` so it fits in ``max_width`` display columns, with ``…``."""
    if _display_width(text) <= max_width:
        return text
    result = ""
    for char in text:
        if _display_width(result + char) > max_width - 1:
            break
        result += char
    return result + "…"


def _title_line(
    name: str,
    label: str,
    color: str,
    border: str,
    inner_width: int,
    health: str | None = None,
) -> str:
    """The top border line: optional ``health`` dot, then label, dashed fill."""
    raw = f"{name.upper()} {label}".replace("\n", " ").strip()
    max_title = max(1, inner_width - 5 - (2 if health else 0))
    title = _truncate_display(raw, max_title)
    dot = f"[{health}]●[/] " if health else ""
    fill = max(
        0,
        inner_width + 2 - len("╭─ ") - (2 if health else 0) - _display_width(title) - len(" ╮"),
    )
    return f"[{border}]╭─ [/]{dot}[{color}]{title}[/] [{border}]{'─' * fill}╮[/]"


def box_lines(
    name: str,
    label: str,
    spark: str,
    color: str,
    border: str,
    inner_width: int,
) -> list[str]:
    """Rounded box lines: label in the top border, graph full-bleed below.

    Lines carry rich markup tags (``[hex]...[/]``) so a ``rich`` console can
    render them; ``inner_width`` is the graph width in characters. Long labels
    are truncated by display width so the top border never overflows (CJK-aware).
    """
    lines = [_title_line(name, label, color, border, inner_width)]
    rows = spark.split("\n") or [""]
    for row in rows:
        content = row.replace("\u2800", " ").ljust(inner_width)
        lines.append(f"[{border}]│[/][{color}]{content}[/][{border}]│[/]")
    lines.append(f"[{border}]╰[/]{'─' * inner_width}[{border}]╯[/]")
    return lines


def provider_box_lines(
    name: str,
    label: str,
    spend_spark: str | None,
    spend_color: str,
    quota_spark: str | None,
    quota_color: str,
    border: str,
    inner_width: int,
    health: str | None = None,
) -> list[str]:
    """One grouped box per provider: consumption on top, quota below.

    ``spend_spark``/``quota_spark`` are ``render_sparkline`` strings; ``None``
    hides that section entirely. Sections are tagged ``S``/``Q`` and the
    optional ``health`` dot (a color) sits next to the provider name.
    """
    lines = [_title_line(name, label, border, border, inner_width, health)]

    def rows_for(spark: str, tag: str | None, color: str) -> None:
        for row in spark.split("\n") or [""]:
            content = row.replace("\u2800", " ").ljust(inner_width)
            if tag:
                content = tag + " " + content[: inner_width - 2].ljust(inner_width - 2)
            lines.append(f"[{border}]│[/][{color}]{content}[/][{border}]│[/]")

    if spend_spark is not None:
        rows_for(spend_spark, "S" if quota_spark is not None else None, spend_color)
    if quota_spark is not None:
        if spend_spark is not None:
            lines.append(f"[{border}]│[/]{' ' * inner_width}[{border}]│[/]")
        rows_for(quota_spark, "Q", quota_color)
    lines.append(f"[{border}]╰[/]{'─' * inner_width}[{border}]╯[/]")
    return lines
