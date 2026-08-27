"""AIUM command-line interface."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Annotated

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from . import paths, storage
from .config import (
    get_provider,
    load_providers,
    load_settings,
    remove_provider,
    save_providers,
    upsert_provider,
)
from .models import (
    BalanceProviderConfig,
    Cycle,
    ManualProviderConfig,
    ProviderType,
    StatusFile,
)
from .providers.registry import all_kinds, get_spec
from .report import build_report
from .secrets import SecretsStore
from .service import poll as run_poll
from .stats import run_stats as run_stats_dashboard

app = typer.Typer()
providers_app = typer.Typer(help="Add, update, list and remove providers")
keys_app = typer.Typer(help="Store and remove API keys in the system keyring")
app.add_typer(providers_app, name="providers")
app.add_typer(keys_app, name="keys")

console = Console()


@app.command()
def init() -> None:
    """Create config directories, database and default config file."""
    paths.ensure_dirs()
    storage.init_db()
    cfg = paths.config_file()
    if not cfg.exists():
        cfg.write_text("base_currency: USD\npoll_interval_minutes: 60\n")
    console.print(f"[green]Initialized[/green] in {paths.config_dir()}")


@providers_app.command()
def add(
    kind: str = typer.Argument(..., help="Provider kind: " + ", ".join(all_kinds())),
    provider_id: str | None = typer.Option(None, "--id", help="Unique id (defaults to kind)"),
    name: str | None = typer.Option(None, "--name", help="Display name"),
    currency: str = typer.Option("USD", "--currency"),
    pricing_url: str | None = typer.Option(None, "--pricing-url"),
    cost: float | None = typer.Option(None, "--cost", help="Cost per cycle (manual only)"),
    cycle: str = typer.Option("monthly", "--cycle", help="monthly | yearly (manual only)"),
    renewal_day: int = typer.Option(1, "--renewal-day", min=1, max=31),
) -> None:
    """Add a provider."""
    spec = get_spec(kind)
    if spec is None:
        console.print(f"[red]Unknown kind[/red] '{kind}'. Available: {', '.join(all_kinds())}")
        raise typer.Exit(1)

    providers = load_providers()
    pid = provider_id or kind
    if get_provider(providers, pid):
        console.print(f"[red]Provider[/red] '{pid}' already exists")
        raise typer.Exit(1)

    if kind == "manual":
        if cost is None:
            console.print("[red]--cost is required for manual providers[/red]")
            raise typer.Exit(1)
        provider: object = ManualProviderConfig(
            id=pid,
            name=name or spec.name,
            type=ProviderType.manual,
            currency=currency,
            pricing_url=pricing_url,
            cost=cost,
            cycle=Cycle(cycle),
            renewal_day=renewal_day,
        )
    else:
        provider = BalanceProviderConfig(
            id=pid,
            name=name or spec.name,
            type=ProviderType.balance,
            kind=kind,
            currency=spec.currency,
            pricing_url=pricing_url or spec.pricing_url,
            usage_url=spec.usage_url or None,
            peak_window=spec.peak_window,
        )

    save_providers(upsert_provider(providers, provider))
    console.print(f"[green]Added[/green] '{pid}' ({spec.name})")


@providers_app.command()
def update(
    provider_id: str = typer.Argument(..., help="Provider id"),
    name: str | None = typer.Option(None, "--name"),
    currency: str | None = typer.Option(None, "--currency"),
    pricing_url: str | None = typer.Option(None, "--pricing-url"),
    usage_url: str | None = typer.Option(None, "--usage-url", help="Consumption/dashboard page"),
    peak_window: str | None = typer.Option(
        None,
        "--peak-window",
        help="UTC peak window 'HH:MM-HH:MM' (e.g. '00:30-16:30'); 'none' clears it",
    ),
    cost: float | None = typer.Option(None, "--cost"),
    cycle: str | None = typer.Option(None, "--cycle", help="monthly | yearly"),
    renewal_day: int | None = typer.Option(None, "--renewal-day", min=1, max=31),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled"),
) -> None:
    """Update provider fields."""
    providers = load_providers()
    provider = get_provider(providers, provider_id)
    if provider is None:
        console.print(f"[red]Provider[/red] '{provider_id}' not found")
        raise typer.Exit(1)

    updates: dict[str, object] = {}
    for field, value in (
        ("name", name),
        ("currency", currency),
        ("pricing_url", pricing_url),
        ("usage_url", usage_url),
    ):
        if value is not None:
            updates[field] = value
    if peak_window is not None:
        updates["peak_window"] = None if peak_window.lower() == "none" else peak_window
    if enabled is not None:
        updates["enabled"] = enabled
    if provider.type == ProviderType.manual:
        if cost is not None:
            updates["cost"] = cost
        if cycle is not None:
            updates["cycle"] = Cycle(cycle)
        if renewal_day is not None:
            updates["renewal_day"] = renewal_day

    if not updates:
        console.print("Nothing to update")
        raise typer.Exit(0)

    updated = provider.model_copy(update=updates)
    save_providers(upsert_provider(providers, updated))
    console.print(f"[green]Updated[/green] '{provider_id}'")


@providers_app.command("list")
def list_providers() -> None:
    """List configured providers."""
    providers = load_providers()
    if not providers:
        console.print("No providers. Run [bold]aium providers add --help[/bold].")
        return
    table = Table("id", "name", "type", "currency", "enabled")
    for p in providers:
        detail = p.currency
        if p.type == ProviderType.manual:
            detail += f" @ {p.cost}/{p.cycle.value}"
        table.add_row(p.id, p.name, p.type.value, detail, str(p.enabled))
    console.print(table)


@providers_app.command()
def show(provider_id: str = typer.Argument(..., help="Provider id")) -> None:
    """Show a provider's full configuration."""
    provider = get_provider(load_providers(), provider_id)
    if provider is None:
        console.print(f"[red]Provider[/red] '{provider_id}' not found")
        raise typer.Exit(1)
    console.print_json(provider.model_dump_json(indent=2))


