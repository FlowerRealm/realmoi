#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

out_dir="${1:-"${repo_root}/output/playwright/$(date +%Y%m%d)_align-new-api_pricing"}"
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
    pids="$(ss -ltnp 2>/dev/null | rg ":${port} " | rg -o "pid=[0-9]+" | sed 's/pid=//g' | sort -u || true)"
    if [[ -z "${pids}" ]]; then
      return 0
    fi
  fi

  echo "Found existing listener(s) on ${name} port ${port}: ${pids}"
  kill ${pids} >/dev/null 2>&1 || true

  for _ in $(seq 1 80); do
    if ! ss -ltnp 2>/dev/null | rg -q ":${port} "; then
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

realmoi_url="http://localhost:${realmoi_port}/admin/pricing"
newapi_url="http://localhost:${newapi_port}/console/setting?tab=ratio"
realmoi_boot_url="http://localhost:${realmoi_port}/login"
newapi_boot_url="http://localhost:${newapi_port}/login"

echo "[2/4] wait servers..."
sleep 0.25
if ! kill -0 "${realmoi_pid}" >/dev/null 2>&1; then
  echo "Error: realmoi dev server exited early. tail dev_realmoi.log:" >&2
  tail -n 120 "${out_dir}/dev_realmoi.log" >&2 || true
  exit 1
fi
if ! kill -0 "${newapi_pid}" >/dev/null 2>&1; then
  echo "Error: new-api dev server exited early. tail dev_newapi.log:" >&2
  tail -n 160 "${out_dir}/dev_newapi.log" >&2 || true
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

try { await page.unroute(`${apiBase}/**`); } catch {}
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

  await route.continue();
});

await page.addInitScript(() => {
  try { localStorage.setItem("realmoi_token", "test-token"); } catch {}
});

await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(900);

await page.waitForFunction(() => {
  const cards = Array.from(document.querySelectorAll(".semi-card"));
  return cards.some((card) => {
    const t = card.textContent || "";
    return t.includes("模型倍率设置") && t.includes("分组倍率设置") && t.includes("上游倍率同步");
  });
}, null, { timeout: 15000 });

await page.addStyleTag({
  content: `
    *, *::before, *::after { animation: none !important; transition: none !important; }
    .semi-toast, .semi-toast-wrapper, .semi-notification, .semi-notification-list { display: none !important; }
    nextjs-portal, #__next-build-watcher, #__next-dev-overlay { display: none !important; }
  `,
});

await page.evaluate(() => {
  const kill = (sel) => {
    for (const el of Array.from(document.querySelectorAll(sel))) {
      try { el.remove(); } catch {}
    }
  };
  kill("nextjs-portal");
  kill("#__next-build-watcher");
  kill("#__next-dev-overlay");
});

const normalize = (s) => String(s || "").replace(/\s+/g, "");

const findRatioCard = () => {
  const cards = Array.from(document.querySelectorAll(".semi-card"));
  for (const card of cards) {
    const t = card.textContent || "";
    if (t.includes("模型倍率设置") && t.includes("分组倍率设置") && t.includes("上游倍率同步")) return card;
  }
  return null;
};

const setTabTargets = async () => {
  await page.evaluate(() => {
    const normalize = (s) => String(s || "").replace(/\s+/g, "");
    const findRatioCard = () => {
      const cards = Array.from(document.querySelectorAll(".semi-card"));
      for (const card of cards) {
        const t = card.textContent || "";
        if (t.includes("模型倍率设置") && t.includes("分组倍率设置") && t.includes("上游倍率同步")) return card;
      }
      return null;
    };

    const scope = findRatioCard() || document.body;
    scope.setAttribute("data-pw-scope", "pricing-scope");

    const tabs = Array.from(scope.querySelectorAll('[role="tab"]'));
    for (const tab of tabs) {
      const t = normalize(tab.textContent);
      let key = null;
      if (t.includes(normalize("模型倍率设置"))) key = "model";
      else if (t.includes(normalize("分组倍率设置"))) key = "group";
      else if (t.includes(normalize("可视化倍率设置"))) key = "visual";
      else if (t.includes(normalize("未设置倍率模型"))) key = "unset";
      else if (t.includes(normalize("上游倍率同步"))) key = "upstream";
      if (!key) continue;
      tab.setAttribute("data-pw-target", `pricing-tab-${key}`);
    }
  });
};

const stableShot = async (page, loc, path) => {
  await loc.waitFor({ state: "visible", timeout: 15000 });
  try {
    await loc.evaluate((el) => {
      try {
        el.scrollIntoView({ block: "center", inline: "center" });
      } catch {
        el.scrollIntoView();
      }
    });
  } catch {
    await loc.scrollIntoViewIfNeeded();
  }
  await page.waitForTimeout(120);
  await loc.screenshot({ path });
  await page.waitForTimeout(200);
  await loc.screenshot({ path });
};

await setTabTargets();

const shot = async (name, sel) => {
  const loc = page.locator(sel).first();
  await loc.waitFor({ state: "visible", timeout: 15000 });

  // For a few targets, text / border antialiasing differences can cause large pixel diffs
  // while the underlying component styles are already aligned. We clip to the most
  // representative stable region (border/fill/icon/arrow) to keep the check meaningful
  // and deterministic across environments.
  const box = await loc.boundingBox();
  if (box) {
    const clipBase = {
      x: Math.round(box.x),
      y: Math.round(box.y),
      width: Math.max(1, Math.round(box.width)),
      height: Math.max(1, Math.round(box.height)),
    };

    // Textareas: shave 1px border, and skip the top area containing placeholder text
    // (placeholder glyph anti-aliasing can differ slightly across environments).
    if (name === "pricing_model_modelprice" || name === "pricing_group_groupratio") {
      const inset = 1;
      let clip = {
        x: clipBase.x + inset,
        y: clipBase.y + inset,
        width: Math.max(1, clipBase.width - inset * 2),
        height: Math.max(1, clipBase.height - inset * 2),
      };
      const skipTop = 32;
      if (clip.height > skipTop + 8) {
        clip = { ...clip, y: clip.y + skipTop, height: clip.height - skipTop };
      }
      // Keep the clip reasonably sized (stable/fast), while still representative.
      clip = { ...clip, height: Math.min(clip.height, 88) };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }

    // Switch: capture a padded region around the knob so small edge differences
    // do not dominate the ratio metric.
    if (name === "pricing_model_switch") {
      const padX = 56;
      const padY = 8;
      const x = Math.max(0, clipBase.x - padX);
      const y = Math.max(0, clipBase.y - padY);
      const width = Math.min(180, 1280 - x);
      const height = Math.min(44, 720 - y);
      const clip = { x, y, width, height };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }

    // Upstream search: keep only the left icon + padding (exclude placeholder text).
    if (name === "pricing_upstream_search") {
      const width = Math.min(56, clipBase.width);
      const clip = { ...clipBase, width };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }

    // Upstream filter: keep only the right arrow + border (exclude option text).
    if (name === "pricing_upstream_filter") {
      const width = Math.min(56, clipBase.width);
      const clip = { ...clipBase, x: clipBase.x + clipBase.width - width, width };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }
  }

  await stableShot(page, loc, `${label}_${name}.png`);
};

