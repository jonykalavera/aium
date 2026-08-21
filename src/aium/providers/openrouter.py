"""OpenRouter provider (https://openrouter.ai)."""

from __future__ import annotations

import httpx

from ..models import Balance, BalanceProviderConfig, Usage
from .base import BalanceProvider, ProviderError

_BASE = "https://openrouter.ai/api/v1"


class OpenRouter(BalanceProvider):
    """OpenRouter reports per-period usage separately from the credit balance.

    BYOK/free usage does not decrement `total_credits`, so `spend_this_month`
    comes from `usage_monthly` (credits used in the current UTC month), which
    OpenRouter provides directly.
    """

    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)

    def _headers(self, secret: str | None) -> dict[str, str]:
        if not secret:
            raise ProviderError("missing API key")
        return {"Authorization": f"Bearer {secret}"}

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance:
        resp = await http.get(f"{_BASE}/credits", headers=self._headers(secret))
        if resp.status_code == 401:
            raise ProviderError("invalid API key")
        resp.raise_for_status()
        data = resp.json()

        body = data.get("data") or {}
        return Balance(
            available=float(body.get("total_credits", 0.0)),
            currency="USD",
        )

    async def fetch_usage(self, http: httpx.AsyncClient, secret: str | None) -> Usage:
        resp = await http.get(f"{_BASE}/key", headers=self._headers(secret))
        if resp.status_code == 401:
            raise ProviderError("invalid API key")
        resp.raise_for_status()
        data = resp.json()

        body = data.get("data") or {}
        monthly = float(body.get("usage_monthly") or body.get("usage") or 0.0)
        return Usage(total=round(monthly, 4), currency="USD")
