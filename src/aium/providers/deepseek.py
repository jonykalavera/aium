"""DeepSeek provider (https://api.deepseek.com)."""

from __future__ import annotations

import httpx

from ..models import Balance, BalanceProviderConfig
from .base import BalanceProvider, ProviderError

_BASE = "https://api.deepseek.com"


class DeepSeek(BalanceProvider):
    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)

    def _headers(self, secret: str | None) -> dict[str, str]:
        if not secret:
            raise ProviderError("missing API key")
        return {"Authorization": f"Bearer {secret}"}

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance:
        resp = await http.get(f"{_BASE}/user/balance", headers=self._headers(secret))
        if resp.status_code == 401:
            raise ProviderError("invalid API key")
        resp.raise_for_status()
        data = resp.json()

        infos = data.get("balance_infos") or []
        if not infos:
            raise ProviderError("empty balance_infos in response")

        target = self.config.currency
        info = next((i for i in infos if i.get("currency") == target), infos[0])
        return Balance(
            available=float(info["total_balance"]),
            granted=float(info.get("granted_balance", 0.0)),
            topped_up=float(info.get("topped_up_balance", 0.0)),
            currency=info.get("currency", target),
        )