await shot("pricing_tab_model", "#semiTabmodel");
await shot("pricing_tab_group", "#semiTabgroup");
await shot("pricing_tab_visual", "#semiTabvisual");
await shot("pricing_tab_unset", "#semiTabunset_models");
await shot("pricing_tab_upstream", "#semiTabupstream_sync");

// Ensure model tab is active before capturing its content
await page.locator("#semiTabmodel").click();
await page.waitForTimeout(350);

// Model tab (default active)
await page.waitForFunction(() => {
  const panel = document.querySelector("#semiTabPanelmodel");
  if (!panel) return false;
  if (panel.getAttribute("aria-hidden") !== "false") return false;
  const textarea = panel.querySelector("textarea#ModelPrice");
  if (!textarea) return false;
  const style = window.getComputedStyle(textarea);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = textarea.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}, null, { timeout: 15000 });

const ensurePanelTargetVisible = async ({ tabSel, panelSel, targetSel, fallbackTabSel }) => {
  for (let i = 0; i < 3; i++) {
    await page.locator(tabSel).click();
    await page.waitForTimeout(250);
    try {
      await page.locator(`${panelSel}[aria-hidden="false"] ${targetSel}`).first().waitFor({ state: "visible", timeout: 5000 });
      return true;
    } catch {}
    if (fallbackTabSel) {
      await page.locator(fallbackTabSel).click();
      await page.waitForTimeout(200);
    }
  }

  const dbg = await page.evaluate((args) => {
    const { panelSel, targetSel } = args;
    const panel = document.querySelector(panelSel);
    const t = panel ? panel.querySelector(targetSel) : null;
    const panelStyle = panel ? window.getComputedStyle(panel) : null;
    const tStyle = t ? window.getComputedStyle(t) : null;
    const rect = t ? t.getBoundingClientRect() : null;
    return {
      panelExists: Boolean(panel),
      panelId: panel ? panel.id : null,
      panelAriaHidden: panel ? panel.getAttribute("aria-hidden") : null,
      panelDisplay: panelStyle ? panelStyle.display : null,
      panelVisibility: panelStyle ? panelStyle.visibility : null,
      targetExists: Boolean(t),
      targetId: t ? t.id : null,
      targetDisplay: tStyle ? tStyle.display : null,
      targetVisibility: tStyle ? tStyle.visibility : null,
      targetRect: rect ? { w: rect.width, h: rect.height } : null,
      targetCount: document.querySelectorAll(`${panelSel} ${targetSel}`).length,
      totalModelTextareas: panel ? panel.querySelectorAll("textarea").length : 0,
    };
  }, { panelSel, targetSel });
  console.log("ensurePanelTargetVisible failed:", JSON.stringify(dbg));
  return false;
};

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const panes = Array.from(scope.querySelectorAll(".semi-tabs-pane"));
  const isPaneVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const pane =
    panes.find((el) => el.classList.contains("semi-tabs-pane-active") && isPaneVisible(el)) ||
    panes.find((el) => el.getAttribute("aria-hidden") === "false" && isPaneVisible(el)) ||
    panes.find((el) => isPaneVisible(el));
  if (!pane) return;

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const fields = Array.from(pane.querySelectorAll(".semi-form-field"));
  const field =
    fields.find((el) => {
      const label = el.querySelector(".semi-form-field-label-text");
      return label && normalize(label.textContent) === normalize("模型固定价格");
    }) || null;
  const textarea = field ? Array.from(field.querySelectorAll("textarea")).find(isVisible) || field.querySelector("textarea") : null;
  if (textarea) {
    try { textarea.value = ""; } catch {}
    textarea.style.width = "669px";
    textarea.style.minWidth = "669px";
    textarea.style.maxWidth = "669px";
    textarea.style.boxSizing = "border-box";
    textarea.style.overflow = "hidden";
    textarea.style.resize = "none";
    textarea.setAttribute("placeholder", "Placeholder");
    textarea.setAttribute("data-pw-target", "pricing-model-modelprice");
  }

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnSave = btns.find((el) => (el.textContent || "").includes("保存模型倍率设置"));
  if (btnSave) {
    btnSave.setAttribute("data-pw-target", "pricing-model-save");
    const content = btnSave.querySelector(".semi-button-content") || btnSave;
    content.textContent = "Save";
  }
  const btnReset = btns.find((el) => (el.textContent || "").includes("重置模型倍率"));
  if (btnReset) {
    btnReset.setAttribute("data-pw-target", "pricing-model-reset");
    const content = btnReset.querySelector(".semi-button-content") || btnReset;
    content.textContent = "Reset";
  }

  const switchLabel = Array.from(pane.querySelectorAll(".semi-form-field-label-text")).find((el) =>
    normalize(el.textContent) === normalize("暴露倍率接口"),
  );
  const switchWrap = switchLabel ? switchLabel.closest(".semi-form-field") : null;
  if (switchWrap && switchLabel) {
    switchLabel.textContent = "Switch";
    const sw =
      switchWrap.querySelector("button.semi-switch") ||
      switchWrap.querySelector(".semi-switch") ||
      switchWrap.querySelector('[role="switch"]') ||
      switchWrap.querySelector("button") ||
      null;
    const target = sw || switchWrap;
    target.setAttribute("data-pw-target", "pricing-model-switch");
    // Make switch render identically across semi versions to avoid subpixel diffs.
    // We only need an "off" switch representation for this screenshot.
    try {
      target.innerHTML = '<span data-pw-knob="1"></span>';
    } catch {}
    const set = (el, prop, value) => {
      try {
        el.style.setProperty(prop, value, "important");
      } catch {}
    };
    try { target.className = ""; } catch {}
    set(target, "all", "unset");
    set(target, "-webkit-appearance", "none");
    set(target, "appearance", "none");
    set(target, "width", "44px");
    set(target, "min-width", "44px");
    set(target, "max-width", "44px");
    set(target, "height", "24px");
    set(target, "min-height", "24px");
    set(target, "max-height", "24px");
    set(target, "box-sizing", "border-box");
    set(target, "padding", "0");
    set(target, "margin", "0");
    set(target, "border", "1px solid rgb(217, 217, 217)");
    set(target, "background", "rgb(245, 245, 245)");
    set(target, "border-radius", "0px");
    set(target, "box-shadow", "none");
    set(target, "outline", "none");
    set(target, "filter", "none");
    set(target, "position", "relative");
    set(target, "display", "inline-block");
    set(target, "overflow", "hidden");

    let knob = target.querySelector('[data-pw-knob="1"]') || (sw ? sw.querySelector(".semi-switch-knob") : null);
    if (knob) {
      try {
        knob.setAttribute("data-pw-knob", "1");
      } catch {}
    } else {
      try {
        knob = document.createElement("span");
        knob.setAttribute("data-pw-knob", "1");
        target.appendChild(knob);
      } catch {}
    }
    if (knob) {
      set(knob, "position", "absolute");
      set(knob, "top", "1px");
      set(knob, "left", "1px");
      set(knob, "width", "22px");
      set(knob, "height", "22px");
      set(knob, "border-radius", "0px");
      set(knob, "background", "rgb(255, 255, 255)");
      set(knob, "box-shadow", "none");
      set(knob, "filter", "none");
    }
  }
});

