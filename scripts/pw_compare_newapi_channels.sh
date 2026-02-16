#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

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

realmoi_url="http://localhost:${realmoi_port}/admin/upstream-models"
newapi_url="http://localhost:${newapi_port}/console/channel"
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

const me = { id: "u_admin", username: "root", role: "admin", is_disabled: false };
const channelsPayload = [
  { channel: "", display_name: "default", base_url: "https://api.example.com", api_key_masked: "sk-****", has_api_key: true, models_path: "/v1/models", is_default: true, is_enabled: true, source: "env" },
  { channel: "openai-cn", display_name: "OpenAI 中国", base_url: "https://openai.example.com", api_key_masked: "sk-****", has_api_key: true, models_path: "/v1/models", is_default: false, is_enabled: true, source: "config" },
];

const modelsPayload = {
  data: [
    { id: "gpt-4o" },
    { id: "gpt-4o-mini" },
    { id: "claude-3-5-sonnet" },
  ],
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

  if (requestUrl === `${apiBase}/admin/upstream/channels`) {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8", ...corsHeaders },
      body: JSON.stringify(channelsPayload),
    });
    return;
  }

  if (requestUrl.startsWith(`${apiBase}/admin/upstream/models`)) {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8", ...corsHeaders },
      body: JSON.stringify(modelsPayload),
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
  const main = document.querySelector("main.newapi-scope") || document.querySelector("main");
  if (!main) return;

  const tabEl =
    main.querySelector('[role="tab"]') ||
    main.querySelector('.semi-tabs-tab-button') ||
    main.querySelector('.semi-tabs-tab') ||
    null;
  if (tabEl) {
    tabEl.setAttribute('data-pw-target', 'channels-tab');
    tabEl.textContent = 'Tab';
  }

  const keywordInput = main.querySelector('input[placeholder*="渠道ID"]');
  const keywordWrap = keywordInput ? keywordInput.closest(".semi-input-wrapper") : null;
  if (keywordWrap && keywordInput) {
    keywordWrap.setAttribute("data-pw-target", "channels-search-keyword");
    keywordInput.value = "";
    keywordInput.setAttribute("placeholder", "Placeholder");
  }

  const modelInput = main.querySelector('input[placeholder*="模型关键字"]');
  const modelWrap = modelInput ? modelInput.closest(".semi-input-wrapper") : null;
  if (modelWrap && modelInput) {
    modelWrap.setAttribute("data-pw-target", "channels-search-model");
    modelInput.value = "";
    modelInput.setAttribute("placeholder", "Placeholder");
  }

  const groupSelect = main.querySelector("form .semi-select");
  if (groupSelect) {
    groupSelect.setAttribute("data-pw-target", "channels-group-select");
    const txt =
      groupSelect.querySelector(".semi-select-selection-text") ||
      groupSelect.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
  }

  const btnAdd = Array.from(main.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("添加渠道"),
  );
  if (btnAdd) {
    btnAdd.setAttribute("data-pw-target", "channels-btn-add");
    const content = btnAdd.querySelector(".semi-button-content") || btnAdd;
    content.textContent = "Primary";
  }

  const btnRefresh = Array.from(main.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("刷新"),
  );
  if (btnRefresh) {
    btnRefresh.setAttribute("data-pw-target", "channels-btn-refresh");
    const content = btnRefresh.querySelector(".semi-button-content") || btnRefresh;
    content.textContent = "Refresh";
  }

  const btnQuery = Array.from(main.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("查询"),
  );
  if (btnQuery) {
    btnQuery.setAttribute("data-pw-target", "channels-btn-query");
    const content = btnQuery.querySelector(".semi-button-content") || btnQuery;
    content.textContent = "Query";
  }

  const btnReset = Array.from(main.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("重置"),
  );
  if (btnReset) {
    btnReset.setAttribute("data-pw-target", "channels-btn-reset");
    const content = btnReset.querySelector(".semi-button-content") || btnReset;
    content.textContent = "Reset";
  }

	  const statusLabel = Array.from(main.querySelectorAll("span,div,p")).find((el) =>
	    normalize(el.textContent).includes(normalize("状态筛选")),
	  );
	  const statusSelect =
	    (statusLabel ? statusLabel.parentElement?.querySelector(".semi-select") : null) || null;
	  if (statusSelect) {
	    statusSelect.setAttribute("data-pw-target", "channels-actions-select");
	    const txt =
	      statusSelect.querySelector(".semi-select-selection-text") ||
	      statusSelect.querySelector(".semi-select-selection-placeholder");
	    if (txt) txt.textContent = "Option";
	  }
	
	  const idSortLabel = Array.from(main.querySelectorAll("span,div,p")).find((el) =>
	    normalize(el.textContent).includes(normalize("使用ID排序")),
	  );
	  const idSortSwitch =
	    (idSortLabel ? idSortLabel.parentElement?.querySelector(".semi-switch") : null) || null;
	  if (idSortSwitch) {
	    idSortSwitch.setAttribute("data-pw-target", "channels-actions-switch");
	  }

  const th = main.querySelector(".semi-table-thead th") || main.querySelector("thead th");
  if (th) {
    th.setAttribute("data-pw-target", "channels-th");
    th.textContent = "Header";
  }
});

