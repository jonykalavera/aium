"""Z.AI (Zhipu GLM) provider (https://api.z.ai)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx

from ..models import Balance, BalanceProviderConfig, QuotaWindow
from .base import BalanceProvider, ProviderError

_BASE = "https://api.z.ai/api/monitor/usage/quota/limit"


def _parse_reset(ms: object) -> datetime | None:
    if isinstance(ms, (int, float)) and ms > 0:
        return datetime.fromtimestamp(ms / 1000, tz=UTC)
    return None


class ZAI(BalanceProvider):
    """Z.AI / GLM subscription quota via the platform's usage/limit endpoint.

    Reports per-window token/time quota utilization; there is no prepaid credit
    balance, so `fetch_balance` returns None.
    """

    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)

    def _headers(self, secret: str | None) -> dict[str, str]:
        if not secret:
            raise ProviderError("missing API key")
        return {"Authorization": secret}  # bare key, no Bearer prefix

    async def _get_data(self, http: httpx.AsyncClient, secret: str | None) -> dict:
        resp = await http.get(_BASE, headers=self._headers(secret))
        if resp.status_code == 401:
            raise ProviderError("invalid API key")
        resp.raise_for_status()
        data = resp.json()
        if data.get("success") is False or (data.get("code") not in (None, 0)):
            msg = data.get("msg") or "quota endpoint error"
            raise ProviderError(f"Z.AI: {msg}")
        return data

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance | None:
        return None

    async def fetch_plan(self, http: httpx.AsyncClient, secret: str | None) -> str | None:
        data = await self._get_data(http, secret)
        level = (data.get("data") or {}).get("level")
        return f"GLM Coding {level}" if isinstance(level, str) and level else None

    async def fetch_quota(self, http: httpx.AsyncClient, secret: str | None) -> list[QuotaWindow]:
        data = await self._get_data(http, secret)
        limits = (data.get("data") or {}).get("limits") or []
        windows = []
        token_index = 0
        for limit in limits:
            if not isinstance(limit, dict):
                continue
            limit_type = limit.get("type")
            pct = limit.get("percentage")
            if not isinstance(pct, (int, float)):
                continue
            if limit_type == "TOKENS_LIMIT":
                token_index += 1
                if token_index == 1:
                    label = "5h"
                elif token_index == 2:
                    label = "7d"
                else:
                    label = f"tokens {token_index}"
            elif limit_type == "TIME_LIMIT":
                label = "30d"
            else:
                continue
            windows.append(
                QuotaWindow(
                    label=label,
                    utilization_pct=round(pct),
                    resets_at=_parse_reset(limit.get("nextResetTime")),
                )
            )
        return windows
