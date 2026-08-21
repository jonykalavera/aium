"""Google Antigravity provider via the Antigravity/Gemini CLI OAuth session."""

from __future__ import annotations

import os
import time
from datetime import datetime

import httpx

from ..models import Balance, BalanceProviderConfig, QuotaWindow
from .base import BalanceProvider, ProviderError
from .oauth import OAuthError, atomic_write, load_json, refresh_token

TOKEN_URL = "https://oauth2.googleapis.com/token"
CLOUD_CODE_BASE = "https://cloudcode-pa.googleapis.com"
# OAuth client for the official Gemini CLI / Antigravity app (matches the `aud`
# in the access token stored in ~/.gemini/oauth_creds.json).
#
# NOTE: these are the PUBLIC client id/secret of Google's open-source Gemini
# CLI (https://github.com/google-gemini/gemini-cli), not a user credential.
CLIENT_ID = "REPLACED_AT_BUILD"
CLIENT_SECRET = "REPLACED_AT_BUILD"
REFRESH_BUFFER_SECS = 300
USER_AGENT = "antigravity/windows/amd64"
X_GOOG_API_CLIENT = "google-cloud-sdk vscode_cloudshelleditor/0.1"
CLIENT_METADATA = '{"ideType":"ANTIGRAVITY","platform":"WINDOWS","pluginType":"GEMINI"}'


def _creds_path() -> str:
    return os.environ.get("AIUM_GEMINI_CREDS", "~/.gemini/oauth_creds.json")


def _parse_rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Google(BalanceProvider):
    """Antigravity via the Gemini CLI OAuth token (individual accounts).

    Reports the account plan (tier) from `loadCodeAssist`. Per-model rate-limit
    quota from `fetchAvailableModels` is only available on paid tiers (free tier
    returns 403, in which case no quota is reported). There is no credit balance
    or monetary usage exposed, so `fetch_balance` returns None.
    """

    def __init__(self, config: BalanceProviderConfig):
        super().__init__(config)
        self._data: dict | None = None
        self._project: str | None = None
        self._tier: str | None = None

    def _headers(self, token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-Goog-Api-Client": X_GOOG_API_CLIENT,
            "Client-Metadata": CLIENT_METADATA,
        }

    async def _access_token(self, http: httpx.AsyncClient) -> str:
        try:
            creds = load_json(_creds_path())
        except OAuthError as exc:
            raise ProviderError(f"{exc}. Run Antigravity (Gemini CLI) to log in.") from exc

        access = creds.get("access_token")
        refresh = creds.get("refresh_token")
        if not isinstance(access, str) or not isinstance(refresh, str):
            raise ProviderError("missing tokens; run Antigravity (Gemini CLI) to log in")

        now_ms = time.time() * 1000
        expiry = creds.get("expiry_date")
        if isinstance(expiry, (int, float)) and now_ms < expiry - REFRESH_BUFFER_SECS * 1000:
            return access

        try:
            data = await refresh_token(
                http, TOKEN_URL, CLIENT_ID, refresh, client_secret=CLIENT_SECRET
            )
        except OAuthError as exc:
            raise ProviderError(
                f"token refresh failed; run Antigravity (Gemini CLI) ({exc})"
            ) from exc

        creds["access_token"] = data["access_token"]
        creds["expiry_date"] = now_ms + int(data.get("expires_in", 3600)) * 1000
        atomic_write(_creds_path(), creds)
        return data["access_token"]

    async def _load_project_and_tier(
        self, http: httpx.AsyncClient, token: str
    ) -> tuple[str, str | None]:
        resp = await http.post(
            f"{CLOUD_CODE_BASE}/v1internal:loadCodeAssist",
            headers=self._headers(token),
            json={"metadata": {"ideType": "ANTIGRAVITY"}},
        )
        if resp.status_code == 401:
            raise ProviderError("OAuth token rejected; run Antigravity (Gemini CLI)")
        if resp.status_code >= 400:
            return "", None
        data = resp.json()
        tier = data.get("currentTier")
        tier_name = tier.get("name") if isinstance(tier, dict) else None
        tier_id = tier.get("id") if isinstance(tier, dict) else None
        if tier_name and tier_id and tier_id != tier_name.lower():
            tier_name = f"{tier_name} ({tier_id})"
        project = data.get("cloudaicompanionProject")
        if isinstance(project, str):
            project_id = project
        elif isinstance(project, dict):
            project_id = project.get("id") or ""
        else:
            project_id = ""
        return project_id, tier_name

    async def _ensure_project(self, http: httpx.AsyncClient, token: str) -> str:
        if self._project is not None:
            return self._project
        project_id, tier = await self._load_project_and_tier(http, token)
        self._project = project_id
        self._tier = tier
        return self._project

    async def fetch_plan(self, http: httpx.AsyncClient, secret: str | None) -> str | None:
        token = await self._access_token(http)
        await self._ensure_project(http, token)
        return self._tier

    async def _get_data(self, http: httpx.AsyncClient) -> dict:
        if self._data is not None:
            return self._data
        token = await self._access_token(http)
        project = await self._ensure_project(http, token)
        body = {"project": project} if project else {}
        resp = await http.post(
            f"{CLOUD_CODE_BASE}/v1internal:fetchAvailableModels",
            headers=self._headers(token),
            json=body,
        )
        if resp.status_code == 401:
            raise ProviderError("OAuth token rejected; run Antigravity (Gemini CLI)")
        payload: dict = {} if resp.status_code >= 400 else resp.json()
        self._data = payload
        return payload

    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance | None:
        return None

    async def fetch_quota(self, http: httpx.AsyncClient, secret: str | None) -> list[QuotaWindow]:
        data = await self._get_data(http)
        models = data.get("models") or {}
        windows = []
        for name, info in models.items():
            if not isinstance(info, dict):
                continue
            quota = info.get("quotaInfo")
            if not isinstance(quota, dict):
                continue
            remaining = quota.get("remainingFraction")
            if not isinstance(remaining, (int, float)):
                continue
            pct = round((1 - remaining) * 100)
            resets_at = _parse_rfc3339(quota.get("resetTime"))
            windows.append(QuotaWindow(label=name, utilization_pct=pct, resets_at=resets_at))
        return windows
