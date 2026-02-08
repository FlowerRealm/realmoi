SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.ONESHELL:

.DEFAULT_GOAL := help

ENV_FILE ?= .env
RUNNER_IMAGE ?= realmoi-runner:dev
BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000
REALMOI_BUILD_USE_CN_MIRROR ?= 1
REALMOI_BUILD_PIP_INDEX_URL ?= https://pypi.tuna.tsinghua.edu.cn/simple
REALMOI_BUILD_NPM_REGISTRY ?= https://registry.npmmirror.com
REALMOI_BUILD_APT_MIRROR ?= https://mirrors.ustc.edu.cn

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
	@echo "  make docker-build-local  Build backend/frontend/runner images locally"
	@echo "  make docker-up-local     Local build + docker compose up -d (no pull)"
	@echo "  make e2e-knapsack   End-to-end knapsack test (requires running backend + valid upstream key)"
	@echo "  make backend-deps   Create venv + install backend deps"
	@echo "  make frontend-deps  Install frontend deps"
	@echo ""
	@echo "Notes:"
	@echo "  - Put secrets/config into .env (ignored by git) or export env vars before running."
	@echo "  - Built-in CN mirrors are enabled by default. Use REALMOI_BUILD_USE_CN_MIRROR=0 to disable."
	@echo "  - Mirror overrides: REALMOI_BUILD_PIP_INDEX_URL / REALMOI_BUILD_NPM_REGISTRY / REALMOI_BUILD_APT_MIRROR."
	@echo "  - Required for real Codex runs: valid upstream API key (env or admin channel config)."

.PHONY: runner-build
runner-build:
	$(LOAD_ENV)
	BUILD_ARGS=()
	BUILD_ARGS+=(--build-arg "USE_CN_MIRROR=$${REALMOI_BUILD_USE_CN_MIRROR:-1}")
	if [[ -n "$${REALMOI_BUILD_NPM_REGISTRY:-}" ]]; then
	  BUILD_ARGS+=(--build-arg "NPM_REGISTRY=$${REALMOI_BUILD_NPM_REGISTRY}")
	fi
	if [[ -n "$${REALMOI_BUILD_APT_MIRROR:-}" ]]; then
	  BUILD_ARGS+=(--build-arg "APT_MIRROR=$${REALMOI_BUILD_APT_MIRROR}")
	fi
	echo "[make] building runner image: $(RUNNER_IMAGE)"
	docker build "$${BUILD_ARGS[@]}" -t "$(RUNNER_IMAGE)" "runner"

.PHONY: docker-build-local
docker-build-local:
	$(LOAD_ENV)
	export REALMOI_RUNNER_IMAGE="$${REALMOI_RUNNER_IMAGE:-realmoi/realmoi-runner:latest}"
	export REALMOI_BUILD_USE_CN_MIRROR="$${REALMOI_BUILD_USE_CN_MIRROR:-1}"
	export REALMOI_BUILD_PIP_INDEX_URL="$${REALMOI_BUILD_PIP_INDEX_URL:-}"
	export REALMOI_BUILD_NPM_REGISTRY="$${REALMOI_BUILD_NPM_REGISTRY:-}"
	export REALMOI_BUILD_APT_MIRROR="$${REALMOI_BUILD_APT_MIRROR:-}"
	BUILD_ARGS=()
	BUILD_ARGS+=(--build-arg "USE_CN_MIRROR=$${REALMOI_BUILD_USE_CN_MIRROR:-1}")
	if [[ -n "$${REALMOI_BUILD_NPM_REGISTRY:-}" ]]; then
	  BUILD_ARGS+=(--build-arg "NPM_REGISTRY=$${REALMOI_BUILD_NPM_REGISTRY}")
	fi
	if [[ -n "$${REALMOI_BUILD_APT_MIRROR:-}" ]]; then
	  BUILD_ARGS+=(--build-arg "APT_MIRROR=$${REALMOI_BUILD_APT_MIRROR}")
	fi
	echo "[make] building local runner image: $${REALMOI_RUNNER_IMAGE}"
	docker build "$${BUILD_ARGS[@]}" -t "$${REALMOI_RUNNER_IMAGE}" "runner"
	echo "[make] building local backend/frontend images via docker compose"
	docker compose build backend frontend

.PHONY: docker-up-local
docker-up-local: docker-build-local
	echo "[make] starting stack from locally built images"
	docker compose up -d --no-build

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