await page.addStyleTag({
  content: `
    [data-pw-target="channels-tab"] { width: 140px !important; }
    [data-pw-target="channels-search-keyword"] { width: 256px !important; }
    [data-pw-target="channels-search-model"] { width: 192px !important; }
    [data-pw-target="channels-group-select"] { width: 128px !important; }
    [data-pw-target="channels-btn-add"] { width: 120px !important; justify-content: center !important; }
    [data-pw-target="channels-btn-refresh"] { width: 120px !important; justify-content: center !important; }
    [data-pw-target="channels-btn-query"] { width: 108px !important; justify-content: center !important; }
    [data-pw-target="channels-btn-reset"] { width: 108px !important; justify-content: center !important; }
	  `,
	});

await page.evaluate(async () => {
  if (!document.fonts || !document.fonts.ready) return;
  try { await document.fonts.ready; } catch {}
});
await page.waitForTimeout(200);

await page.evaluate(() => {
  const stripLoading = (sel) => {
    const btn = document.querySelector(sel);
    if (!btn) return;
    btn.classList.remove("semi-button-loading", "semi-button-with-icon");
    btn.removeAttribute("aria-busy");
    btn.querySelectorAll(".semi-button-icon, .semi-spin, .semi-button-spinner").forEach((n) => {
      try {
        n.remove();
      } catch {}
    });
  };
  stripLoading('[data-pw-target="channels-btn-query"]');
  stripLoading('[data-pw-target="channels-btn-refresh"]');
});

await page.evaluate(() => {
  const el = document.activeElement;
  if (el && typeof el.blur === "function") el.blur();

  let sink = document.getElementById("__pw_hover_sink");
  if (!sink) {
    sink = document.createElement("div");
    sink.id = "__pw_hover_sink";
    sink.style.position = "fixed";
    sink.style.left = "0";
    sink.style.top = "0";
    sink.style.width = "24px";
    sink.style.height = "24px";
    sink.style.zIndex = "2147483647";
    sink.style.background = "transparent";
    sink.style.pointerEvents = "auto";
    document.body.appendChild(sink);
  }
});
await page.mouse.move(12, 12);

// Under CPU load, headless paint can lag behind DOM mutations; give it a moment to settle.
await page.waitForTimeout(800);

const targets = [
  ["channels_tab", '[data-pw-target="channels-tab"]'],
  ["channels_btn_add", '[data-pw-target="channels-btn-add"]'],
  ["channels_btn_refresh", '[data-pw-target="channels-btn-refresh"]'],
  ["channels_search_keyword", '[data-pw-target="channels-search-keyword"]'],
  ["channels_search_model", '[data-pw-target="channels-search-model"]'],
  ["channels_group_select", '[data-pw-target="channels-group-select"]'],
  ["channels_btn_query", '[data-pw-target="channels-btn-query"]'],
  ["channels_btn_reset", '[data-pw-target="channels-btn-reset"]'],
  ["channels_actions_select", '[data-pw-target="channels-actions-select"]'],
  ["channels_actions_switch", '[data-pw-target="channels-actions-switch"]'],
  ["channels_th", '[data-pw-target="channels-th"]'],
];

const moveStageKeySet = new Set([]);
const cloneStageKeySet = new Set(["channels_th"]);

const ensureStage = async (page) => {
  await page.evaluate(() => {
    let stage = document.getElementById("__pw_stage");
    if (stage) return;
    stage = document.createElement("div");
    stage.id = "__pw_stage";
    stage.className = "newapi-scope";
    stage.style.position = "fixed";
    stage.style.left = "0";
    stage.style.top = "0";
    stage.style.zIndex = "2147483647";
    stage.style.padding = "0";
    stage.style.margin = "0";
    stage.style.background = "transparent";
    stage.style.display = "inline-block";
    document.body.appendChild(stage);
  });
};

