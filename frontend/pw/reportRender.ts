import type {
  AuditRecord,
  ClipOffender,
  ElementRef,
  LayoutMetrics,
  MisalignedButtonRowOffender,
  OccludedOffender,
  OverlapOffender,
  OverflowOffender,
  TextTruncationOffender,
} from "./reportTypes";

type RenderOptions = { baseURL: string; outDir: string };

// RenderContext caches derived collections (grouping, counts, buckets) so each
// section renderer can stay small and straightforward.
type RenderContext = {
  nowIso: string;
  records: AuditRecord[];
  opts: RenderOptions;
  byRoute: Record<string, AuditRecord[]>;
  routeKeys: string[];
  counts: {
    total: number;
    ok: number;
    skipped: number;
    error: number;
  };
  buckets: {
    overflow: AuditRecord[];
    clipped: AuditRecord[];
    occluded: AuditRecord[];
    overlaps: AuditRecord[];
    misalignedRows: AuditRecord[];
    truncations: AuditRecord[];
  };
};

// Collection helpers ---------------------------------------------------------

function groupBy<T>(items: T[], keyFn: (item: T) => string): Record<string, T[]> {
  const map: Record<string, T[]> = {};
  for (const item of items) {
    const k = keyFn(item);
    (map[k] ||= []).push(item);
  }
  return map;
}

// Markdown helpers -----------------------------------------------------------

function escapeMd(text: string): string {
  return text.replaceAll("|", "\\|");
}

function formatElementCompact(el: ElementRef): string {
  const id = el.id ? `#${el.id}` : "";
  const cls = el.className ? `.${el.className.split(/\\s+/)[0]}` : "";
  return `${el.tag}${id}${cls}`;
}

// Data prep ------------------------------------------------------------------

function buildRenderContext(records: AuditRecord[], opts: RenderOptions): RenderContext {
  const nowIso = new Date().toISOString();
  const total = records.length;
  const ok = records.filter((r) => r.status === "ok").length;
  const skipped = records.filter((r) => r.status === "skipped").length;
  const error = records.filter((r) => r.status === "error").length;

  const buckets = {
    overflow: records.filter((r) => (r.metrics?.horizontalOverflowPx || 0) > 0),
    clipped: records.filter((r) => (r.metrics?.clipped || []).length > 0),
    occluded: records.filter((r) => (r.metrics?.occluded || []).length > 0),
    overlaps: records.filter((r) => (r.metrics?.overlaps || []).length > 0),
    misalignedRows: records.filter((r) => (r.metrics?.misalignedButtonRows || []).length > 0),
    truncations: records.filter((r) => (r.metrics?.textTruncations || []).length > 0),
  };

  const byRoute = groupBy(records, (r) => r.routePattern);
  const routeKeys = Object.keys(byRoute).sort((a, b) => a.localeCompare(b));

  return {
    nowIso,
    records,
    opts,
    byRoute,
    routeKeys,
    counts: { total, ok, skipped, error },
    buckets,
  };
}

// Sections ------------------------------------------------------------------

function pushHeader(lines: string[], ctx: RenderContext): void {
  lines.push(`# UI 巡检报告（Playwright）`);
  lines.push("");
  lines.push(`- 生成时间: ${ctx.nowIso}`);
  lines.push(`- Base URL: ${ctx.opts.baseURL}`);
  lines.push(`- 输出目录: ${ctx.opts.outDir}`);
  lines.push("");
}

function pushSummary(lines: string[], ctx: RenderContext): void {
  lines.push("## 摘要");
  lines.push("");
  lines.push(`- 总记录: ${ctx.counts.total}`);
  lines.push(`- ✅ ok: ${ctx.counts.ok}`);
  lines.push(`- ⚠️ skipped: ${ctx.counts.skipped}`);
  lines.push(`- ❌ error: ${ctx.counts.error}`);
  lines.push(`- 发现水平溢出: ${ctx.buckets.overflow.length}`);
  lines.push(`- 发现 overflow 裁切: ${ctx.buckets.clipped.length}`);
  lines.push(`- 发现点击目标被遮挡: ${ctx.buckets.occluded.length}`);
  lines.push(`- 发现点击目标重叠: ${ctx.buckets.overlaps.length}`);
  lines.push(`- 发现按钮行不对齐: ${ctx.buckets.misalignedRows.length}`);
  lines.push(`- 发现文本截断: ${ctx.buckets.truncations.length}`);
  lines.push("");
}

