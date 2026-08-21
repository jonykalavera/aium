"""Manual (fixed-cost subscription) provider: no API polling."""

from __future__ import annotations

import calendar
from datetime import datetime
from typing import cast

from ..models import Cycle, ManualProviderConfig, utcnow
from .base import ManualProvider


class ManualSubscription(ManualProvider):
    def __init__(self, config: ManualProviderConfig):
        super().__init__(config)

    def _config(self) -> ManualProviderConfig:
        return cast(ManualProviderConfig, self.config)

    def monthly_equivalent(self) -> float:
        config = self._config()
        if config.cycle == Cycle.yearly:
            return round(config.cost / 12, 2)
        return config.cost

    def days_until_renewal(self, now: datetime | None = None) -> int | None:
        config = self._config()
        if config.cycle == Cycle.yearly:
            return None
        now = now or utcnow()
        today = now.day
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        target = min(config.renewal_day, days_in_month)
        if today <= target:
            return target - today
        return days_in_month - today + target