const moveToStage = async (page, loc, stageKey) => {
  await ensureStage(page);
  await loc.evaluate((el, key) => {
    const stage = document.getElementById("__pw_stage");
    if (!stage) return;
    stage.innerHTML = "";

    const marker = document.createElement("span");
    marker.setAttribute("data-pw-marker", key);
    marker.style.display = "none";
    el.parentNode?.insertBefore(marker, el);

    el.setAttribute("data-pw-stage", key);
    stage.appendChild(el);
  }, stageKey);
};

const restoreFromStage = async (page, stageKey) => {
  await page.evaluate((key) => {
    const stage = document.getElementById("__pw_stage");
    const el = document.querySelector(`[data-pw-stage="${key}"]`);
    const marker = document.querySelector(`[data-pw-marker="${key}"]`);
    if (el && marker && marker.parentNode) {
      marker.parentNode.insertBefore(el, marker);
      marker.remove();
    }
    if (el) el.removeAttribute("data-pw-stage");
    if (stage) stage.innerHTML = "";
  }, stageKey);
};

const cloneTableCellToStage = async (page, loc, stageKey) => {
  await ensureStage(page);
  await loc.evaluate((el, key) => {
    const stage = document.getElementById("__pw_stage");
    if (!stage) return;
    stage.innerHTML = "";

    const wrapper = document.createElement("div");
    wrapper.className = "semi-table";
    wrapper.style.display = "inline-block";
    wrapper.style.background = "transparent";

    const table = document.createElement("table");
    table.style.borderCollapse = "separate";
    table.style.borderSpacing = "0";
    table.style.background = "transparent";

    const thead = document.createElement("thead");
    thead.className = "semi-table-thead";
    const tr = document.createElement("tr");
    tr.className = "semi-table-row";

    const clone = el.cloneNode(true);
    clone.setAttribute("data-pw-stage", key);
    tr.appendChild(clone);
    thead.appendChild(tr);
    table.appendChild(thead);
    wrapper.appendChild(table);
    stage.appendChild(wrapper);
  }, stageKey);
};

const clearStage = async (page) => {
  await page.evaluate(() => {
    const stage = document.getElementById("__pw_stage");
    if (stage) stage.innerHTML = "";
  });
};

const stableShot = async (page, loc, path) => {
  await loc.waitFor({ state: "visible", timeout: 15000 });
  await loc.scrollIntoViewIfNeeded();
  await page.waitForTimeout(120);
  await loc.screenshot({ path });
  await page.waitForTimeout(200);
  await loc.screenshot({ path });
};

for (const [name, sel] of targets) {
  const loc = page.locator(sel).first();
  const p = `${label}_${name}.png`;
  if (moveStageKeySet.has(name)) {
    await moveToStage(page, loc, name);
    const staged = page.locator(`[data-pw-stage="${name}"]`).first();
    await stableShot(page, staged, p);
    await restoreFromStage(page, name);
    continue;
  }
  if (cloneStageKeySet.has(name)) {
    await cloneTableCellToStage(page, loc, name);
    const staged = page.locator(`[data-pw-stage="${name}"]`).first();
    await stableShot(page, staged, p);
    await clearStage(page);
    continue;
  }
  await stableShot(page, loc, p);
}

const semiVars = await page.evaluate(() => {
  const host = document.body || document.documentElement;
  const cs = host ? getComputedStyle(host) : null;
  const getVar = (name) => (cs ? (cs.getPropertyValue(name) || "").trim() : "");
  return {
    fill0: getVar("--semi-color-fill-0"),
    fill1: getVar("--semi-color-fill-1"),
    fill2: getVar("--semi-color-fill-2"),
    bg0: getVar("--semi-color-bg-0"),
    bg1: getVar("--semi-color-bg-1"),
    border: getVar("--semi-color-border"),
    text0: getVar("--semi-color-text-0"),
    text1: getVar("--semi-color-text-1"),
    text2: getVar("--semi-color-text-2"),
    tertiary: getVar("--semi-color-tertiary"),
  };
});

