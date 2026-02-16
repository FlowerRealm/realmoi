#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

out_dir="${1:-"${repo_root}/output/playwright/$(date +%Y%m%d)_align-new-api_billing"}"
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
  echo "Tip: export NEWAPI_WEB_DIR=\"/abs/path/to/new-api/web\"" >&2
  exit 1
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

wait_url() {
  local url="$1"
  local name="$2"
  local tries="${3:-80}"
  local sleep_s="${4:-0.25}"
  for _ in $(seq 1 "${tries}"); do
    if curl --noproxy "*" -fsS --connect-timeout 1 --max-time 2 "${url}" >/dev/null 2>&1; then
      return 0
    fi
    sleep "${sleep_s}"
  done
  echo "Error: ${name} not ready: ${url}" >&2
  return 1
}

cleanup() {
  if [[ -n "${realmoi_pid:-}" ]]; then
    kill "${realmoi_pid}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${newapi_pid:-}" ]]; then
    kill "${newapi_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "[1/4] start dev servers..."
kill_port_listeners "${realmoi_port}" "realmoi" || exit 1
kill_port_listeners "${newapi_port}" "new-api" || exit 1

WATCHPACK_POLLING=true npm -C "${repo_root}/frontend" run dev -- --port "${realmoi_port}" --hostname 0.0.0.0 >"${out_dir}/dev_realmoi.log" 2>&1 &
realmoi_pid="$!"

npm -C "${newapi_web_dir}" run dev -- --port "${newapi_port}" --host 0.0.0.0 >"${out_dir}/dev_newapi.log" 2>&1 &
newapi_pid="$!"

realmoi_url="http://localhost:${realmoi_port}/billing"
newapi_url="http://localhost:${newapi_port}/console/log"
realmoi_boot_url="http://localhost:${realmoi_port}/login"
newapi_boot_url="http://localhost:${newapi_port}/login"

echo "[2/4] wait servers..."
sleep 0.25
if ! kill -0 "${realmoi_pid}" >/dev/null 2>&1; then
  echo "Error: realmoi dev server exited early. tail dev_realmoi.log:" >&2
  tail -n 80 "${out_dir}/dev_realmoi.log" >&2 || true
  exit 1
fi
if ! kill -0 "${newapi_pid}" >/dev/null 2>&1; then
  echo "Error: new-api dev server exited early. tail dev_newapi.log:" >&2
  tail -n 120 "${out_dir}/dev_newapi.log" >&2 || true
  exit 1
fi
wait_url "${realmoi_boot_url}" "realmoi"
wait_url "${newapi_boot_url}" "new-api"

echo "[3/4] playwright screenshots..."
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export PWCLI="${CODEX_HOME}/skills/playwright/scripts/playwright_cli.sh"

shoot_js_realmoi() {
  local label="$1"
  local url="$2"
  local api_base="$3"
  local js
  js="$(cat <<'JS'
async (page) => {
const label = "__LABEL__";
const url = "__URL__";
const apiBase = "__API_BASE__".replace(/\/$/, "");

const corsHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
  "access-control-allow-headers": "*",
  "access-control-max-age": "600",
};

const me = { id: "u_user", username: "user", role: "user", is_disabled: false };

const eventsPayload = {
  query: { start: "2026-02-01", end: "2026-02-02", limit: 50, before_id: null },
  events: [
    {
      id: "rec_1",
      created_at: "2026-02-13 00:00:00",
      job_id: "job_1",
      stage: "solve",
      model: "gpt-4o-mini",
      input_tokens: 120,
      cached_input_tokens: 0,
      output_tokens: 80,
      cached_output_tokens: 0,
      total_tokens: 200,
      cached_tokens: 0,
      cost: { currency: "USD", cost_microusd: 1000, amount: "0.0010" },
    },
  ],
  next_before_id: null,
};

await page.route(`${apiBase}/**`, async (route) => {
  const req = route.request();
  const requestUrl = req.url();
  if (req.method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: corsHeaders, body: "" });
    return;
  }

  if (requestUrl === `${apiBase}/auth/me`) {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8", ...corsHeaders },
      body: JSON.stringify(me),
    });
    return;
  }

  if (requestUrl.startsWith(`${apiBase}/billing/events`)) {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8", ...corsHeaders },
      body: JSON.stringify(eventsPayload),
    });
    return;
  }

  await route.continue();
});

