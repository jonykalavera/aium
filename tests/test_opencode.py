"""Tests for the OpenCode Go subscription provider."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from aium.models import BalanceProviderConfig, ProviderType
from aium.providers.base import ProviderError
from aium.providers.opencode import USAGE_URL, OpenCodeGo, _pct

KEY = "sk-" + "A" * 64


def _opencode_cfg() -> BalanceProviderConfig:
    return BalanceProviderConfig(
        id="opencode-go", name="OpenCode Go", type=ProviderType.balance, kind="opencode-go"
    )


@pytest.fixture
def opencode_creds(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"opencode-go": {"type": "api", "key": KEY}}))
    monkeypatch.setenv("AIUM_OPENCODE_AUTH", str(path))
    return path


def _usage_payload() -> dict:
    return {
        "usage": {
            "rolling": {"status": "ok", "percent": 42, "resetsAt": "2026-09-01T00:00:00.000Z"},
            "weekly": {"status": "ok", "percent": 18, "resetsAt": "2026-09-07T00:00:00.000Z"},
            "monthly": {"status": "ok", "percent": 7, "resetsAt": "2026-09-30T00:00:00.000Z"},
        }
    }


@respx.mock
async def test_opencode_quota_balance_usage_and_plan(opencode_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=_usage_payload()))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, None)
        usage = await provider.fetch_usage(http, None)
        quota = await provider.fetch_quota(http, None)
        plan = await provider.fetch_plan(http, None)
    assert plan == "Go"
    assert balance is None
    assert usage is None
    assert [w.label for w in quota] == ["5h", "7d", "30d"]
    assert [w.utilization_pct for w in quota] == [pytest.approx(x) for x in (42, 18, 7)]
    for w in quota:
        assert w.resets_at is not None
        assert w.resets_at.year == 2026


@respx.mock
async def test_opencode_sends_bearer_key(opencode_creds):
    route = respx.get(USAGE_URL).mock(return_value=httpx.Response(200, json=_usage_payload()))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        await provider.fetch_quota(http, None)
    assert route.calls
    assert route.calls.last.request.headers["authorization"] == f"Bearer {KEY}"


@respx.mock
async def test_opencode_401(opencode_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(401, json={"type": "error"}))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="API key"):
            await provider.fetch_quota(http, None)


@respx.mock
async def test_opencode_403(opencode_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(403, json={"type": "error"}))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="subscription"):
            await provider.fetch_quota(http, None)


async def test_opencode_missing_creds(tmp_path, monkeypatch):
    monkeypatch.setenv("AIUM_OPENCODE_AUTH", str(tmp_path / "nope.json"))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="not found"):
            await provider.fetch_quota(http, None)


async def test_opencode_missing_go_entry(tmp_path, monkeypatch):
    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"opencode": {"type": "api", "key": KEY}}))
    monkeypatch.setenv("AIUM_OPENCODE_AUTH", str(path))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="opencode-go"):
            await provider.fetch_quota(http, None)


@respx.mock
async def test_opencode_non_json_response(opencode_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(200, text="not json"))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="not JSON"):
            await provider.fetch_quota(http, None)


@respx.mock
async def test_opencode_http_500(opencode_creds):
    respx.get(USAGE_URL).mock(return_value=httpx.Response(500, text="boom"))
    provider = OpenCodeGo(_opencode_cfg())
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="HTTP 500"):
            await provider.fetch_quota(http, None)


def test_pct_rejects_non_finite():
    assert _pct(float("inf")) is None
    assert _pct(float("-inf")) is None
    assert _pct(float("nan")) is None
    assert _pct(12.4) == 12