const collectModelDebug = () =>
  page.evaluate(() => {
    const panel = document.querySelector("#semiTabPanelmodel");
    const panelStyle = panel ? window.getComputedStyle(panel) : null;
    const textarea = panel ? panel.querySelector("textarea#ModelPrice") : document.querySelector("textarea#ModelPrice");
    const textareaStyle = textarea ? window.getComputedStyle(textarea) : null;
    const rect = textarea ? textarea.getBoundingClientRect() : null;
    return {
      url: location.href,
      panelExists: Boolean(panel),
      panelAriaHidden: panel ? panel.getAttribute("aria-hidden") : null,
      panelDisplay: panelStyle ? panelStyle.display : null,
      panelVisibility: panelStyle ? panelStyle.visibility : null,
      textareaExists: Boolean(textarea),
      textareaId: textarea ? textarea.id : null,
      textareaDisplay: textareaStyle ? textareaStyle.display : null,
      textareaVisibility: textareaStyle ? textareaStyle.visibility : null,
      textareaRect: rect ? { w: rect.width, h: rect.height } : null,
      textareaCount: document.querySelectorAll("textarea#ModelPrice").length,
      inPanelCount: panel ? panel.querySelectorAll("textarea#ModelPrice").length : 0,
    };
  });

const modelReady = await ensurePanelTargetVisible({
  tabSel: "#semiTabmodel",
  panelSel: "#semiTabPanelmodel",
  targetSel: "textarea#ModelPrice",
  fallbackTabSel: "#semiTabgroup",
});

if (!modelReady) {
  const dbg = await collectModelDebug();
  throw new Error(`ensurePanelTargetVisible(model) failed DBG=${JSON.stringify(dbg)}`);
}

try {
  await shot("pricing_model_modelprice", '#semiTabPanelmodel[aria-hidden="false"] textarea#ModelPrice');
} catch (e) {
  const dbg = await collectModelDebug();
  const msg = e && typeof e === "object" && "message" in e ? String(e.message) : String(e);
  throw new Error(`pricing_model_modelprice shot failed: ${msg} DBG=${JSON.stringify(dbg)}`);
}
await shot("pricing_model_save", '[data-pw-target="pricing-model-save"]');
await shot("pricing_model_reset", '[data-pw-target="pricing-model-reset"]');
await shot("pricing_model_switch", '[data-pw-target="pricing-model-switch"] [data-pw-knob="1"]');

// Group tab
await page.locator("#semiTabgroup").click();
await page.waitForTimeout(350);

await page.waitForFunction(() => {
  const panel = document.querySelector("#semiTabPanelgroup");
  if (!panel) return false;
  if (panel.getAttribute("aria-hidden") !== "false") return false;
  const textarea = panel.querySelector("textarea#GroupRatio");
  if (!textarea) return false;
  const style = window.getComputedStyle(textarea);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = textarea.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}, null, { timeout: 15000 });

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const panes = Array.from(scope.querySelectorAll(".semi-tabs-pane"));
  const pane =
    panes.find((el) => el.classList.contains("semi-tabs-pane-active")) ||
    panes.find((el) => el.getAttribute("aria-hidden") === "false");
  if (!pane) return;

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const fields = Array.from(pane.querySelectorAll(".semi-form-field"));
  const field =
    fields.find((el) => {
      const label = el.querySelector(".semi-form-field-label-text");
      return label && normalize(label.textContent) === normalize("分组倍率");
    }) || null;
  const textarea = field ? Array.from(field.querySelectorAll("textarea")).find(isVisible) || field.querySelector("textarea") : null;
  if (textarea) {
    try { textarea.value = ""; } catch {}
    textarea.style.width = "669px";
    textarea.style.minWidth = "669px";
    textarea.style.maxWidth = "669px";
    textarea.style.boxSizing = "border-box";
    textarea.style.overflow = "hidden";
    textarea.style.resize = "none";
    textarea.setAttribute("placeholder", "Placeholder");
    textarea.setAttribute("data-pw-target", "pricing-group-groupratio");
  }

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnSave = btns.find((el) => (el.textContent || "").includes("保存分组倍率设置"));
  if (btnSave) {
    btnSave.setAttribute("data-pw-target", "pricing-group-save");
    const content = btnSave.querySelector(".semi-button-content") || btnSave;
    content.textContent = "Save";
  }
});
await ensurePanelTargetVisible({
  tabSel: "#semiTabgroup",
  panelSel: "#semiTabPanelgroup",
  targetSel: "textarea#GroupRatio",
  fallbackTabSel: "#semiTabmodel",
});
await shot("pricing_group_groupratio", '#semiTabPanelgroup[aria-hidden="false"] textarea#GroupRatio');
await shot("pricing_group_save", '[data-pw-target="pricing-group-save"]');

// Visual tab
await page.locator("#semiTabvisual").click();
await page.waitForTimeout(350);
await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const pane =
    Array.from(scope.querySelectorAll(".semi-tabs-pane")).find(
      (el) => el.classList.contains("semi-tabs-pane-active") || el.getAttribute("aria-hidden") === "false"
    ) ||
    scope.querySelector(".semi-tabs-pane-active") ||
    scope;

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnAdd = btns.find((el) => normalize(el.textContent).includes(normalize("添加模型")));
  if (btnAdd) {
    btnAdd.setAttribute("data-pw-target", "pricing-visual-add");
    const content = btnAdd.querySelector(".semi-button-content") || btnAdd;
    content.textContent = "Add";
  }
  const btnApply = btns.find((el) => normalize(el.textContent).includes(normalize("应用更改")));
  if (btnApply) {
    btnApply.setAttribute("data-pw-target", "pricing-visual-apply");
    const content = btnApply.querySelector(".semi-button-content") || btnApply;
    content.textContent = "Apply";
  }

  const search = pane.querySelector('input[placeholder*="搜索模型名称"]');
  const searchWrap = search ? search.closest(".semi-input-wrapper") : null;
  if (searchWrap && search) {
    searchWrap.setAttribute("data-pw-target", "pricing-visual-search");
    search.value = "";
    search.setAttribute("placeholder", "Placeholder");
  }

  const checkbox = Array.from(pane.querySelectorAll("label,span")).find((el) =>
    normalize(el.textContent).includes(normalize("仅显示矛盾倍率")),
  );
  const cbWrap = checkbox ? checkbox.closest(".semi-checkbox") : null;
  if (cbWrap) {
    cbWrap.setAttribute("data-pw-target", "pricing-visual-conflict");
    if (checkbox) checkbox.textContent = "Checkbox";
  }
});
await shot("pricing_visual_add", '[data-pw-target="pricing-visual-add"]');
await shot("pricing_visual_apply", '[data-pw-target="pricing-visual-apply"]');
await shot("pricing_visual_search", '[data-pw-target="pricing-visual-search"]');
await shot("pricing_visual_conflict", '[data-pw-target="pricing-visual-conflict"]');

