#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

out_dir="${1:-"${repo_root}/output/playwright/$(date +%Y%m%d)_align-new-api_login"}"
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

echo "[0/4] ensure realmoi dev cache fresh..."
ts="$(date +%Y%m%d_%H%M%S)"
realmoi_next_dev_dir="${repo_root}/frontend/.next/dev"
if [[ -d "${realmoi_next_dev_dir}/cache/turbopack" ]]; then
  mv "${realmoi_next_dev_dir}/cache/turbopack" "${realmoi_next_dev_dir}/cache/turbopack.bak_${ts}" || true
fi
if [[ -d "${realmoi_next_dev_dir}/static/chunks" ]]; then
  mv "${realmoi_next_dev_dir}/static/chunks" "${realmoi_next_dev_dir}/static/chunks.bak_${ts}" || true
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

realmoi_login_url="http://localhost:${realmoi_port}/login"
newapi_login_url="http://localhost:${newapi_port}/login"

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
wait_url "${realmoi_login_url}" "realmoi"
wait_url "${newapi_login_url}" "new-api"

echo "[3/4] playwright screenshots..."
export CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
export PWCLI="${CODEX_HOME}/skills/playwright/scripts/playwright_cli.sh"

if ! command -v npx >/dev/null 2>&1; then
  echo "Error: npx is required but not found on PATH." >&2
  exit 1
fi

shoot_js_for() {
  local label="$1"
  local url="$2"
  local js
  js="$(cat <<'JS'
async (page) => {
const label = "__LABEL__";
const url = "__URL__";

// Stabilize new-api login: stub status API to avoid error banners/toasts.
if (label === "newapi") {
  await page.addInitScript(() => {
    try { localStorage.setItem("i18nextLng", "zh"); } catch {}
  });

  await page.route("**/api/status", async (route) => {
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/json; charset=utf-8" },
      body: JSON.stringify({ success: true, data: { system_name: "Realm OI", logo: "/favicon.ico", footer_html: "", quota_per_unit: 500000, display_in_currency: false, quota_display_type: "USD", enable_drawing: false, enable_task: false, enable_data_export: false, chats: [], data_export_default_time: "7", default_collapse_sidebar: false, mj_notify_enabled: false, docs_link: "", HeaderNavModules: null, turnstile_check: false, user_agreement_enabled: false, privacy_policy_enabled: false } }),
    });
  });
}

await page.goto(url, { waitUntil: 'domcontentloaded' });
await page.waitForTimeout(800);

// Wait for global CSS (Tailwind + globals.css) to apply in Next dev.
await page.waitForFunction(() => getComputedStyle(document.body).margin === "0px", null, { timeout: 8000 }).catch(() => {});

await page.evaluate(() => {
  const el = document.activeElement;
  if (el && typeof el.blur === "function") el.blur();
});

await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\s+/g, "");
  const card = document.querySelector(".semi-card");
  const titleEl = card
    ? Array.from(
        card.querySelectorAll(
          ".semi-typography-h1, .semi-typography-h2, .semi-typography-h3, h1, h2, h3",
        ),
      ).find((el) => normalize(el.textContent) === normalize("登 录"))
    : null;
  if (titleEl) titleEl.setAttribute("data-pw-target", "login-title");

  const wrappers = card ? Array.from(card.querySelectorAll(".semi-input-wrapper")) : [];
  const usernameWrapper = wrappers[0] || null;
  const passwordWrapper = wrappers[1] || null;
  const usernameInput = usernameWrapper ? usernameWrapper.querySelector("input") : null;
  const passwordInput = passwordWrapper ? passwordWrapper.querySelector("input") : null;
  if (usernameInput) usernameInput.setAttribute("data-pw-target", "login-username-input");
  if (passwordInput) passwordInput.setAttribute("data-pw-target", "login-password-input");

  const btnEl = card
    ? Array.from(card.querySelectorAll("button")).find(
        (el) => normalize(el.textContent) === normalize("继续"),
      )
    : null;
  if (btnEl) btnEl.setAttribute("data-pw-target", "login-continue");

  const forgotEl = card
    ? Array.from(card.querySelectorAll("button")).find(
        (el) => normalize(el.textContent) === normalize("忘记密码？"),
      )
    : null;
  if (forgotEl) forgotEl.setAttribute("data-pw-target", "login-forgot");

  const registerEl = card
    ? Array.from(card.querySelectorAll("a")).find(
        (el) => normalize(el.textContent) === normalize("注册"),
      )
    : null;
  if (registerEl) registerEl.setAttribute("data-pw-target", "login-register");

  const shell = document.querySelector("div.relative.overflow-hidden");
  if (shell) shell.setAttribute("data-pw-target", "login-shell");
});