await page.addInitScript(() => {
  try { localStorage.setItem("realmoi_token", "test-token"); } catch {}
});

await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(900);

await page.addStyleTag({
  content: `
    *, *::before, *::after { animation: none !important; transition: none !important; }
    .semi-toast, .semi-toast-wrapper, .semi-notification, .semi-notification-list { display: none !important; }
  `,
});

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector(".table-scroll-card") || document.body;

  const rangeInput = scope.querySelector(".semi-datepicker-range-input") || scope.querySelector(".semi-datepicker-range");
  if (rangeInput) {
    rangeInput.setAttribute("data-pw-target", "billing-date-range");
    const inputs = Array.from(rangeInput.querySelectorAll("input"));
    for (const i of inputs) {
      try { i.value = ""; } catch {}
      i.setAttribute("placeholder", "Placeholder");
    }
  }

  const tokenInput =
    scope.querySelector('input[placeholder*="令牌名称"]') ||
    scope.querySelector('input[placeholder*="token"]');
  const tokenWrap = tokenInput ? tokenInput.closest(".semi-input-wrapper") : null;
  if (tokenWrap && tokenInput) {
    tokenWrap.setAttribute("data-pw-target", "billing-token");
    tokenInput.value = "";
    tokenInput.setAttribute("placeholder", "Placeholder");
  }

  const select = scope.querySelector("form .semi-select");
  if (select) {
    select.setAttribute("data-pw-target", "billing-select");
    const txt =
      select.querySelector(".semi-select-selection-text") ||
      select.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
  }

  const btnQuery = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("查询"),
  );
  if (btnQuery) {
    btnQuery.setAttribute("data-pw-target", "billing-btn-query");
    const content = btnQuery.querySelector(".semi-button-content") || btnQuery;
    content.textContent = "Query";
  }

  const btnReset = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("重置"),
  );
  if (btnReset) {
    btnReset.setAttribute("data-pw-target", "billing-btn-reset");
    const content = btnReset.querySelector(".semi-button-content") || btnReset;
    content.textContent = "Reset";
  }

  const btnCols = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("列设置"),
  );
  if (btnCols) {
    btnCols.setAttribute("data-pw-target", "billing-btn-cols");
    const content = btnCols.querySelector(".semi-button-content") || btnCols;
    content.textContent = "Cols";
  }

  const th = scope.querySelector(".semi-table-thead th") || scope.querySelector("thead th");
  if (th) {
    th.setAttribute("data-pw-target", "billing-th");
    th.textContent = "Header";
  }
});

await page.addStyleTag({
  content: `
    [data-pw-target="billing-date-range"] { width: 360px !important; height: 32px !important; }
    [data-pw-target="billing-date-range"] input { height: 32px !important; line-height: 32px !important; }
    [data-pw-target="billing-token"] { width: 240px !important; height: 32px !important; }
    [data-pw-target="billing-token"] input { height: 32px !important; line-height: 32px !important; }
    [data-pw-target="billing-select"] { width: 160px !important; height: 32px !important; }
    [data-pw-target="billing-btn-query"] { width: 120px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="billing-btn-reset"] { width: 120px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="billing-btn-cols"] { width: 120px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="billing-th"] { width: 220px !important; height: 44px !important; vertical-align: middle !important; }
  `,
});

await page.evaluate(async () => {
  if (!document.fonts || !document.fonts.ready) return;
  try { await document.fonts.ready; } catch {}
});
await page.waitForTimeout(200);

const targets = [
  ["billing_date_range", '[data-pw-target="billing-date-range"]'],
  ["billing_token", '[data-pw-target="billing-token"]'],
  ["billing_select", '[data-pw-target="billing-select"]'],
  ["billing_btn_query", '[data-pw-target="billing-btn-query"]'],
  ["billing_btn_reset", '[data-pw-target="billing-btn-reset"]'],
  ["billing_btn_cols", '[data-pw-target="billing-btn-cols"]'],
  ["billing_th", '[data-pw-target="billing-th"]'],
];

for (const [name, sel] of targets) {
  const loc = page.locator(sel).first();
  await loc.waitFor({ state: "visible", timeout: 15000 });
  await loc.scrollIntoViewIfNeeded();
  if (name === "billing_select" || name.startsWith("billing_btn_")) {
    const box = await loc.boundingBox();
    if (box) {
      const inset = 1;
      await page.screenshot({
        path: `${label}_${name}.png`,
        clip: {
          x: Math.round(box.x) + inset,
          y: Math.round(box.y) + inset,
          width: Math.max(1, Math.round(box.width) - inset * 2),
          height: Math.max(1, Math.round(box.height) - inset * 2),
        },
      });
      continue;
    }
  }
  await loc.screenshot({ path: `${label}_${name}.png` });
}

