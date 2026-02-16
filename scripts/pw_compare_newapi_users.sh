#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

out_dir="${1:-"${repo_root}/output/playwright/$(date +%Y%m%d)_align-new-api_users"}"
realmoi_port="${REALMOI_PORT:-3110}"
newapi_port="${NEWAPI_PORT:-3120}"
newapi_web_dir="${NEWAPI_WEB_DIR:-"${repo_root}/../new-api/web"}"

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

realmoi_url="http://localhost:${realmoi_port}/admin/users"
newapi_url="http://localhost:${newapi_port}/console/user"
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

if ! command -v npx >/dev/null 2>&1; then
  echo "Error: npx is required but not found on PATH." >&2
  exit 1
fi

shoot_js_realmoi() {
  local label="$1"
  local url="$2"
  local api_base="${3:-"http://0.0.0.0:8000/api"}"
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

const me = { id: "u_admin", username: "root", role: "admin", is_disabled: false };
const usersPayload = {
  items: [
    { id: "u_1", username: "alice", role: "admin", is_disabled: false, created_at: "2025-01-01T00:00:00Z" },
    { id: "u_2", username: "bob", role: "user", is_disabled: true, created_at: "2025-01-02T00:00:00Z" },
    { id: "u_3", username: "charlie", role: "user", is_disabled: false, created_at: "2025-01-03T00:00:00Z" },
  ],
  total: 200,
};

try {
  await page.unroute(`${apiBase}/**`);
} catch {}

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

  if (requestUrl === `${apiBase}/admin/users` || requestUrl.startsWith(`${apiBase}/admin/users?`)) {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8", ...corsHeaders },
      body: JSON.stringify(usersPayload),
    });
    return;
  }

  await route.continue();
});

await page.addInitScript(() => {
  try { localStorage.setItem("realmoi_token", "test-token"); } catch {}
});

await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(800);

await page.addStyleTag({
  content: `
    *, *::before, *::after { animation: none !important; transition: none !important; }
  `,
});

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\\s+/g, "");
  const main = document.querySelector("main.newapi-scope") || document.querySelector("main");
  if (!main) return;

  const searchInput =
    main.querySelector('.semi-input-wrapper input[placeholder*="搜索"]') ||
    main.querySelector('.semi-input-wrapper input') ||
    main.querySelector('input[placeholder*="搜索"]') ||
    main.querySelector("input");
  const searchWrap = searchInput ? searchInput.closest(".semi-input-wrapper") : null;
  if (searchInput && searchWrap) {
    searchWrap.setAttribute("data-pw-target", "users-search");
    searchInput.value = "";
    searchInput.setAttribute("placeholder", "Placeholder");
  }

  const select = (searchWrap ? searchWrap.closest("form") : null)?.querySelector(".semi-select") || main.querySelector("form .semi-select") || main.querySelector(".semi-select");
  if (select) {
    select.setAttribute("data-pw-target", "users-select");
    const txt =
      select.querySelector(".semi-select-selection-text") ||
      select.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
  }

  const btnPrimary = Array.from(main.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("添加用户"),
  );
  if (btnPrimary) {
    btnPrimary.setAttribute("data-pw-target", "users-btn-primary");
    const btnPrimaryContent = btnPrimary.querySelector(".semi-button-content") || btnPrimary;
    btnPrimaryContent.textContent = "Action";
  }

  const btnSecondary = Array.from(main.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("查询"),
  );
  if (btnSecondary) {
    btnSecondary.setAttribute("data-pw-target", "users-btn-secondary");
    const btnSecondaryContent = btnSecondary.querySelector(".semi-button-content") || btnSecondary;
    btnSecondaryContent.textContent = "Secondary";
  }

  const tag = main.querySelector("tbody .semi-tag") || main.querySelector(".semi-tag");
  if (tag) {
    tag.setAttribute("data-pw-target", "users-tag");
    const tagContent = tag.querySelector(".semi-tag-content") || tag;
    tagContent.textContent = "Tag";
  }

  const th = main.querySelector(".semi-table-thead th") || main.querySelector("thead th");
  if (th) {
    th.setAttribute("data-pw-target", "users-th");
    th.textContent = "Header";
  }
});