const dump = await page.evaluate(() => {
  const pick = (key) => {
    const el = document.querySelector(`[data-pw-target="${key}"]`);
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    let html = "";
    try {
      html = (el.outerHTML || "").slice(0, 600);
    } catch {
      html = "";
    }

    const pickInner = () => {
      const node =
        el.querySelector(".semi-select-selection-text") ||
        el.querySelector(".semi-select-selection-placeholder") ||
        el.querySelector(".semi-button-content") ||
        null;
      if (!node) return null;
      const cs = getComputedStyle(node);
      return {
        tagName: node.tagName || null,
        className: (node.className || null),
        text: (node.textContent || "").slice(0, 80),
        style: {
          fontFamily: cs.fontFamily,
          fontSize: cs.fontSize,
          fontWeight: cs.fontWeight,
          lineHeight: cs.lineHeight,
          letterSpacing: cs.letterSpacing,
          color: cs.color,
          webkitFontSmoothing: cs.getPropertyValue("-webkit-font-smoothing"),
          mozOsxFontSmoothing: cs.getPropertyValue("-moz-osx-font-smoothing"),
          textRendering: cs.textRendering,
        },
      };
    };

    const pickSwitchKnob = () => {
      const knob = el.querySelector(".semi-switch-knob");
      if (!knob) return null;
      const cs = getComputedStyle(knob);
      const r = knob.getBoundingClientRect();
      return {
        rect: {
          x: r.x,
          y: r.y,
          width: r.width,
          height: r.height,
        },
        style: {
          backgroundColor: cs.backgroundColor,
          borderRadius: cs.borderRadius,
          transform: cs.transform,
        },
      };
    };

    return {
      tagName: el.tagName || null,
      className: (el.className || null),
      rect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      },
      style: (() => {
        const cs = getComputedStyle(el);
        return {
          display: cs.display,
          width: cs.width,
          height: cs.height,
          padding: cs.padding,
          backgroundColor: cs.backgroundColor,
          color: cs.color,
          fontFamily: cs.fontFamily,
          fontSize: cs.fontSize,
          fontWeight: cs.fontWeight,
          lineHeight: cs.lineHeight,
          letterSpacing: cs.letterSpacing,
          webkitFontSmoothing: cs.getPropertyValue("-webkit-font-smoothing"),
          mozOsxFontSmoothing: cs.getPropertyValue("-moz-osx-font-smoothing"),
          textRendering: cs.textRendering,
          zoom: cs.getPropertyValue("zoom"),
          borderTop: `${cs.borderTopWidth} ${cs.borderTopStyle} ${cs.borderTopColor}`,
          borderRight: `${cs.borderRightWidth} ${cs.borderRightStyle} ${cs.borderRightColor}`,
          borderBottom: `${cs.borderBottomWidth} ${cs.borderBottomStyle} ${cs.borderBottomColor}`,
          borderLeft: `${cs.borderLeftWidth} ${cs.borderLeftStyle} ${cs.borderLeftColor}`,
          borderRadius: cs.borderRadius,
          boxShadow: cs.boxShadow,
          transform: cs.transform,
          opacity: cs.opacity,
        };
      })(),
      inner: pickInner(),
      switchKnob: pickSwitchKnob(),
      html,
    };
  };

  return {
    env: (() => {
      const doc = document.documentElement;
      const body = document.body;
      const dcs = doc ? getComputedStyle(doc) : null;
      const bcs = body ? getComputedStyle(body) : null;
      return {
        dpr: window.devicePixelRatio,
        docFontSize: dcs ? dcs.fontSize : null,
        docZoom: dcs ? dcs.getPropertyValue("zoom") : null,
        bodyFontSize: bcs ? bcs.fontSize : null,
        bodyZoom: bcs ? bcs.getPropertyValue("zoom") : null,
      };
    })(),
    keyword: pick("channels-search-keyword"),
    queryBtn: pick("channels-btn-query"),
    resetBtn: pick("channels-btn-reset"),
    refreshBtn: pick("channels-btn-refresh"),
    actionsSelect: pick("channels-actions-select"),
    actionsSwitch: pick("channels-actions-switch"),
    th: pick("channels-th"),
  };
});

return { ok: true, semiVars, dump };
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
    localStorage.setItem("enable-tag-mode", "false");
    localStorage.setItem("enable-batch-delete", "false");
    localStorage.setItem("id-sort", "false");
    localStorage.setItem("channel-status-filter", "all");
  } catch {}
});