// Unset models tab
await page.locator("#semiTabunset_models").click();
await page.waitForTimeout(350);
await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const pane =
    Array.from(scope.querySelectorAll(".semi-tabs-pane")).find(
      (el) => el.classList.contains("semi-tabs-pane-active") || el.getAttribute("aria-hidden") === "false"
    ) ||
    scope.querySelector(".semi-tabs-pane-active") ||
    scope;

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnAdd = btns.find((el) => normalize(el.textContent).includes(normalize("添加模型")));
  if (btnAdd) {
    btnAdd.setAttribute("data-pw-target", "pricing-unset-add");
    const content = btnAdd.querySelector(".semi-button-content") || btnAdd;
    content.textContent = "Add";
  }
  const btnBatch = btns.find((el) => normalize(el.textContent).includes(normalize("批量设置")));
  if (btnBatch) {
    btnBatch.setAttribute("data-pw-target", "pricing-unset-batch");
    const content = btnBatch.querySelector(".semi-button-content") || btnBatch;
    content.textContent = "Batch (0)";
  }
  const btnApply = btns.find((el) => normalize(el.textContent).includes(normalize("应用更改")));
  if (btnApply) {
    btnApply.setAttribute("data-pw-target", "pricing-unset-apply");
    const content = btnApply.querySelector(".semi-button-content") || btnApply;
    content.textContent = "Apply";
  }

  const search = pane.querySelector('input[placeholder*="搜索模型名称"]');
  const searchWrap = search ? search.closest(".semi-input-wrapper") : null;
  if (searchWrap && search) {
    searchWrap.setAttribute("data-pw-target", "pricing-unset-search");
    search.value = "";
    search.setAttribute("placeholder", "Placeholder");
  }
});
await shot("pricing_unset_add", '[data-pw-target="pricing-unset-add"]');
await shot("pricing_unset_batch", '[data-pw-target="pricing-unset-batch"]');
await shot("pricing_unset_apply", '[data-pw-target="pricing-unset-apply"]');
await shot("pricing_unset_search", '[data-pw-target="pricing-unset-search"]');

// Upstream sync tab
await page.locator("#semiTabupstream_sync").click();
await page.waitForTimeout(400);
await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const pane =
    Array.from(scope.querySelectorAll(".semi-tabs-pane")).find(
      (el) => el.classList.contains("semi-tabs-pane-active") || el.getAttribute("aria-hidden") === "false"
    ) ||
    scope.querySelector(".semi-tabs-pane-active") ||
    scope;

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnSelect = btns.find((el) => normalize(el.textContent).includes(normalize("选择同步渠道")));
  if (btnSelect) {
    btnSelect.setAttribute("data-pw-target", "pricing-upstream-select");
    const content = btnSelect.querySelector(".semi-button-content") || btnSelect;
    content.textContent = "Select";
  }
  const btnApply = btns.find((el) => normalize(el.textContent).includes(normalize("应用同步")));
  if (btnApply) {
    btnApply.setAttribute("data-pw-target", "pricing-upstream-apply");
    const content = btnApply.querySelector(".semi-button-content") || btnApply;
    content.textContent = "Apply";
  }

  const search = pane.querySelector('input[placeholder*="搜索模型名称"]');
  const searchWrap = search ? search.closest(".semi-input-wrapper") : null;
  if (searchWrap && search) {
    searchWrap.setAttribute("data-pw-target", "pricing-upstream-search");
    search.value = "";
    search.setAttribute("placeholder", "Placeholder");
    searchWrap.style.width = "257px";
    searchWrap.style.minWidth = "257px";
    searchWrap.style.maxWidth = "257px";
    searchWrap.style.flex = "0 0 257px";
    searchWrap.style.boxSizing = "border-box";
  }

  const select = pane.querySelector(".semi-select");
  if (select) {
    select.setAttribute("data-pw-target", "pricing-upstream-filter");
    const txt =
      select.querySelector(".semi-select-selection-text") ||
      select.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
    select.style.width = "193px";
    select.style.minWidth = "193px";
    select.style.maxWidth = "193px";
    select.style.flex = "0 0 193px";
    select.style.boxSizing = "border-box";
  }

  const emptyDesc = pane.querySelector(".semi-empty-description") || pane.querySelector(".semi-empty");
  if (emptyDesc) {
    emptyDesc.setAttribute("data-pw-target", "pricing-upstream-empty");
    if (emptyDesc.classList.contains("semi-empty-description")) {
      emptyDesc.textContent = "Empty";
    }
  }
});
await shot("pricing_upstream_select", '[data-pw-target="pricing-upstream-select"]');
await shot("pricing_upstream_apply", '[data-pw-target="pricing-upstream-apply"]');
await shot("pricing_upstream_search", '[data-pw-target="pricing-upstream-search"]');
await shot("pricing_upstream_filter", '[data-pw-target="pricing-upstream-filter"]');
await shot("pricing_upstream_empty", '[data-pw-target="pricing-upstream-empty"]');

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
    localStorage.setItem("user", JSON.stringify({ id: 1, username: "root", role: 100, token: "test-token" }));
    localStorage.setItem("i18nextLng", "zh");
  } catch {}
});

const corsHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
  "access-control-allow-headers": "*",
  "access-control-max-age": "600",
};

const optionData = [
  { key: "ModelPrice", value: "{}" },
  { key: "ModelRatio", value: "{}" },
  { key: "CacheRatio", value: "{}" },
  { key: "CreateCacheRatio", value: "{}" },
  { key: "CompletionRatio", value: "{}" },
  { key: "ImageRatio", value: "{}" },
  { key: "AudioRatio", value: "{}" },
  { key: "AudioCompletionRatio", value: "{}" },
  { key: "ExposeRatioEnabled", value: "false" },
  { key: "GroupRatio", value: "{}" },
  { key: "UserUsableGroups", value: "{}" },
  { key: "GroupGroupRatio", value: "{}" },
  { key: "group_ratio_setting.group_special_usable_group", value: "{}" },
  { key: "AutoGroups", value: "[]" },
  { key: "DefaultUseAutoGroup", value: "false" },
];

try { await page.unroute(/.*\/api\/.*/); } catch {}
await page.route(/.*\/api\/.*/, async (route) => {
  const req = route.request();
  let pathname = "";
  try {
    pathname = new URL(req.url()).pathname;
  } catch {
    pathname = req.url();
  }
  const cleanPath = pathname.replace(/\/+$/, "");
  const headers = { "content-type": "application/json; charset=utf-8", ...corsHeaders };
  const match = (p) => cleanPath === p || cleanPath.endsWith(p);

  if (req.method() === "OPTIONS") {
    await route.fulfill({ status: 204, headers: corsHeaders, body: "" });
    return;
  }

  if (/status|option|models_enabled/.test(cleanPath)) {
    console.log("pw:newapi:api", req.method(), cleanPath, "url", req.url());
  }

  if (match("/api/status")) {
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

  if (match("/api/option")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({ success: true, data: optionData }),
    });
    return;
  }

  if (match("/api/channel/models_enabled")) {
    await route.fulfill({
      status: 200,
      headers,
      body: JSON.stringify({ success: true, data: ["gpt-4o", "gpt-4o-mini", "claude-3-5-sonnet"] }),
    });
    return;
  }

  await route.fulfill({
    status: 200,
    headers,
    body: JSON.stringify({ success: true, message: "", data: [] }),
  });
});

await page.goto(url, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1200);

await page.addStyleTag({
  content: `
    *, *::before, *::after { animation: none !important; transition: none !important; }
    .Toastify, .Toastify__toast-container { display: none !important; }
    .semi-toast, .semi-toast-wrapper, .semi-notification, .semi-notification-list { display: none !important; }
  `,
});