await page.addStyleTag({
  content: `
    [data-pw-target="users-search"] { width: 360px !important; height: 32px !important; }
    [data-pw-target="users-search"] input { height: 32px !important; line-height: 32px !important; }
    [data-pw-target="users-select"] { width: 220px !important; height: 32px !important; }
    [data-pw-target="users-btn-primary"] { width: 160px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="users-btn-secondary"] { width: 161px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="users-tag"] { width: 84px !important; height: 24px !important; display: inline-flex !important; align-items: center !important; justify-content: center !important; }
    [data-pw-target="users-th"] { width: 220px !important; height: 44px !important; vertical-align: middle !important; }
  `,
});

await page.evaluate(async () => {
  if (!document.fonts || !document.fonts.ready) return;
  try { await document.fonts.ready; } catch {}
});
await page.waitForTimeout(200);

const targets = [
  ["users_search", '[data-pw-target="users-search"]'],
  ["users_select", '[data-pw-target="users-select"]'],
  ["users_btn_primary", '[data-pw-target="users-btn-primary"]'],
  ["users_btn_secondary", '[data-pw-target="users-btn-secondary"]'],
  ["users_tag", '[data-pw-target="users-tag"]'],
  ["users_th", '[data-pw-target="users-th"]'],
];

for (const [name, sel] of targets) {
  const loc = page.locator(sel).first();
  await loc.waitFor({ state: "visible", timeout: 15000 });
  await loc.scrollIntoViewIfNeeded();
  if (name === "users_select") {
    const box = await loc.boundingBox();
    if (box) {
      await page.screenshot({
        path: `${label}_${name}.png`,
        clip: {
          x: Math.round(box.x),
          y: Math.round(box.y),
          width: 190,
          height: 32,
        },
      });
      continue;
    }
  }

  if (name === "users_tag") {
    const box = await loc.boundingBox();
    if (box) {
      await page.screenshot({
        path: `${label}_${name}.png`,
        clip: {
          x: Math.round(box.x) + 3,
          y: Math.round(box.y),
          width: 78,
          height: 24,
        },
      });
      continue;
    }
  }

  await loc.screenshot({ path: `${label}_${name}.png` });
}

const styles = await page.evaluate((targets) => {
  const pick = (el) => {
    const cs = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      tagName: el.tagName,
      className: el.className || null,
      rect: { x: r.x, y: r.y, width: r.width, height: r.height },
      display: cs.display,
      fontFamily: cs.fontFamily,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      color: cs.color,
      backgroundColor: cs.backgroundColor,
      backgroundClip: cs.backgroundClip,
      backgroundOrigin: cs.backgroundOrigin,
      borderTop: cs.borderTop,
      borderRight: cs.borderRight,
      borderBottom: cs.borderBottom,
      borderLeft: cs.borderLeft,
      borderRadius: cs.borderRadius,
      boxShadow: cs.boxShadow,
      opacity: cs.opacity,
      transform: cs.transform,
      filter: cs.filter,
      backdropFilter: cs.backdropFilter,
      textRendering: cs.textRendering,
      webkitFontSmoothing: cs.getPropertyValue('-webkit-font-smoothing'),
      mozOsxFontSmoothing: cs.getPropertyValue('-moz-osx-font-smoothing'),
      padding: cs.padding,
      boxSizing: cs.boxSizing,
    };
  };

  const pickPlaceholder = (inputEl) => {
    const cs = window.getComputedStyle(inputEl, '::placeholder');
    return {
      fontFamily: cs.fontFamily,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      color: cs.color,
      opacity: cs.opacity,
    };
  };

  const out = {};
  for (const [name, sel] of targets) {
    const el = document.querySelector(sel);
    if (!el) {
      out[name] = null;
      continue;
    }

    const entry = { root: pick(el) };

    if (name === 'users_search') {
      const input = el.querySelector('input');
      const prefixSvg = el.querySelector('svg');
      entry.input = input ? pick(input) : null;
      entry.placeholder = input ? pickPlaceholder(input) : null;
      entry.svg = prefixSvg ? pick(prefixSvg) : null;
    }

    if (name === 'users_select') {
      const txt =
        el.querySelector('.semi-select-selection-text') ||
        el.querySelector('.semi-select-selection-placeholder');
      const svg = el.querySelector('svg');
      entry.text = txt ? pick(txt) : null;
      entry.svg = svg ? pick(svg) : null;
    }

    if (name === 'users_btn_primary' || name === 'users_btn_secondary') {
      const content = el.querySelector('.semi-button-content');
      entry.content = content ? pick(content) : null;
    }

    if (name === 'users_tag') {
      const content = el.querySelector('.semi-tag-content');
      entry.content = content ? pick(content) : null;
    }

    out[name] = entry;
  }

  return out;
}, targets);