@providers_app.command()
def remove(
    provider_id: str = typer.Argument(..., help="Provider id"),
    delete_key: bool = typer.Option(False, "--delete-key", help="Also remove its API key"),
) -> None:
    """Remove a provider."""
    providers = load_providers()
    if get_provider(providers, provider_id) is None:
        console.print(f"[red]Provider[/red] '{provider_id}' not found")
        raise typer.Exit(1)
    save_providers(remove_provider(providers, provider_id))
    if delete_key:
        SecretsStore().delete(provider_id)
    console.print(f"[green]Removed[/green] '{provider_id}'")


@keys_app.command()
def set(
    provider_id: str = typer.Argument(..., help="Provider id"),
    secret: str | None = typer.Option(None, "--secret", help="API key (prompts if omitted)"),
) -> None:
    """Store an API key for a provider in the system keyring."""
    provider = get_provider(load_providers(), provider_id)
    if provider is None:
        console.print(
            f"[red]Provider[/red] '{provider_id}' not found. "
            f"Add it first with `aium providers add {provider_id}`."
        )
        raise typer.Exit(1)
    if provider.type == ProviderType.manual:
        console.print("[yellow]Note:[/yellow] manual providers do not use an API key.")
    else:
        spec = get_spec(provider.kind)
        if spec is not None and not spec.uses_api_key:
            console.print(
                f"[yellow]Note:[/yellow] '{provider_id}' authenticates via OAuth; "
                "no API key is needed."
            )
    value = secret or typer.prompt("API key", hide_input=True)
    SecretsStore().set(provider_id, value)
    console.print(f"[green]Stored[/green] key for '{provider_id}'")


@keys_app.command()
def delete(provider_id: str = typer.Argument(..., help="Provider id")) -> None:
    """Remove a provider's API key (works for orphaned ids too)."""
    SecretsStore().delete(provider_id)
    console.print(f"[green]Deleted[/green] key for '{provider_id}' (if present)")


@keys_app.command("list")
def list_keys() -> None:
    """List all stored keys, marking ids that are not configured providers."""
    stored = SecretsStore().list_ids()
    if not stored:
        console.print("No keys stored.")
        return
    configured = {p.id for p in load_providers()}
    table = Table("provider id", "status")
    for pid in stored:
        status = "configured" if pid in configured else "[yellow]orphan (not configured)[/yellow]"
        table.add_row(pid, status)
    console.print(table)


def _print_status(status: StatusFile) -> None:
    t = status.totals
    console.print(
        f"Monthly spend: [bold]{t.spend_this_month} {t.currency}[/bold]  |  "
        f"Today: [bold]{t.spend_today} {t.currency}[/bold]  |  "
        f"Prepaid balance: [bold]{t.balance} {t.currency}[/bold]  |  "
        f"Updated: {status.generated_at.isoformat()}"
    )
    table = Table("provider", "type", "balance", "spend/mo", "tariff", "status")
    for p in status.providers:
        bal = f"{p.balance.available:.4f}" if p.balance else "-"
        spend = f"{p.spend_this_month:.2f}" if p.spend_this_month is not None else "-"
        tariff = "-"
        if p.peak is False:
            tariff = "[green]🔥 discounted[/green]"
        state = "[green]ok[/green]" if p.ok else f"[red]{p.error}[/red]"
        table.add_row(p.id, p.type.value, bal, spend, tariff, state)
    console.print(table)