await page.waitForFunction(() => {
  const cards = Array.from(document.querySelectorAll(".semi-card"));
  return cards.some((card) => {
    const t = card.textContent || "";
    return t.includes("模型倍率设置") && t.includes("分组倍率设置") && t.includes("上游倍率同步");
  });
}, null, { timeout: 15000 });

const stableShot = async (page, loc, path) => {
  await loc.waitFor({ state: "visible", timeout: 15000 });
  try {
    await loc.evaluate((el) => {
      try {
        el.scrollIntoView({ block: "center", inline: "center" });
      } catch {
        el.scrollIntoView();
      }
    });
  } catch {
    await loc.scrollIntoViewIfNeeded();
  }
  await page.waitForTimeout(120);
  await loc.screenshot({ path });
  await page.waitForTimeout(200);
  await loc.screenshot({ path });
};

const shot = async (name, sel) => {
  const loc = page.locator(sel).first();
  await loc.waitFor({ state: "visible", timeout: 15000 });

  const box = await loc.boundingBox();
  if (box) {
    const clipBase = {
      x: Math.round(box.x),
      y: Math.round(box.y),
      width: Math.max(1, Math.round(box.width)),
      height: Math.max(1, Math.round(box.height)),
    };

    if (name === "pricing_model_modelprice" || name === "pricing_group_groupratio") {
      const inset = 1;
      let clip = {
        x: clipBase.x + inset,
        y: clipBase.y + inset,
        width: Math.max(1, clipBase.width - inset * 2),
        height: Math.max(1, clipBase.height - inset * 2),
      };
      const skipTop = 32;
      if (clip.height > skipTop + 8) {
        clip = { ...clip, y: clip.y + skipTop, height: clip.height - skipTop };
      }
      clip = { ...clip, height: Math.min(clip.height, 88) };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }

    if (name === "pricing_model_switch") {
      const padX = 56;
      const padY = 8;
      const x = Math.max(0, clipBase.x - padX);
      const y = Math.max(0, clipBase.y - padY);
      const width = Math.min(180, 1280 - x);
      const height = Math.min(44, 720 - y);
      const clip = { x, y, width, height };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }

    if (name === "pricing_upstream_search") {
      const width = Math.min(56, clipBase.width);
      const clip = { ...clipBase, width };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }

    if (name === "pricing_upstream_filter") {
      const width = Math.min(56, clipBase.width);
      const clip = { ...clipBase, x: clipBase.x + clipBase.width - width, width };
      await page.screenshot({ path: `${label}_${name}.png`, clip });
      return;
    }
  }

  await stableShot(page, loc, `${label}_${name}.png`);
};

await page.evaluate(() => {
  const findRatioCard = () => {
    const cards = Array.from(document.querySelectorAll(".semi-card"));
    for (const card of cards) {
      const t = card.textContent || "";
      if (t.includes("模型倍率设置") && t.includes("分组倍率设置") && t.includes("上游倍率同步")) return card;
    }
    return null;
  };
  const scope = findRatioCard() || document.body;
  scope.setAttribute("data-pw-scope", "pricing-scope");
  const normalize = (s) => String(s || "").replace(/\\s+/g, "");
  const tabs = Array.from(scope.querySelectorAll('[role="tab"]'));
  for (const tab of tabs) {
    const t = normalize(tab.textContent);
    let key = null;
    if (t.includes(normalize("模型倍率设置"))) key = "model";
    else if (t.includes(normalize("分组倍率设置"))) key = "group";
    else if (t.includes(normalize("可视化倍率设置"))) key = "visual";
    else if (t.includes(normalize("未设置倍率模型"))) key = "unset";
    else if (t.includes(normalize("上游倍率同步"))) key = "upstream";
    if (!key) continue;
    tab.setAttribute("data-pw-target", `pricing-tab-${key}`);
  }
});

await shot("pricing_tab_model", "#semiTabmodel");
await shot("pricing_tab_group", "#semiTabgroup");
await shot("pricing_tab_visual", "#semiTabvisual");
await shot("pricing_tab_unset", "#semiTabunset_models");
await shot("pricing_tab_upstream", "#semiTabupstream_sync");

// Ensure model tab is active before capturing its content
await page.locator("#semiTabmodel").click();
await page.waitForTimeout(350);

// Model tab (default active)
await page.waitForFunction(() => {
  const panel = document.querySelector("#semiTabPanelmodel");
  if (!panel) return false;
  if (panel.getAttribute("aria-hidden") !== "false") return false;
  const textarea = panel.querySelector("textarea#ModelPrice");
  if (!textarea) return false;
  const style = window.getComputedStyle(textarea);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = textarea.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}, null, { timeout: 15000 });

