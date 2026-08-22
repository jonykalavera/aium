import json

import httpx
import respx
from typer.testing import CliRunner

from aium.cli import app
from aium.config import load_providers, save_providers
from aium.models import (
    Balance,
    BalanceProviderConfig,
    Cycle,
    ManualProviderConfig,
    ProviderStatus,
    ProviderType,
)
from aium.service import _aggregate

runner = CliRunner()


def test_init_and_add_manual_provider():
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(
        app,
        [
            "providers",
            "add",
            "manual",
            "--id",
            "chatgpt",
            "--name",
            "ChatGPT Plus",
            "--cost",
            "20",
            "--cycle",
            "monthly",
            "--renewal-day",
            "15",
        ],
    )
    assert result.exit_code == 0, result.output

    providers = load_providers()
    assert providers[0].id == "chatgpt"
    assert providers[0].type == ProviderType.manual
    assert providers[0].cost == 20.0


def test_manual_requires_cost():
    result = runner.invoke(app, ["providers", "add", "manual", "--id", "x"])
    assert result.exit_code == 1
    assert "--cost is required" in result.output


def test_add_unknown_kind():
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["providers", "add", "nope"])
    assert result.exit_code == 1
    assert "Unknown kind" in result.output


def test_yaml_roundtrip():
    save_providers(
        [
            BalanceProviderConfig(
                id="ds", name="DeepSeek", type=ProviderType.balance, kind="deepseek"
            ),
            ManualProviderConfig(
                id="plus",
                name="ChatGPT Plus",
                type=ProviderType.manual,
                cost=20.0,
                cycle=Cycle.monthly,
                renewal_day=15,
            ),
        ]
    )
    providers = load_providers()
    assert providers[0].type == ProviderType.balance
    assert providers[0].kind == "deepseek"
    assert providers[1].type == ProviderType.manual
    assert providers[1].cost == 20.0


@respx.mock
def test_poll_and_status(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["providers", "add", "deepseek"]).exit_code == 0
    assert runner.invoke(app, ["keys", "set", "deepseek", "--secret", "sk-test"]).exit_code == 0

    respx.get("https://api.deepseek.com/user/balance").mock(
        return_value=httpx.Response(
            200,
            json={"balance_infos": [{"currency": "USD", "total_balance": "100.00"}]},
        )
    )

    result = runner.invoke(app, ["poll"])
    assert result.exit_code == 0, result.output
    assert "deepseek" in result.output

    status_result = runner.invoke(app, ["status", "--json"])
    assert status_result.exit_code == 0
    payload = json.loads(status_result.stdout)
    assert payload["totals"]["balance"] == 100.0
    assert payload["providers"][0]["id"] == "deepseek"
    assert payload["providers"][0]["ok"] is True
    assert payload["providers"][0]["usage_url"] == "https://platform.deepseek.com/usage"
    assert isinstance(payload["providers"][0]["peak"], bool)


def test_add_deepseek_sets_peak_window(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["providers", "add", "deepseek"]).exit_code == 0
    assert load_providers()[0].peak_window == "00:30-16:30"


def test_update_peak_window(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["providers", "add", "deepseek"]).exit_code == 0
    result = runner.invoke(app, ["providers", "update", "deepseek", "--peak-window", "20:00-08:00"])
    assert result.exit_code == 0, result.output
    assert load_providers()[0].peak_window == "20:00-08:00"


def test_update_usage_url(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["providers", "add", "deepseek"]).exit_code == 0
    result = runner.invoke(
        app, ["providers", "update", "deepseek", "--usage-url", "https://example.com/u"]
    )
    assert result.exit_code == 0, result.output
    providers = load_providers()
    assert providers[0].usage_url == "https://example.com/u"


@respx.mock
def test_poll_does_not_crash_on_http_error(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["providers", "add", "deepseek"]).exit_code == 0
    assert runner.invoke(app, ["keys", "set", "deepseek", "--secret", "sk-test"]).exit_code == 0

    respx.get("https://api.deepseek.com/user/balance").mock(
        return_value=httpx.Response(500, json={"error": "boom"})
    )

    result = runner.invoke(app, ["poll"])
    assert result.exit_code == 0, result.output
    assert "deepseek" in result.output

    status_result = runner.invoke(app, ["status", "--json"])
    payload = json.loads(status_result.stdout)
    assert payload["providers"][0]["id"] == "deepseek"
    assert payload["providers"][0]["ok"] is False


@respx.mock
def test_openrouter_usage_uses_usage_monthly(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["providers", "add", "openrouter"]).exit_code == 0
    assert runner.invoke(app, ["keys", "set", "openrouter", "--secret", "sk-test"]).exit_code == 0

    respx.get("https://openrouter.ai/api/v1/credits").mock(
        return_value=httpx.Response(
            200, json={"data": {"total_credits": 10.0, "total_usage": 3.71}}
        )
    )
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {"usage_monthly": 2.0}})
    )
    assert runner.invoke(app, ["poll"]).exit_code == 0
    # spend reflects the provider's own monthly usage, not a balance delta
    respx.get("https://openrouter.ai/api/v1/key").mock(
        return_value=httpx.Response(200, json={"data": {"usage_monthly": 6.29}})
    )
    assert runner.invoke(app, ["poll"]).exit_code == 0

    status_result = runner.invoke(app, ["status", "--json"])
    payload = json.loads(status_result.stdout)
    provider = payload["providers"][0]
    assert provider["id"] == "openrouter"
    assert provider["spend_this_month"] == 6.29
    assert provider["balance"]["available"] == 6.29
    assert provider["sparkline"] == [4.29]


def test_keys_set_rejects_unknown_provider(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["keys", "set", "nope", "--secret", "x"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_keys_list_marks_orphans(fake_secrets):
    assert runner.invoke(app, ["init"]).exit_code == 0
    assert runner.invoke(app, ["providers", "add", "deepseek"]).exit_code == 0
    assert runner.invoke(app, ["keys", "set", "deepseek", "--secret", "x"]).exit_code == 0
    fake_secrets["orphan"] = "y"

    result = runner.invoke(app, ["keys", "list"])
    assert result.exit_code == 0
    assert "deepseek" in result.output
    assert "orphan" in result.output


def test_aggregate_only_prepaid_balance():
    prepaid = ProviderStatus(
        id="ds",
        name="DeepSeek",
        type=ProviderType.balance,
        currency="USD",
        balance=Balance(available=10),
        balance_kind="prepaid",
        spend_this_month=2,
        spend_today=0.5,
    )
    budget = ProviderStatus(
        id="an",
        name="Anthropic",
        type=ProviderType.balance,
        currency="USD",
        balance=Balance(available=20),
        balance_kind="budget",
        spend_this_month=0,
        spend_today=0,
    )
    totals = _aggregate([prepaid, budget], "USD")
    assert totals.balance == 10.0
    assert totals.spend_this_month == 2.0
    assert totals.spend_today == 0.5