return { ok: true, styles };
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
    localStorage.setItem("user", JSON.stringify({ id: 1, username: "root", role: 10, token: "test-token" }));
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

  const isPath = (s) => pathname === s || pathname.startsWith(s) || requestUrl.includes(s);

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

  if (isPath("/api/group")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({ success: true, data: ["default", "vip"] }),
    });
    return;
  }

  if (isPath("/api/user")) {
    if (isPath("/api/user/self")) {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({
          success: true,
          message: "",
          data: {
            id: 1,
            username: "root",
            display_name: "",
            password: "",
            github_id: "",
            oidc_id: "",
            discord_id: "",
            wechat_id: "",
            telegram_id: "",
            email: "",
            quota: 10000,
            group: "default",
            remark: "",
            status: 1,
            role: 10,
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

    if (isPath("/api/user/manage")) {
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({ success: true, message: "", data: { status: 1, role: 10 } }),
      });
      return;
    }

    const detailMatch = requestUrl.match(/\/api\/user\/(\d+)(?:\b|\/|$)/);
    if (detailMatch) {
      const id = parseInt(detailMatch[1], 10);
      await route.fulfill({
        status: 200,
        headers,
        body: JSON.stringify({
          success: true,
          message: "",
          data: {
            id,
            username: `user_${id}`,
            display_name: "",
            password: "",
            github_id: "",
            oidc_id: "",
            discord_id: "",
            wechat_id: "",
            telegram_id: "",
            email: "",
            quota: 10000,
            group: "default",
            remark: "",
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

    const payload = {
      success: true,
      message: "",
      data: {
        page: 1,
        total: 3,
        items: [
          {
            id: 1,
            username: "alice",
            remark: "",
            status: 1,
            group: "default",
            role: 10,
            used_quota: "1234",
            quota: "10000",
            request_count: 42,
            inviter_id: 0,
            aff_count: 0,
            aff_history_quota: "0",
            DeletedAt: null,
          },
          {
            id: 2,
            username: "bob",
            remark: "",
            status: 2,
            group: "default",
            role: 1,
            used_quota: "567",
            quota: "10000",
            request_count: 7,
            inviter_id: 0,
            aff_count: 0,
            aff_history_quota: "0",
            DeletedAt: null,
          },
          {
            id: 3,
            username: "charlie",
            remark: "",
            status: 1,
            group: "vip",
            role: 1,
            used_quota: "0",
            quota: "10000",
            request_count: 0,
            inviter_id: 0,
            aff_count: 0,
            aff_history_quota: "0",
            DeletedAt: null,
          },
        ],
      },
    };
    await route.fulfill({ status: 200, headers, body: JSON.stringify(payload) });
    return;
  }

  await route.fulfill({
    status: 200,
    headers,
    body: JSON.stringify({ success: true, message: "", data: null }),
  });
});

await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(900);

// Wait for the table to render (API + React state)
await page.waitForSelector(".semi-table", { timeout: 15000 }).catch(() => {});
await page.waitForSelector("tbody .semi-tag", { timeout: 15000 }).catch(() => {});

await page.addStyleTag({
  content: `
    *, *::before, *::after { animation: none !important; transition: none !important; }
    .Toastify, .Toastify__toast-container { display: none !important; }
  `,
});

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\\s+/g, "");

  const searchInput = document.querySelector(".semi-input-wrapper input");
  const searchWrap = searchInput ? searchInput.closest(".semi-input-wrapper") : null;
  if (searchInput && searchWrap) {
    searchWrap.setAttribute("data-pw-target", "users-search");
    searchInput.value = "";
    searchInput.setAttribute("placeholder", "Placeholder");
  }

  const select = (searchWrap ? searchWrap.closest("form") : null)?.querySelector(".semi-select") || document.querySelector("form .semi-select") || document.querySelector(".semi-select");
  if (select) {
    select.setAttribute("data-pw-target", "users-select");
    const txt =
      select.querySelector(".semi-select-selection-text") ||
      select.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
  }

  const btnPrimary = Array.from(document.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("添加用户"),
  );
  if (btnPrimary) {
    btnPrimary.setAttribute("data-pw-target", "users-btn-primary");
    const btnPrimaryContent = btnPrimary.querySelector(".semi-button-content") || btnPrimary;
    btnPrimaryContent.textContent = "Action";
  }

  const btnSecondary = Array.from(document.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("查询"),
  );
  if (btnSecondary) {
    btnSecondary.setAttribute("data-pw-target", "users-btn-secondary");
    const btnSecondaryContent = btnSecondary.querySelector(".semi-button-content") || btnSecondary;
    btnSecondaryContent.textContent = "Secondary";
  }

  const pickVisible = (els) => {
    for (const el of els) {
      const cs = window.getComputedStyle(el);
      if (!cs || cs.display === "none" || cs.visibility === "hidden") continue;
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) continue;
      return el;
    }
    return null;
  };

  const tag = pickVisible(Array.from(document.querySelectorAll("tbody .semi-tag, .semi-tag")));
  if (tag) {
    tag.setAttribute("data-pw-target", "users-tag");
    const tagContent = tag.querySelector(".semi-tag-content") || tag;
    tagContent.textContent = "Tag";
  }

  const th = document.querySelector(".semi-table-thead th");
  if (th) {
    th.setAttribute("data-pw-target", "users-th");
    th.textContent = "Header";
  }
});

await page.addStyleTag({
  content: `
    [data-pw-target="users-search"] { width: 360px !important; height: 32px !important; }
    [data-pw-target="users-search"] input { height: 32px !important; line-height: 32px !important; }
    [data-pw-target="users-select"] { width: 220px !important; height: 32px !important; }
    [data-pw-target="users-btn-primary"] { width: 160px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="users-btn-secondary"] { width: 161px !important; height: 32px !important; justify-content: center !important; }
    [data-pw-target="users-tag"] { width: 84px !important; height: 24px !important; display: inline-flex !important; align-items: center !important; justify-content: center !important; }
    [data-pw-target="users-th"] { width: 220px !important; height: 44px !important; vertical-align: middle !important; }
  `,
});

await page.evaluate(async () => {
  if (!document.fonts || !document.fonts.ready) return;
  try { await document.fonts.ready; } catch {}
});
await page.waitForTimeout(200);

const targets = [
  ["users_search", '[data-pw-target="users-search"]'],
  ["users_select", '[data-pw-target="users-select"]'],
  ["users_btn_primary", '[data-pw-target="users-btn-primary"]'],
  ["users_btn_secondary", '[data-pw-target="users-btn-secondary"]'],
  ["users_tag", '[data-pw-target="users-tag"]'],
  ["users_th", '[data-pw-target="users-th"]'],
];

for (const [name, sel] of targets) {
  const loc = page.locator(sel).first();
  await loc.waitFor({ state: "visible", timeout: 15000 });
  await loc.scrollIntoViewIfNeeded();
  if (name === "users_select") {
    const box = await loc.boundingBox();
    if (box) {
      await page.screenshot({
        path: `${label}_${name}.png`,
        clip: {
          x: Math.round(box.x),
          y: Math.round(box.y),
          width: 190,
          height: 32,
        },
      });
      continue;
    }
  }

  if (name === "users_tag") {
    const box = await loc.boundingBox();
    if (box) {
      await page.screenshot({
        path: `${label}_${name}.png`,
        clip: {
          x: Math.round(box.x) + 3,
          y: Math.round(box.y),
          width: 78,
          height: 24,
        },
      });
      continue;
    }
  }

  await loc.screenshot({ path: `${label}_${name}.png` });
}

const styles = await page.evaluate((targets) => {
  const pick = (el) => {
    const cs = window.getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return {
      tagName: el.tagName,
      className: el.className || null,
      rect: { x: r.x, y: r.y, width: r.width, height: r.height },
      display: cs.display,
      fontFamily: cs.fontFamily,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      color: cs.color,
      backgroundColor: cs.backgroundColor,
      backgroundClip: cs.backgroundClip,
      backgroundOrigin: cs.backgroundOrigin,
      borderTop: cs.borderTop,
      borderRight: cs.borderRight,
      borderBottom: cs.borderBottom,
      borderLeft: cs.borderLeft,
      borderRadius: cs.borderRadius,
      boxShadow: cs.boxShadow,
      opacity: cs.opacity,
      transform: cs.transform,
      filter: cs.filter,
      backdropFilter: cs.backdropFilter,
      textRendering: cs.textRendering,
      webkitFontSmoothing: cs.getPropertyValue('-webkit-font-smoothing'),
      mozOsxFontSmoothing: cs.getPropertyValue('-moz-osx-font-smoothing'),
      padding: cs.padding,
      boxSizing: cs.boxSizing,
    };
  };

  const pickPlaceholder = (inputEl) => {
    const cs = window.getComputedStyle(inputEl, '::placeholder');
    return {
      fontFamily: cs.fontFamily,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      color: cs.color,
      opacity: cs.opacity,
    };
  };

  const out = {};
  for (const [name, sel] of targets) {
    const el = document.querySelector(sel);
    if (!el) {
      out[name] = null;
      continue;
    }

    const entry = { root: pick(el) };

    if (name === 'users_search') {
      const input = el.querySelector('input');
      const prefixSvg = el.querySelector('svg');
      entry.input = input ? pick(input) : null;
      entry.placeholder = input ? pickPlaceholder(input) : null;
      entry.svg = prefixSvg ? pick(prefixSvg) : null;
    }

    if (name === 'users_select') {
      const txt =
        el.querySelector('.semi-select-selection-text') ||
        el.querySelector('.semi-select-selection-placeholder');
      const svg = el.querySelector('svg');
      entry.text = txt ? pick(txt) : null;
      entry.svg = svg ? pick(svg) : null;
    }

    if (name === 'users_btn_primary' || name === 'users_btn_secondary') {
      const content = el.querySelector('.semi-button-content');
      entry.content = content ? pick(content) : null;
    }

    if (name === 'users_tag') {
      const content = el.querySelector('.semi-tag-content');
      entry.content = content ? pick(content) : null;
    }

    out[name] = entry;
  }

  return out;
}, targets);

return { ok: true, styles };
}
JS
)"
  js="${js//__LABEL__/${label}}"
  js="${js//__URL__/${url}}"
  printf "%s" "${js}"
}

