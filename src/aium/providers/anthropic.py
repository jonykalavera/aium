"""Anthropic provider via the Claude Code OAuth session (~/.claude/.credentials.json)."""

from __future__ import annotations

import os
import time
from datetime import datetime

import httpx

from ..models import Balance, BalanceProviderConfig, QuotaWindow, Usage
from .base import BalanceProvider, ProviderError
from .oauth import OAuthError, atomic_write, load_json, refresh_token

TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
BETA = "oauth-2025-04-20"
USER_AGENT = "claude-code/2.1.183"
REFRESH_BUFFER_SECS = 300


def _creds_path() -> str:
    return os.environ.get("AIUM_ANTHROPIC_CREDS", "~/.claude/.credentials.json")


def _parse_rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _window(raw: object, label: str) -> QuotaWindow | None:
    if not isinstance(raw, dict):
        return None
    utilization = raw.get("utilization")
    if not isinstance(utilization, (int, float)):
        return None
    return QuotaWindow(
        label=label,
        utilization_pct=int(utilization),
        resets_at=_parse_rfc3339(raw.get("resets_at")),
    )


class Anthropic(BalanceProvider):
    """Claude usage via the Claude Code OAuth token (individual accounts)."""

    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)
        self._data: dict | None = None

    async def _access_token(self, http: httpx.AsyncClient) -> str:
        try:
            creds = load_json(_creds_path())
        except OAuthError as exc:
            raise ProviderError(f"{exc}. Run `claude` (Claude Code) to authenticate.") from exc

        block = creds.get("claudeAiOauth")
        if not isinstance(block, dict):
            raise ProviderError(
                "claudeAiOauth missing in credentials; run `claude` to authenticate"
            )

        access = block.get("accessToken")
        refresh = block.get("refreshToken")
        if not isinstance(access, str) or not isinstance(refresh, str):
            raise ProviderError("missing tokens; run `claude` to authenticate")

        now_ms = time.time() * 1000
        expires_ms = block.get("expiresAt")
        if isinstance(expires_ms, (int, float)) and now_ms < (
            expires_ms - REFRESH_BUFFER_SECS * 1000
        ):
            return access

        try:
            data = await refresh_token(
                http, TOKEN_URL, CLIENT_ID, refresh, extra_headers={"anthropic-beta": BETA}
            )
        except OAuthError as exc:
            raise ProviderError(
                f"token refresh failed; run `claude` to re-authenticate ({exc})"
            ) from exc

        block["accessToken"] = data["access_token"]
        if "refresh_token" in data:
            block["refreshToken"] = data["refresh_token"]
        block["expiresAt"] = now_ms + int(data.get("expires_in", 3600)) * 1000
        atomic_write(_creds_path(), creds)
        return data["access_token"]

    async def _get_data(self, http: httpx.AsyncClient) -> dict:
        if self._data is not None:
            return self._data
        token = await self._access_token(http)
        resp = await http.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": BETA,
                "User-Agent": USER_AGENT,
                "Content-Type": "application/json",
            },
        )
        if resp.status_code == 401:
            raise ProviderError("OAuth token rejected; run `claude` to re-authenticate")
        resp.raise_for_status()
        payload = resp.json()
        self._data = payload
        return payload

    def _extra_usage(self, data: dict) -> dict | None:
        eu = data.get("extra_usage")
        return eu if isinstance(eu, dict) and eu.get("is_enabled") is True else None

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance | None:
        data = await self._get_data(http)
        eu = self._extra_usage(data)
        if eu is None:
            return None
        limit = float(eu.get("monthly_limit", 0))
        used = float(eu.get("used_credits", 0))
        return Balance(available=round((limit - used) / 100, 4), currency="USD")

    async def fetch_usage(self, http: httpx.AsyncClient, secret: str | None) -> Usage | None:
        data = await self._get_data(http)
        eu = self._extra_usage(data)
        if eu is None:
            return None
        return Usage(total=round(float(eu.get("used_credits", 0)) / 100, 4), currency="USD")

    async def fetch_plan(self, http: httpx.AsyncClient, secret: str | None) -> str | None:
        try:
            creds = load_json(_creds_path())
        except OAuthError:
            return None
        block = creds.get("claudeAiOauth")
        if isinstance(block, dict):
            sub = block.get("subscriptionType")
            return str(sub) if sub else None
        return None

    async def fetch_quota(self, http: httpx.AsyncClient, secret: str | None) -> list[QuotaWindow]:
        data = await self._get_data(http)
        windows = []
        for key, label in (
            ("five_hour", "5h"),
            ("seven_day", "7d"),
            ("seven_day_sonnet", "7d sonnet"),
        ):
            window = _window(data.get(key), label)
            if window is not None:
                windows.append(window)
        return windows