return { ok: true };
}
JS
)"

  js="${js//__LABEL__/${label}}"
  js="${js//__URL__/${url}}"
  js="${js//__API_BASE__/${api_base}}"
  printf "%s" "${js}"
}

shoot_js_newapi() {
  local label="$1"
  local url="$2"
  local js
  js="$(cat <<'JS'
async (page) => {
const label = "__LABEL__";
const url = "__URL__";

await page.addInitScript(() => {
  try {
    localStorage.setItem("user", JSON.stringify({ id: 1, username: "user", role: 1, token: "test-token" }));
    localStorage.setItem("i18nextLng", "zh");
  } catch {}
});

try {
  await page.unroute(/.*\/api\/.*/);
} catch {}

await page.route(/.*\/api\/.*/, async (route) => {
  const req = route.request();
  const requestUrl = req.url();
  let pathname = requestUrl;
  try {
    pathname = new URL(requestUrl).pathname;
  } catch {}

  const headers = { "content-type": "application/json; charset=utf-8" };

  const now = Math.floor(Date.now() / 1000);

  const isPath = (s) =>
    pathname === s || pathname.startsWith(s) || requestUrl.includes(s);

  if (isPath("/api/status")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        success: true,
        data: {
          system_name: "Realm OI",
          logo: "/favicon.ico",
          footer_html: "",
          quota_per_unit: 500000,
          display_in_currency: false,
          quota_display_type: "USD",
          enable_drawing: false,
          enable_task: false,
          enable_data_export: false,
          chats: [],
          data_export_default_time: "7",
          default_collapse_sidebar: false,
          mj_notify_enabled: false,
          docs_link: "",
          HeaderNavModules: null,
          turnstile_check: false,
          user_agreement_enabled: false,
          privacy_policy_enabled: false,
        },
      }),
    });
    return;
  }

  if (isPath("/api/user/self")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        success: true,
        message: "",
        data: {
          id: 1,
          username: "user",
          display_name: "",
          email: "",
          quota: 10000,
          group: "default",
          status: 1,
          role: 1,
          used_quota: "0",
          request_count: 0,
          inviter_id: 0,
          aff_count: 0,
          aff_history_quota: "0",
          DeletedAt: null,
        },
      }),
    });
    return;
  }

  if (isPath("/api/log/self/stat")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({ success: true, message: "", data: { quota: 0, rpm: 0, tpm: 0 } }),
    });
    return;
  }

  if (isPath("/api/log/self")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        success: true,
        message: "",
        data: {
          items: [
            {
              id: 1,
              created_at: now - 60,
              token_name: "t",
              model_name: "gpt-4o-mini",
              group: "default",
              type: 2,
              prompt_tokens: 1,
              completion_tokens: 2,
              quota: 10,
              request_id: "req_1",
              other: "{}",
            },
          ],
          page: 1,
          page_size: 10,
          total: 1,
        },
      }),
    });
    return;
  }

  await route.fulfill({
    status: 200,
    headers,
    body: JSON.stringify({ success: true, message: "", data: null }),
  });
});

await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1100);

