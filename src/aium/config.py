"""General settings (pydantic-settings + YAML) and provider CRUD."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import TypeAdapter
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from . import paths
from .models import ProviderConfig


class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """Settings source that reads a flat YAML file."""

    def __init__(self, settings_cls: type[BaseSettings], yaml_path: Path):
        super().__init__(settings_cls)
        self.yaml_path = yaml_path
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.yaml_path.exists():
            return {}
        data = yaml.safe_load(self.yaml_path.read_text()) or {}
        return data if isinstance(data, dict) else {}

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        if field_name in self._data:
            return self._data[field_name], field_name, False
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field_name, field in self.settings_cls.model_fields.items():
            value, key, _ = self.get_field_value(field, field_name)
            if value is not None:
                data[key] = value
        return data


class Settings(BaseSettings):
    """General settings (config.yaml + AIUM_* environment variables)."""

    base_currency: str = "USD"
    poll_interval_minutes: int = 60

    model_config = SettingsConfigDict(env_prefix="AIUM_", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls, paths.config_file()),
        )


def load_settings() -> Settings:
    return Settings()


_ProvidersList = TypeAdapter(list[ProviderConfig])


def load_providers() -> list[ProviderConfig]:
    f = paths.providers_file()
    if not f.exists():
        return []
    data = yaml.safe_load(f.read_text()) or {}
    items = data.get("providers", data) if isinstance(data, dict) else data
    return _ProvidersList.validate_python(items)


def save_providers(providers: list[ProviderConfig]) -> None:
    paths.ensure_dirs()
    items = [p.model_dump(mode="json") for p in providers]
    paths.providers_file().write_text(
        yaml.safe_dump({"providers": items}, sort_keys=False, allow_unicode=True)
    )


def get_provider(providers: list[ProviderConfig], provider_id: str) -> ProviderConfig | None:
    return next((p for p in providers if p.id == provider_id), None)


def upsert_provider(
    providers: list[ProviderConfig], provider: ProviderConfig
) -> list[ProviderConfig]:
    others = [p for p in providers if p.id != provider.id]
    return [*others, provider]


def remove_provider(providers: list[ProviderConfig], provider_id: str) -> list[ProviderConfig]:
    return [p for p in providers if p.id != provider_id]