await page.addStyleTag({
  content: `
    *, *::before, *::after { animation: none !important; transition: none !important; }
    .semi-toast, .semi-toast-wrapper, .semi-notification, .semi-notification-list { display: none !important; }
    input:-webkit-autofill, textarea:-webkit-autofill, select:-webkit-autofill {
      box-shadow: 0 0 0px 1000px transparent inset !important;
      -webkit-text-fill-color: inherit !important;
      transition: background-color 9999s ease-in-out 0s !important;
    }
  `,
});

await page.evaluate(async () => {
  if (!document.fonts || !document.fonts.ready) return;
  try {
    await document.fonts.ready;
  } catch {}
});
await page.waitForTimeout(300);

// Ensure realmoi auth body class is applied (Next hydration)
if (label === "realmoi") {
  await page
    .waitForFunction(() => document.body.classList.contains("newapi-auth"), null, {
      timeout: 8000,
    })
    .catch(() => {});
}

await page.screenshot({ path: `${label}_login.png` });

const card = page.locator('.semi-card').first();
await card.waitFor({ state: 'visible', timeout: 15000 });
await card.scrollIntoViewIfNeeded();
await card.screenshot({ path: `${label}_login_card.png` });

const cardBox = await card.boundingBox();
if (cardBox) {
  const wTop = 64;
  const hTop = 64;
  const wBottom = 24;
  const hBottom = 24;
  const topInset = 1;
  await page.screenshot({
    path: `${label}_login_card_topleft.png`,
    clip: {
      x: cardBox.x,
      y: cardBox.y + topInset,
      width: wTop,
      height: hTop - topInset,
    },
  });
  await page.screenshot({
    path: `${label}_login_card_topright.png`,
    clip: {
      x: cardBox.x + cardBox.width - wTop,
      y: cardBox.y + topInset,
      width: wTop,
      height: hTop - topInset,
    },
  });
  await page.screenshot({
    path: `${label}_login_card_bottomleft.png`,
    clip: {
      x: cardBox.x,
      y: cardBox.y + cardBox.height - hBottom,
      width: wBottom,
      height: hBottom,
    },
  });
  await page.screenshot({
    path: `${label}_login_card_bottomright.png`,
    clip: {
      x: cardBox.x + cardBox.width - wBottom,
      y: cardBox.y + cardBox.height - hBottom,
      width: wBottom,
      height: hBottom,
    },
  });
}

const title = page.locator('[data-pw-target="login-title"]').first();
await title.waitFor({ state: 'visible', timeout: 15000 });
await title.screenshot({ path: `${label}_login_title.png`, timeout: 15000 });

const wrappers = card.locator('.semi-input-wrapper');
await wrappers.nth(0).screenshot({ path: `${label}_login_username_wrapper.png` });
await wrappers.nth(1).screenshot({ path: `${label}_login_password_wrapper.png` });

const btnContinue = page.locator('[data-pw-target="login-continue"]').first();
await btnContinue.screenshot({ path: `${label}_login_btn_continue.png`, timeout: 15000 });

const btnForgot = page.locator('[data-pw-target="login-forgot"]').first();
await btnForgot.waitFor({ state: 'visible', timeout: 15000 });
await btnForgot.screenshot({ path: `${label}_login_btn_forgot.png`, timeout: 15000 });

const linkRegister = page.locator('[data-pw-target="login-register"]').first();
await linkRegister.waitFor({ state: 'visible', timeout: 15000 });
await linkRegister.screenshot({ path: `${label}_login_register_link.png`, timeout: 15000 });

