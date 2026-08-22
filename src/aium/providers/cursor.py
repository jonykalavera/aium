"""Cursor provider via the IDE session (state.vscdb) or cursor-agent auth.json."""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from ..models import Balance, BalanceProviderConfig, QuotaWindow, Usage
from .base import BalanceProvider, ProviderError
from .oauth import OAuthError, jwt_exp, jwt_payload, load_json

USAGE_URL = "https://cursor.com/api/usage-summary"
TOKEN_KEY = "cursorAuth/accessToken"
BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)%")


def _platform_config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata)
        return Path.home() / "AppData" / "Roaming"
    return Path.home() / ".config"


def _default_db_path() -> Path:
    return _platform_config_dir() / "Cursor" / "User" / "globalStorage" / "state.vscdb"


def _default_agent_auth_path() -> Path:
    return _platform_config_dir() / "cursor" / "auth.json"


def _normalize_token(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith('"'):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(parsed, str):
            return parsed.strip()
    return raw


def _connect_readonly(path: Path) -> sqlite3.Connection:
    """Open Cursor's state DB read-only so a running IDE's WAL is visible.

    Do not use `immutable=1`: that ignores `-wal`/`-shm`, so a token Cursor
    just wrote can look missing while the user is signed in.
    """
    uri = path.resolve().as_uri()
    try:
        return sqlite3.connect(f"{uri}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise ProviderError(
            f"could not open Cursor database at {path}: {exc}. "
            "Retry, or quit the Cursor IDE if it is holding a lock."
        ) from exc


def _read_ide_token(path: Path) -> str:
    if not path.exists():
        raise ProviderError(
            f"Cursor database not found at {path}. Sign in to the Cursor IDE, then try again."
        )
    conn = _connect_readonly(path)
    try:
        row = conn.execute("SELECT value FROM ItemTable WHERE key = ?", (TOKEN_KEY,)).fetchone()
    except sqlite3.Error as exc:
        raise ProviderError(f"could not read Cursor session from {path}: {exc}") from exc
    finally:
        conn.close()
    if row is None or not isinstance(row[0], str) or not row[0].strip():
        raise ProviderError(
            f"no Cursor session found in {path}. Sign in to the Cursor IDE, then try again."
        )
    token = _normalize_token(row[0])
    if not token:
        raise ProviderError("Cursor session token is empty. Sign in to the Cursor IDE again.")
    return token


def _read_agent_token(path: Path) -> str:
    try:
        data = load_json(path)
    except OAuthError as exc:
        raise ProviderError(f"{exc}. Run `cursor-agent` or sign in to the Cursor IDE.") from exc
    token = data.get("accessToken")
    if not isinstance(token, str) or not token.strip():
        raise ProviderError(f"no accessToken in {path}. Sign in with `cursor-agent` again.")
    return token.strip()


def _access_token() -> str:
    auth_override = os.environ.get("AIUM_CURSOR_AUTH")
    if auth_override:
        return _read_agent_token(Path(auth_override))

    db_override = os.environ.get("AIUM_CURSOR_DB")
    if db_override:
        return _read_ide_token(Path(db_override))

    db_path = _default_db_path()
    agent_path = _default_agent_auth_path()
    if db_path.exists():
        return _read_ide_token(db_path)
    return _read_agent_token(agent_path)


def _session_cookie(token: str) -> str:
    claims = jwt_payload(token)
    if claims is None:
        raise ProviderError(
            "Cursor session token could not be decoded. Sign in to the Cursor IDE again."
        )
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise ProviderError("Cursor session token has no `sub` claim.")
    user_id = sub.split("|", 1)[1] if "|" in sub else sub
    if not user_id:
        raise ProviderError(f"Cursor session token `sub` claim has an unexpected shape: {sub!r}")
    expires = jwt_exp(token)
    if expires is not None and time.time() >= expires:
        raise ProviderError("Cursor session expired. Sign in to the Cursor IDE again.")
    return f"{user_id}%3A%3A{token}"


def _parse_rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cents(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return round(float(value) / 100.0, 4)


def _pct(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return max(0, round(value))


def _pct_from_message(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    match = _PERCENT_RE.search(value)
    if match is None:
        return None
    return _pct(float(match.group(1)))


def _title_case(value: str) -> str:
    return value.replace("_", " ").title() or "Cursor"


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


class Cursor(BalanceProvider):
    """Cursor usage via the IDE / cursor-agent session (individual accounts).

    Hits the dashboard's undocumented `GET /api/usage-summary`. Reports the
    two monthly pools as quota windows (auto = Cursor Models, api = Other
    Models).

    Spend and budget are both USD but different pools: `fetch_usage()` is
    included usage consumed plus on-demand overage (month-to-date spend);
    `fetch_balance()` is remaining included-usage budget only and does not
    shrink by on-demand.
    """

    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)
        self._data: dict | None = None

    def _headers(self) -> dict[str, str]:
        token = _access_token()
        cookie = _session_cookie(token)
        return {
            "Cookie": f"WorkosCursorSessionToken={cookie}",
            "Origin": "https://cursor.com",
            "Referer": "https://cursor.com/dashboard",
            "User-Agent": BROWSER_UA,
        }

    async def _get_data(self, http: httpx.AsyncClient) -> dict:
        if self._data is not None:
            return self._data
        resp = await http.get(USAGE_URL, headers=self._headers())
        if resp.status_code in (401, 403):
            raise ProviderError("Cursor session rejected. Sign in to the Cursor IDE again.")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"Cursor usage-summary HTTP {exc.response.status_code}") from exc
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("Cursor usage-summary response is not JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderError("Cursor usage-summary response is not an object")
        self._data = payload
        return payload

    def _plan_block(self, data: dict) -> dict:
        individual = _as_dict(data.get("individualUsage"))
        return _as_dict(individual.get("plan"))

    def _on_demand_block(self, data: dict) -> dict:
        individual = _as_dict(data.get("individualUsage"))
        team = _as_dict(data.get("teamUsage"))
        on_demand = individual.get("onDemand")
        if not isinstance(on_demand, dict):
            on_demand = team.get("onDemand")
        return _as_dict(on_demand)

    def _resets_at(self, data: dict) -> datetime | None:
        return _parse_rfc3339(data.get("billingCycleEnd"))

    async def fetch_plan(self, http: httpx.AsyncClient, secret: str | None) -> str | None:
        data = await self._get_data(http)
        membership = data.get("membershipType")
        if not isinstance(membership, str) or not membership.strip():
            return None
        return _title_case(membership.strip())

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance | None:
        data = await self._get_data(http)
        if data.get("isUnlimited") is True:
            return None
        remaining = _cents(self._plan_block(data).get("remaining"))
        if remaining is None:
            return None
        return Balance(available=remaining, currency="USD")

    async def fetch_usage(self, http: httpx.AsyncClient, secret: str | None) -> Usage | None:
        data = await self._get_data(http)
        if data.get("isUnlimited") is True:
            return None
        included = _cents(self._plan_block(data).get("used"))
        on_demand = self._on_demand_block(data)
        extra = _cents(on_demand.get("used")) if on_demand.get("enabled") is True else None
        parts = [part for part in (included, extra) if part is not None]
        if not parts:
            return None
        return Usage(
            total=round(sum(parts), 4),
            currency="USD",
            period_start=_parse_rfc3339(data.get("billingCycleStart")),
            period_end=self._resets_at(data),
        )

    async def fetch_quota(self, http: httpx.AsyncClient, secret: str | None) -> list[QuotaWindow]:
        data = await self._get_data(http)
        if data.get("isUnlimited") is True:
            return []
        resets_at = self._resets_at(data)
        plan = self._plan_block(data)
        windows: list[QuotaWindow] = []
        for key, label in (("autoPercentUsed", "auto"), ("apiPercentUsed", "api")):
            pct = _pct(plan.get(key))
            if pct is not None:
                windows.append(QuotaWindow(label=label, utilization_pct=pct, resets_at=resets_at))
        if windows:
            return windows
        auto = _pct_from_message(data.get("autoModelSelectedDisplayMessage"))
        api = _pct_from_message(data.get("namedModelSelectedDisplayMessage"))
        if auto is not None:
            windows.append(QuotaWindow(label="auto", utilization_pct=auto, resets_at=resets_at))
        if api is not None:
            windows.append(QuotaWindow(label="api", utilization_pct=api, resets_at=resets_at))
        return windows
