"""Secrets storage backed by the system keyring."""

from __future__ import annotations

from contextlib import suppress

import keyring
import keyring.errors

SERVICE = "aium"


class SecretsStore:
    """Read/write provider credentials in the system keyring."""

    def set(self, provider_id: str, secret: str) -> None:
        keyring.set_password(SERVICE, provider_id, secret)

    def get(self, provider_id: str) -> str | None:
        try:
            return keyring.get_password(SERVICE, provider_id)
        except keyring.errors.NoKeyringError:
            return None

    def delete(self, provider_id: str) -> None:
        with suppress(keyring.errors.PasswordDeleteError):
            keyring.delete_password(SERVICE, provider_id)

    def list_ids(self) -> list[str]:
        """Return every provider id that has a stored secret (incl. orphans)."""
        try:
            import secretstorage

            bus = secretstorage.dbus_init()
            collection = secretstorage.get_default_collection(bus)
            items = collection.search_items({"service": SERVICE})
            ids = []
            for item in items:
                username = item.get_attributes().get("username")
                if isinstance(username, str) and username:
                    ids.append(username)
            return sorted(set(ids))
        except Exception:  # noqa: BLE001 - keyring may be unavailable
            return []