await page.addStyleTag({
  content: `
    *, *::before, *::after { animation: none !important; transition: none !important; }
    .Toastify, .Toastify__toast-container { display: none !important; }
  `,
});

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector(".table-scroll-card") || document.body;

  const rangeInput = scope.querySelector(".semi-datepicker-range-input") || scope.querySelector(".semi-datepicker-range");
  if (rangeInput) {
    rangeInput.setAttribute("data-pw-target", "billing-date-range");
    const inputs = Array.from(rangeInput.querySelectorAll("input"));
    for (const i of inputs) {
      try { i.value = ""; } catch {}
      i.setAttribute("placeholder", "Placeholder");
    }
  }

  const tokenInput =
    scope.querySelector('input[placeholder*="令牌名称"]') ||
    scope.querySelector('input[placeholder*="token"]');
  const tokenWrap = tokenInput ? tokenInput.closest(".semi-input-wrapper") : null;
  if (tokenWrap && tokenInput) {
    tokenWrap.setAttribute("data-pw-target", "billing-token");
    tokenInput.value = "";
    tokenInput.setAttribute("placeholder", "Placeholder");
  }

  const select = scope.querySelector("form .semi-select");
  if (select) {
    select.setAttribute("data-pw-target", "billing-select");
    const txt =
      select.querySelector(".semi-select-selection-text") ||
      select.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
  }

  const btnQuery = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("查询"),
  );
  if (btnQuery) {
    btnQuery.setAttribute("data-pw-target", "billing-btn-query");
    const content = btnQuery.querySelector(".semi-button-content") || btnQuery;
    content.textContent = "Query";
  }

  const btnReset = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("重置"),
  );
  if (btnReset) {
    btnReset.setAttribute("data-pw-target", "billing-btn-reset");
    const content = btnReset.querySelector(".semi-button-content") || btnReset;
    content.textContent = "Reset";
  }

  const btnCols = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("列设置"),
  );
  if (btnCols) {
    btnCols.setAttribute("data-pw-target", "billing-btn-cols");
    const content = btnCols.querySelector(".semi-button-content") || btnCols;
    content.textContent = "Cols";
  }

  const th = scope.querySelector(".semi-table-thead th") || scope.querySelector("thead th");
  if (th) {
    th.setAttribute("data-pw-target", "billing-th");
    th.textContent = "Header";
  }
});

await page.addStyleTag({
  content: `
    [data-pw-target="billing-date-range"] { width: 360px !important; height: 32px !important; }
    [data-pw-target="billing-date-range"] input { height: 32px !important; line-height: 32px !important; }
    [data-pw-target="billing-token"] { width: 240px !important; height: 32px !important; }
    [data-pw-target="billing-token"] input { height: 32px !important; line-height: 32px !important; }
    [data-pw-target="billing-select"] { width: 160px !important; height: 32px !important; }
    [data-pw-target="billing-btn-query"] { width: 120px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="billing-btn-reset"] { width: 120px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="billing-btn-cols"] { width: 120px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="billing-th"] { width: 220px !important; height: 44px !important; vertical-align: middle !important; }
  `,
});

await page.evaluate(async () => {
  if (!document.fonts || !document.fonts.ready) return;
  try { await document.fonts.ready; } catch {}
});
await page.waitForTimeout(200);

const targets = [
  ["billing_date_range", '[data-pw-target="billing-date-range"]'],
  ["billing_token", '[data-pw-target="billing-token"]'],
  ["billing_select", '[data-pw-target="billing-select"]'],
  ["billing_btn_query", '[data-pw-target="billing-btn-query"]'],
  ["billing_btn_reset", '[data-pw-target="billing-btn-reset"]'],
  ["billing_btn_cols", '[data-pw-target="billing-btn-cols"]'],
  ["billing_th", '[data-pw-target="billing-th"]'],
];

for (const [name, sel] of targets) {
  const loc = page.locator(sel).first();
  await loc.waitFor({ state: "visible", timeout: 15000 });
  await loc.scrollIntoViewIfNeeded();
  if (name === "billing_select" || name.startsWith("billing_btn_")) {
    const box = await loc.boundingBox();
    if (box) {
      const inset = 1;
      await page.screenshot({
        path: `${label}_${name}.png`,
        clip: {
          x: Math.round(box.x) + inset,
          y: Math.round(box.y) + inset,
          width: Math.max(1, Math.round(box.width) - inset * 2),
          height: Math.max(1, Math.round(box.height) - inset * 2),
        },
      });
      continue;
    }
  }
  await loc.screenshot({ path: `${label}_${name}.png` });
}

return { ok: true };
}
JS
)"

  js="${js//__LABEL__/${label}}"
  js="${js//__URL__/${url}}"
  printf "%s" "${js}"
}

pushd "${out_dir}" >/dev/null
"${PWCLI}" --session "align-realmoi-${realmoi_port}" open "about:blank"
"${PWCLI}" --session "align-realmoi-${realmoi_port}" resize 1280 720
"${PWCLI}" --session "align-realmoi-${realmoi_port}" run-code "$(shoot_js_realmoi "realmoi" "${realmoi_url}" "${realmoi_api_base}")" | tee "pw_realmoi.log"

"${PWCLI}" --session "align-newapi-${newapi_port}" open "about:blank"
"${PWCLI}" --session "align-newapi-${newapi_port}" resize 1280 720
"${PWCLI}" --session "align-newapi-${newapi_port}" run-code "$(shoot_js_newapi "newapi" "${newapi_url}")" | tee "pw_newapi.log"
popd >/dev/null

