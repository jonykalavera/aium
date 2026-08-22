"""Pydantic models: provider config, balances, usage and aggregated status."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ProviderType(StrEnum):
    balance = "balance"
    cloud = "cloud"
    manual = "manual"


class Cycle(StrEnum):
    monthly = "monthly"
    yearly = "yearly"


class BaseProviderConfig(BaseModel):
    id: str
    name: str
    type: ProviderType
    currency: str = "USD"
    pricing_url: str | None = None
    usage_url: str | None = None
    peak_window: str | None = Field(
        default=None, description="UTC peak window 'HH:MM-HH:MM' (high tariff hours)"
    )
    enabled: bool = True


class BalanceProviderConfig(BaseProviderConfig):
    type: Literal[ProviderType.balance] = ProviderType.balance
    kind: str


class CloudProviderConfig(BaseProviderConfig):
    type: Literal[ProviderType.cloud] = ProviderType.cloud
    kind: str


class ManualProviderConfig(BaseProviderConfig):
    type: Literal[ProviderType.manual] = ProviderType.manual
    cost: float = Field(gt=0, description="Cost per cycle in `currency`")
    cycle: Cycle = Cycle.monthly
    renewal_day: int = Field(default=1, ge=1, le=31)


ProviderConfig = Annotated[
    BalanceProviderConfig | CloudProviderConfig | ManualProviderConfig,
    Field(discriminator="type"),
]


class Balance(BaseModel):
    available: float = 0.0
    granted: float = 0.0
    topped_up: float = 0.0
    currency: str = "USD"


class Usage(BaseModel):
    total: float
    currency: str
    period_start: datetime | None = None
    period_end: datetime | None = None


class QuotaWindow(BaseModel):
    label: str
    utilization_pct: int
    resets_at: datetime | None = None


class ProviderStatus(BaseModel):
    id: str
    name: str
    type: ProviderType
    currency: str
    ok: bool = True
    error: str | None = None
    balance: Balance | None = None
    balance_kind: str | None = None
    balance_label: str | None = None
    spend_this_month: float | None = None
    spend_today: float | None = None
    usage: Usage | None = None
    quota: list[QuotaWindow] = []
    sparkline: list[float] | None = None
    plan: str | None = None
    peak: bool | None = None
    usage_url: str | None = None
    subscription: ManualProviderConfig | None = None
    days_until_renewal: int | None = None
    last_updated: datetime | None = None


class Totals(BaseModel):
    spend_this_month: float = 0.0
    spend_today: float = 0.0
    balance: float = 0.0
    currency: str = "USD"
    # Spend per local day of the current month (oldest to newest, today last),
    # summed across providers. Zeros for days with no data.
    spend_daily: list[float] = []


class StatusFile(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    totals: Totals
    providers: list[ProviderStatus]


def utcnow() -> datetime:
    return datetime.now(UTC)
