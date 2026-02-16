import fs from "node:fs";
import path from "node:path";

export type AuditStatus = "ok" | "error" | "skipped";

export type ElementRef = {
  tag: string;
  id: string | null;
  className: string | null;
  text: string | null;
};

export type OverflowOffender = {
  tag: string;
  id: string | null;
  className: string | null;
  text: string | null;
  overflowRightPx: number;
  overflowLeftPx: number;
};

export type ClipOffender = {
  el: ElementRef;
  clipBy: ElementRef;
  clipLeftPx: number;
  clipRightPx: number;
  clipTopPx: number;
  clipBottomPx: number;
};

export type OccludedOffender = {
  el: ElementRef;
  at: { x: number; y: number };
  top: ElementRef;
};

export type OverlapOffender = {
  a: ElementRef;
  b: ElementRef;
  intersectionAreaPx: number;
};

export type MisalignedButtonRowOffender = {
  container: ElementRef;
  buttonCount: number;
  deltaTopPx: number;
  deltaHeightPx: number;
  sampleTexts: string[];
};

export type TextTruncationOffender = {
  el: ElementRef;
  clientWidth: number;
  scrollWidth: number;
};

export type LayoutMetrics = {
  viewportWidth: number;
  viewportHeight: number;
  clientWidth: number;
  scrollWidth: number;
  clientHeight: number;
  scrollHeight: number;
  horizontalOverflowPx: number;
  offenders: OverflowOffender[];
  clipped: ClipOffender[];
  occluded: OccludedOffender[];
  overlaps: OverlapOffender[];
  misalignedButtonRows: MisalignedButtonRowOffender[];
  textTruncations: TextTruncationOffender[];
};

export type AuditScreenshots = {
  viewport: string;
  fullPage: string;
};

export type AuditRecord = {
  ts: string;
  project: string;
  routePattern: string;
  routeResolved: string | null;
  url: string | null;
  finalUrl: string | null;
  status: AuditStatus;
  reason?: string;
  durationMs?: number;
  metrics?: LayoutMetrics;
  screenshots?: AuditScreenshots;
  error?: string;
};

function ensureDir(dirPath: string) {
  fs.mkdirSync(dirPath, { recursive: true });
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
  fs.appendFileSync(jsonlPath, JSON.stringify(record) + "\n", "utf8");
}

export function readJsonl<T>(filePath: string): T[] {
  if (!fs.existsSync(filePath)) return [];
  const raw = fs.readFileSync(filePath, "utf8");
  const lines = raw.split(/\r?\n/).filter(Boolean);
  const out: T[] = [];
  for (const line of lines) {
    try {
      out.push(JSON.parse(line) as T);
    } catch {
      // ignore
    }
  }
  return out;
}

function groupBy<T>(items: T[], keyFn: (item: T) => string): Record<string, T[]> {
  const map: Record<string, T[]> = {};
  for (const item of items) {
    const k = keyFn(item);
    (map[k] ||= []).push(item);
  }
  return map;
}

function escapeMd(text: string): string {
  return text.replaceAll("|", "\\|");
}

function formatElementCompact(el: ElementRef): string {
  const id = el.id ? `#${el.id}` : "";
  const cls = el.className ? `.${el.className.split(/\s+/)[0]}` : "";
  return `${el.tag}${id}${cls}`;
}

