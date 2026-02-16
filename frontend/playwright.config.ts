import path from "node:path";

import { defineConfig, devices } from "@playwright/test";

function tsStamp(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(
    d.getMinutes()
  )}${pad(d.getSeconds())}`;
}

function resolveOutDir(): string {
  const raw = process.env.REALMOI_PW_OUT_DIR?.trim();
  if (raw) return path.resolve(raw);
  const repoRoot = path.resolve(__dirname, "..");
  return path.join(repoRoot, "output", "playwright", "ui-audit", tsStamp(new Date()));
}

function resolveBaseUrl(): string {
  const raw = process.env.REALMOI_PW_BASE_URL?.trim();
  if (raw) return raw.replace(/\/$/, "");
  const port = process.env.REALMOI_FRONTEND_PORT?.trim() || "3000";
  return `http://127.0.0.1:${port}`;
}

const outDir = resolveOutDir();
const baseURL = resolveBaseUrl();
const authFile = path.resolve(__dirname, ".pw", "auth.json");

process.env.REALMOI_PW_OUT_DIR ??= outDir;
process.env.REALMOI_PW_BASE_URL ??= baseURL;
process.env.REALMOI_PW_AUTH_FILE ??= authFile;

export default defineConfig({
  testDir: "./pw",
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  globalSetup: require.resolve("./pw/global-setup"),
  globalTeardown: require.resolve("./pw/global-teardown"),
  use: {
    baseURL,
    storageState: authFile,
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  projects: [
    {
      name: "mobile-360x800",
      use: {
        ...devices["Pixel 5"],
        viewport: { width: 360, height: 800 },
      },
    },
    {
      name: "mobile-390x844",
      use: {
        ...devices["iPhone 13"],
        viewport: { width: 390, height: 844 },
      },
    },
    {
      name: "tablet-768x1024",
      use: {
        viewport: { width: 768, height: 1024 },
        deviceScaleFactor: 1,
        isMobile: false,
        hasTouch: true,
      },
    },
    {
      name: "desktop-1280x720",
      use: {
        viewport: { width: 1280, height: 720 },
      },
    },
    {
      name: "desktop-1440x900",
      use: {
        viewport: { width: 1440, height: 900 },
      },
    },
    {
      name: "desktop-1920x1080",
      use: {
        viewport: { width: 1920, height: 1080 },
      },
    },
  ],
});

