SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.ONESHELL:

.DEFAULT_GOAL := help

ENV_FILE ?= .env
RUNNER_IMAGE ?= realmoi-runner:dev
BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000

define LOAD_ENV
set -a
if [[ -f "$(ENV_FILE)" ]]; then
  source "$(ENV_FILE)"
fi
set +a
endef

.PHONY: help
help:
	@echo "Targets:"
	@echo "  make dev            Start backend + frontend (dev)"
	@echo "  make test           Run backend tests (pytest)"
	@echo "  make runner-build   Build runner docker image"
	@echo "  make e2e-knapsack   End-to-end knapsack test (requires running backend + valid upstream key)"
	@echo "  make backend-deps   Create venv + install backend deps"
	@echo "  make frontend-deps  Install frontend deps"
	@echo ""
	@echo "Notes:"
	@echo "  - Put secrets/config into .env (ignored by git) or export env vars before running."
	@echo "  - Required for real Codex runs: REALMOI_OPENAI_API_KEY."

.PHONY: runner-build
runner-build:
	echo "[make] building runner image: $(RUNNER_IMAGE)"
	docker build -t "$(RUNNER_IMAGE)" "runner"

.PHONY: backend-deps
backend-deps:
	$(LOAD_ENV)
	if [[ ! -d ".venv" ]]; then
	  python3 -m venv ".venv"
	fi
	source ".venv/bin/activate"
	pip install -q -r "backend/requirements-dev.txt"

.PHONY: frontend-deps
frontend-deps:
	if [[ -d "frontend/node_modules" ]]; then
	  echo "[make] frontend/node_modules exists"
	  exit 0
	fi
	cd "frontend"
	npm install

.PHONY: dev
dev: runner-build backend-deps frontend-deps
	$(LOAD_ENV)

	export REALMOI_RUNNER_IMAGE="$(RUNNER_IMAGE)"
	export REALMOI_OPENAI_BASE_URL="$${REALMOI_OPENAI_BASE_URL:-https://api.openai.com}"
	export REALMOI_JWT_SECRET="$${REALMOI_JWT_SECRET:-dev-secret-change-me}"
	export REALMOI_ALLOW_SIGNUP="$${REALMOI_ALLOW_SIGNUP:-1}"
	export REALMOI_ADMIN_USERNAME="$${REALMOI_ADMIN_USERNAME:-admin}"
	export REALMOI_ADMIN_PASSWORD="$${REALMOI_ADMIN_PASSWORD:-admin-password-123}"

	source ".venv/bin/activate"

	echo "[make] backend: http://localhost:$(BACKEND_PORT) (api: /api)"
	uvicorn backend.app.main:app --reload --host "$(BACKEND_HOST)" --port "$(BACKEND_PORT)" &
	BACKEND_PID=$$!

	echo "[make] frontend: http://localhost:$(FRONTEND_PORT)"
	cd "frontend"
	export NEXT_PUBLIC_API_BASE_URL="$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:$(BACKEND_PORT)/api}"
	export PORT="$(FRONTEND_PORT)"
	npm run dev &
	FRONTEND_PID=$$!

	trap 'kill "$${BACKEND_PID}" "$${FRONTEND_PID}" 2>/dev/null || true' INT TERM EXIT
	wait "$${BACKEND_PID}" "$${FRONTEND_PID}"

.PHONY: test
test: backend-deps
	$(LOAD_ENV)
	source ".venv/bin/activate"
	pytest

.PHONY: e2e-knapsack
e2e-knapsack: backend-deps runner-build
	$(LOAD_ENV)
	source ".venv/bin/activate"
	python3 -X utf8 "scripts/e2e_knapsack.py"
