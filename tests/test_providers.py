import httpx
import pytest
import respx

from aium.models import BalanceProviderConfig, ProviderType
from aium.providers.base import ProviderError
from aium.providers.deepseek import DeepSeek
from aium.providers.kimi import Kimi
from aium.providers.openrouter import OpenRouter
from aium.providers.zai import ZAI


@pytest.fixture
def deepseek_cfg() -> BalanceProviderConfig:
    return BalanceProviderConfig(
        id="deepseek", name="DeepSeek", type=ProviderType.balance, kind="deepseek"
    )


@respx.mock
async def test_deepseek_picks_configured_currency(deepseek_cfg):
    respx.get("https://api.deepseek.com/user/balance").mock(
        return_value=httpx.Response(
            200,
            json={
                "balance_infos": [
                    {
                        "currency": "CNY",
                        "total_balance": "10.00",
                        "granted_balance": "2.00",
                        "topped_up_balance": "8.00",
                    },
                    {
                        "currency": "USD",
                        "total_balance": "1.50",
                        "granted_balance": "0.00",
                        "topped_up_balance": "1.50",
                    },
                ]
            },
        )
    )
    provider = DeepSeek(deepseek_cfg)
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, "sk-test")
    assert balance.available == 1.50
    assert balance.currency == "USD"


@respx.mock
async def test_deepseek_invalid_key(deepseek_cfg):
    respx.get("https://api.deepseek.com/user/balance").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    provider = DeepSeek(deepseek_cfg)
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="invalid API key"):
            await provider.fetch_balance(http, "bad-key")


@respx.mock
async def test_kimi_balance():
    cfg = BalanceProviderConfig(id="kimi", name="Kimi", type=ProviderType.balance, kind="kimi")
    respx.get("https://api.moonshot.ai/v1/users/me/balance").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "available_balance": 49.58,
                    "voucher_balance": 46.58,
                    "cash_balance": 3.0,
                },
            },
        )
    )
    provider = Kimi(cfg)
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, "sk-test")
    assert balance.available == 49.58
    assert balance.granted == 46.58
    assert balance.topped_up == 3.0


@respx.mock
async def test_openrouter_monthly_usage():
    cfg = BalanceProviderConfig(
        id="openrouter", name="OpenRouter", type=ProviderType.balance, kind="openrouter"
    )
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {"usage_monthly": 6.29, "label": "sk-..."}})
    )
    provider = OpenRouter(cfg)
    assert provider.usage_cumulative is False
    async with httpx.AsyncClient() as http:
        usage = await provider.fetch_usage(http, "sk-test")
    assert usage.total == 6.29
    assert usage.currency == "USD"


@respx.mock
async def test_openrouter_balance_is_credits_minus_usage():
    cfg = BalanceProviderConfig(
        id="openrouter", name="OpenRouter", type=ProviderType.balance, kind="openrouter"
    )
    respx.get("https://openrouter.ai/api/v1/credits").mock(
        return_value=httpx.Response(
            200, json={"data": {"total_credits": 10.0, "total_usage": 9.9835}}
        )
    )
    provider = OpenRouter(cfg)
    async with httpx.AsyncClient() as http:
        balance = await provider.fetch_balance(http, "sk-test")
    assert balance.available == 0.0165
    assert balance.currency == "USD"


@respx.mock
async def test_zai_quota_and_plan():
    cfg = BalanceProviderConfig(id="glm", name="Z.AI", type=ProviderType.balance, kind="zai")
    respx.get("https://api.z.ai/api/monitor/usage/quota/limit").mock(
        return_value=httpx.Response(
            200,
            json={
                "code": 0,
                "success": True,
                "data": {
                    "level": "pro",
                    "limits": [
                        {"type": "TOKENS_LIMIT", "percentage": 62, "nextResetTime": 1787372813339},
                        {"type": "TOKENS_LIMIT", "percentage": 30, "nextResetTime": 1787372813339},
                        {"type": "TIME_LIMIT", "percentage": 10, "nextResetTime": 1787372813339},
                    ],
                },
            },
        )
    )
    provider = ZAI(cfg)
    async with httpx.AsyncClient() as http:
        quota = await provider.fetch_quota(http, "sk")
        plan = await provider.fetch_plan(http, "sk")
        balance = await provider.fetch_balance(http, "sk")
    assert balance is None
    assert plan == "GLM Coding pro"
    assert [w.label for w in quota] == ["5h", "7d", "30d"]
    assert quota[0].utilization_pct == 62


@respx.mock
async def test_zai_no_coding_plan():
    cfg = BalanceProviderConfig(id="glm", name="Z.AI", type=ProviderType.balance, kind="zai")
    respx.get("https://api.z.ai/api/monitor/usage/quota/limit").mock(
        return_value=httpx.Response(200, json={"code": 500, "msg": "no plan", "success": False})
    )
    provider = ZAI(cfg)
    async with httpx.AsyncClient() as http:
        with pytest.raises(ProviderError, match="Z.AI"):
            await provider.fetch_quota(http, "sk")
