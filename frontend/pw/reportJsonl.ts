import fs from "node:fs";
import path from "node:path";

import type { AuditRecord } from "./reportTypes";

// JSONL I/O helpers for UI audit reporting.
// - append-only write (`report.jsonl`)
// - tolerant reads (ignore partial last line)

function ensureDir(dirPath: string): void {
  try {
    fs.mkdirSync(dirPath, { recursive: true });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`[pw-report] ensureDir failed: ${dirPath}: ${msg}`);
  }
}

export function getOutDir(): string {
  const outDir = process.env.REALMOI_PW_OUT_DIR?.trim();
  if (!outDir) {
    throw new Error("missing_env_REALMOI_PW_OUT_DIR");
  }
  return path.resolve(outDir);
}

export function getReportJsonlPath(outDir: string): string {
  return path.join(outDir, "report.jsonl");
}

export function appendRecord(outDir: string, record: AuditRecord) {
  ensureDir(outDir);
  const jsonlPath = getReportJsonlPath(outDir);
  try {
    fs.appendFileSync(jsonlPath, JSON.stringify(record) + "\n", "utf8");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`[pw-report] appendRecord failed: ${jsonlPath}: ${msg}`);
  }
}

export function readJsonl<T>(filePath: string): T[] {
  let raw = "";
  try {
    raw = fs.readFileSync(filePath, "utf8");
  } catch (err: unknown) {
    if (err && typeof err === "object" && "code" in err && (err as { code?: unknown }).code === "ENOENT") {
      return [];
    }
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`[pw-report] readJsonl failed: ${filePath}: ${msg}`);
  }
  const lines = raw.split(/\r?\n/).filter(Boolean);
  const out: T[] = [];
  let ignored = 0;
  let firstErrorMessage: string | null = null;

  for (const line of lines) {
    try {
      out.push(JSON.parse(line) as T);
    } catch (err: unknown) {
      // report.jsonl is append-only; a partial last line is safe to ignore.
      ignored += 1;
      if (!firstErrorMessage) {
        firstErrorMessage = err instanceof Error ? err.message : String(err);
      }
    }
  }
  if (ignored > 0) {
    // Best-effort signal; callers may run this in CI.
    // eslint-disable-next-line no-console
    console.warn(
      `[pw-report] ignored ${ignored} invalid jsonl line(s) in ${filePath}. first_error=${firstErrorMessage || "unknown"}`
    );
  }
  return out;
}
