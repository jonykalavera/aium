"""Tests for the Cursor IDE-session provider."""

from __future__ import annotations

import base64
import json
import sqlite3
import time

import httpx
import pytest
import respx

from aium.models import BalanceProviderConfig, ProviderType
from aium.providers.base import ProviderError
from aium.providers.cursor import TOKEN_KEY, Cursor

USAGE_URL = "https://cursor.com/api/usage-summary"


def _cursor_cfg() -> BalanceProviderConfig:
    return BalanceProviderConfig(
        id="cursor", name="Cursor", type=ProviderType.balance, kind="cursor"
    )


def _fake_jwt(*, sub: str = "auth0|user_123", exp: float | None = None) -> str:
    claims: dict = {"sub": sub}
    if exp is not None:
        claims["exp"] = exp
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJub25lIn0.{payload}.sig"


def _write_auth(path, token: str) -> None:
    path.write_text(json.dumps({"accessToken": token, "refreshToken": "rt"}))


def _seed_db(path, token: str | None) -> None:
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE ItemTable (key TEXT, value TEXT)")
    if token is not None:
        conn.execute("INSERT INTO ItemTable (key, value) VALUES (?, ?)", (TOKEN_KEY, token))
    conn.commit()
    conn.close()


@pytest.fixture
def cursor_creds(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    _write_auth(path, _fake_jwt(exp=time.time() + 3600))
    monkeypatch.setenv("AIUM_CURSOR_AUTH", str(path))
    return path


def _summary(
    *,
    membership: str = "pro",
    auto: float = 40.2,
    api: float = 12.0,
    used: int = 1500,
    remaining: int = 500,
    on_demand_used: int = 2309,
    on_demand_enabled: bool = True,
    unlimited: bool = False,
) -> dict:
    return {
        "billingCycleStart": "2026-08-04T00:35:51.000Z",
        "billingCycleEnd": "2026-09-04T00:35:51.000Z",
        "membershipType": membership,
        "isUnlimited": unlimited,
        "individualUsage": {
            "plan": {
                "enabled": True,
                "used": used,
                "limit": used + remaining,
                "remaining": remaining,
                "autoPercentUsed": auto,
                "apiPercentUsed": api,
                "totalPercentUsed": max(auto, api),
            },
            "onDemand": {"enabled": on_demand_enabled, "used": on_demand_used, "limit": None},
        },
    }


@respx.mock
async def test_cursor_balance_usage_quota_and_plan(cursor_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=_summary()))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, None)
        usage = await provider.fetch_usage(http, None)
        quota = await provider.fetch_quota(http, None)
        plan = await provider.fetch_plan(http, None)
    assert plan == "Pro"
    assert balance is not None
    assert balance.available == pytest.approx(5.0)
    assert usage is not None
    assert usage.total == pytest.approx(38.09)  # 15.00 included + 23.09 on-demand
    assert [w.label for w in quota] == ["auto", "api"]
    assert quota[0].utilization_pct == 40
    assert quota[1].utilization_pct == 12
    assert quota[0].resets_at is not None
    assert quota[0].resets_at.year == 2026


@respx.mock
async def test_cursor_sends_workos_session_cookie(cursor_creds):
    token = json.loads(cursor_creds.read_text())["accessToken"]
    route = respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=_summary()))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        await provider.fetch_plan(http, None)
    assert route.calls
    cookie = route.calls.last.request.headers["cookie"]
    assert cookie == f"WorkosCursorSessionToken=user_123%3A%3A{token}"


@respx.mock
async def test_cursor_unlimited_has_no_quota_or_balance(cursor_creds):
    respx.get(USAGE_URL).mock(
        return_value=httpx.Response(200, json=_summary(unlimited=True, remaining=0, used=0))
    )
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        assert await provider.fetch_balance(http, None) is None
        assert await provider.fetch_quota(http, None) == []
        assert await provider.fetch_usage(http, None) is None
        assert await provider.fetch_plan(http, None) == "Pro"


@respx.mock
async def test_cursor_over_allowance_percentage_is_kept_above_100(cursor_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=_summary(auto=142.7, api=5)))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        quota = await provider.fetch_quota(http, None)
    assert quota[0].utilization_pct == 143


@respx.mock
async def test_cursor_team_falls_back_to_display_messages(cursor_creds):
    respx.get(USAGE_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "billingCycleEnd": "2026-09-04T00:00:00.000Z",
                "membershipType": "team",
                "autoModelSelectedDisplayMessage": "You've used 42% of your included total usage",
                "namedModelSelectedDisplayMessage": "You've used 15% of your included API usage",
                "teamUsage": {"onDemand": {"enabled": True, "used": 100}},
            },
        )
    )
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        quota = await provider.fetch_quota(http, None)
        plan = await provider.fetch_plan(http, None)
        usage = await provider.fetch_usage(http, None)
        balance = await provider.fetch_balance(http, None)
    assert plan == "Team"
    assert [w.label for w in quota] == ["auto", "api"]
    assert quota[0].utilization_pct == 42
    assert quota[1].utilization_pct == 15
    assert balance is None
    assert usage is not None
    assert usage.total == pytest.approx(1.0)


async def test_cursor_missing_creds(tmp_path, monkeypatch):
    monkeypatch.setenv("AIUM_CURSOR_AUTH", str(tmp_path / "nope.json"))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="not found"):
            await provider.fetch_balance(http, None)


async def test_cursor_expired_token(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    _write_auth(path, _fake_jwt(exp=time.time() - 10))
    monkeypatch.setenv("AIUM_CURSOR_AUTH", str(path))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="expired"):
            await provider.fetch_plan(http, None)


@respx.mock
async def test_cursor_reads_token_from_ide_db(tmp_path, monkeypatch):
    token = _fake_jwt(exp=time.time() + 3600)
    db_path = tmp_path / "state.vscdb"
    _seed_db(db_path, token)
    monkeypatch.delenv("AIUM_CURSOR_AUTH", raising=False)
    monkeypatch.setenv("AIUM_CURSOR_DB", str(db_path))
    route = respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=_summary()))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        assert await provider.fetch_plan(http, None) == "Pro"
    cookie = route.calls.last.request.headers["cookie"]
    assert cookie == f"WorkosCursorSessionToken=user_123%3A%3A{token}"


@respx.mock
async def test_cursor_json_quoted_token_in_ide_db(tmp_path, monkeypatch):
    token = _fake_jwt(exp=time.time() + 3600)
    db_path = tmp_path / "state.vscdb"
    _seed_db(db_path, json.dumps(token))
    monkeypatch.delenv("AIUM_CURSOR_AUTH", raising=False)
    monkeypatch.setenv("AIUM_CURSOR_DB", str(db_path))
    route = respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=_summary()))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        await provider.fetch_plan(http, None)
    cookie = route.calls.last.request.headers["cookie"]
    assert cookie == f"WorkosCursorSessionToken=user_123%3A%3A{token}"


@respx.mock
async def test_cursor_401(cursor_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(401, json={"error": "not_authenticated"}))
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="Sign in"):
            await provider.fetch_balance(http, None)


@respx.mock
async def test_cursor_pro_plus_plan_name(cursor_creds):
    respx.get(USAGE_URL).mock(
        return_value=httpx.Response(200, json=_summary(membership="pro_plus"))
    )
    provider = Cursor(_cursor_cfg())
    async with httpx.AsyncClient() as http:
        assert await provider.fetch_plan(http, None) == "Pro Plus"