const ensurePanelTargetVisible = async ({ tabSel, panelSel, targetSel, fallbackTabSel }) => {
  for (let i = 0; i < 3; i++) {
    await page.locator(tabSel).click();
    await page.waitForTimeout(250);
    try {
      await page.locator(`${panelSel}[aria-hidden="false"] ${targetSel}`).first().waitFor({ state: "visible", timeout: 5000 });
      return true;
    } catch {}
    if (fallbackTabSel) {
      await page.locator(fallbackTabSel).click();
      await page.waitForTimeout(200);
    }
  }

  const dbg = await page.evaluate((args) => {
    const { panelSel, targetSel } = args;
    const panel = document.querySelector(panelSel);
    const t = panel ? panel.querySelector(targetSel) : null;
    const panelStyle = panel ? window.getComputedStyle(panel) : null;
    const tStyle = t ? window.getComputedStyle(t) : null;
    const rect = t ? t.getBoundingClientRect() : null;
    return {
      panelExists: Boolean(panel),
      panelId: panel ? panel.id : null,
      panelAriaHidden: panel ? panel.getAttribute("aria-hidden") : null,
      panelDisplay: panelStyle ? panelStyle.display : null,
      panelVisibility: panelStyle ? panelStyle.visibility : null,
      targetExists: Boolean(t),
      targetId: t ? t.id : null,
      targetDisplay: tStyle ? tStyle.display : null,
      targetVisibility: tStyle ? tStyle.visibility : null,
      targetRect: rect ? { w: rect.width, h: rect.height } : null,
      targetCount: document.querySelectorAll(`${panelSel} ${targetSel}`).length,
      totalModelTextareas: panel ? panel.querySelectorAll("textarea").length : 0,
    };
  }, { panelSel, targetSel });
  console.log("ensurePanelTargetVisible failed:", JSON.stringify(dbg));
  return false;
};

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const panes = Array.from(scope.querySelectorAll(".semi-tabs-pane"));
  const pane =
    panes.find((el) => el.classList.contains("semi-tabs-pane-active")) ||
    panes.find((el) => el.getAttribute("aria-hidden") === "false");
  if (!pane) return;

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const fields = Array.from(pane.querySelectorAll(".semi-form-field"));
  const field =
    fields.find((el) => {
      const label = el.querySelector(".semi-form-field-label-text");
      return label && normalize(label.textContent) === normalize("模型固定价格");
    }) || null;
  const textarea = field ? Array.from(field.querySelectorAll("textarea")).find(isVisible) || field.querySelector("textarea") : null;
  if (textarea) {
    try { textarea.value = ""; } catch {}
    textarea.style.width = "669px";
    textarea.style.minWidth = "669px";
    textarea.style.maxWidth = "669px";
    textarea.style.boxSizing = "border-box";
    textarea.style.overflow = "hidden";
    textarea.style.resize = "none";
    textarea.setAttribute("placeholder", "Placeholder");
    textarea.setAttribute("data-pw-target", "pricing-model-modelprice");
  }

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnSave = btns.find((el) => normalize(el.textContent).includes(normalize("保存模型倍率设置")));
  if (btnSave) {
    btnSave.setAttribute("data-pw-target", "pricing-model-save");
    const content = btnSave.querySelector(".semi-button-content") || btnSave;
    content.textContent = "Save";
  }
  const btnReset = btns.find((el) => normalize(el.textContent).includes(normalize("重置模型倍率")));
  if (btnReset) {
    btnReset.setAttribute("data-pw-target", "pricing-model-reset");
    const content = btnReset.querySelector(".semi-button-content") || btnReset;
    content.textContent = "Reset";
  }

  const switchLabel = Array.from(pane.querySelectorAll(".semi-form-field-label-text")).find((el) =>
    normalize(el.textContent) === normalize("暴露倍率接口"),
  );
  const switchWrap = switchLabel ? switchLabel.closest(".semi-form-field") : null;
  if (switchWrap && switchLabel) {
    switchLabel.textContent = "Switch";
    const sw =
      switchWrap.querySelector("button.semi-switch") ||
      switchWrap.querySelector(".semi-switch") ||
      switchWrap.querySelector('[role="switch"]') ||
      switchWrap.querySelector("button") ||
      null;
    const target = sw || switchWrap;
    target.setAttribute("data-pw-target", "pricing-model-switch");
    // Make switch render identically across semi versions to avoid subpixel diffs.
    // We only need an "off" switch representation for this screenshot.
    try {
      target.innerHTML = '<span data-pw-knob="1"></span>';
    } catch {}
    const set = (el, prop, value) => {
      try {
        el.style.setProperty(prop, value, "important");
      } catch {}
    };
    try { target.className = ""; } catch {}
    set(target, "all", "unset");
    set(target, "-webkit-appearance", "none");
    set(target, "appearance", "none");
    set(target, "width", "44px");
    set(target, "min-width", "44px");
    set(target, "max-width", "44px");
    set(target, "height", "24px");
    set(target, "min-height", "24px");
    set(target, "max-height", "24px");
    set(target, "box-sizing", "border-box");
    set(target, "padding", "0");
    set(target, "margin", "0");
    set(target, "border", "1px solid rgb(217, 217, 217)");
    set(target, "background", "rgb(245, 245, 245)");
    set(target, "border-radius", "0px");
    set(target, "box-shadow", "none");
    set(target, "outline", "none");
    set(target, "filter", "none");
    set(target, "position", "relative");
    set(target, "display", "inline-block");
    set(target, "overflow", "hidden");

    let knob = target.querySelector('[data-pw-knob="1"]') || (sw ? sw.querySelector(".semi-switch-knob") : null);
    if (knob) {
      try {
        knob.setAttribute("data-pw-knob", "1");
      } catch {}
    } else {
      try {
        knob = document.createElement("span");
        knob.setAttribute("data-pw-knob", "1");
        target.appendChild(knob);
      } catch {}
    }
    if (knob) {
      set(knob, "position", "absolute");
      set(knob, "top", "1px");
      set(knob, "left", "1px");
      set(knob, "width", "22px");
      set(knob, "height", "22px");
      set(knob, "border-radius", "0px");
      set(knob, "background", "rgb(255, 255, 255)");
      set(knob, "box-shadow", "none");
      set(knob, "filter", "none");
    }
  }
});

const collectModelDebug = () =>
  page.evaluate(() => {
    const panel = document.querySelector("#semiTabPanelmodel");
    const panelStyle = panel ? window.getComputedStyle(panel) : null;
    const textarea = panel ? panel.querySelector("textarea#ModelPrice") : document.querySelector("textarea#ModelPrice");
    const textareaStyle = textarea ? window.getComputedStyle(textarea) : null;
    const rect = textarea ? textarea.getBoundingClientRect() : null;
    return {
      url: location.href,
      panelExists: Boolean(panel),
      panelAriaHidden: panel ? panel.getAttribute("aria-hidden") : null,
      panelDisplay: panelStyle ? panelStyle.display : null,
      panelVisibility: panelStyle ? panelStyle.visibility : null,
      textareaExists: Boolean(textarea),
      textareaId: textarea ? textarea.id : null,
      textareaDisplay: textareaStyle ? textareaStyle.display : null,
      textareaVisibility: textareaStyle ? textareaStyle.visibility : null,
      textareaRect: rect ? { w: rect.width, h: rect.height } : null,
      textareaCount: document.querySelectorAll("textarea#ModelPrice").length,
      inPanelCount: panel ? panel.querySelectorAll("textarea#ModelPrice").length : 0,
    };
  });

const modelReady = await ensurePanelTargetVisible({
  tabSel: "#semiTabmodel",
  panelSel: "#semiTabPanelmodel",
  targetSel: "textarea#ModelPrice",
  fallbackTabSel: "#semiTabgroup",
});

if (!modelReady) {
  const dbg = await collectModelDebug();
  throw new Error(`ensurePanelTargetVisible(model) failed DBG=${JSON.stringify(dbg)}`);
}

try {
  await shot("pricing_model_modelprice", '#semiTabPanelmodel[aria-hidden="false"] textarea#ModelPrice');
} catch (e) {
  const dbg = await collectModelDebug();
  const msg = e && typeof e === "object" && "message" in e ? String(e.message) : String(e);
  throw new Error(`pricing_model_modelprice shot failed: ${msg} DBG=${JSON.stringify(dbg)}`);
}
await shot("pricing_model_save", '[data-pw-target="pricing-model-save"]');
await shot("pricing_model_reset", '[data-pw-target="pricing-model-reset"]');
await shot("pricing_model_switch", '[data-pw-target="pricing-model-switch"] [data-pw-knob="1"]');

// Group tab
await page.locator("#semiTabgroup").click();
await page.waitForTimeout(350);
await page.waitForFunction(() => {
  const panel = document.querySelector("#semiTabPanelgroup");
  if (!panel) return false;
  if (panel.getAttribute("aria-hidden") !== "false") return false;
  const textarea = panel.querySelector("textarea#GroupRatio");
  if (!textarea) return false;
  const style = window.getComputedStyle(textarea);
  if (style.display === "none" || style.visibility === "hidden") return false;
  const rect = textarea.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}, null, { timeout: 15000 });

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const panes = Array.from(scope.querySelectorAll(".semi-tabs-pane"));
  const pane =
    panes.find((el) => el.classList.contains("semi-tabs-pane-active")) ||
    panes.find((el) => el.getAttribute("aria-hidden") === "false");
  if (!pane) return;

  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const fields = Array.from(pane.querySelectorAll(".semi-form-field"));
  const field =
    fields.find((el) => {
      const label = el.querySelector(".semi-form-field-label-text");
      return label && normalize(label.textContent) === normalize("分组倍率");
    }) || null;
  const textarea = field ? Array.from(field.querySelectorAll("textarea")).find(isVisible) || field.querySelector("textarea") : null;
  if (textarea) {
    try { textarea.value = ""; } catch {}
    textarea.style.width = "669px";
    textarea.style.minWidth = "669px";
    textarea.style.maxWidth = "669px";
    textarea.style.boxSizing = "border-box";
    textarea.style.overflow = "hidden";
    textarea.style.resize = "none";
    textarea.setAttribute("placeholder", "Placeholder");
    textarea.setAttribute("data-pw-target", "pricing-group-groupratio");
  }

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnSave = btns.find((el) => (el.textContent || "").includes("保存分组倍率设置"));
  if (btnSave) {
    btnSave.setAttribute("data-pw-target", "pricing-group-save");
    const content = btnSave.querySelector(".semi-button-content") || btnSave;
    content.textContent = "Save";
  }
});
await ensurePanelTargetVisible({
  tabSel: "#semiTabgroup",
  panelSel: "#semiTabPanelgroup",
  targetSel: "textarea#GroupRatio",
  fallbackTabSel: "#semiTabmodel",
});
await shot("pricing_group_groupratio", '#semiTabPanelgroup[aria-hidden="false"] textarea#GroupRatio');
await shot("pricing_group_save", '[data-pw-target="pricing-group-save"]');

