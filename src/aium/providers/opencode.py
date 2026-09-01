"""OpenCode Go provider via the opencode CLI auth file (~/.local/share/opencode/auth.json)."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime

import httpx

from ..models import Balance, BalanceProviderConfig, QuotaWindow, Usage
from .base import BalanceProvider, ProviderError
from .oauth import OAuthError, load_json

USAGE_URL = "https://opencode.ai/zen/go/v1/usage"
GO_KEY_ID = "opencode-go"


def _auth_path() -> str:
    return os.environ.get("AIUM_OPENCODE_AUTH", "~/.local/share/opencode/auth.json")


def _pct(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return max(0, min(100, round(value)))


def _resets_at(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _go_key() -> str:
    try:
        data = load_json(_auth_path())
    except OAuthError as exc:
        raise ProviderError(f"{exc}. Run `opencode login` and connect the Go plan.") from exc
    entry = data.get(GO_KEY_ID)
    if not isinstance(entry, dict) or entry.get("type") != "api":
        raise ProviderError(
            f"no `{GO_KEY_ID}` API entry in {_auth_path()}. "
            "Run `opencode login` and connect the Go plan."
        )
    key = entry.get("key")
    if not isinstance(key, str) or not key.strip():
        raise ProviderError(
            f"`{GO_KEY_ID}` entry in {_auth_path()} has no API key. "
            "Run `opencode login` and connect the Go plan."
        )
    return key.strip()


class OpenCodeGo(BalanceProvider):
    """OpenCode Go subscription quota windows (5h / weekly / monthly utilization).

    Dollar-denominated usage limits ($12/5h, $30/week, $60/month) are exposed
    only as utilization percentages on a private, undocumented endpoint; there
    is no prepaid balance or absolute-spend API.
    """

    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)
        self._data: dict | None = None

    async def _get_data(self, http: httpx.AsyncClient) -> dict:
        if self._data is not None:
            return self._data
        key = _go_key()
        resp = await http.get(USAGE_URL, headers={"Authorization": f"Bearer {key}"})
        if resp.status_code == 401:
            raise ProviderError("OpenCode Go invalid API key; run `opencode login`")
        if resp.status_code == 403:
            raise ProviderError("OpenCode Go subscription required; run `opencode login`")
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"OpenCode Go usage HTTP {exc.response.status_code}") from exc
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise ProviderError("OpenCode Go usage response is not JSON") from exc
        if not isinstance(payload, dict):
            raise ProviderError("OpenCode Go usage response is not an object")
        self._data = payload
        return payload

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance | None:
        return None

    async def fetch_usage(self, http: httpx.AsyncClient, secret: str | None) -> Usage | None:
        return None

    async def fetch_plan(self, http: httpx.AsyncClient, secret: str | None) -> str | None:
        return "Go"

    async def fetch_quota(self, http: httpx.AsyncClient, secret: str | None) -> list[QuotaWindow]:
        data = await self._get_data(http)
        usage = data.get("usage")
        if not isinstance(usage, dict):
            return []
        windows: list[QuotaWindow] = []
        for key, label in (("rolling", "5h"), ("weekly", "7d"), ("monthly", "30d")):
            block = usage.get(key)
            if not isinstance(block, dict):
                continue
            pct = _pct(block.get("percent"))
            if pct is None:
                continue
            windows.append(
                QuotaWindow(
                    label=label,
                    utilization_pct=pct,
                    resets_at=_resets_at(block.get("resetsAt")),
                )
            )
        return windows
