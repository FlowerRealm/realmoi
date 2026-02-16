#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

out_dir="${1:-"${repo_root}/output/playwright/ui-audit/$(date +%Y%m%d_%H%M%S)"}"
backend_port="${REALMOI_BACKEND_PORT:-8000}"
frontend_port="${REALMOI_FRONTEND_PORT:-3000}"
backend_host="${REALMOI_BACKEND_HOST:-0.0.0.0}"

mkdir -p "${out_dir}"
out_dir="$(cd "${out_dir}" && pwd)"

db_path="${REALMOI_DB_PATH:-"${out_dir}/realmoi.db"}"
jobs_root="${REALMOI_JOBS_ROOT:-"${out_dir}/jobs"}"
codex_auth_json_path="${REALMOI_CODEX_AUTH_JSON_PATH:-"${out_dir}/secrets/codex/auth.json"}"

mkdir -p "${jobs_root}"

seed_sample_job() {
  local src_jobs_dir="${repo_root}/jobs"
  if [[ ! -d "${src_jobs_dir}" ]]; then
    return 0
  fi
  if [[ -n "$(find "${jobs_root}" -mindepth 2 -maxdepth 2 -type f -name "state.json" -print -quit 2>/dev/null || true)" ]]; then
    return 0
  fi

  local sample_state
  sample_state="$(find "${src_jobs_dir}" -mindepth 2 -maxdepth 2 -type f -name "state.json" 2>/dev/null | head -n 1 || true)"
  if [[ -z "${sample_state}" ]]; then
    return 0
  fi

  local sample_dir
  sample_dir="$(dirname -- "${sample_state}")"
  local sample_id
  sample_id="$(basename -- "${sample_dir}")"

  echo "Seeding jobs root with sample job: ${sample_id}"
  cp -a "${sample_dir}" "${jobs_root}/${sample_id}"
}

if [[ -z "${REALMOI_JOBS_ROOT:-}" && "${jobs_root}" == "${out_dir}/jobs" ]]; then
  seed_sample_job || true
fi

kill_port_listeners() {
  local port="$1"
  local name="$2"
  local pids
  pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi

  echo "Found existing listener(s) on ${name} port ${port}: ${pids}"
  kill ${pids} >/dev/null 2>&1 || true

  for _ in $(seq 1 80); do
    if ! lsof -tiTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done

  echo "Error: ${name} port still in use after kill: ${port}" >&2
  return 1
}

wait_http_any() {
  local url="$1"
  local name="$2"
  local tries="${3:-80}"
  local sleep_s="${4:-0.25}"
  for _ in $(seq 1 "${tries}"); do
    local code
    code="$(curl --noproxy "*" -sS -o /dev/null -w "%{http_code}" --connect-timeout 1 --max-time 2 "${url}" || true)"
    if [[ -n "${code}" && "${code}" != "000" ]]; then
      return 0
    fi
    sleep "${sleep_s}"
  done
  echo "Error: ${name} not ready: ${url}" >&2
  return 1
}

cleanup() {
  if [[ -n "${frontend_pid:-}" ]]; then
    kill "${frontend_pid}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${backend_pid:-}" ]]; then
    kill "${backend_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[0/6] deps..."
if [[ ! -d "${repo_root}/.venv" ]]; then
  make -C "${repo_root}" backend-deps >/dev/null
fi

echo "[1/6] npm install (frontend)..."
npm -C "${repo_root}/frontend" install >/dev/null

echo "[2/6] start dev servers..."
kill_port_listeners "${backend_port}" "backend" || exit 1
kill_port_listeners "${frontend_port}" "frontend" || exit 1

export REALMOI_JWT_SECRET="${REALMOI_JWT_SECRET:-dev-secret-change-me}"
export REALMOI_ALLOW_SIGNUP="${REALMOI_ALLOW_SIGNUP:-1}"
export REALMOI_ADMIN_USERNAME="${REALMOI_ADMIN_USERNAME:-admin}"
export REALMOI_ADMIN_PASSWORD="${REALMOI_ADMIN_PASSWORD:-admin-password-123}"
export REALMOI_DB_PATH="${db_path}"
export REALMOI_JOBS_ROOT="${jobs_root}"
export REALMOI_CODEX_AUTH_JSON_PATH="${codex_auth_json_path}"

source "${repo_root}/.venv/bin/activate"
uvicorn backend.app.main:app --reload --host "${backend_host}" --port "${backend_port}" >"${out_dir}/dev_backend.log" 2>&1 &
backend_pid="$!"

export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://127.0.0.1:${backend_port}/api}"
export PORT="${frontend_port}"
npm -C "${repo_root}/frontend" run dev -- --port "${frontend_port}" --hostname 0.0.0.0 >"${out_dir}/dev_frontend.log" 2>&1 &
frontend_pid="$!"

echo "[3/6] wait servers..."
sleep 0.25
if ! kill -0 "${backend_pid}" >/dev/null 2>&1; then
  echo "Error: backend exited early. tail dev_backend.log:" >&2
  tail -n 120 "${out_dir}/dev_backend.log" >&2 || true
  exit 1
fi
if ! kill -0 "${frontend_pid}" >/dev/null 2>&1; then
  echo "Error: frontend exited early. tail dev_frontend.log:" >&2
  tail -n 200 "${out_dir}/dev_frontend.log" >&2 || true
  exit 1
fi

wait_http_any "http://127.0.0.1:${backend_port}/api" "backend"
wait_http_any "http://127.0.0.1:${frontend_port}/login" "frontend"

echo "[4/6] playwright install (chromium)..."
npm -C "${repo_root}/frontend" run pw:install >/dev/null

echo "[5/6] ui audit (screenshots + report)..."
export REALMOI_PW_OUT_DIR="${out_dir}"
export REALMOI_PW_BASE_URL="http://127.0.0.1:${frontend_port}"
export REALMOI_PW_API_BASE_URL="http://127.0.0.1:${backend_port}/api"
export REALMOI_PW_EXPECT_ROLE="${REALMOI_PW_EXPECT_ROLE:-admin}"
export REALMOI_PW_USERNAME="${REALMOI_PW_USERNAME:-${REALMOI_ADMIN_USERNAME}}"
export REALMOI_PW_PASSWORD="${REALMOI_PW_PASSWORD:-${REALMOI_ADMIN_PASSWORD}}"

npm -C "${repo_root}/frontend" run pw:ui-audit >"${out_dir}/playwright.log" 2>&1 || {
  echo "Error: playwright run failed. tail playwright.log:" >&2
  tail -n 200 "${out_dir}/playwright.log" >&2 || true
  exit 1
}

echo "[6/6] done: ${out_dir}"
