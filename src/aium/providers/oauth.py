"""OAuth helpers: read CLI credential files and refresh access tokens."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx


class OAuthError(Exception):
    """Raised when OAuth credentials cannot be read or refreshed."""


def load_json(path: str | Path) -> dict:
    path = Path(path).expanduser()
    if not path.exists():
        raise OAuthError(f"credentials file not found at {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise OAuthError(f"could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OAuthError(f"could not parse {path}: top-level value is not an object")
    return data


def atomic_write(path: str | Path, data: dict) -> None:
    path = Path(path).expanduser()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


async def refresh_token(
    http: httpx.AsyncClient,
    token_url: str,
    client_id: str,
    refresh_token: str,
    *,
    scope: str | None = None,
    client_secret: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict:
    """Exchange a refresh token for a fresh access token. Returns the raw JSON."""
    body: dict[str, str] = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if scope:
        body["scope"] = scope
    if client_secret:
        body["client_secret"] = client_secret
    headers = {"Content-Type": "application/json", **(extra_headers or {})}
    resp = await http.post(token_url, json=body, headers=headers)
    if resp.status_code in (400, 401):
        raise OAuthError(f"refresh token rejected (HTTP {resp.status_code})")
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or "access_token" not in data:
        raise OAuthError("token response missing access_token")
    return data


def jwt_exp(id_token: str) -> float | None:
    """Return the `exp` claim (epoch seconds) of a JWT, or None."""
    try:
        payload = id_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload))
        exp = data.get("exp")
        return float(exp) if isinstance(exp, (int, float)) else None
    except IndexError, ValueError, TypeError, json.JSONDecodeError:
        return None