await page.route(/.*\/api\/.*/, async (route) => {
  const req = route.request();
  let pathname = "";
  try {
    pathname = new URL(req.url()).pathname;
  } catch {
    pathname = req.url();
  }

  const headers = { "content-type": "application/json; charset=utf-8" };

  if (pathname === "/api/status") {
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

  if (pathname.startsWith("/api/option")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        success: true,
        data: [
          { key: "global.pass_through_request_enabled", value: "false" },
        ],
      }),
    });
    return;
  }

  if (pathname.startsWith("/api/group")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({ success: true, data: ["default", "vip"] }),
    });
    return;
  }

  if (pathname.startsWith("/api/models")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        success: true,
        data: { openai: ["gpt-4o"] },
      }),
    });
    return;
  }

  if (pathname.startsWith("/api/channel")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({
        success: true,
        message: "",
        data: { items: [], total: 0, type_counts: {} },
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

  const tabEl =
    scope.querySelector('[role="tab"]') ||
    scope.querySelector('.semi-tabs-tab-button') ||
    scope.querySelector('.semi-tabs-tab') ||
    null;
  if (tabEl) {
    tabEl.setAttribute('data-pw-target', 'channels-tab');
    tabEl.textContent = 'Tab';
  }

  const keywordInput =
    scope.querySelector('input[name="searchKeyword"]') ||
    scope.querySelector('input[placeholder*="渠道ID"]');
  const keywordWrap = keywordInput ? keywordInput.closest(".semi-input-wrapper") : null;
  if (keywordWrap && keywordInput) {
    keywordWrap.setAttribute("data-pw-target", "channels-search-keyword");
    keywordInput.value = "";
    keywordInput.setAttribute("placeholder", "Placeholder");
  }

  const modelInput =
    scope.querySelector('input[name="searchModel"]') ||
    scope.querySelector('input[placeholder*="模型关键字"]');
  const modelWrap = modelInput ? modelInput.closest(".semi-input-wrapper") : null;
  if (modelWrap && modelInput) {
    modelWrap.setAttribute("data-pw-target", "channels-search-model");
    modelInput.value = "";
    modelInput.setAttribute("placeholder", "Placeholder");
  }

  const groupSelect = scope.querySelector("form .semi-select");
  if (groupSelect) {
    groupSelect.setAttribute("data-pw-target", "channels-group-select");
    const txt =
      groupSelect.querySelector(".semi-select-selection-text") ||
      groupSelect.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
  }

  const btnAdd = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("添加渠道"),
  );
  if (btnAdd) {
    btnAdd.setAttribute("data-pw-target", "channels-btn-add");
    const content = btnAdd.querySelector(".semi-button-content") || btnAdd;
    content.textContent = "Primary";
  }

  const btnRefresh = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("刷新"),
  );
  if (btnRefresh) {
    btnRefresh.setAttribute("data-pw-target", "channels-btn-refresh");
    const content = btnRefresh.querySelector(".semi-button-content") || btnRefresh;
    content.textContent = "Refresh";
  }

  const btnQuery = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("查询"),
  );
  if (btnQuery) {
    btnQuery.setAttribute("data-pw-target", "channels-btn-query");
    const content = btnQuery.querySelector(".semi-button-content") || btnQuery;
    content.textContent = "Query";
  }

  const btnReset = Array.from(scope.querySelectorAll("button")).find(
    (el) => normalize(el.textContent) === normalize("重置"),
  );
  if (btnReset) {
    btnReset.setAttribute("data-pw-target", "channels-btn-reset");
    const content = btnReset.querySelector(".semi-button-content") || btnReset;
    content.textContent = "Reset";
  }

  const statusLabel = Array.from(scope.querySelectorAll("span,div,p")).find((el) =>
    normalize(el.textContent).includes(normalize("状态筛选")),
  );
  const statusSelect =
    (statusLabel ? statusLabel.parentElement?.querySelector(".semi-select") : null) || null;
  if (statusSelect) {
    statusSelect.setAttribute("data-pw-target", "channels-actions-select");
    const txt =
      statusSelect.querySelector(".semi-select-selection-text") ||
      statusSelect.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
  }

  const idSortLabel = Array.from(scope.querySelectorAll("span,div,p")).find((el) =>
    normalize(el.textContent).includes(normalize("使用ID排序")),
  );
  const idSortSwitch =
    (idSortLabel ? idSortLabel.parentElement?.querySelector(".semi-switch") : null) || null;
  if (idSortSwitch) {
    idSortSwitch.setAttribute("data-pw-target", "channels-actions-switch");
  }

  const th =
    scope.querySelector(".semi-table-thead th") ||
    scope.querySelector("thead th");
  if (th) {
    th.setAttribute("data-pw-target", "channels-th");
    th.textContent = "Header";
  }
});

await page.addStyleTag({
  content: `
    [data-pw-target="channels-tab"] { width: 140px !important; }
    [data-pw-target="channels-search-keyword"] { width: 256px !important; }
    [data-pw-target="channels-search-model"] { width: 192px !important; }
    [data-pw-target="channels-group-select"] { width: 128px !important; }
    [data-pw-target="channels-btn-add"] { width: 120px !important; justify-content: center !important; }
    [data-pw-target="channels-btn-refresh"] { width: 120px !important; justify-content: center !important; }
    [data-pw-target="channels-btn-query"] { width: 108px !important; justify-content: center !important; }
    [data-pw-target="channels-btn-reset"] { width: 108px !important; justify-content: center !important; }
	  `,
	});