const dump = await page.evaluate(() => {
  const normalize = (s) => String(s || "").replace(/\\s+/g, "");
  const rectOf = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return { x: r.x, y: r.y, width: r.width, height: r.height };
  };
  const styleOf = (el) => {
    if (!el) return null;
    const s = getComputedStyle(el);
    return {
      tag: el.tagName.toLowerCase(),
      className: el.className || "",
      text: (el.textContent || "").trim(),
      rect: rectOf(el),
      fontFamily: s.fontFamily,
      fontSize: s.fontSize,
      fontWeight: s.fontWeight,
      lineHeight: s.lineHeight,
      letterSpacing: s.letterSpacing,
      textRendering: s.textRendering,
      webkitFontSmoothing: s.getPropertyValue("-webkit-font-smoothing"),
      mozOsxFontSmoothing: s.getPropertyValue("-moz-osx-font-smoothing"),
      fontFeatureSettings: s.fontFeatureSettings,
      fontKerning: s.fontKerning,
      fontOpticalSizing: s.fontOpticalSizing,
      fontVariationSettings: s.fontVariationSettings,
      fontSynthesis: s.fontSynthesis,
      color: s.color,
      backgroundColor: s.backgroundColor,
      borderColor: s.borderColor,
      borderRadius: s.borderRadius,
      borderWidth: s.borderWidth,
      borderStyle: s.borderStyle,
      boxShadow: s.boxShadow,
      transform: s.transform,
      filter: s.filter,
      backdropFilter: s.backdropFilter,
      opacity: s.opacity,
      padding: s.padding,
      margin: s.margin,
      height: s.height,
      width: s.width,
      display: s.display,
    };
  };
  const allStyleOf = (el) => {
    if (!el) return null;
    const s = getComputedStyle(el);
    const out = {};
    for (let i = 0; i < s.length; i += 1) {
      const key = s[i];
      out[key] = s.getPropertyValue(key);
    }
    return out;
  };
  const ancestorChainOf = (el) => {
    if (!el) return null;
    const out = [];
    let cur = el;
    while (cur) {
      const s = getComputedStyle(cur);
      out.push({
        tag: cur.tagName ? cur.tagName.toLowerCase() : "",
        id: cur.id || "",
        className: cur.className || "",
        transform: s.transform,
        filter: s.filter,
        backdropFilter: s.backdropFilter,
        opacity: s.opacity,
        willChange: s.willChange,
        position: s.position,
        zIndex: s.zIndex,
        isolation: s.isolation,
        contain: s.contain,
        mixBlendMode: s.mixBlendMode,
      });
      cur = cur.parentElement;
    }
    return out;
  };
  const placeholderOf = (inputEl) => {
    if (!inputEl) return null;
    const p = getComputedStyle(inputEl, "::placeholder");
    return {
      color: p.color,
      opacity: p.opacity,
      fontFamily: p.fontFamily,
      fontSize: p.fontSize,
      fontWeight: p.fontWeight,
      lineHeight: p.lineHeight,
      letterSpacing: p.letterSpacing,
      textRendering: p.textRendering,
      webkitFontSmoothing: p.getPropertyValue("-webkit-font-smoothing"),
      mozOsxFontSmoothing: p.getPropertyValue("-moz-osx-font-smoothing"),
      fontFeatureSettings: p.fontFeatureSettings,
      fontKerning: p.fontKerning,
      fontOpticalSizing: p.fontOpticalSizing,
      fontVariationSettings: p.fontVariationSettings,
      fontSynthesis: p.fontSynthesis,
    };
  };

  const card = document.querySelector(".semi-card");
  const bodyEl = document.body;
  const scopeEl = document.querySelector(".newapi-scope");
  const shellEl = document.querySelector('[data-pw-target="login-shell"]');
  const wrappers = card ? Array.from(card.querySelectorAll(".semi-input-wrapper")) : [];
  const titleEl = document.querySelector('[data-pw-target="login-title"]');
  const btnEl = document.querySelector('[data-pw-target="login-continue"]');

  const usernameWrapper = wrappers[0] || null;
  const passwordWrapper = wrappers[1] || null;
  const usernameInput =
    document.querySelector('[data-pw-target="login-username-input"]') ||
    (usernameWrapper ? usernameWrapper.querySelector("input") : null);
  const passwordInput =
    document.querySelector('[data-pw-target="login-password-input"]') ||
    (passwordWrapper ? passwordWrapper.querySelector("input") : null);

  const fontCheck = (spec) => {
    try {
      if (!document.fonts || !document.fonts.check) return null;
      return document.fonts.check(spec);
    } catch {
      return null;
    }
  };

  const activeEl = document.activeElement;
  const activeInfo = activeEl
    ? {
        tag: activeEl.tagName.toLowerCase(),
        id: activeEl.id || "",
        className: activeEl.className || "",
        name: activeEl.getAttribute ? activeEl.getAttribute("name") : null,
      }
    : null;

  return {
    dpr: window.devicePixelRatio,
    userAgent: navigator.userAgent,
    fontChecks: {
      inter: fontCheck('14px "Inter"'),
      lato: fontCheck('14px "Lato"'),
      geist: fontCheck('14px "Geist"'),
      notoSansSc: fontCheck('14px "Noto Sans SC"'),
      notoSansCjkSc: fontCheck('14px "Noto Sans CJK SC"'),
      microsoftYaHei: fontCheck('14px "Microsoft YaHei"'),
      pingFangSc: fontCheck('14px "PingFang SC"'),
      dejavuSans: fontCheck('14px "DejaVu Sans"'),
    },
    body: styleOf(bodyEl),
    shell: styleOf(shellEl),
    scope: styleOf(scopeEl),
    formValues: {
      usernameValue: usernameInput ? usernameInput.value : null,
      usernamePlaceholder: usernameInput ? usernameInput.getAttribute("placeholder") : null,
      passwordValue: passwordInput ? passwordInput.value : null,
      passwordPlaceholder: passwordInput ? passwordInput.getAttribute("placeholder") : null,
    },
    activeElement: activeInfo,
    card: styleOf(card),
    title: styleOf(titleEl),
    titleAllStyles: allStyleOf(titleEl),
    titleAncestors: ancestorChainOf(titleEl),
    usernameWrapper: styleOf(usernameWrapper),
    usernameInput: styleOf(usernameInput),
    usernamePlaceholder: placeholderOf(usernameInput),
    passwordWrapper: styleOf(passwordWrapper),
    passwordInput: styleOf(passwordInput),
    passwordPlaceholder: placeholderOf(passwordInput),
    continueButton: styleOf(btnEl),
  };
});