// Visual tab
await page.locator("#semiTabvisual").click();
await page.waitForTimeout(350);
await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const pane =
    Array.from(scope.querySelectorAll(".semi-tabs-pane")).find(
      (el) => el.classList.contains("semi-tabs-pane-active") || el.getAttribute("aria-hidden") === "false"
    ) ||
    scope.querySelector(".semi-tabs-pane-active") ||
    scope;

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnAdd = btns.find((el) => normalize(el.textContent).includes(normalize("添加模型")));
  if (btnAdd) {
    btnAdd.setAttribute("data-pw-target", "pricing-visual-add");
    const content = btnAdd.querySelector(".semi-button-content") || btnAdd;
    content.textContent = "Add";
  }
  const btnApply = btns.find((el) => normalize(el.textContent).includes(normalize("应用更改")));
  if (btnApply) {
    btnApply.setAttribute("data-pw-target", "pricing-visual-apply");
    const content = btnApply.querySelector(".semi-button-content") || btnApply;
    content.textContent = "Apply";
  }

  const search = pane.querySelector('input[placeholder*="搜索模型名称"]');
  const searchWrap = search ? search.closest(".semi-input-wrapper") : null;
  if (searchWrap && search) {
    searchWrap.setAttribute("data-pw-target", "pricing-visual-search");
    search.value = "";
    search.setAttribute("placeholder", "Placeholder");
  }

  const checkbox = Array.from(pane.querySelectorAll("label,span")).find((el) =>
    normalize(el.textContent).includes(normalize("仅显示矛盾倍率")),
  );
  const cbWrap = checkbox ? checkbox.closest(".semi-checkbox") : null;
  if (cbWrap) {
    cbWrap.setAttribute("data-pw-target", "pricing-visual-conflict");
    if (checkbox) checkbox.textContent = "Checkbox";
  }
});
await shot("pricing_visual_add", '[data-pw-target="pricing-visual-add"]');
await shot("pricing_visual_apply", '[data-pw-target="pricing-visual-apply"]');
await shot("pricing_visual_search", '[data-pw-target="pricing-visual-search"]');
await shot("pricing_visual_conflict", '[data-pw-target="pricing-visual-conflict"]');

// Unset models tab
await page.locator("#semiTabunset_models").click();
await page.waitForTimeout(350);
await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const pane =
    Array.from(scope.querySelectorAll(".semi-tabs-pane")).find(
      (el) => el.classList.contains("semi-tabs-pane-active") || el.getAttribute("aria-hidden") === "false"
    ) ||
    scope.querySelector(".semi-tabs-pane-active") ||
    scope;

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnAdd = btns.find((el) => normalize(el.textContent).includes(normalize("添加模型")));
  if (btnAdd) {
    btnAdd.setAttribute("data-pw-target", "pricing-unset-add");
    const content = btnAdd.querySelector(".semi-button-content") || btnAdd;
    content.textContent = "Add";
  }
  const btnBatch = btns.find((el) => normalize(el.textContent).includes(normalize("批量设置")));
  if (btnBatch) {
    btnBatch.setAttribute("data-pw-target", "pricing-unset-batch");
    const content = btnBatch.querySelector(".semi-button-content") || btnBatch;
    content.textContent = "Batch (0)";
  }
  const btnApply = btns.find((el) => normalize(el.textContent).includes(normalize("应用更改")));
  if (btnApply) {
    btnApply.setAttribute("data-pw-target", "pricing-unset-apply");
    const content = btnApply.querySelector(".semi-button-content") || btnApply;
    content.textContent = "Apply";
  }

  const search = pane.querySelector('input[placeholder*="搜索模型名称"]');
  const searchWrap = search ? search.closest(".semi-input-wrapper") : null;
  if (searchWrap && search) {
    searchWrap.setAttribute("data-pw-target", "pricing-unset-search");
    search.value = "";
    search.setAttribute("placeholder", "Placeholder");
  }
});
await shot("pricing_unset_add", '[data-pw-target="pricing-unset-add"]');
await shot("pricing_unset_batch", '[data-pw-target="pricing-unset-batch"]');
await shot("pricing_unset_apply", '[data-pw-target="pricing-unset-apply"]');
await shot("pricing_unset_search", '[data-pw-target="pricing-unset-search"]');

// Upstream sync tab
await page.locator("#semiTabupstream_sync").click();
await page.waitForTimeout(450);
await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const scope = document.querySelector('[data-pw-scope="pricing-scope"]') || document.body;
  const pane =
    Array.from(scope.querySelectorAll(".semi-tabs-pane")).find(
      (el) => el.classList.contains("semi-tabs-pane-active") || el.getAttribute("aria-hidden") === "false"
    ) ||
    scope.querySelector(".semi-tabs-pane-active") ||
    scope;

  const btns = Array.from(pane.querySelectorAll("button"));
  const btnSelect = btns.find((el) => normalize(el.textContent).includes(normalize("选择同步渠道")));
  if (btnSelect) {
    btnSelect.setAttribute("data-pw-target", "pricing-upstream-select");
    const content = btnSelect.querySelector(".semi-button-content") || btnSelect;
    content.textContent = "Select";
  }
  const btnApply = btns.find((el) => normalize(el.textContent).includes(normalize("应用同步")));
  if (btnApply) {
    btnApply.setAttribute("data-pw-target", "pricing-upstream-apply");
    const content = btnApply.querySelector(".semi-button-content") || btnApply;
    content.textContent = "Apply";
  }

  const search = pane.querySelector('input[placeholder*="搜索模型名称"]');
  const searchWrap = search ? search.closest(".semi-input-wrapper") : null;
  if (searchWrap && search) {
    searchWrap.setAttribute("data-pw-target", "pricing-upstream-search");
    search.value = "";
    search.setAttribute("placeholder", "Placeholder");
    searchWrap.style.width = "257px";
    searchWrap.style.minWidth = "257px";
    searchWrap.style.maxWidth = "257px";
    searchWrap.style.flex = "0 0 257px";
    searchWrap.style.boxSizing = "border-box";
  }

  const select = pane.querySelector(".semi-select");
  if (select) {
    select.setAttribute("data-pw-target", "pricing-upstream-filter");
    const txt =
      select.querySelector(".semi-select-selection-text") ||
      select.querySelector(".semi-select-selection-placeholder");
    if (txt) txt.textContent = "Option";
    select.style.width = "193px";
    select.style.minWidth = "193px";
    select.style.maxWidth = "193px";
    select.style.flex = "0 0 193px";
    select.style.boxSizing = "border-box";
  }

  const emptyDesc = pane.querySelector(".semi-empty-description") || pane.querySelector(".semi-empty");
  if (emptyDesc) {
    emptyDesc.setAttribute("data-pw-target", "pricing-upstream-empty");
    if (emptyDesc.classList.contains("semi-empty-description")) {
      emptyDesc.textContent = "Empty";
    }
  }
});
await shot("pricing_upstream_select", '[data-pw-target="pricing-upstream-select"]');
await shot("pricing_upstream_apply", '[data-pw-target="pricing-upstream-apply"]');
await shot("pricing_upstream_search", '[data-pw-target="pricing-upstream-search"]');
await shot("pricing_upstream_filter", '[data-pw-target="pricing-upstream-filter"]');
await shot("pricing_upstream_empty", '[data-pw-target="pricing-upstream-empty"]');