export function renderMarkdown(records: AuditRecord[], opts: { baseURL: string; outDir: string }): string {
  const now = new Date().toISOString();
  const total = records.length;
  const ok = records.filter((r) => r.status === "ok").length;
  const skipped = records.filter((r) => r.status === "skipped").length;
  const error = records.filter((r) => r.status === "error").length;

  const overflow = records.filter((r) => (r.metrics?.horizontalOverflowPx || 0) > 0);
  const clipped = records.filter((r) => (r.metrics?.clipped || []).length > 0);
  const occluded = records.filter((r) => (r.metrics?.occluded || []).length > 0);
  const overlaps = records.filter((r) => (r.metrics?.overlaps || []).length > 0);
  const misalignedRows = records.filter((r) => (r.metrics?.misalignedButtonRows || []).length > 0);
  const truncations = records.filter((r) => (r.metrics?.textTruncations || []).length > 0);

  const byRoute = groupBy(records, (r) => r.routePattern);
  const routeKeys = Object.keys(byRoute).sort((a, b) => a.localeCompare(b));

  const lines: string[] = [];
  lines.push(`# UI 巡检报告（Playwright）`);
  lines.push("");
  lines.push(`- 生成时间: ${now}`);
  lines.push(`- Base URL: ${opts.baseURL}`);
  lines.push(`- 输出目录: ${opts.outDir}`);
  lines.push("");
  lines.push("## 摘要");
  lines.push("");
  lines.push(`- 总记录: ${total}`);
  lines.push(`- ✅ ok: ${ok}`);
  lines.push(`- ⚠️ skipped: ${skipped}`);
  lines.push(`- ❌ error: ${error}`);
  lines.push(`- 发现水平溢出: ${overflow.length}`);
  lines.push(`- 发现 overflow 裁切: ${clipped.length}`);
  lines.push(`- 发现点击目标被遮挡: ${occluded.length}`);
  lines.push(`- 发现点击目标重叠: ${overlaps.length}`);
  lines.push(`- 发现按钮行不对齐: ${misalignedRows.length}`);
  lines.push(`- 发现文本截断: ${truncations.length}`);
  lines.push("");

  if (error > 0) {
    lines.push("## 错误列表");
    lines.push("");
    lines.push("| 页面 | 视口 | 错误 |");
    lines.push("|---|---|---|");
    for (const r of records.filter((x) => x.status === "error")) {
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${escapeMd(r.error || r.reason || "unknown")} |`
      );
    }
    lines.push("");
  }

  if (overflow.length > 0) {
    lines.push("## 水平溢出（疑似布局问题）");
    lines.push("");
    lines.push("| 页面 | 视口 | 溢出(px) | offenders(Top) | 截图 |");
    lines.push("|---|---:|---:|---|---|");
    const rows = overflow
      .slice()
      .sort(
        (a, b) =>
          (b.metrics?.horizontalOverflowPx || 0) - (a.metrics?.horizontalOverflowPx || 0)
      );
    for (const r of rows) {
      const offenders = (r.metrics?.offenders || [])
        .slice(0, 3)
        .map((o) => `${o.tag}${o.id ? `#${o.id}` : ""}`)
        .join(", ");
      const shots = r.screenshots
        ? `\`${escapeMd(r.screenshots.viewport)}\` / \`${escapeMd(r.screenshots.fullPage)}\``
        : "-";
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${r.metrics?.horizontalOverflowPx || 0} | ${escapeMd(
          offenders || "-"
        )} | ${shots} |`
      );
    }
    lines.push("");
  }

  if (clipped.length > 0) {
    lines.push("## overflow 裁切（overflow:hidden/clip）");
    lines.push("");
    lines.push("| 页面 | 视口 | 发现 | Top | 截图 |");
    lines.push("|---|---:|---:|---|---|");
    const rows = clipped
      .slice()
      .sort((a, b) => (b.metrics?.clipped?.length || 0) - (a.metrics?.clipped?.length || 0));
    for (const r of rows) {
      const top = (r.metrics?.clipped || [])
        .slice(0, 3)
        .map((o) => `${formatElementCompact(o.el)} <= ${formatElementCompact(o.clipBy)}`)
        .join(", ");
      const shots = r.screenshots
        ? `\`${escapeMd(r.screenshots.viewport)}\` / \`${escapeMd(r.screenshots.fullPage)}\``
        : "-";
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${(r.metrics?.clipped || []).length} | ${escapeMd(
          top || "-"
        )} | ${shots} |`
      );
    }
    lines.push("");
  }

  if (occluded.length > 0) {
    lines.push("## 点击目标被遮挡（elementFromPoint）");
    lines.push("");
    lines.push("| 页面 | 视口 | 发现 | Top | 截图 |");
    lines.push("|---|---:|---:|---|---|");
    const rows = occluded
      .slice()
      .sort((a, b) => (b.metrics?.occluded?.length || 0) - (a.metrics?.occluded?.length || 0));
    for (const r of rows) {
      const top = (r.metrics?.occluded || [])
        .slice(0, 3)
        .map((o) => `${formatElementCompact(o.el)} <= ${formatElementCompact(o.top)}`)
        .join(", ");
      const shots = r.screenshots
        ? `\`${escapeMd(r.screenshots.viewport)}\` / \`${escapeMd(r.screenshots.fullPage)}\``
        : "-";
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${(r.metrics?.occluded || []).length} | ${escapeMd(
          top || "-"
        )} | ${shots} |`
      );
    }
    lines.push("");
  }

  if (overlaps.length > 0) {
    lines.push("## 点击目标重叠（点击热区交叠）");
    lines.push("");
    lines.push("| 页面 | 视口 | 发现 | Top | 截图 |");
    lines.push("|---|---:|---:|---|---|");
    const rows = overlaps
      .slice()
      .sort((a, b) => (b.metrics?.overlaps?.length || 0) - (a.metrics?.overlaps?.length || 0));
    for (const r of rows) {
      const top = (r.metrics?.overlaps || [])
        .slice(0, 3)
        .map((o) => `${formatElementCompact(o.a)} x ${formatElementCompact(o.b)} (${o.intersectionAreaPx})`)
        .join(", ");
      const shots = r.screenshots
        ? `\`${escapeMd(r.screenshots.viewport)}\` / \`${escapeMd(r.screenshots.fullPage)}\``
        : "-";
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${(r.metrics?.overlaps || []).length} | ${escapeMd(
          top || "-"
        )} | ${shots} |`
      );
    }
    lines.push("");
  }

  if (misalignedRows.length > 0) {
    lines.push("## 按钮行不对齐（flex row）");
    lines.push("");
    lines.push("| 页面 | 视口 | 发现 | Top | 截图 |");
    lines.push("|---|---:|---:|---|---|");
    const rows = misalignedRows
      .slice()
      .sort(
        (a, b) =>
          (b.metrics?.misalignedButtonRows?.length || 0) - (a.metrics?.misalignedButtonRows?.length || 0)
      );
    for (const r of rows) {
      const top = (r.metrics?.misalignedButtonRows || [])
        .slice(0, 2)
        .map((o) => `${formatElementCompact(o.container)} Δtop=${o.deltaTopPx}, Δh=${o.deltaHeightPx}`)
        .join(", ");
      const shots = r.screenshots
        ? `\`${escapeMd(r.screenshots.viewport)}\` / \`${escapeMd(r.screenshots.fullPage)}\``
        : "-";
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${(r.metrics?.misalignedButtonRows || []).length} | ${escapeMd(
          top || "-"
        )} | ${shots} |`
      );
    }
    lines.push("");
  }

  if (truncations.length > 0) {
    lines.push("## 文本截断（scrollWidth > clientWidth）");
    lines.push("");
    lines.push("| 页面 | 视口 | 发现 | Top | 截图 |");
    lines.push("|---|---:|---:|---|---|");
    const rows = truncations
      .slice()
      .sort((a, b) => (b.metrics?.textTruncations?.length || 0) - (a.metrics?.textTruncations?.length || 0));
    for (const r of rows) {
      const top = (r.metrics?.textTruncations || [])
        .slice(0, 3)
        .map((o) => `${formatElementCompact(o.el)} (${o.clientWidth}/${o.scrollWidth})`)
        .join(", ");
      const shots = r.screenshots
        ? `\`${escapeMd(r.screenshots.viewport)}\` / \`${escapeMd(r.screenshots.fullPage)}\``
        : "-";
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${(r.metrics?.textTruncations || []).length} | ${escapeMd(
          top || "-"
        )} | ${shots} |`
      );
    }
    lines.push("");
  }

  lines.push("## 全量索引");
  lines.push("");
  lines.push("| 页面 | 视口 | 状态 | 最终URL | 指标 | 截图 |");
  lines.push("|---|---:|---|---|---|---|");

  for (const route of routeKeys) {
    const items = byRoute[route] || [];
    items.sort((a, b) => a.project.localeCompare(b.project));
    for (const r of items) {
      const status =
        r.status === "ok" ? "✅ ok" : r.status === "skipped" ? "⚠️ skipped" : "❌ error";
      const metrics = r.metrics
        ? `w:${r.metrics.clientWidth}/${r.metrics.scrollWidth}, hOverflow:${r.metrics.horizontalOverflowPx}, clip:${r.metrics.clipped.length}, occ:${r.metrics.occluded.length}, ovlp:${r.metrics.overlaps.length}`
        : "-";
      const shots = r.screenshots
        ? `\`${escapeMd(r.screenshots.viewport)}\` / \`${escapeMd(r.screenshots.fullPage)}\``
        : "-";
      lines.push(
        `| \`${escapeMd(r.routePattern)}\` | \`${escapeMd(r.project)}\` | ${status} | ${escapeMd(
          r.finalUrl || r.url || "-"
        )} | ${escapeMd(metrics)} | ${shots} |`
      );
    }
  }

  lines.push("");
  lines.push("## 说明");
  lines.push("");
  lines.push("- 本报告用于“先巡检后修复”的流程（你选择的 B）。");
  lines.push("- `水平溢出` 仅是自动检测信号，仍需结合截图人工确认。");
  lines.push("- 动态路由（如 `/jobs/[jobId]`）在缺少参数时会标记为 skipped，并给出补齐方式。");
  lines.push("");
  return lines.join("\n");
}