echo "[4/4] imagemagick diff..."
OUT_DIR="${out_dir}" python3 - <<'PY'
import json
import os
import subprocess

out_dir = os.environ["OUT_DIR"]
pairs = [
  ("billing_date_range", "realmoi_billing_date_range.png", "newapi_billing_date_range.png", "diff_billing_date_range.png"),
  ("billing_token", "realmoi_billing_token.png", "newapi_billing_token.png", "diff_billing_token.png"),
  ("billing_select", "realmoi_billing_select.png", "newapi_billing_select.png", "diff_billing_select.png"),
  ("billing_btn_query", "realmoi_billing_btn_query.png", "newapi_billing_btn_query.png", "diff_billing_btn_query.png"),
  ("billing_btn_reset", "realmoi_billing_btn_reset.png", "newapi_billing_btn_reset.png", "diff_billing_btn_reset.png"),
  ("billing_btn_cols", "realmoi_billing_btn_cols.png", "newapi_billing_btn_cols.png", "diff_billing_btn_cols.png"),
  ("billing_th", "realmoi_billing_th.png", "newapi_billing_th.png", "diff_billing_th.png"),
]

def identify_size(path: str):
  out = subprocess.check_output(["identify", "-format", "%w %h", path], text=True).strip()
  w, h = out.split()
  return int(w), int(h)

metrics = []
cwd = out_dir
for label, a, b, out in pairs:
  a_path = os.path.join(cwd, a)
  b_path = os.path.join(cwd, b)
  out_path = os.path.join(cwd, out)
  wa, ha = identify_size(a_path)
  wb, hb = identify_size(b_path)
  mw, mh = max(wa, wb), max(ha, hb)

  a_cmp = a_path
  b_cmp = b_path
  cropped = False
  if (wa, ha) != (mw, mh):
    a_cmp = os.path.join(cwd, a.replace(".png", "_norm.png"))
    subprocess.check_call(
      ["convert", a_path, "-background", "none", "-gravity", "NorthWest", "-extent", f"{mw}x{mh}", a_cmp]
    )
    cropped = True
  if (wb, hb) != (mw, mh):
    b_cmp = os.path.join(cwd, b.replace(".png", "_norm.png"))
    subprocess.check_call(
      ["convert", b_path, "-background", "none", "-gravity", "NorthWest", "-extent", f"{mw}x{mh}", b_cmp]
    )
    cropped = True

  total = mw * mh
  proc = subprocess.run(
    ["compare", "-metric", "AE", a_cmp, b_cmp, out_path],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    text=True,
  )
  diff_pixels = int(proc.stderr.strip() or "0")
  metrics.append(
    {
      "label": label,
      "size": [mw, mh],
      "diff_pixels": diff_pixels,
      "total_pixels": total,
      "diff_ratio": (diff_pixels / total) if total else 0.0,
      "a": a,
      "b": b,
      "out": out,
      "cropped": cropped,
      "a_size": [wa, ha],
      "b_size": [wb, hb],
    }
  )

with open(os.path.join(cwd, "metrics.json"), "w", encoding="utf-8") as f:
  json.dump(metrics, f, ensure_ascii=False, indent=2)

print("metrics.json written:", os.path.join(cwd, "metrics.json"))
for m in metrics:
  print(f"- {m['label']}: diff_ratio={m['diff_ratio']:.6f} diff_pixels={m['diff_pixels']}")

# Strict 1:1 gate (per user requirement)
ratio_max = 0.01
pixels_max = 20
failed = [
  m
  for m in metrics
  if (m["diff_ratio"] >= ratio_max) or (m["diff_pixels"] >= pixels_max)
]
if failed:
  print("")
  print("FAIL: new-api 1:1 diff gate not met.")
  print(f"Gate: diff_ratio < {ratio_max} AND diff_pixels < {pixels_max} for every entry.")
  for m in failed:
    print(
      f"- {m['label']}: diff_ratio={m['diff_ratio']:.6f} diff_pixels={m['diff_pixels']}"
    )
  raise SystemExit(2)

print("")
print(
  f"PASS: all {len(metrics)}/{len(metrics)} entries satisfy diff_ratio < {ratio_max} and diff_pixels < {pixels_max}."
)
PY
