"""Provider abstraction: balance, cloud and manual providers."""

from __future__ import annotations

from abc import abstractmethod

import httpx

from ..models import Balance, ProviderConfig, QuotaWindow, Usage


class ProviderError(Exception):
    """Raised when a provider cannot be queried (auth, HTTP, parsing)."""


class Provider:
    """Base class for all providers."""

    def __init__(self, config: ProviderConfig):
        self.config = config


class BalanceProvider(Provider):
    """Provider with a prepaid/metered balance or usage exposed through an API."""

    #: True when fetch_usage() returns a cumulative total (e.g. OpenRouter's
    #: total usage) instead of a period-specific spend. The service then derives
    #: the monthly spend from the delta within the current month.
    usage_cumulative: bool = False

    @abstractmethod
    async def fetch_balance(self, http: httpx.AsyncClient, secret: str | None) -> Balance | None:
        """Return the current balance, or None if the provider has no balance.
        Raises ProviderError on failure."""

    async def fetch_usage(self, http: httpx.AsyncClient, secret: str | None) -> Usage | None:
        """Optional: authoritative usage for the current period."""
        return None

    async def fetch_quota(self, http: httpx.AsyncClient, secret: str | None) -> list[QuotaWindow]:
        """Optional: rate-limit quota windows (utilization % + reset time)."""
        return []

    async def fetch_plan(self, http: httpx.AsyncClient, secret: str | None) -> str | None:
        """Optional: the account's plan/subscription tier name."""
        return None


class CloudProvider(Provider):
    """Provider billed through a cloud platform (usage/cost APIs)."""

    @abstractmethod
    async def fetch_cost_to_date(self, http: httpx.AsyncClient, secret: str | None) -> Usage:
        """Return month-to-date cost. Raises ProviderError on failure."""


class ManualProvider(Provider):
    """Fixed-cost subscription entered by hand; no API polling."""

    async def status(self) -> Balance | None:
        return None
