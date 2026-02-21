#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- \"$(dirname -- \"${BASH_SOURCE[0]}\")/..\" && pwd)"

out_dir="${1:-"${repo_root}/output/playwright/$(date +%Y%m%d)_align-new-api_channels"}"
realmoi_port="${REALMOI_PORT:-3110}"
newapi_port="${NEWAPI_PORT:-3120}"
newapi_web_dir="${NEWAPI_WEB_DIR:-"${repo_root}/../new-api/web"}"
realmoi_api_base="${REALMOI_API_BASE:-"http://0.0.0.0:8000/api"}"

mkdir -p "${out_dir}"

if [[ ! -f "${repo_root}/frontend/package.json" ]]; then
  echo "Error: frontend/package.json not found under repo root: ${repo_root}" >&2
  exit 1
fi

if [[ ! -f "${newapi_web_dir}/package.json" ]]; then
  echo "Error: NEWAPI_WEB_DIR invalid (package.json not found): ${newapi_web_dir}" >&2
  echo 'Tip: export NEWAPI_WEB_DIR="/abs/path/to/new-api/web"' >&2
  exit 1
fi

lib_path="${repo_root}/scripts/pw_compare_newapi/_lib.sh"
if [[ ! -f "${lib_path}" ]]; then
  echo "Error: helper library not found: ${lib_path}" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "${lib_path}"

cleanup() {
  if [[ -n "${realmoi_pid:-}" ]]; then
    kill "${realmoi_pid}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${newapi_pid:-}" ]]; then
    kill "${newapi_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo '[1/4] start dev servers...'
pwc_kill_port_listeners "${realmoi_port}" realmoi || exit 1
pwc_kill_port_listeners "${newapi_port}" 'new-api' || exit 1

WATCHPACK_POLLING=true npm -C "${repo_root}/frontend" run dev -- --port "${realmoi_port}" --hostname 0.0.0.0 >"${out_dir}/dev_realmoi.log" 2>&1 &
realmoi_pid="$!"

npm -C "${newapi_web_dir}" run dev -- --port "${newapi_port}" --host 0.0.0.0 >"${out_dir}/dev_newapi.log" 2>&1 &
newapi_pid="$!"

realmoi_url="http://localhost:${realmoi_port}/admin/upstream-models"
newapi_url="http://localhost:${newapi_port}/console/channel"
realmoi_boot_url="http://localhost:${realmoi_port}/login"
newapi_boot_url="http://localhost:${newapi_port}/login"

echo '[2/4] wait servers...'
sleep 0.25
if ! kill -0 "${realmoi_pid}" >/dev/null 2>&1; then
  echo 'Error: realmoi dev server exited early. tail dev_realmoi.log:' >&2
  tail -n 120 "${out_dir}/dev_realmoi.log" >&2 || true
  exit 1
fi
if ! kill -0 "${newapi_pid}" >/dev/null 2>&1; then
  echo 'Error: new-api dev server exited early. tail dev_newapi.log:' >&2
  tail -n 160 "${out_dir}/dev_newapi.log" >&2 || true
  exit 1
fi
pwc_wait_url "${realmoi_boot_url}" realmoi
pwc_wait_url "${newapi_boot_url}" 'new-api'

echo '[3/4] playwright screenshots...'
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export PWCLI="${PWCLI:-${CODEX_HOME}/skills/playwright/scripts/playwright_cli.sh}"

realmoi_template="${repo_root}/scripts/pw_compare_newapi/templates/channels_realmoi.pw.js.tmpl"
newapi_template="${repo_root}/scripts/pw_compare_newapi/templates/channels_newapi.pw.js.tmpl"

pwc_require_executable "${PWCLI}" PWCLI
pwc_require_file "${realmoi_template}" 'realmoi template'
pwc_require_file "${newapi_template}" 'newapi template'

pushd "${out_dir}" >/dev/null
session_suffix="$(basename -- "${out_dir}")"
realmoi_session="align-realmoi-${realmoi_port}-${session_suffix}"
newapi_session="align-newapi-${newapi_port}-${session_suffix}"

"${PWCLI}" --session "${realmoi_session}" open about:blank
"${PWCLI}" --session "${realmoi_session}" resize 1280 720
"${PWCLI}" --session "${realmoi_session}" run-code "$(
  pwc_render_template     "${realmoi_template}"     "__LABEL__=realmoi"     "__URL__=${realmoi_url}"     "__API_BASE__=${realmoi_api_base}"
)" | tee pw_realmoi.log

"${PWCLI}" --session "${newapi_session}" open about:blank
"${PWCLI}" --session "${newapi_session}" resize 1280 720
"${PWCLI}" --session "${newapi_session}" run-code "$(
  pwc_render_template     "${newapi_template}"     "__LABEL__=newapi"     "__URL__=${newapi_url}"
)" | tee pw_newapi.log
popd >/dev/null

echo '[4/4] imagemagick diff...'
pwc_require_cmd python3
pwc_require_file "${repo_root}/scripts/pw_compare_newapi/diff_images.py" 'diff script'
pwc_require_file "${repo_root}/scripts/pw_compare_newapi/pairs/channels.json" 'diff pairs'
python3 -X utf8 "${repo_root}/scripts/pw_compare_newapi/diff_images.py"   --out-dir "${out_dir}"   --pairs "${repo_root}/scripts/pw_compare_newapi/pairs/channels.json"
