"""Provider registry: maps a kind string to its implementation and metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import ProviderType
from .anthropic import Anthropic
from .base import Provider
from .deepseek import DeepSeek
from .google import Google
from .kimi import Kimi
from .openai import OpenAI
from .openrouter import OpenRouter
from .zai import ZAI


@dataclass(frozen=True)
class ProviderSpec:
    kind: str
    name: str
    currency: str
    pricing_url: str
    provider_type: ProviderType
    cls: type[Provider] | None
    uses_api_key: bool = True
    usage_url: str = ""
    peak_window: str | None = None
    balance_kind: str = "prepaid"
    balance_label: str = "balance"


BALANCE_PROVIDERS: dict[str, ProviderSpec] = {
    "deepseek": ProviderSpec(
        kind="deepseek",
        name="DeepSeek",
        currency="USD",
        pricing_url="https://api-docs.deepseek.com/quick_start/pricing",
        provider_type=ProviderType.balance,
        cls=DeepSeek,
        usage_url="https://platform.deepseek.com/usage",
        peak_window="00:30-16:30",
    ),
    "kimi": ProviderSpec(
        kind="kimi",
        name="Kimi (Moonshot)",
        currency="USD",
        pricing_url="https://platform.kimi.ai/docs/pricing/chat.md",
        provider_type=ProviderType.balance,
        cls=Kimi,
        usage_url="https://platform.kimi.ai/console/usage",
    ),
    "openai": ProviderSpec(
        kind="openai",
        name="OpenAI (Codex)",
        currency="USD",
        pricing_url="https://platform.openai.com/docs/pricing",
        provider_type=ProviderType.balance,
        cls=OpenAI,
        uses_api_key=False,
        usage_url="https://platform.openai.com/usage",
    ),
    "anthropic": ProviderSpec(
        kind="anthropic",
        name="Anthropic (Claude Code)",
        currency="USD",
        pricing_url="https://platform.claude.com/docs/en/about-claude/pricing",
        provider_type=ProviderType.balance,
        cls=Anthropic,
        uses_api_key=False,
        usage_url="https://platform.claude.com/usage",
        balance_kind="budget",
        balance_label="budget",
    ),
    "openrouter": ProviderSpec(
        kind="openrouter",
        name="OpenRouter",
        currency="USD",
        pricing_url="https://openrouter.ai/models",
        provider_type=ProviderType.balance,
        cls=OpenRouter,
        usage_url="https://openrouter.ai/activity",
        balance_label="credits",
    ),
    "google": ProviderSpec(
        kind="google",
        name="Google (Antigravity)",
        currency="USD",
        pricing_url="https://aistudio.google.com/pricing",
        provider_type=ProviderType.balance,
        cls=Google,
        uses_api_key=False,
        usage_url="https://aistudio.google.com/",
    ),
    "zai": ProviderSpec(
        kind="zai",
        name="Z.AI (GLM)",
        currency="USD",
        pricing_url="https://z.ai/",
        provider_type=ProviderType.balance,
        cls=ZAI,
        usage_url="https://z.ai/",
    ),
}

MANUAL_SPEC = ProviderSpec(
    kind="manual",
    name="Manual subscription",
    currency="USD",
    pricing_url="",
    provider_type=ProviderType.manual,
    cls=None,
)


def get_spec(kind: str) -> ProviderSpec | None:
    return BALANCE_PROVIDERS.get(kind) or (MANUAL_SPEC if kind == "manual" else None)


def balance_kinds() -> list[str]:
    return list(BALANCE_PROVIDERS.keys())


def all_kinds() -> list[str]:
    return [*BALANCE_PROVIDERS.keys(), "manual"]


def build_provider(config: Any) -> Provider:
    if config.type == ProviderType.manual:
        from .manual import ManualSubscription

        return ManualSubscription(config)
    spec = BALANCE_PROVIDERS.get(config.kind)
    if spec is None or spec.cls is None:
        raise ValueError(f"unknown provider kind: {config.kind}")
    return spec.cls(config)