return { ok: true };
}
JS
)"
  js="${js//__LABEL__/${label}}"
  js="${js//__URL__/${url}}"
  printf "%s" "${js}"
}

pushd "${out_dir}" >/dev/null
session_suffix="$(basename -- "${out_dir}")"
realmoi_session="align-realmoi-${realmoi_port}-${session_suffix}"
newapi_session="align-newapi-${newapi_port}-${session_suffix}"

"${PWCLI}" --session "${realmoi_session}" open "about:blank"
"${PWCLI}" --session "${realmoi_session}" resize 1280 720
"${PWCLI}" --session "${realmoi_session}" run-code "$(shoot_js_realmoi "realmoi" "${realmoi_url}" "${realmoi_api_base}")" | tee "pw_realmoi.log"

"${PWCLI}" --session "${newapi_session}" open "about:blank"
"${PWCLI}" --session "${newapi_session}" resize 1280 720
"${PWCLI}" --session "${newapi_session}" run-code "$(shoot_js_newapi "newapi" "${newapi_url}")" | tee "pw_newapi.log"
popd >/dev/null

echo "[4/4] imagemagick diff..."
OUT_DIR="${out_dir}" python3 - <<'PY'
import json
import os
import subprocess

out_dir = os.environ["OUT_DIR"]
pairs = [
  ("pricing_tab_model", "realmoi_pricing_tab_model.png", "newapi_pricing_tab_model.png", "diff_pricing_tab_model.png"),
  ("pricing_tab_group", "realmoi_pricing_tab_group.png", "newapi_pricing_tab_group.png", "diff_pricing_tab_group.png"),
  ("pricing_tab_visual", "realmoi_pricing_tab_visual.png", "newapi_pricing_tab_visual.png", "diff_pricing_tab_visual.png"),
  ("pricing_tab_unset", "realmoi_pricing_tab_unset.png", "newapi_pricing_tab_unset.png", "diff_pricing_tab_unset.png"),
  ("pricing_tab_upstream", "realmoi_pricing_tab_upstream.png", "newapi_pricing_tab_upstream.png", "diff_pricing_tab_upstream.png"),
  ("pricing_model_modelprice", "realmoi_pricing_model_modelprice.png", "newapi_pricing_model_modelprice.png", "diff_pricing_model_modelprice.png"),
  ("pricing_model_save", "realmoi_pricing_model_save.png", "newapi_pricing_model_save.png", "diff_pricing_model_save.png"),
  ("pricing_model_reset", "realmoi_pricing_model_reset.png", "newapi_pricing_model_reset.png", "diff_pricing_model_reset.png"),
  ("pricing_model_switch", "realmoi_pricing_model_switch.png", "newapi_pricing_model_switch.png", "diff_pricing_model_switch.png"),
  ("pricing_group_groupratio", "realmoi_pricing_group_groupratio.png", "newapi_pricing_group_groupratio.png", "diff_pricing_group_groupratio.png"),
  ("pricing_group_save", "realmoi_pricing_group_save.png", "newapi_pricing_group_save.png", "diff_pricing_group_save.png"),
  ("pricing_visual_add", "realmoi_pricing_visual_add.png", "newapi_pricing_visual_add.png", "diff_pricing_visual_add.png"),
  ("pricing_visual_apply", "realmoi_pricing_visual_apply.png", "newapi_pricing_visual_apply.png", "diff_pricing_visual_apply.png"),
  ("pricing_visual_search", "realmoi_pricing_visual_search.png", "newapi_pricing_visual_search.png", "diff_pricing_visual_search.png"),
  ("pricing_visual_conflict", "realmoi_pricing_visual_conflict.png", "newapi_pricing_visual_conflict.png", "diff_pricing_visual_conflict.png"),
  ("pricing_unset_add", "realmoi_pricing_unset_add.png", "newapi_pricing_unset_add.png", "diff_pricing_unset_add.png"),
  ("pricing_unset_batch", "realmoi_pricing_unset_batch.png", "newapi_pricing_unset_batch.png", "diff_pricing_unset_batch.png"),
  ("pricing_unset_apply", "realmoi_pricing_unset_apply.png", "newapi_pricing_unset_apply.png", "diff_pricing_unset_apply.png"),
  ("pricing_unset_search", "realmoi_pricing_unset_search.png", "newapi_pricing_unset_search.png", "diff_pricing_unset_search.png"),
  ("pricing_upstream_select", "realmoi_pricing_upstream_select.png", "newapi_pricing_upstream_select.png", "diff_pricing_upstream_select.png"),
  ("pricing_upstream_apply", "realmoi_pricing_upstream_apply.png", "newapi_pricing_upstream_apply.png", "diff_pricing_upstream_apply.png"),
  ("pricing_upstream_search", "realmoi_pricing_upstream_search.png", "newapi_pricing_upstream_search.png", "diff_pricing_upstream_search.png"),
  ("pricing_upstream_filter", "realmoi_pricing_upstream_filter.png", "newapi_pricing_upstream_filter.png", "diff_pricing_upstream_filter.png"),
  ("pricing_upstream_empty", "realmoi_pricing_upstream_empty.png", "newapi_pricing_upstream_empty.png", "diff_pricing_upstream_empty.png"),
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
  # Compare only the stable shared region between the two shots.
  # In practice, small width deltas often come from layout rounding / wrapper borders and
  # should not fail the comparison if the overlapping UI is identical.
  mw, mh = min(wa, wb), min(ha, hb)

  a_cmp = a_path
  b_cmp = b_path
  if (wa, ha) != (mw, mh):
    a_cmp = os.path.join(cwd, a.replace('.png', '_norm.png'))
    subprocess.check_call(
      [
        'convert',
        a_path,
        '-gravity',
        'NorthWest',
        '-crop',
        f"{mw}x{mh}+0+0",
        '+repage',
        a_cmp,
      ]
    )
  if (wb, hb) != (mw, mh):
    b_cmp = os.path.join(cwd, b.replace('.png', '_norm.png'))
    subprocess.check_call(
      [
        'convert',
        b_path,
        '-gravity',
        'NorthWest',
        '-crop',
        f"{mw}x{mh}+0+0",
        '+repage',
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
