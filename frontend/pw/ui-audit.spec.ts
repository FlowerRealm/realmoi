import fs from "node:fs";
import path from "node:path";

import { test } from "@playwright/test";

import { collectLayoutMetrics } from "./audit-metrics";
import { appendRecord, getOutDir, type AuditRecord } from "./report";
import { discoverRoutes, hasDynamicSegments, slugFromRoute } from "./routes";

type PwPage = import("@playwright/test").Page;
type ScreenshotOptions = Parameters<PwPage["screenshot"]>[0];

function ensureDir(dirPath: string) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function isoNow(): string {
  return new Date().toISOString();
}

function normalizeApiBase(raw: string): string {
  return raw.replace(/\/$/, "");
}

function normalizePathname(p: string): string {
  if (p.length > 1 && p.endsWith("/")) return p.slice(0, -1);
  return p;
}

async function screenshotWithRetry(page: PwPage, opts: ScreenshotOptions & { path: string }): Promise<void> {
  let lastErr: unknown = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await page.screenshot({ timeout: 20_000, ...opts });
      return;
    } catch (e: unknown) {
      lastErr = e;
      await page.waitForTimeout(250);
    }
  }
  throw lastErr;
}

async function resolveJobId(page: PwPage): Promise<string | null> {
  const envJobId = process.env.REALMOI_PW_JOB_ID?.trim();
  if (envJobId) return envJobId;

  const apiBaseRaw = process.env.REALMOI_PW_API_BASE_URL?.trim();
  if (!apiBaseRaw) return null;
  const apiBase = normalizeApiBase(apiBaseRaw);

  const token = await page.evaluate(() => localStorage.getItem("realmoi_token"));
  if (!token) return null;

  try {
    const resp = await page.request.get(`${apiBase}/jobs`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: 8_000,
    });
    if (!resp.ok()) return null;
    const data = (await resp.json()) as unknown;
    if (!data || typeof data !== "object") return null;
    const items = (data as { items?: unknown }).items;
    if (!Array.isArray(items) || items.length === 0) return null;
    const first = items[0] as { job_id?: unknown };
    const jobId = typeof first?.job_id === "string" ? first.job_id : "";
    return jobId || null;
  } catch {
    return null;
  }
}

async function resolveRoute(page: PwPage, pattern: string): Promise<{ resolved: string | null; reason?: string }> {
  if (!hasDynamicSegments(pattern)) return { resolved: pattern };

  if (pattern === "/jobs/[jobId]") {
    const jobId = await resolveJobId(page);
    if (!jobId) return { resolved: null, reason: "missing_job_id (set REALMOI_PW_JOB_ID or create any job first)" };
    return { resolved: `/jobs/${jobId}` };
  }

  return { resolved: null, reason: "unhandled_dynamic_route" };
}

test("ui-audit", async ({ page }, testInfo) => {
  const outDir = getOutDir();
  const project = testInfo.project.name;

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const style = document.createElement("style");
    style.setAttribute("data-pw", "no-anim");
    style.textContent = `
*,
*::before,
*::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  caret-color: transparent !important;
}

/* Hide Next.js dev overlay (it can occlude UI in screenshots). */
nextjs-portal,
#__nextjs__container,
#nextjs__container,
[data-nextjs-dev-overlay],
[data-nextjs-toast] {
  display: none !important;
}
`;
    document.documentElement.appendChild(style);
  });

  const routes = discoverRoutes();

  const projectShotsDir = path.join(outDir, "screenshots", project);
  ensureDir(projectShotsDir);

  for (const r of routes) {
    const started = Date.now();
    const base: AuditRecord = {
      ts: isoNow(),
      project,
      routePattern: r.pattern,
      routeResolved: null,
      url: null,
      finalUrl: null,
      status: "ok",
      durationMs: 0,
    };

    const { resolved, reason } = await resolveRoute(page, r.pattern);
    if (!resolved) {
      appendRecord(outDir, {
        ...base,
        status: "skipped",
        reason: reason || "skipped",
        durationMs: Date.now() - started,
      });
      continue;
    }

    const slug = slugFromRoute(r.pattern);
    const viewportRel = path.posix.join("screenshots", project, `${slug}.viewport.png`);
    const fullRel = path.posix.join("screenshots", project, `${slug}.full.png`);

    try {
      await page.goto(resolved, { waitUntil: "domcontentloaded", timeout: 25_000 });

      await page.waitForFunction(() => getComputedStyle(document.body).margin === "0px", null, {
        timeout: 8_000,
      }).catch(() => {});

      await page
        .waitForFunction(() => (document.fonts ? document.fonts.status !== "loading" : true), null, {
          timeout: 8_000,
        })
        .catch(() => {});

      await page.waitForTimeout(350);
      await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (el && typeof el.blur === "function") el.blur();
      });

      const metrics = await collectLayoutMetrics(page);

      const expectedPath = normalizePathname(resolved);
      const actualPath = normalizePathname(new URL(page.url()).pathname);
      const redirectAllowed = r.pattern === "/jobs" && actualPath === "/";

      const viewportAbs = path.join(outDir, viewportRel);
      const fullAbs = path.join(outDir, fullRel);
      ensureDir(path.dirname(viewportAbs));

      await screenshotWithRetry(page, { path: viewportAbs, fullPage: false });
      await screenshotWithRetry(page, { path: fullAbs, fullPage: true });

      appendRecord(outDir, {
        ...base,
        routeResolved: resolved,
        url: resolved,
        finalUrl: page.url(),
        status: redirectAllowed || actualPath === expectedPath ? "ok" : "error",
        reason:
          redirectAllowed || actualPath === expectedPath
            ? undefined
            : `unexpected_redirect(expected=${expectedPath}, actual=${actualPath})`,
        durationMs: Date.now() - started,
        metrics,
        screenshots: { viewport: viewportRel, fullPage: fullRel },
      });
    } catch (e: unknown) {
      appendRecord(outDir, {
        ...base,
        routeResolved: resolved,
        url: resolved,
        finalUrl: page.url(),
        status: "error",
        durationMs: Date.now() - started,
        error: e instanceof Error ? e.message : String(e),
        reason: e instanceof Error ? e.name : "error",
      });
    }
  }
});
