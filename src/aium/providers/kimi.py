"""Kimi (Moonshot AI) provider (https://api.moonshot.ai)."""

from __future__ import annotations

import httpx

from ..models import Balance, BalanceProviderConfig
from .base import BalanceProvider, ProviderError

_BASE = "https://api.moonshot.ai"


class Kimi(BalanceProvider):
    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)

    def _headers(self, secret: str | None) -> dict[str, str]:
        if not secret:
            raise ProviderError("missing API key")
        return {"Authorization": f"Bearer {secret}"}

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance:
        resp = await http.get(f"{_BASE}/v1/users/me/balance", headers=self._headers(secret))
        if resp.status_code == 401:
            raise ProviderError("invalid API key")
        resp.raise_for_status()
        data = resp.json()

        body = data.get("data")
        if not body:
            raise ProviderError("empty data in response")

        return Balance(
            available=float(body["available_balance"]),
            granted=float(body.get("voucher_balance", 0.0)),
            topped_up=float(body.get("cash_balance", 0.0)),
            currency="USD",
        )
