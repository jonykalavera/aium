"""XDG path resolution for config, data and cache directories."""

from __future__ import annotations

import os
from pathlib import Path


def _xdg_dir(env: str, default: str) -> Path:
    value = os.environ.get(env)
    return Path(value).expanduser() if value else Path(default).expanduser()


def config_dir() -> Path:
    base = _xdg_dir("XDG_CONFIG_HOME", "~/.config")
    return Path(os.environ.get("AIUM_CONFIG_HOME", base / "aium"))


def data_dir() -> Path:
    base = _xdg_dir("XDG_DATA_HOME", "~/.local/share")
    return Path(os.environ.get("AIUM_DATA_HOME", base / "aium"))


def cache_dir() -> Path:
    base = _xdg_dir("XDG_CACHE_HOME", "~/.cache")
    return Path(os.environ.get("AIUM_CACHE_HOME", base / "aium"))


def providers_file() -> Path:
    return config_dir() / "providers.yaml"


def config_file() -> Path:
    return config_dir() / "config.yaml"


def db_file() -> Path:
    return data_dir() / "history.db"


def status_file() -> Path:
    return cache_dir() / "status.json"


def ensure_dirs() -> None:
    for d in (config_dir(), data_dir(), cache_dir()):
        d.mkdir(parents=True, exist_ok=True)