function pushErrorList(lines: string[], ctx: RenderContext): void {
  if (ctx.counts.error <= 0) return;
  lines.push("## 错误列表");
  lines.push("");
  lines.push("| 页面 | 视口 | 错误 |");
  lines.push("|---|---|---|");
  for (const r of ctx.records.filter((x) => x.status === "error")) {
    lines.push(
      `| \\`${escapeMd(r.routePattern)}\\` | \\`${escapeMd(r.project)}\\` | ${escapeMd(r.error || r.reason || "unknown")} |`
    );
  }
  lines.push("");
}

function renderShots(record: AuditRecord): string {
  return record.screenshots
    ? `\\`${escapeMd(record.screenshots.viewport)}\\` / \\`${escapeMd(record.screenshots.fullPage)}\\``
    : "-";
}

// Counted sections share a consistent table shape; only the "Top" formatter
// differs per metric family.
type CountedMetricKey =
  | "clipped"
  | "occluded"
  | "overlaps"
  | "misalignedButtonRows"
  | "textTruncations";

type CountedMetricItem =
  | ClipOffender
  | OccludedOffender
  | OverlapOffender
  | MisalignedButtonRowOffender
  | TextTruncationOffender;

function getCountedMetric(metrics: LayoutMetrics | undefined, key: CountedMetricKey): CountedMetricItem[] {
  if (!metrics) return [];
  const value = metrics[key];
  return Array.isArray(value) ? (value as CountedMetricItem[]) : [];
}

function pushCountedSection(args: {
  lines: string[];
  ctx: RenderContext;
  title: string;
  key: CountedMetricKey;
  maxTop: number;
  formatTop: (item: CountedMetricItem) => string;
}): void {
  const { ctx, key, lines, title, maxTop, formatTop } = args;
  const bucket = ctx.records.filter((r) => getCountedMetric(r.metrics, key).length > 0);
  if (bucket.length <= 0) return;

  lines.push(title);
  lines.push("");
  lines.push("| 页面 | 视口 | 发现 | Top | 截图 |");
  lines.push("|---|---:|---:|---|---|");

  const rows = bucket
    .slice()
    .sort((a, b) => getCountedMetric(b.metrics, key).length - getCountedMetric(a.metrics, key).length);
  for (const r of rows) {
    const items = getCountedMetric(r.metrics, key);
    const top = items
      .slice(0, maxTop)
      .map((o) => formatTop(o))
      .join(", ");
    lines.push(
      `| \\`${escapeMd(r.routePattern)}\\` | \\`${escapeMd(r.project)}\\` | ${items.length} | ${escapeMd(top || "-")} | ${renderShots(r)} |`
    );
  }
  lines.push("");
}

