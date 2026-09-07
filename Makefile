SHELL := /bin/bash

.PHONY: format lint check typecheck test ext-test omarchy-sync omarchy-check omarchy-install

PYTHON_DIRS ?= src tests
UV_VERSION ?= 0.12.5


# ── UV rules ───────────────────────────────────────────────────────────────────
install-uv:
	curl -LsSf https://astral.sh/uv/$(UV_VERSION)/install.sh | sh

install-python: install-uv
	uv python install $$(cat .python-version)

# Wrap any target in uv's environment: make uv.lint, make uv.test, ...
uv.%:
	uv run $(MAKE) -s $*

# ── Developer rules ────────────────────────────────────────────────────────────
install:
	uv sync --all-groups --locked

format:
	ruff format $(PYTHON_DIRS)
	ruff check --fix-only $(PYTHON_DIRS)

lint:
	ruff check $(PYTHON_DIRS)

typecheck:
	-ty check $(PYTHON_DIRS)

check: lint typecheck
	ruff format --check $(PYTHON_DIRS)

test:
	pytest --cov aium --blockage

ext-test:
	gjs -m extension/tests/run.js
	./scripts/check-extension-syntax.sh

# ── Omarchy shell plugin ──────────────────────────────────────────────────────
# The display logic in omarchy/lib is GENERATED from extension/lib (the
# source of truth); omarchy-check re-syncs and fails on drift. Local visual
# iteration: make omarchy-install (hot-reloads in omarchy-shell).
omarchy-sync:
	python3 scripts/sync-omarchy-lib.py

omarchy-check: omarchy-sync
	python3 scripts/check-omarchy.py

omarchy-install:
	./scripts/omarchy-install.sh

run-%:
	./scripts/$*.sh

release:
	@test -n "$(VERSION)" || (echo "Usage: make release VERSION=0.1.0" && exit 1)
	git tag -a "v$(VERSION)" -m "Release v$(VERSION)"
	git push origin "v$(VERSION)"
