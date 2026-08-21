"""OpenAI provider via the Codex CLI OAuth session (~/.codex/auth.json)."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import cast

import httpx

from ..models import Balance, BalanceProviderConfig, QuotaWindow
from .base import BalanceProvider, ProviderError
from .oauth import OAuthError, atomic_write, jwt_exp, load_json, refresh_token

TOKEN_URL = "https://auth.openai.com/oauth/token"
USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
SCOPE = "openid profile email"
USER_AGENT = "codex-cli"
REFRESH_BUFFER_SECS = 300


def _auth_path() -> str:
    return os.environ.get("AIUM_CODEX_AUTH", "~/.codex/auth.json")


def _money_to_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("$", "").replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _expires_at_secs(tokens: dict) -> float | None:
    value = tokens.get("expires_at")
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    id_token = tokens.get("id_token")
    if isinstance(id_token, str):
        return jwt_exp(id_token)
    return None


def _window(raw: object, label: str, now: float) -> QuotaWindow | None:
    if not isinstance(raw, dict):
        return None
    pct = raw.get("used_percent")
    if not isinstance(pct, (int, float)):
        return None
    reset_at = raw.get("reset_at")
    if isinstance(reset_at, (int, float)):
        resets = datetime.fromtimestamp(float(reset_at), tz=UTC)
    else:
        after = raw.get("reset_after_seconds")
        if not isinstance(after, (int, float)):
            return None
        resets = datetime.fromtimestamp(now + float(after), tz=UTC)
    return QuotaWindow(label=label, utilization_pct=int(min(100, max(0, pct))), resets_at=resets)


class OpenAI(BalanceProvider):
    """ChatGPT/Codex usage via the Codex CLI OAuth token (individual accounts)."""

    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)
        self._data: dict | None = None

    async def _access_token(self, http: httpx.AsyncClient) -> str:
        try:
            creds = load_json(_auth_path())
        except OAuthError as exc:
            raise ProviderError(f"{exc}. Run `codex login` to authenticate.") from exc

        tokens = creds.get("tokens")
        if not isinstance(tokens, dict):
            raise ProviderError("tokens missing in auth file; run `codex login`")

        access = tokens.get("access_token")
        refresh = tokens.get("refresh_token")
        if not isinstance(access, str) or not isinstance(refresh, str):
            raise ProviderError("missing tokens; run `codex login`")

        now = time.time()
        expires = _expires_at_secs(tokens)
        if expires is not None and now < expires - REFRESH_BUFFER_SECS:
            return access

        try:
            data = await refresh_token(http, TOKEN_URL, CLIENT_ID, refresh, scope=SCOPE)
        except OAuthError as exc:
            raise ProviderError(f"token refresh failed; run `codex login` ({exc})") from exc

        tokens["access_token"] = data["access_token"]
        if "refresh_token" in data:
            tokens["refresh_token"] = data["refresh_token"]
        if "id_token" in data:
            tokens["id_token"] = data["id_token"]
        atomic_write(_auth_path(), creds)
        return data["access_token"]

    async def _get_data(self, http: httpx.AsyncClient) -> dict:
        if self._data is not None:
            return self._data
        try:
            creds = load_json(_auth_path())
        except OAuthError as exc:
            raise ProviderError(f"{exc}. Run `codex login` to authenticate.") from exc
        tokens = creds.get("tokens", {})
        account_id = tokens.get("account_id") if isinstance(tokens, dict) else None

        token = await self._access_token(http)
        headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
        if isinstance(account_id, str) and account_id:
            headers["ChatGPT-Account-Id"] = account_id

        resp = await http.get(USAGE_URL, headers=headers)
        if resp.status_code == 401:
            raise ProviderError("OAuth token rejected; run `codex login`")
        resp.raise_for_status()
        payload = resp.json()
        self._data = payload
        return payload

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance | None:
        data = await self._get_data(http)
        credits = data.get("credits")
        if not isinstance(credits, dict):
            return None
        balance = _money_to_float(credits.get("balance"))
        if balance is None:
            return None
        return Balance(available=balance, currency="USD")

    async def fetch_quota(self, http: httpx.AsyncClient, secret: str | None) -> list[QuotaWindow]:
        data = await self._get_data(http)
        now = time.time()
        rate_limit = cast(dict, data.get("rate_limit") or {})
        windows = []
        for key, label in (("primary_window", "5h"), ("secondary_window", "7d")):
            window = _window(rate_limit.get(key), label, now)
            if window is not None:
                windows.append(window)
        return windows
