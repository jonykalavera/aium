"""Tests for the OAuth-session providers (Anthropic / OpenAI Codex / Google)."""

import json
import time

import httpx
import pytest
import respx

from aium.models import BalanceProviderConfig, ProviderType
from aium.providers.anthropic import Anthropic
from aium.providers.base import ProviderError
from aium.providers.google import Google
from aium.providers.openai import OpenAI


def _anthropic_cfg() -> BalanceProviderConfig:
    return BalanceProviderConfig(
        id="anthropic", name="Anthropic", type=ProviderType.balance, kind="anthropic"
    )


def _openai_cfg() -> BalanceProviderConfig:
    return BalanceProviderConfig(
        id="openai", name="OpenAI", type=ProviderType.balance, kind="openai"
    )


@pytest.fixture
def anthropic_creds(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "tok-valid",
                    "refreshToken": "rt",
                    "expiresAt": (time.time() + 3600) * 1000,
                    "subscriptionType": "pro",
                    "rateLimitTier": "default_claude_ai",
                }
            }
        )
    )
    monkeypatch.setenv("AIUM_ANTHROPIC_CREDS", str(path))
    return path


@pytest.fixture
def openai_creds(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(
        json.dumps(
            {
                "tokens": {
                    "access_token": "tok-valid",
                    "refresh_token": "rt",
                    "id_token": "h.eyJleHAiOjk5OTk5OTk5OTk5fQ.s",
                    "account_id": "acct_123",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            }
        )
    )
    monkeypatch.setenv("AIUM_CODEX_AUTH", str(path))
    return path


@respx.mock
async def test_anthropic_balance_usage_and_quota(anthropic_creds):
    respx.get("https://api.anthropic.com/api/oauth/usage").mock(
        return_value=httpx.Response(
            200,
            json={
                "five_hour": {"utilization": 62, "resets_at": "2026-08-21T20:00:00Z"},
                "seven_day": {"utilization": 30, "resets_at": "2026-08-25T00:00:00Z"},
                "seven_day_sonnet": None,
                "extra_usage": {
                    "is_enabled": True,
                    "monthly_limit": 20000,
                    "used_credits": 5321,
                },
            },
        )
    )
    provider = Anthropic(_anthropic_cfg())
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, None)
        usage = await provider.fetch_usage(http, None)
        quota = await provider.fetch_quota(http, None)
    assert balance is not None
    assert usage is not None
    assert balance.available == pytest.approx((20000 - 5321) / 100)
    assert usage.total == pytest.approx(53.21)
    assert [w.label for w in quota] == ["5h", "7d"]
    assert quota[0].utilization_pct == 62


@respx.mock
async def test_anthropic_without_extra_usage(anthropic_creds):
    respx.get("https://api.anthropic.com/api/oauth/usage").mock(
        return_value=httpx.Response(
            200,
            json={
                "five_hour": {"utilization": 10, "resets_at": None},
                "seven_day": {"utilization": 5, "resets_at": None},
                "extra_usage": {"is_enabled": False},
            },
        )
    )
    provider = Anthropic(_anthropic_cfg())
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, None)
        usage = await provider.fetch_usage(http, None)
    assert balance is None
    assert usage is None


async def test_anthropic_missing_creds(tmp_path, monkeypatch):
    monkeypatch.setenv("AIUM_ANTHROPIC_CREDS", str(tmp_path / "nope.json"))
    provider = Anthropic(_anthropic_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="claude"):
            await provider.fetch_balance(http, None)


@respx.mock
async def test_openai_balance_and_quota(openai_creds):
    respx.get("https://chatgpt.com/backend-api/wham/usage").mock(
        return_value=httpx.Response(
            200,
            json={
                "plan_type": "plus",
                "rate_limit": {
                    "primary_window": {
                        "used_percent": 40,
                        "limit_window_seconds": 18000,
                        "reset_after_seconds": 3600,
                    },
                    "secondary_window": {
                        "used_percent": 70,
                        "limit_window_seconds": 604800,
                        "reset_at": int(time.time()) + 10000,
                    },
                },
                "credits": {"balance": "$25.00", "has_credits": True},
            },
        )
    )
    provider = OpenAI(_openai_cfg())
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, None)
        quota = await provider.fetch_quota(http, None)
    assert balance is not None
    assert balance.available == 25.0
    assert [w.label for w in quota] == ["5h", "7d"]
    assert quota[0].utilization_pct == 40


