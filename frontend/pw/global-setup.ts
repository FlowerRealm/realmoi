import fs from "node:fs";
import path from "node:path";

import { chromium } from "@playwright/test";

function ensureDir(dirPath: string) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function requiredEnv(name: string, fallback?: string): string {
  const v = process.env[name]?.trim();
  if (v) return v;
  if (fallback !== undefined) return fallback;
  throw new Error(`missing_env_${name}`);
}

export default async function globalSetup() {
  const baseURL = requiredEnv("REALMOI_PW_BASE_URL");
  const authFile =
    process.env.REALMOI_PW_AUTH_FILE?.trim() || path.resolve(__dirname, "..", ".pw", "auth.json");
  ensureDir(path.dirname(authFile));

  const username =
    process.env.REALMOI_PW_USERNAME?.trim() ||
    process.env.REALMOI_ADMIN_USERNAME?.trim() ||
    "admin";
  const password =
    process.env.REALMOI_PW_PASSWORD?.trim() ||
    process.env.REALMOI_ADMIN_PASSWORD?.trim() ||
    "admin-password-123";

  const browser = await chromium.launch();
  const context = await browser.newContext({ baseURL });
  const page = await context.newPage();

  await page.goto("/login", { waitUntil: "domcontentloaded" });

  await page.locator('input[name="username"]').fill(username);
  await page.locator('input[name="password"]').fill(password);

  await Promise.all([
    page.waitForFunction(() => Boolean(localStorage.getItem("realmoi_token")), null, {
      timeout: 15_000,
    }),
    page.getByRole("button", { name: "继续" }).click(),
  ]);

  const token = await page.evaluate(() => localStorage.getItem("realmoi_token"));
  if (!token) {
    throw new Error("login_failed_no_token");
  }

  const expectedRole = process.env.REALMOI_PW_EXPECT_ROLE?.trim() || "admin";
  if (expectedRole) {
    const apiBaseRaw = process.env.REALMOI_PW_API_BASE_URL?.trim();
    if (apiBaseRaw) {
      const apiBase = apiBaseRaw.replace(/\/$/, "");
      const me = await page.evaluate(
        async ({ apiBase, token }) => {
          const resp = await fetch(`${apiBase}/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (!resp.ok) return null;
          return (await resp.json()) as { role?: unknown } | null;
        },
        { apiBase, token }
      );
      const role = me && typeof me.role === "string" ? me.role : "";
      if (role !== expectedRole) {
        throw new Error(`login_role_mismatch(expected=${expectedRole}, actual=${role || "unknown"})`);
      }
    } else if (expectedRole === "admin") {
      await page.goto("/admin/users", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(800);
      const pathname = new URL(page.url()).pathname;
      if (pathname !== "/admin/users") {
        throw new Error("login_role_mismatch(expected=admin, actual=non-admin)");
      }
    }
  }

  await context.storageState({ path: authFile });
  await browser.close();
}