extract_result_json() {
  local log_file="$1"
  local out_file="$2"
  python3 - "${log_file}" "${out_file}" <<'PY'
import json
import sys

log_file = sys.argv[1]
out_file = sys.argv[2]

lines = open(log_file, "r", encoding="utf-8", errors="ignore").read().splitlines()
for i, line in enumerate(lines):
  if line.strip() == "### Result":
    buf = []
    for j in range(i + 1, len(lines)):
      if lines[j].startswith("### "):
        break
      buf.append(lines[j])
    payload = "\n".join(buf).strip()
    data = json.loads(payload) if payload else None
    with open(out_file, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
    sys.exit(0)

raise SystemExit("No ### Result block found in log: " + log_file)
PY
}

pushd "${out_dir}" >/dev/null
"${PWCLI}" --session "align-realmoi-${realmoi_port}" open "about:blank"
"${PWCLI}" --session "align-realmoi-${realmoi_port}" resize 1280 720
"${PWCLI}" --session "align-realmoi-${realmoi_port}" run-code "$(shoot_js_realmoi "realmoi" "${realmoi_url}")" | tee "pw_realmoi.log"
extract_result_json "pw_realmoi.log" "realmoi_users_styles.json"

"${PWCLI}" --session "align-newapi-${newapi_port}" open "about:blank"
"${PWCLI}" --session "align-newapi-${newapi_port}" resize 1280 720
"${PWCLI}" --session "align-newapi-${newapi_port}" run-code "$(shoot_js_newapi "newapi" "${newapi_url}")" | tee "pw_newapi.log"
extract_result_json "pw_newapi.log" "newapi_users_styles.json"
popd >/dev/null

echo "[4/4] imagemagick diff..."
OUT_DIR="${out_dir}" python3 - <<'PY'
import json, os, subprocess

out_dir = os.environ["OUT_DIR"]
pairs = [
  ("users_search", "realmoi_users_search.png", "newapi_users_search.png", "diff_users_search.png"),
  ("users_select", "realmoi_users_select.png", "newapi_users_select.png", "diff_users_select.png"),
  ("users_btn_primary", "realmoi_users_btn_primary.png", "newapi_users_btn_primary.png", "diff_users_btn_primary.png"),
  ("users_btn_secondary", "realmoi_users_btn_secondary.png", "newapi_users_btn_secondary.png", "diff_users_btn_secondary.png"),
  ("users_tag", "realmoi_users_tag.png", "newapi_users_tag.png", "diff_users_tag.png"),
  ("users_th", "realmoi_users_th.png", "newapi_users_th.png", "diff_users_th.png"),
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

  ca_path = a_path
  cb_path = b_path
  cropped = False
  if (wa, ha) != (wb, hb):
    cropped = True
    min_w = min(wa, wb)
    min_h = min(ha, hb)
    ca_path = os.path.join(cwd, f"__crop_a_{label}.png")
    cb_path = os.path.join(cwd, f"__crop_b_{label}.png")
    subprocess.check_call(["convert", a_path, "-crop", f"{min_w}x{min_h}+0+0", "+repage", ca_path])
    subprocess.check_call(["convert", b_path, "-crop", f"{min_w}x{min_h}+0+0", "+repage", cb_path])
    wa, ha = identify_size(ca_path)
    wb, hb = identify_size(cb_path)
  total = wa * ha
  proc = subprocess.run(
    ["compare", "-metric", "AE", ca_path, cb_path, out_path],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    text=True,
  )
  diff_pixels = int(proc.stderr.strip() or "0")
  metrics.append(
    {
      "label": label,
      "size": [wa, ha],
      "diff_pixels": diff_pixels,
      "total_pixels": total,
      "diff_ratio": (diff_pixels / total) if total else 0.0,
      "a": a,
      "b": b,
      "out": out,
      "cropped": cropped,
      "a_size": [wa, ha] if not cropped else [identify_size(a_path)[0], identify_size(a_path)[1]],
      "b_size": [wb, hb] if not cropped else [identify_size(b_path)[0], identify_size(b_path)[1]],
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