await page.evaluate(async () => {
  if (!document.fonts || !document.fonts.ready) return;
  try { await document.fonts.ready; } catch {}
});
await page.waitForTimeout(200);

await page.evaluate(() => {
  const stripLoading = (sel) => {
    const btn = document.querySelector(sel);
    if (!btn) return;
    btn.classList.remove("semi-button-loading", "semi-button-with-icon");
    btn.removeAttribute("aria-busy");
    btn.querySelectorAll(".semi-button-icon, .semi-spin, .semi-button-spinner").forEach((n) => {
      try {
        n.remove();
      } catch {}
    });
  };
  stripLoading('[data-pw-target="channels-btn-query"]');
  stripLoading('[data-pw-target="channels-btn-refresh"]');
});

await page.evaluate(() => {
  const el = document.activeElement;
  if (el && typeof el.blur === "function") el.blur();

  let sink = document.getElementById("__pw_hover_sink");
  if (!sink) {
    sink = document.createElement("div");
    sink.id = "__pw_hover_sink";
    sink.style.position = "fixed";
    sink.style.left = "0";
    sink.style.top = "0";
    sink.style.width = "24px";
    sink.style.height = "24px";
    sink.style.zIndex = "2147483647";
    sink.style.background = "transparent";
    sink.style.pointerEvents = "auto";
    document.body.appendChild(sink);
  }
});
await page.mouse.move(12, 12);

// Under CPU load, headless paint can lag behind DOM mutations; give it a moment to settle.
await page.waitForTimeout(800);

const targets = [
  ["channels_tab", '[data-pw-target="channels-tab"]'],
  ["channels_btn_add", '[data-pw-target="channels-btn-add"]'],
  ["channels_btn_refresh", '[data-pw-target="channels-btn-refresh"]'],
  ["channels_search_keyword", '[data-pw-target="channels-search-keyword"]'],
  ["channels_search_model", '[data-pw-target="channels-search-model"]'],
  ["channels_group_select", '[data-pw-target="channels-group-select"]'],
  ["channels_btn_query", '[data-pw-target="channels-btn-query"]'],
  ["channels_btn_reset", '[data-pw-target="channels-btn-reset"]'],
  ["channels_actions_select", '[data-pw-target="channels-actions-select"]'],
  ["channels_actions_switch", '[data-pw-target="channels-actions-switch"]'],
  ["channels_th", '[data-pw-target="channels-th"]'],
];

const moveStageKeySet = new Set([]);
const cloneStageKeySet = new Set(["channels_th"]);

const ensureStage = async (page) => {
  await page.evaluate(() => {
    let stage = document.getElementById("__pw_stage");
    if (stage) return;
    stage = document.createElement("div");
    stage.id = "__pw_stage";
    stage.className = "newapi-scope";
    stage.style.position = "fixed";
    stage.style.left = "0";
    stage.style.top = "0";
    stage.style.zIndex = "2147483647";
    stage.style.padding = "0";
    stage.style.margin = "0";
    stage.style.background = "transparent";
    stage.style.display = "inline-block";
    document.body.appendChild(stage);
  });
};

const moveToStage = async (page, loc, stageKey) => {
  await ensureStage(page);
  await loc.evaluate((el, key) => {
    const stage = document.getElementById("__pw_stage");
    if (!stage) return;
    stage.innerHTML = "";

    const marker = document.createElement("span");
    marker.setAttribute("data-pw-marker", key);
    marker.style.display = "none";
    el.parentNode?.insertBefore(marker, el);

    el.setAttribute("data-pw-stage", key);
    stage.appendChild(el);
  }, stageKey);
};

const restoreFromStage = async (page, stageKey) => {
  await page.evaluate((key) => {
    const stage = document.getElementById("__pw_stage");
    const el = document.querySelector(`[data-pw-stage="${key}"]`);
    const marker = document.querySelector(`[data-pw-marker="${key}"]`);
    if (el && marker && marker.parentNode) {
      marker.parentNode.insertBefore(el, marker);
      marker.remove();
    }
    if (el) el.removeAttribute("data-pw-stage");
    if (stage) stage.innerHTML = "";
  }, stageKey);
};

