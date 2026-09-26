# AlphaCouncil — developer commands
#
# ⚠️ Every target here is a thin wrapper around `backend/scripts/dev.py`, which
# is the **real implementation**. Reason: `make` is not installed on every
# machine we target — verified 2026-09-26, `which make` finds nothing on the
# primary dev box. A gate that cannot be run is not a gate; it is a sentence in
# a document.
#
#   with make:      make check-lite
#   without make:   python backend/scripts/dev.py check-lite
#
# `check` fails when a gate is missing, so a green run cannot be mistaken for a
# complete one (T-19). Use `check-lite` for the daily loop.

.DEFAULT_GOAL := help
PYTHON ?= python
BACKEND := backend
DEV := $(BACKEND)/scripts/dev.py

ifeq ($(OS),Windows_NT)
	VENV_BIN := $(BACKEND)/.venv/Scripts
else
	VENV_BIN := $(BACKEND)/.venv/bin
endif

.PHONY: help
help: ## Show available commands
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
.PHONY: venv
venv: ## Create the virtual environment
	$(PYTHON) -m venv $(BACKEND)/.venv

.PHONY: install
install: venv ## Install runtime + dev dependencies (editable)
	$(VENV_BIN)/python -m pip install --upgrade pip
	$(VENV_BIN)/python -m pip install -e "$(BACKEND)[dev]"

.PHONY: install-hooks
install-hooks: ## Install pre-commit git hooks
	$(VENV_BIN)/pre-commit install

# ---------------------------------------------------------------------------
# Quality gates — one implementation, in scripts/dev.py
# ---------------------------------------------------------------------------
.PHONY: lint
lint: ## Run ruff lint
	$(VENV_BIN)/python $(DEV) lint

.PHONY: format
format: ## Auto-format with ruff
	$(VENV_BIN)/python -m ruff format $(BACKEND)
	$(VENV_BIN)/python -m ruff check --fix $(BACKEND)

.PHONY: typecheck
typecheck: ## Run mypy in strict mode
	$(VENV_BIN)/python $(DEV) typecheck

.PHONY: licenses
licenses: ## Scan dependencies for copyleft licences (ADR-0024 · L-06)
	$(VENV_BIN)/python $(DEV) licenses

.PHONY: test
test: ## Run unit tests
	$(VENV_BIN)/python $(DEV) test

.PHONY: test-cov
test-cov: ## Run unit tests with coverage report
	$(VENV_BIN)/python $(DEV) test-cov

.PHONY: check
check: ## Run every gate CI runs (skipped gates fail the run)
	$(VENV_BIN)/python $(DEV) check

.PHONY: check-lite
check-lite: ## Run only the gates implemented today
	$(VENV_BIN)/python $(DEV) check-lite

.PHONY: precommit
precommit: ## Run all pre-commit hooks against every file
	$(VENV_BIN)/pre-commit run --all-files

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
.PHONY: run
run: ## Start the API server
	$(VENV_BIN)/python -m alphacouncil

# ⚠️ `dev` and `down` targets were removed on 2026-09-26. They started a
# docker-compose stack (deploy/docker-compose.yml), which belonged to the v1
# "server + Qdrant" architecture. The product is a **Windows desktop
# application with a local SQLite file** — there is no infrastructure to bring
# up. See ADR-0006 / ADR-0007.

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------
.PHONY: clean
clean: ## Remove caches and build artefacts
	$(VENV_BIN)/python $(DEV) clean