// Special case: overflow uses a different table shape (includes overflow px).
function pushOverflowSection(lines: string[], ctx: RenderContext): void {
  const overflow = ctx.buckets.overflow;
  if (overflow.length <= 0) return;
  lines.push("## 水平溢出（疑似布局问题）");
  lines.push("");
  lines.push("| 页面 | 视口 | 溢出(px) | offenders(Top) | 截图 |");
  lines.push("|---|---:|---:|---|---|");
  const rows = overflow
    .slice()
    .sort((a, b) => (b.metrics?.horizontalOverflowPx || 0) - (a.metrics?.horizontalOverflowPx || 0));
  for (const r of rows) {
    const offenders = (r.metrics?.offenders || [])
      .slice(0, 3)
      .map((o: OverflowOffender) => `${o.tag}${o.id ? `#${o.id}` : ""}`)
      .join(", ");
    lines.push(
      `| \\`${escapeMd(r.routePattern)}\\` | \\`${escapeMd(r.project)}\\` | ${r.metrics?.horizontalOverflowPx || 0} | ${escapeMd(
        offenders || "-"
      )} | ${renderShots(r)} |`
    );
  }
  lines.push("");
}

// Index is always rendered, even if buckets are empty.
function pushIndex(lines: string[], ctx: RenderContext): void {
  lines.push("## 全量索引");
  lines.push("");
  lines.push("| 页面 | 视口 | 状态 | 最终URL | 指标 | 截图 |");
  lines.push("|---|---:|---|---|---|---|");

  for (const route of ctx.routeKeys) {
    const items = ctx.byRoute[route] || [];
    items.sort((a, b) => a.project.localeCompare(b.project));
    for (const r of items) {
      const status = r.status === "ok" ? "✅ ok" : r.status === "skipped" ? "⚠️ skipped" : "❌ error";
      const metrics = r.metrics
        ? `w:${r.metrics.clientWidth}/${r.metrics.scrollWidth}, hOverflow:${r.metrics.horizontalOverflowPx}, clip:${r.metrics.clipped.length}, occ:${r.metrics.occluded.length}, ovlp:${r.metrics.overlaps.length}`
        : "-";
      lines.push(
        `| \\`${escapeMd(r.routePattern)}\\` | \\`${escapeMd(r.project)}\\` | ${status} | ${escapeMd(
          r.finalUrl || r.url || "-"
        )} | ${escapeMd(metrics)} | ${renderShots(r)} |`
      );
    }
  }
  lines.push("");
}

function pushNotes(lines: string[]): void {
  lines.push("## 说明");
  lines.push("");
  lines.push("- 本报告用于“先巡检后修复”的流程（你选择的 B）。");
  lines.push("- `水平溢出` 仅是自动检测信号，仍需结合截图人工确认。");
  lines.push("- 动态路由（如 `/jobs/[jobId]`）在缺少参数时会标记为 skipped，并给出补齐方式。");
  lines.push("");
}

export function renderMarkdown(records: AuditRecord[], opts: RenderOptions): string {
  // Entry: build a markdown document in a deterministic order.
  const ctx = buildRenderContext(records, opts);
  const lines: string[] = [];
  pushHeader(lines, ctx);
  pushSummary(lines, ctx);
  pushErrorList(lines, ctx);
  pushOverflowSection(lines, ctx);
  pushCountedSection({
    lines,
    ctx,
    title: "## overflow 裁切（overflow:hidden/clip）",
    key: "clipped",
    maxTop: 3,
    formatTop: (o) => {
      const item = o as ClipOffender;
      return `${formatElementCompact(item.el)} <= ${formatElementCompact(item.clipBy)}`;
    },
  });
  pushCountedSection({
    lines,
    ctx,
    title: "## 点击目标被遮挡（elementFromPoint）",
    key: "occluded",
    maxTop: 3,
    formatTop: (o) => {
      const item = o as OccludedOffender;
      return `${formatElementCompact(item.el)} <= ${formatElementCompact(item.top)}`;
    },
  });
  pushCountedSection({
    lines,
    ctx,
    title: "## 点击目标重叠（点击热区交叠）",
    key: "overlaps",
    maxTop: 3,
    formatTop: (o) => {
      const item = o as OverlapOffender;
      return `${formatElementCompact(item.a)} x ${formatElementCompact(item.b)} (${item.intersectionAreaPx})`;
    },
  });
  pushCountedSection({
    lines,
    ctx,
    title: "## 按钮行不对齐（flex row）",
    key: "misalignedButtonRows",
    maxTop: 2,
    formatTop: (o) => {
      const item = o as MisalignedButtonRowOffender;
      return `${formatElementCompact(item.container)} Δtop=${item.deltaTopPx}, Δh=${item.deltaHeightPx}`;
    },
  });
  pushCountedSection({
    lines,
    ctx,
    title: "## 文本截断（scrollWidth > clientWidth）",
    key: "textTruncations",
    maxTop: 3,
    formatTop: (o) => {
      const item = o as TextTruncationOffender;
      return `${formatElementCompact(item.el)} (${item.clientWidth}/${item.scrollWidth})`;
    },
  });
  pushIndex(lines, ctx);
  pushNotes(lines);
  return lines.join("\\n");
}