try {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("DOM.enable");
  await cdp.send("CSS.enable");
  const { root } = await cdp.send("DOM.getDocument", { depth: -1 });
  const getFontsForSelector = async (selector) => {
    try {
      const { nodeId } = await cdp.send("DOM.querySelector", {
        nodeId: root.nodeId,
        selector,
      });
      if (!nodeId) return null;
      const { fonts } = await cdp.send("CSS.getPlatformFontsForNode", { nodeId });
      return fonts;
    } catch (e) {
      return { error: String(e) };
    }
  };
  dump.platformFonts = {
    shell: await getFontsForSelector('[data-pw-target="login-shell"]'),
    title: await getFontsForSelector('[data-pw-target="login-title"]'),
    usernameInput: await getFontsForSelector('[data-pw-target="login-username-input"]'),
    passwordInput: await getFontsForSelector('[data-pw-target="login-password-input"]'),
    continueButton: await getFontsForSelector('[data-pw-target="login-continue"]'),
  };
} catch (e) {
  dump.platformFonts = { error: String(e) };
}

return dump;
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
"${PWCLI}" --session "align-realmoi-${realmoi_port}" run-code "$(shoot_js_for "realmoi" "${realmoi_login_url}")" | tee "pw_realmoi.log"
extract_result_json "pw_realmoi.log" "realmoi_login_styles.json"

"${PWCLI}" --session "align-newapi-${newapi_port}" open "about:blank"
"${PWCLI}" --session "align-newapi-${newapi_port}" resize 1280 720
"${PWCLI}" --session "align-newapi-${newapi_port}" run-code "$(shoot_js_for "newapi" "${newapi_login_url}")" | tee "pw_newapi.log"
extract_result_json "pw_newapi.log" "newapi_login_styles.json"
popd >/dev/null

echo "[4/4] imagemagick diff..."
OUT_DIR="${out_dir}" python3 - <<'PY'
import json, os, subprocess

out_dir = os.environ["OUT_DIR"]
pairs = [
  ("login_card_topleft", "realmoi_login_card_topleft.png", "newapi_login_card_topleft.png", "diff_login_card_topleft.png"),
  ("login_card_topright", "realmoi_login_card_topright.png", "newapi_login_card_topright.png", "diff_login_card_topright.png"),
  ("login_card_bottomleft", "realmoi_login_card_bottomleft.png", "newapi_login_card_bottomleft.png", "diff_login_card_bottomleft.png"),
  ("login_card_bottomright", "realmoi_login_card_bottomright.png", "newapi_login_card_bottomright.png", "diff_login_card_bottomright.png"),
  ("login_title", "realmoi_login_title.png", "newapi_login_title.png", "diff_login_title.png"),
  ("login_username_wrapper", "realmoi_login_username_wrapper.png", "newapi_login_username_wrapper.png", "diff_login_username_wrapper.png"),
  ("login_password_wrapper", "realmoi_login_password_wrapper.png", "newapi_login_password_wrapper.png", "diff_login_password_wrapper.png"),
  ("login_btn_continue", "realmoi_login_btn_continue.png", "newapi_login_btn_continue.png", "diff_login_btn_continue.png"),
  ("login_btn_forgot", "realmoi_login_btn_forgot.png", "newapi_login_btn_forgot.png", "diff_login_btn_forgot.png"),
  ("login_register_link", "realmoi_login_register_link.png", "newapi_login_register_link.png", "diff_login_register_link.png"),
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
  if (wa, ha) != (wb, hb):
    raise SystemExit(
      f"Size mismatch for {label}: {a}={wa}x{ha} {b}={wb}x{hb}. "
      "Likely a selector mismatch or CSS not applied."
    )
  total = wa * ha
  proc = subprocess.run(
    ["compare", "-metric", "AE", a_path, b_path, out_path],
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
