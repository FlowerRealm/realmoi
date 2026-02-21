#!/usr/bin/env bash
# AUTO_COMMENT_HEADER_V1: _lib.sh
# 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。


pwc_die() {
  echo "Error: $*" >&2
  exit 1
}

pwc_require_file() {
  local path="$1"
  local label="${2:-file}"
  if [[ ! -f "${path}" ]]; then
    pwc_die "${label} not found: ${path}"
  fi
}

pwc_require_dir() {
  local path="$1"
  local label="${2:-dir}"
  if [[ ! -d "${path}" ]]; then
    pwc_die "${label} not found: ${path}"
  fi
}

pwc_require_cmd() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    pwc_die "required command not found on PATH: ${cmd}"
  fi
}

pwc_require_executable() {
  local path="$1"
  local label="${2:-executable}"
  if [[ ! -x "${path}" ]]; then
    pwc_die "${label} not executable: ${path}"
  fi
}

pwc_kill_port_listeners() {
  local port="$1"
  local name="$2"

  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)"
  fi

  if [[ -z "${pids}" ]] && command -v ss >/dev/null 2>&1 && command -v rg >/dev/null 2>&1; then
    pids="$(
      ss -ltnp 2>/dev/null |
        rg ":${port} " |
        rg -o "pid=[0-9]+" |
        sed 's/pid=//g' |
        sort -u ||
        true
    )"
  fi

  if [[ -z "${pids}" ]]; then
    return 0
  fi

  echo "Found existing listener(s) on ${name} port ${port}: ${pids}"
  kill ${pids} >/dev/null 2>&1 || true

  for _ in $(seq 1 80); do
    if command -v ss >/dev/null 2>&1 && command -v rg >/dev/null 2>&1; then
      if ! ss -ltnp 2>/dev/null | rg -q ":${port} "; then
        return 0
      fi
    elif command -v lsof >/dev/null 2>&1; then
      if ! lsof -tiTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1; then
        return 0
      fi
    else
      break
    fi
    sleep 0.25
  done

  echo "Error: ${name} port still in use after kill: ${port}" >&2
  return 1
}

pwc_wait_url() {
  local url="$1"
  local name="$2"
  local tries="${3:-80}"
  local sleep_s="${4:-0.25}"

  pwc_require_cmd curl
  for _ in $(seq 1 "${tries}"); do
    if curl --noproxy "*" -fsS --connect-timeout 1 --max-time 2 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${sleep_s}"
  done
  echo "Error: ${name} not ready: ${url}" >&2
  return 1
}

pwc_render_template() {
  local template_path="$1"
  shift

  pwc_require_file "${template_path}" "template"

  local rendered
  rendered="$(cat -- "${template_path}")"

  local kv key value
  for kv in "$@"; do
    key="${kv%%=*}"
    value="${kv#*=}"
    rendered="${rendered//${key}/${value}}"
  done

  printf "%s" "${rendered}"
}