async def test_openai_missing_creds(tmp_path, monkeypatch):
    monkeypatch.setenv("AIUM_CODEX_AUTH", str(tmp_path / "nope.json"))
    provider = OpenAI(_openai_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="codex"):
            await provider.fetch_balance(http, None)


@pytest.fixture
def google_creds(tmp_path, monkeypatch):
    path = tmp_path / "oauth_creds.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "tok-valid",
                "refresh_token": "rt",
                "expiry_date": (time.time() + 3600) * 1000,
                "scope": "cloud-platform openid",
                "token_type": "Bearer",
            }
        )
    )
    monkeypatch.setenv("AIUM_GEMINI_CREDS", str(path))
    return path


def _google_cfg() -> BalanceProviderConfig:
    return BalanceProviderConfig(
        id="google", name="Google", type=ProviderType.balance, kind="google"
    )


@respx.mock
async def test_google_quota(google_creds):
    respx.post("https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist").mock(
        return_value=httpx.Response(
            200,
            json={
                "cloudaicompanionProject": {"id": "proj-1"},
                "currentTier": {"id": "free-tier", "name": "Antigravity"},
            },
        )
    )
    respx.post("https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels").mock(
        return_value=httpx.Response(
            200,
            json={
                "models": {
                    "gemini-3-pro": {
                        "quotaInfo": {"remainingFraction": 0.5, "resetTime": "2026-08-22T00:00:00Z"}
                    },
                    "gemini-3-flash": {"quotaInfo": {"remainingFraction": 0.9, "resetTime": None}},
                    "no-quota": {},
                }
            },
        )
    )
    provider = Google(_google_cfg())
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, None)
        quota = await provider.fetch_quota(http, None)
        plan = await provider.fetch_plan(http, None)
    assert balance is None
    assert [w.label for w in quota] == ["gemini-3-pro", "gemini-3-flash"]
    assert quota[0].utilization_pct == 50
    assert quota[1].utilization_pct == 10
    assert plan == "Antigravity (free-tier)"


@respx.mock
async def test_google_free_tier_no_quota(google_creds):
    respx.post("https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist").mock(
        return_value=httpx.Response(200, json={"currentTier": {"name": "Antigravity"}})
    )
    respx.post("https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels").mock(
        return_value=httpx.Response(403, json={"error": {"code": 403, "message": "denied"}})
    )
    provider = Google(_google_cfg())
    async with httpx.AsyncClient() as http:
        assert await provider.fetch_quota(http, None) == []


@respx.mock
async def test_google_refresh_token_with_secret(tmp_path, monkeypatch):
    path = tmp_path / "oauth_creds.json"
    path.write_text(
        json.dumps(
            {
                "access_token": "stale",
                "refresh_token": "rt",
                "expiry_date": (time.time() - 600) * 1000,  # expired
                "scope": "cloud-platform openid",
                "token_type": "Bearer",
            }
        )
    )
    monkeypatch.setenv("AIUM_GEMINI_CREDS", str(path))

    respx.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})
    )
    respx.post("https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist").mock(
        return_value=httpx.Response(200, json={"cloudaicompanionProject": "proj-1"})
    )
    respx.post("https://cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels").mock(
        return_value=httpx.Response(200, json={"models": {}})
    )
    provider = Google(_google_cfg())
    async with httpx.AsyncClient() as http:
        assert await provider.fetch_quota(http, None) == []
    # token refresh must have persisted a new access token
    import json as _json

    saved = _json.loads(path.read_text())
    assert saved["access_token"] == "fresh"