const cloneTableCellToStage = async (page, loc, stageKey) => {
  await ensureStage(page);
  await loc.evaluate((el, key) => {
    const stage = document.getElementById("__pw_stage");
    if (!stage) return;
    stage.innerHTML = "";

    const wrapper = document.createElement("div");
    wrapper.className = "semi-table";
    wrapper.style.display = "inline-block";
    wrapper.style.background = "transparent";

    const table = document.createElement("table");
    table.style.borderCollapse = "separate";
    table.style.borderSpacing = "0";
    table.style.background = "transparent";

    const thead = document.createElement("thead");
    thead.className = "semi-table-thead";
    const tr = document.createElement("tr");
    tr.className = "semi-table-row";

    const clone = el.cloneNode(true);
    clone.setAttribute("data-pw-stage", key);
    tr.appendChild(clone);
    thead.appendChild(tr);
    table.appendChild(thead);
    wrapper.appendChild(table);
    stage.appendChild(wrapper);
  }, stageKey);
};

const clearStage = async (page) => {
  await page.evaluate(() => {
    const stage = document.getElementById("__pw_stage");
    if (stage) stage.innerHTML = "";
  });
};

const stableShot = async (page, loc, path) => {
  await loc.waitFor({ state: "visible", timeout: 15000 });
  await loc.scrollIntoViewIfNeeded();
  await page.waitForTimeout(120);
  await loc.screenshot({ path });
  await page.waitForTimeout(200);
  await loc.screenshot({ path });
};

for (const [name, sel] of targets) {
  const loc = page.locator(sel).first();
  const p = `${label}_${name}.png`;
  if (moveStageKeySet.has(name)) {
    await moveToStage(page, loc, name);
    const staged = page.locator(`[data-pw-stage="${name}"]`).first();
    await stableShot(page, staged, p);
    await restoreFromStage(page, name);
    continue;
  }
  if (cloneStageKeySet.has(name)) {
    await cloneTableCellToStage(page, loc, name);
    const staged = page.locator(`[data-pw-stage="${name}"]`).first();
    await stableShot(page, staged, p);
    await clearStage(page);
    continue;
  }
  await stableShot(page, loc, p);
}

const semiVars = await page.evaluate(() => {
  const host = document.body || document.documentElement;
  const cs = host ? getComputedStyle(host) : null;
  const getVar = (name) => (cs ? (cs.getPropertyValue(name) || "").trim() : "");
  return {
    fill0: getVar("--semi-color-fill-0"),
    fill1: getVar("--semi-color-fill-1"),
    fill2: getVar("--semi-color-fill-2"),
    bg0: getVar("--semi-color-bg-0"),
    bg1: getVar("--semi-color-bg-1"),
    border: getVar("--semi-color-border"),
    text0: getVar("--semi-color-text-0"),
    text1: getVar("--semi-color-text-1"),
    text2: getVar("--semi-color-text-2"),
    tertiary: getVar("--semi-color-tertiary"),
  };
});

