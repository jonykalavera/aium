"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from aium.secrets import SecretsStore


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point config/data/cache to a temporary directory."""
    monkeypatch.setenv("AIUM_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("AIUM_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("AIUM_CACHE_HOME", str(tmp_path / "cache"))
    yield tmp_path


@pytest.fixture
def fake_secrets(monkeypatch):
    """Replace keyring with an in-memory dict."""
    data: dict[str, str] = {}
    monkeypatch.setattr(SecretsStore, "set", lambda self, pid, v: data.__setitem__(pid, v))
    monkeypatch.setattr(SecretsStore, "get", lambda self, pid: data.get(pid))
    monkeypatch.setattr(SecretsStore, "delete", lambda self, pid: data.pop(pid, None))
    monkeypatch.setattr(SecretsStore, "list_ids", lambda self: sorted(data.keys()))
    return data
