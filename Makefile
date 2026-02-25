SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.ONESHELL:

.DEFAULT_GOAL := help

ENV_FILE ?= .env
RUNNER_IMAGE ?= realmoi/realmoi-runner:latest
RUNNER_EXECUTOR ?= local
BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000
REALMOI_BUILD_USE_CN_MIRROR ?= 1
REALMOI_BUILD_PIP_INDEX_URL ?= https://mirrors.aliyun.com/pypi/simple
REALMOI_BUILD_NPM_REGISTRY ?= https://registry.npmmirror.com
REALMOI_BUILD_APT_MIRROR ?= http://mirrors.aliyun.com

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
	@echo "  make dev            Start backend + frontend locally (no docker build)"
	@echo "  make judge          Start independent judge daemon locally"
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
	@echo "  - make dev defaults to local runner execution (RUNNER_EXECUTOR=local) and starts judge in independent mode."
	@echo "  - To force docker runner, set RUNNER_EXECUTOR=docker and ensure RUNNER_IMAGE exists."
	@echo "  - If ports are busy, make dev may reuse existing listeners; otherwise stop the process (or docker compose stack) using them, or override BACKEND_PORT/FRONTEND_PORT."

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
	export REALMOI_RUNNER_EXECUTOR="$${REALMOI_RUNNER_EXECUTOR:-docker}"
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
dev: backend-deps frontend-deps
	$(LOAD_ENV)

	export REALMOI_RUNNER_IMAGE="$(RUNNER_IMAGE)"
	export REALMOI_RUNNER_EXECUTOR="$(RUNNER_EXECUTOR)"
	export REALMOI_JUDGE_MODE="$${REALMOI_JUDGE_MODE:-independent}"
	export REALMOI_OPENAI_BASE_URL="$${REALMOI_OPENAI_BASE_URL:-https://api.openai.com}"
	export REALMOI_JWT_SECRET="$${REALMOI_JWT_SECRET:-dev-secret-change-me}"
	export REALMOI_ALLOW_SIGNUP="$${REALMOI_ALLOW_SIGNUP:-1}"
	export REALMOI_ADMIN_USERNAME="$${REALMOI_ADMIN_USERNAME:-admin}"
	export REALMOI_ADMIN_PASSWORD="$${REALMOI_ADMIN_PASSWORD:-admin-password-123}"

	source ".venv/bin/activate"

	BACKEND_HOST="$(BACKEND_HOST)"
	BACKEND_PORT="$(BACKEND_PORT)"
	FRONTEND_PORT="$(FRONTEND_PORT)"

	BACKEND_PID=0
	FRONTEND_PID=0
	JUDGE_PID=0
	cleanup() {
	  if [[ "$${BACKEND_PID}" -gt 0 ]]; then
	    kill "$${BACKEND_PID}" 2>/dev/null || true
	  fi
	  if [[ "$${FRONTEND_PID}" -gt 0 ]]; then
	    kill "$${FRONTEND_PID}" 2>/dev/null || true
	  fi
	  if [[ "$${JUDGE_PID}" -gt 0 ]]; then
	    kill "$${JUDGE_PID}" 2>/dev/null || true
	  fi
	}
	trap cleanup INT TERM EXIT

	port_is_available() {
	  local port="$$1"
	  python3 -X utf8 -c 'import socket,sys; p=int(sys.argv[1]); s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(("0.0.0.0", p)); s.close()' "$$port" >/dev/null 2>&1
	}

	print_port_diagnostics() {
	  local port="$$1"
	  echo "[make] diagnostics: common suspects for port $$port"
	  ps -eo pid,user,cmd | grep -nF -- "--port $$port" || true
	  ps -eo pid,user,cmd | grep -nE -- "docker-proxy .* -host-port $$port([^0-9]|$$)" || true
	  if command -v docker >/dev/null 2>&1; then
	    echo "[make] diagnostics: docker containers publishing $$port"
	    docker ps --filter "publish=$$port" --format "  - {{.Names}} ({{.Image}}) {{.Ports}}" || true
	    if [[ -f "docker-compose.yml" ]]; then
	      echo "[make] diagnostics: docker compose ps (if applicable)"
	      docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || true
	    fi
	  fi
	}

	backend_listener_looks_like_realmoi() {
	  local port="$$1"
	  if ps -eo cmd | grep -F "uvicorn backend.app.main:app" | grep -F -- "--port $$port" >/dev/null 2>&1; then
	    return 0
	  fi
	  if command -v docker >/dev/null 2>&1; then
	    if docker ps --filter "publish=$$port" --format "{{.Image}} {{.Names}}" | grep -E "realmoi/realmoi-backend|realmoi-backend" >/dev/null 2>&1; then
	      return 0
	    fi
	  fi
	  return 1
	}

	check_port_available() {
	  local port="$$1"
	  local name="$$2"
	  if port_is_available "$$port"; then
	    return 0
	  fi
	  echo "[make] error: $$name port $$port is unavailable (already in use or no permission)"
	  print_port_diagnostics "$$port"
	  echo "[make] hint: stop the process/container using the port, then re-run 'make dev'"
	  echo "[make] hint: or override ports: 'make dev BACKEND_PORT=8001 FRONTEND_PORT=3001'"
	  exit 1
	}

	wait_for_port() {
	  local host="$$1"
	  local port="$$2"
	  local timeout_s="$$3"
	  local tries
	  tries=$$(python3 -X utf8 -c 'import sys; print(max(1, int(float(sys.argv[1]) * 10)))' "$$timeout_s")
	  for ((i=0; i<tries; i++)); do
	    if python3 -X utf8 -c 'import socket,sys; host=sys.argv[1]; port=int(sys.argv[2]); s=socket.socket(); s.settimeout(0.2); rc=s.connect_ex((host,port)); s.close(); sys.exit(0 if rc==0 else 1)' "$$host" "$$port" >/dev/null 2>&1; then
	      return 0
	    fi
	    sleep 0.1
	  done
	  return 1
	}

	START_BACKEND=1
	if ! port_is_available "$${BACKEND_PORT}"; then
	  if wait_for_port "127.0.0.1" "$${BACKEND_PORT}" "0.5"; then
	    if backend_listener_looks_like_realmoi "$${BACKEND_PORT}"; then
	      START_BACKEND=0
	      echo "[make] backend: detected existing listener on port $${BACKEND_PORT}; reusing"
	    else
	      echo "[make] error: backend port $${BACKEND_PORT} is in use, but it doesn't look like realmoi backend"
	      print_port_diagnostics "$${BACKEND_PORT}"
	      echo "[make] hint: stop the process/container using the port, then re-run 'make dev'"
	      echo "[make] hint: or override ports: 'make dev BACKEND_PORT=8001 FRONTEND_PORT=3001'"
	      exit 1
	    fi
	  else
	    echo "[make] error: backend port $${BACKEND_PORT} is unavailable (already in use or no permission)"
	    print_port_diagnostics "$${BACKEND_PORT}"
	    echo "[make] hint: stop the process/container using the port, then re-run 'make dev'"
	    echo "[make] hint: or override ports: 'make dev BACKEND_PORT=8001 FRONTEND_PORT=3001'"
	    exit 1
	  fi
	fi

	START_FRONTEND=1
	if ! port_is_available "$${FRONTEND_PORT}"; then
	  if wait_for_port "127.0.0.1" "$${FRONTEND_PORT}" "0.5"; then
	    START_FRONTEND=0
	    echo "[make] frontend: detected existing listener on port $${FRONTEND_PORT}; reusing"
	  else
	    echo "[make] error: frontend port $${FRONTEND_PORT} is unavailable (already in use or no permission)"
	    print_port_diagnostics "$${FRONTEND_PORT}"
	    echo "[make] hint: stop the process/container using the port, then re-run 'make dev'"
	    echo "[make] hint: or override ports: 'make dev BACKEND_PORT=8001 FRONTEND_PORT=3001'"
	    exit 1
	  fi
	fi

	echo "[make] backend: http://localhost:$${BACKEND_PORT} (api: /api)"
	echo "[make] runner executor: $${REALMOI_RUNNER_EXECUTOR}"
	echo "[make] runner image (docker mode only): $${REALMOI_RUNNER_IMAGE}"
	echo "[make] judge mode: $${REALMOI_JUDGE_MODE}"

	if [[ "$${START_BACKEND}" -eq 1 ]]; then
	  uvicorn backend.app.main:app --reload --host "$${BACKEND_HOST}" --port "$${BACKEND_PORT}" &
	  BACKEND_PID=$$!

	  if ! wait_for_port "127.0.0.1" "$${BACKEND_PORT}" "5.0"; then
	    if ! kill -0 "$${BACKEND_PID}" 2>/dev/null; then
	      echo "[make] error: backend process exited early"
	    else
	      echo "[make] error: backend did not start listening on port $${BACKEND_PORT} within timeout"
	    fi
	    exit 1
	  fi
	fi

	if [[ "$${REALMOI_JUDGE_MODE}" == "independent" ]]; then
	  if ps -eo cmd | grep -F "backend.app.judge_daemon" >/dev/null 2>&1; then
	    echo "[make] judge: already running"
	  else
	    echo "[make] judge: starting independent daemon"
	    export REALMOI_JUDGE_API_BASE_URL="$${REALMOI_JUDGE_API_BASE_URL:-http://127.0.0.1:$${BACKEND_PORT}}"
	    python3 -X utf8 -m backend.app.judge_daemon &
	    JUDGE_PID=$$!
	  fi
	fi

	echo "[make] frontend: http://localhost:$${FRONTEND_PORT}"
	if [[ "$${START_FRONTEND}" -eq 1 ]]; then
	  cd "frontend"
	  export NEXT_PUBLIC_API_BASE_URL="$${NEXT_PUBLIC_API_BASE_URL:-http://localhost:$${BACKEND_PORT}/api}"
	  export PORT="$${FRONTEND_PORT}"
	  npm run dev &
	  FRONTEND_PID=$$!
	fi
	WAIT_PIDS=()
	if [[ "$${BACKEND_PID}" -gt 0 ]]; then
	  WAIT_PIDS+=("$${BACKEND_PID}")
	fi
	if [[ "$${FRONTEND_PID}" -gt 0 ]]; then
	  WAIT_PIDS+=("$${FRONTEND_PID}")
	fi
	if [[ "$${#WAIT_PIDS[@]}" -gt 0 ]]; then
	  wait "$${WAIT_PIDS[@]}"
	elif [[ "$${JUDGE_PID}" -gt 0 ]]; then
	  wait "$${JUDGE_PID}"
	else
	  echo "[make] note: backend/frontend/judge already running; nothing to do"
	fi

.PHONY: judge
judge: backend-deps
	$(LOAD_ENV)
	export REALMOI_JUDGE_MODE="$${REALMOI_JUDGE_MODE:-independent}"
	source ".venv/bin/activate"
	python3 -X utf8 -m backend.app.judge_daemon

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
