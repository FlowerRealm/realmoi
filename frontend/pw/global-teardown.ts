import fs from "node:fs";
import path from "node:path";

import { getOutDir, getReportJsonlPath, readJsonl, renderMarkdown, type AuditRecord } from "./report";

export default async function globalTeardown() {
  let outDir: string;
  try {
    outDir = getOutDir();
  } catch {
    return;
  }
  const jsonlPath = getReportJsonlPath(outDir);
  const records = readJsonl<AuditRecord>(jsonlPath);
  if (records.length === 0) return;

  const baseURL = process.env.REALMOI_PW_BASE_URL?.trim() || "";
  const md = renderMarkdown(records, { baseURL, outDir });
  fs.writeFileSync(path.join(outDir, "report.md"), md, "utf8");
}