@app.command()
def poll() -> None:
    """Fetch every provider now and refresh the cache."""
    storage.init_db()
    status = asyncio.run(run_poll())
    _print_status(status)


@app.command()
def status(as_json: bool = typer.Option(False, "--json", help="Print raw JSON")) -> None:
    """Show the last cached status."""
    cached = storage.read_status()
    if cached is None:
        console.print("No cached status. Run [bold]aium poll[/bold] first.")
        raise typer.Exit(1)
    if as_json:
        console.print_json(cached.model_dump_json(indent=2))
    else:
        _print_status(cached)


@app.command()
def history(
    provider_id: str = typer.Argument(..., help="Provider id"),
    days: int = typer.Option(30, "--days", min=1),
) -> None:
    """Show balance snapshot history for a provider."""
    since = datetime.now(UTC) - timedelta(days=days)
    snapshots = storage.get_snapshots(provider_id, since=since)
    if not snapshots:
        console.print(f"No snapshots for '{provider_id}' in the last {days} days.")
        return
    table = Table("timestamp", "balance")
    for ts, balance in snapshots:
        table.add_row(ts.isoformat(), f"{balance:.4f}")
    console.print(table)


@app.command()
def stats(
    provider_id: str | None = typer.Option(None, "--provider", help="Only show this provider"),
    once: bool = typer.Option(False, "--once", help="Print one frame and exit"),
    poll: bool = typer.Option(
        False, "--poll", help="Re-run provider polls on each refresh (min interval 60s)"
    ),
    interval: float = typer.Option(
        0.0, "--interval", help="Refresh seconds (default: 5 watch, 60 with --poll)"
    ),
    height: int = typer.Option(3, "--height", min=1, max=8, help="Sparkline height in rows"),
    samples: int | None = typer.Option(None, "--samples", min=1, help="History samples"),
) -> None:
    """Render spend history as braille sparklines (live by default, Ctrl+C to stop)."""
    import shutil

    run_stats_dashboard(
        once=once,
        poll=poll,
        interval=interval,
        height=height,
        samples=samples,
        provider_id=provider_id,
        width=shutil.get_terminal_size((80, 24)).columns,
        tty=sys.stdout.isatty(),
    )


@app.command()
def report(
    group: str = typer.Option("day", "--group", help="day | week | month"),
    periods: int | None = typer.Option(None, "--periods", min=1, help="Number of periods"),
    provider_id: str | None = typer.Option(None, "--provider", help="Only this provider"),
    as_json: bool = typer.Option(False, "--json", help="Print raw JSON"),
) -> None:
    """Show consumption (spend) history grouped by day, week or month."""
    group = group.lower()
    if group not in {"day", "week", "month"}:
        console.print(f"[red]Unknown group[/red] '{group}'. Use day | week | month.")
        raise typer.Exit(1)

    if periods is None:
        periods = {"day": 30, "week": 12, "month": 12}[group]

    rows = build_report(group, periods, provider_id)

    if as_json:
        console.print_json(json.dumps(rows))
        return

    currency = load_settings().base_currency
    provider_cols: list[str] = []
    for row in rows:
        for pid in row["providers"]:
            if pid not in provider_cols:
                provider_cols.append(pid)

    table = Table()
    table.add_column("period")
    for pid in provider_cols:
        table.add_column(pid, justify="right")
    table.add_column(f"total ({currency})", justify="right")

    for row in rows:
        label = row["label"]
        if group == "week":
            start = datetime.fromisoformat(row["start"])
            end = datetime.fromisoformat(row["end"]) - timedelta(days=1)
            if (start.year, start.month) == (end.year, end.month):
                label = f"{label} ({start:%b %d}\u2013{end.day})"
            else:
                label = f"{label} ({start:%b %d}\u2013{end:%b %d})"
        cells = [label]
        cells += [f"{row['providers'].get(pid, 0.0):.2f}" for pid in provider_cols]
        cells.append(f"[bold]{row['total']:.2f}[/bold]")
        table.add_row(*cells)
    console.print(table)


@app.callback(no_args_is_help=True, invoke_without_command=True)
def callback(
    version: Annotated[
        bool, typer.Option("--version", "-v", help="Show the version and exit.")
    ] = False,
) -> None:
    """AI Usage Monitor."""
    if version:
        rprint(f"aium {_cli_version()}")


def _cli_version() -> str:
    """The installed package version (single source: ``pyproject.toml``)."""
    try:
        return package_version("aium")
    except PackageNotFoundError:
        return "unknown"


def main() -> None:
    app()


if __name__ == "__main__":
    app()
