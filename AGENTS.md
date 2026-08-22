# AGENTS.md

AI usage monitor: a Python CLI core + a GNOME Shell extension (passive outlet).

## Two components, one contract

- **`src/aium/`** — Python core. Owns all config, secrets, history and polling.
- **`extension/`** — GJS (GNOME Shell 50, ESM). Pure display: reads
  `~/.cache/aium/status.json` and renders it. **No provider CRUD, no secrets** —
  everything is done via the CLI (`aium providers|keys ...`).
- The JSON schema in `src/aium/models.py` (`StatusFile`/`ProviderStatus`) is the
  contract between the two. Changing a field means updating both `service.py`
  and `extension/extension.js`.

## Commands

```bash
uv sync --all-groups --locked   # install deps
make uv.check                   # ruff lint + ty typecheck + ruff format --check
make uv.test                    # pytest --cov aium --blockage (network blocked)
make uv.typecheck / make uv.lint / make uv.format
```

Recipes use bare commands; the `uv.%` wrapper (`make uv.<target>`) runs them in
the uv venv. Run `make uv.check` before considering work done.

The systemd timer (`systemctl --user list-timers aium-poll.timer`) runs the
**installed** binary at `~/.local/bin/aium`, not `uv run aium` — after core
changes, reinstall it (`uv tool install --force .` or `./local-install.sh`), or
the timer keeps polling with the previous build.

`install.sh` is the remote `curl | bash` installer (downloads from GitHub, honors
`AIUM_VERSION`); `local-install.sh` installs from this repo for development.

## Type checking (ty)

- ty is in `[tool.ty]` (pyproject) and runs over `src tests`.
- **ty does NOT respect `# type: ignore[code]`** (only plain `# type: ignore`
  or `# ty: ignore`). Prefer fixing types: `cast(...)`, `TypedDict` for
  `**kwargs` spread into pydantic models, `assert x is not None` to narrow.

## Adding a provider

Create `src/aium/providers/<name>.py` implementing a class in
`providers/base.py` and register it in `providers/registry.py` (`ProviderSpec`:
kind, name, pricing/usage URLs, `peak_window`, `uses_api_key`). `service.py`
falls back to the spec's `usage_url`/`peak_window` when the config omits them.

Set the spec's `balance_kind`/`balance_label` for what `fetch_balance()`
returns: `prepaid` (`balance`/`credits`) or `budget`. Only `prepaid` balances
are summed into `Totals.balance`.

Provider methods: `fetch_balance()`, `fetch_usage()`, `fetch_quota()`,
`fetch_plan()` (all may be `None`/`[]`). Set `usage_cumulative = True` when
`fetch_usage()` returns an all-time counter (monthly spend is then derived from
its delta).

**API-key providers** (deepseek, kimi, openrouter) read secrets from the system
keyring (service `aium`) — set with `aium keys set <id>` (validates the id
exists to avoid typo strays; `aium keys list` shows orphans).

**OAuth providers** (openai, anthropic, google) read the CLI's credential files
from disk, not keyring, and hit private/undocumented endpoints. Env override
for tests: `AIUM_CODEX_AUTH` (`~/.codex/auth.json`), `AIUM_ANTHROPIC_CREDS`
(`~/.claude/.credentials.json`), `AIUM_GEMINI_CREDS` (`~/.gemini/oauth_creds.json`).
Token refresh writes back atomically (`providers/oauth.py`); endpoints may
break without notice.

**Cursor** (`uses_api_key=False`) reads the IDE session from
`~/.config/Cursor/User/globalStorage/state.vscdb` (`cursorAuth/accessToken`),
falling back to `~/.config/cursor/auth.json`; tests override with
`AIUM_CURSOR_AUTH` / `AIUM_CURSOR_DB`. The session is not refreshed — sign in
to the IDE again if it expires.

## Storage / ledger

- SQLite at `~/.local/share/aium/history.db` (tables `snapshots`,
  `quota_history`, `usage_history`). Always use the `_conn` context manager in
  `storage.py` (it `commit()`s and `close()`s — plain `sqlite3.connect` with
  `with` leaks connections).
- `ledger.py` derives monthly spend from balance deltas (top-up aware),
  cumulative-usage deltas, and `peak_window` (UTC "HH:MM-HH:MM", may wrap
  midnight). DeepSeek defaults to peak `00:30-16:30` (off-peak 16:30-00:30).

## GNOME extension gotchas (hard-won)

- `PanelMenu.Button` is a `ButtonBox` that **only allocates its first child** —
  wrap icon + text in a single `St.BoxLayout` before `add_child`.
- A `St.DrawingArea` subclass **must** be registered with
  `GObject.registerClass` (else "Tried to construct an object without a GType").
- Cairo import is **`gi://cairo` (lowercase)** on this system, not `gi://Cairo`.
- `ui/tooltip.js` does not exist in GNOME 50; the extension ships its own
  `PanelTooltip`.
- Panel labels need a CSS `min-width` — a crowded right box squeezes children
  to their minimum (text collapses to 1px).
- **No hot reload on Wayland**: `gnome-extensions disable/enable` does NOT
  reload `extension.js` (ESM cache). Schema/metadata changes need logout/login.
  For iteration use `./scripts/dev-nested.sh` (`dbus-run-session -- gnome-shell
  --wayland --devkit`); requires the `mutter-devkit` package. `dev-install.sh`
  copies files, compiles the schema and installs the robot icon.

## Tests

- pytest + `respx` (mock HTTP) + `pytest-blockage` (blocks real network in
  `make uv.test`). Fixtures: `isolated_home` (points XDG dirs at tmp),
  `fake_secrets` (in-memory keyring). OAuth provider tests set the `AIUM_*_CREDS`
  env vars to temp credential files.