const dump = await page.evaluate(() => {
  const pick = (key) => {
    const el = document.querySelector(`[data-pw-target="${key}"]`);
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    let html = "";
    try {
      html = (el.outerHTML || "").slice(0, 600);
    } catch {
      html = "";
    }

    const pickInner = () => {
      const node =
        el.querySelector(".semi-select-selection-text") ||
        el.querySelector(".semi-select-selection-placeholder") ||
        el.querySelector(".semi-button-content") ||
        null;
      if (!node) return null;
      const cs = getComputedStyle(node);
      return {
        tagName: node.tagName || null,
        className: (node.className || null),
        text: (node.textContent || "").slice(0, 80),
        style: {
          fontFamily: cs.fontFamily,
          fontSize: cs.fontSize,
          fontWeight: cs.fontWeight,
          lineHeight: cs.lineHeight,
          letterSpacing: cs.letterSpacing,
          color: cs.color,
          webkitFontSmoothing: cs.getPropertyValue("-webkit-font-smoothing"),
          mozOsxFontSmoothing: cs.getPropertyValue("-moz-osx-font-smoothing"),
          textRendering: cs.textRendering,
        },
      };
    };

    const pickSwitchKnob = () => {
      const knob = el.querySelector(".semi-switch-knob");
      if (!knob) return null;
      const cs = getComputedStyle(knob);
      const r = knob.getBoundingClientRect();
      return {
        rect: {
          x: r.x,
          y: r.y,
          width: r.width,
          height: r.height,
        },
        style: {
          backgroundColor: cs.backgroundColor,
          borderRadius: cs.borderRadius,
          transform: cs.transform,
        },
      };
    };

    return {
      tagName: el.tagName || null,
      className: (el.className || null),
      rect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      },
      style: (() => {
        const cs = getComputedStyle(el);
        return {
          display: cs.display,
          width: cs.width,
          height: cs.height,
          padding: cs.padding,
          backgroundColor: cs.backgroundColor,
          color: cs.color,
          fontFamily: cs.fontFamily,
          fontSize: cs.fontSize,
          fontWeight: cs.fontWeight,
          lineHeight: cs.lineHeight,
          letterSpacing: cs.letterSpacing,
          webkitFontSmoothing: cs.getPropertyValue("-webkit-font-smoothing"),
          mozOsxFontSmoothing: cs.getPropertyValue("-moz-osx-font-smoothing"),
          textRendering: cs.textRendering,
          zoom: cs.getPropertyValue("zoom"),
          borderTop: `${cs.borderTopWidth} ${cs.borderTopStyle} ${cs.borderTopColor}`,
          borderRight: `${cs.borderRightWidth} ${cs.borderRightStyle} ${cs.borderRightColor}`,
          borderBottom: `${cs.borderBottomWidth} ${cs.borderBottomStyle} ${cs.borderBottomColor}`,
          borderLeft: `${cs.borderLeftWidth} ${cs.borderLeftStyle} ${cs.borderLeftColor}`,
          borderRadius: cs.borderRadius,
          boxShadow: cs.boxShadow,
          transform: cs.transform,
          opacity: cs.opacity,
        };
      })(),
      inner: pickInner(),
      switchKnob: pickSwitchKnob(),
      html,
    };
  };

  return {
    env: (() => {
      const doc = document.documentElement;
      const body = document.body;
      const dcs = doc ? getComputedStyle(doc) : null;
      const bcs = body ? getComputedStyle(body) : null;
      return {
        dpr: window.devicePixelRatio,
        docFontSize: dcs ? dcs.fontSize : null,
        docZoom: dcs ? dcs.getPropertyValue("zoom") : null,
        bodyFontSize: bcs ? bcs.fontSize : null,
        bodyZoom: bcs ? bcs.getPropertyValue("zoom") : null,
      };
    })(),
    keyword: pick("channels-search-keyword"),
    queryBtn: pick("channels-btn-query"),
    resetBtn: pick("channels-btn-reset"),
    refreshBtn: pick("channels-btn-refresh"),
    actionsSelect: pick("channels-actions-select"),
    actionsSwitch: pick("channels-actions-switch"),
    th: pick("channels-th"),
  };
});

return { ok: true, semiVars, dump };
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
  ("channels_tab", "realmoi_channels_tab.png", "newapi_channels_tab.png", "diff_channels_tab.png"),
  ("channels_btn_add", "realmoi_channels_btn_add.png", "newapi_channels_btn_add.png", "diff_channels_btn_add.png"),
  ("channels_btn_refresh", "realmoi_channels_btn_refresh.png", "newapi_channels_btn_refresh.png", "diff_channels_btn_refresh.png"),
  ("channels_search_keyword", "realmoi_channels_search_keyword.png", "newapi_channels_search_keyword.png", "diff_channels_search_keyword.png"),
  ("channels_search_model", "realmoi_channels_search_model.png", "newapi_channels_search_model.png", "diff_channels_search_model.png"),
  ("channels_group_select", "realmoi_channels_group_select.png", "newapi_channels_group_select.png", "diff_channels_group_select.png"),
  ("channels_btn_query", "realmoi_channels_btn_query.png", "newapi_channels_btn_query.png", "diff_channels_btn_query.png"),
  ("channels_btn_reset", "realmoi_channels_btn_reset.png", "newapi_channels_btn_reset.png", "diff_channels_btn_reset.png"),
  ("channels_actions_select", "realmoi_channels_actions_select.png", "newapi_channels_actions_select.png", "diff_channels_actions_select.png"),
  ("channels_actions_switch", "realmoi_channels_actions_switch.png", "newapi_channels_actions_switch.png", "diff_channels_actions_switch.png"),
  ("channels_th", "realmoi_channels_th.png", "newapi_channels_th.png", "diff_channels_th.png"),
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
  if (wa, ha) != (mw, mh):
    a_cmp = os.path.join(cwd, a.replace('.png', '_norm.png'))
    subprocess.check_call(
      [
        'convert',
        a_path,
        '-background',
        'none',
        '-gravity',
        'NorthWest',
        '-extent',
        f"{mw}x{mh}",
        a_cmp,
      ]
    )
  if (wb, hb) != (mw, mh):
    b_cmp = os.path.join(cwd, b.replace('.png', '_norm.png'))
    subprocess.check_call(
      [
        'convert',
        b_path,
        '-background',
        'none',
        '-gravity',
        'NorthWest',
        '-extent',
        f"{mw}x{mh}",
        b_cmp,
      ]
    )

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
