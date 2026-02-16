"use client";

import React, { useMemo, useState } from "react";
import { getErrorMessage } from "@/lib/api";
import { getMcpClient } from "@/lib/mcp";
import type { JobTestMeta, JobTestPreview, ReportArtifact } from "./types";

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; data: JobTestPreview }
  | { status: "error"; message: string };

function caseKey(group: string, name: string): string {
  return `${group}/${name}`;
}

function safeTextDecoder(bytes: Uint8Array): string {
  try {
    return new TextDecoder().decode(bytes);
  } catch {
    return "";
  }
}

function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function decodeB64Text(b64: string | undefined): string {
  const s = String(b64 || "");
  if (!s) return "";
  try {
    return safeTextDecoder(b64ToBytes(s));
  } catch {
    return "";
  }
}

function formatTimeMs(ms: number): string {
  if (!Number.isFinite(ms)) return "—";
  if (ms < 1000) return `${Math.max(0, Math.round(ms))}ms`;
  const s = ms / 1000;
  return `${s.toFixed(s < 10 ? 2 : 1)}s`;
}

function formatMemoryKb(kb: number): string {
  if (!Number.isFinite(kb)) return "—";
  const mb = Math.max(0, kb / 1024);
  const digits = mb < 10 ? 2 : mb < 100 ? 1 : 0;
  let s = mb.toFixed(digits);
  s = s.replace(/\.0+$/, "").replace(/(\.\d*[1-9])0+$/, "$1");
  return `${s}MB`;
}

function badgeForVerdict(verdict: string): { text: string; className: string } {
  const v = verdict.trim().toUpperCase();
  if (v === "AC") return { text: "AC", className: "bg-emerald-50 text-emerald-700 border border-emerald-200" };
  if (v === "WA") return { text: "WA", className: "bg-rose-50 text-rose-700 border border-rose-200" };
  if (v === "RE") return { text: "RE", className: "bg-orange-50 text-orange-700 border border-orange-200" };
  if (v === "TLE") return { text: "TLE", className: "bg-fuchsia-50 text-fuchsia-700 border border-fuchsia-200" };
  if (v === "OLE") return { text: "OLE", className: "bg-amber-50 text-amber-800 border border-amber-200" };
  if (v === "SKIP") return { text: "SKIP", className: "bg-slate-100 text-slate-600 border border-slate-200" };
  if (v === "RUN") return { text: "RUN", className: "bg-indigo-50 text-indigo-700 border border-indigo-200" };
  return { text: v || "—", className: "bg-slate-100 text-slate-600 border border-slate-200" };
}

function frameForVerdict(verdict: string): { frame: string; chevron: string; blockBorder: string; blockBg: string } {
  const v = verdict.trim().toUpperCase();
  if (v === "AC") {
    return {
      frame: "border-emerald-200 bg-emerald-50/70 shadow-emerald-500/5",
      chevron: "text-emerald-400",
      blockBorder: "border-emerald-200/60",
      blockBg: "bg-emerald-50/50",
    };
  }
  if (v === "WA") {
    return {
      frame: "border-rose-200 bg-rose-50/75 shadow-rose-500/5",
      chevron: "text-rose-400",
      blockBorder: "border-rose-200/60",
      blockBg: "bg-rose-50/55",
    };
  }
  if (v === "RE") {
    return {
      frame: "border-orange-200 bg-orange-50/75 shadow-orange-500/5",
      chevron: "text-orange-400",
      blockBorder: "border-orange-200/60",
      blockBg: "bg-orange-50/55",
    };
  }
  if (v === "TLE") {
    return {
      frame: "border-fuchsia-200 bg-fuchsia-50/75 shadow-fuchsia-500/5",
      chevron: "text-fuchsia-400",
      blockBorder: "border-fuchsia-200/60",
      blockBg: "bg-fuchsia-50/55",
    };
  }
  if (v === "OLE") {
    return {
      frame: "border-amber-200 bg-amber-50/75 shadow-amber-500/5",
      chevron: "text-amber-500",
      blockBorder: "border-amber-200/60",
      blockBg: "bg-amber-50/55",
    };
  }
  if (v === "SKIP") {
    return {
      frame: "border-slate-200 bg-slate-50/70 shadow-slate-500/5",
      chevron: "text-slate-400",
      blockBorder: "border-slate-200/70",
      blockBg: "bg-slate-50/60",
    };
  }
  if (v === "RUN") {
    return {
      frame: "border-indigo-200 bg-indigo-50/70 shadow-indigo-500/5",
      chevron: "text-indigo-400",
      blockBorder: "border-indigo-100/70",
      blockBg: "bg-indigo-50/55",
    };
  }
  return {
    frame: "border-slate-200 bg-white/80 shadow-slate-500/5",
    chevron: "text-slate-400",
    blockBorder: "border-slate-200/70",
    blockBg: "bg-white/70",
  };
}

function CopyButton({ text, label = "复制" }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 800);
    } catch {
      // ignore
    }
  };
  return (
    <button
      onClick={onCopy}
      className="px-2 py-1 rounded-md text-[10px] font-semibold text-slate-600 hover:bg-slate-100 border border-slate-200"
      title="复制到剪贴板"
      type="button"
    >
      {copied ? "已复制" : label}
    </button>
  );
}

function Block({
  title,
  text,
  meta,
  className,
}: {
  title: string;
  text: string;
  meta?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={["rounded-lg border overflow-hidden", className || "border-slate-200 bg-white/90"].join(" ")}>
      <div className="px-3 py-2 border-b border-black/5 flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold text-slate-600">{title}</div>
        <div className="shrink-0 flex items-center gap-1.5">
          {meta}
          <CopyButton text={text} />
        </div>
      </div>
      <pre className="px-3 py-2.5 whitespace-pre-wrap break-words text-[12px] leading-5 text-[#24292f] font-mono bg-white/60 max-h-44 overflow-auto custom-scrollbar">
{text || "（空）"}
      </pre>
    </div>
  );
}

export function JobTestsPanel({
  jobId,
  tests,
  report,
  loading,
  errorText,
}: {
  jobId: string | null;
  tests: JobTestMeta[] | null;
  report: ReportArtifact | null;
  loading?: boolean;
  errorText?: string | null;
}) {
  const resultByKey = useMemo(() => {
    const m = new Map<string, NonNullable<ReportArtifact["tests"]>[number]>();
    for (const t of report?.tests ?? []) {
      const name = String(t?.name ?? "").trim();
      if (!name) continue;
      const group = String(t?.group ?? "default").trim() || "default";
      m.set(caseKey(group, name), t);
    }
    return m;
  }, [report]);

  const rows = useMemo(() => {
    if (tests && tests.length > 0) return tests;
    if (!tests && (report?.tests?.length ?? 0) > 0) {
      return (report?.tests ?? [])
        .map((t) => ({
          name: String(t?.name ?? "").trim() || "—",
          group: String(t?.group ?? "default").trim() || "default",
          input_rel: String(t?.input_rel ?? ""),
          expected_rel: (t?.expected_rel as string | null) ?? null,
          expected_present: Boolean(t?.expected_present),
        }))
        .filter((x) => x.name !== "—");
    }
    return tests ?? [];
  }, [tests, report]);

  const summaryText = useMemo(() => {
    const total = report?.summary?.total;
    const passed = report?.summary?.passed;
    const failed = report?.summary?.failed;
    const judged = report?.summary?.judged;
    if (typeof total === "number" && typeof passed === "number" && typeof failed === "number") {
      const bits = [`${passed}/${total} 通过`];
      if (typeof judged === "number") bits.push(`judged=${judged}`);
      if (failed > 0) bits.push(`failed=${failed}`);
      return bits.join(" · ");
    }
    return "";
  }, [report]);

  const actualMetrics = useMemo(() => {
    let totalTimeMs: number | null = null;
    let peakMemoryKb: number | null = null;

    for (const t of report?.tests ?? []) {
      const timeMs = typeof t?.time_ms === "number" ? t.time_ms : null;
      if (timeMs !== null && Number.isFinite(timeMs)) {
        totalTimeMs = totalTimeMs === null ? timeMs : totalTimeMs + timeMs;
      }

      const memoryKb = typeof t?.memory_kb === "number" ? t.memory_kb : null;
      if (memoryKb !== null && Number.isFinite(memoryKb)) {
        peakMemoryKb = peakMemoryKb === null ? memoryKb : Math.max(peakMemoryKb, memoryKb);
      }
    }

    return {
      totalTimeMs,
      peakMemoryKb,
    };
  }, [report]);

  const [previewMap, setPreviewMap] = useState<Record<string, PreviewState>>({});

  const ensurePreviewLoaded = async (meta: JobTestMeta) => {
    if (!jobId) return;
    const key = caseKey(meta.group, meta.name);
    const st = previewMap[key];
    if (st?.status === "loading" || st?.status === "loaded") return;

    setPreviewMap((prev) => ({ ...prev, [key]: { status: "loading" } }));
    try {
      const client = getMcpClient();
      const payload = await client.callTool<JobTestPreview>("job.get_test_preview", {
        job_id: jobId,
        input_rel: meta.input_rel,
        expected_rel: meta.expected_rel,
        max_bytes: 64 * 1024,
      });
      setPreviewMap((prev) => ({ ...prev, [key]: { status: "loaded", data: payload } }));
    } catch (e: unknown) {
      setPreviewMap((prev) => ({ ...prev, [key]: { status: "error", message: getErrorMessage(e) } }));
    }
  };

  return (
    <div className="h-full min-h-0 flex flex-col">
      <div className="shrink-0 px-4 py-3 border-b border-slate-200/80 bg-white/90">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide">样例 / 结果</div>
            <div className="text-[11px] text-slate-500 mt-1">
              {summaryText ? summaryText : rows.length > 0 ? `共 ${rows.length} 个样例` : "—"}
            </div>
          </div>
          <div className="shrink-0 flex flex-col items-end gap-1">
            {actualMetrics.totalTimeMs !== null || actualMetrics.peakMemoryKb !== null ? (
              <div className="flex items-center gap-1.5">
                {actualMetrics.totalTimeMs !== null ? (
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-slate-900/5 border border-slate-200 text-slate-700">
                    总耗时 {formatTimeMs(actualMetrics.totalTimeMs)}
                  </span>
                ) : null}
                {actualMetrics.peakMemoryKb !== null ? (
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-slate-900/5 border border-slate-200 text-slate-700">
                    峰值内存 {formatMemoryKb(actualMetrics.peakMemoryKb)}
                  </span>
                ) : null}
              </div>
            ) : null}
            {report?.summary?.first_failure ? (
              <div className="text-[10px] text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-2 py-1">
                首个失败: {report.summary.first_failure} {report.summary.first_failure_verdict}
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto custom-scrollbar p-4 bg-white/58">
        {errorText ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50/80 px-3 py-2 text-[12px] text-rose-700">
            加载样例失败：{errorText}
          </div>
        ) : loading || tests === null ? (
          <div className="text-[12px] text-slate-500">加载样例中…</div>
        ) : rows.length === 0 ? (
          <div className="text-[12px] text-slate-500">当前 Job 未上传 tests.zip（或已被清理）。</div>
        ) : (
          <div className="space-y-2">
            {rows.map((tc) => {
              const key = caseKey(tc.group, tc.name);
              const r = resultByKey.get(key);
              const verdict = r?.verdict ? String(r.verdict) : report ? "—" : "PENDING";
              const toneVerdict = r?.verdict ? String(r.verdict) : report ? "SKIP" : "RUN";
              const badge = badgeForVerdict(verdict === "PENDING" ? "RUN" : verdict);
              const frame = frameForVerdict(toneVerdict === "PENDING" ? "RUN" : toneVerdict);
              const timeMs = typeof r?.time_ms === "number" ? r.time_ms : null;
              const memoryKb = typeof r?.memory_kb === "number" ? r.memory_kb : null;
              const diffMsg = String(r?.diff?.message ?? "").trim();

              const previewState = previewMap[key] ?? { status: "idle" };
              const inputText = previewState.status === "loaded" ? previewState.data.input.text : "";
              const expectedText =
                previewState.status === "loaded"
                  ? previewState.data.expected?.text ?? ""
                  : "";
              const actualText = decodeB64Text(r?.stdout_b64);
              const stderrText = decodeB64Text(r?.stderr_b64);

              const inputMeta =
                previewState.status === "loaded" && previewState.data.input.truncated ? (
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-white/70 border border-black/5 text-slate-600">
                    已截断
                  </span>
                ) : null;
              const expectedMeta =
                previewState.status === "loaded"
                && previewState.data.expected
                && (previewState.data.expected.missing || previewState.data.expected.truncated) ? (
                  <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-white/70 border border-black/5 text-slate-600">
                    {previewState.data.expected.missing ? "缺失" : "已截断"}
                  </span>
                ) : null;
              const actualMeta = r?.stdout_truncated ? (
                <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-white/70 border border-black/5 text-slate-600">
                  已截断
                </span>
              ) : null;

              return (
                <details
                  key={key}
                  className={[
                    "group rounded-xl border shadow-sm",
                    "transition-all duration-200",
                    "hover:shadow-md hover:-translate-y-[1px]",
                    "group-open:shadow-md group-open:-translate-y-[1px]",
                    frame.frame,
                  ].join(" ")}
                  onToggle={(e) => {
                    const el = e.currentTarget;
                    if (el.open) ensurePreviewLoaded(tc);
                  }}
                >
                  <summary className="list-none cursor-pointer px-3 py-2.5 flex items-center justify-between gap-2">
                    <div className="min-w-0 flex items-center gap-2">
                      <span className="text-[12px] font-mono text-slate-700 truncate">
                        {tc.group !== "default" ? `[${tc.group}] ` : ""}
                        {tc.name}
                      </span>
                      <span className={["inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold", badge.className].join(" ")}>
                        {r ? badge.text : report ? "—" : "待测评"}
                      </span>
                      {r ? (
                        <span className="flex items-center gap-1.5">
                          <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-white/65 border border-black/5 text-slate-700">
                            时间 {timeMs !== null ? formatTimeMs(timeMs) : "—"}
                          </span>
                          <span className="inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold bg-white/65 border border-black/5 text-slate-700">
                            内存 {memoryKb !== null ? formatMemoryKb(memoryKb) : "—"}
                          </span>
                        </span>
                      ) : null}
                    </div>
                    <span className={[frame.chevron, "transition-transform group-open:rotate-180"].join(" ")}>⌄</span>
                  </summary>

                  <div className="px-3 pb-3 space-y-2.5">
                    {previewState.status === "error" ? (
                      <div className="text-[11px] text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-2 py-1">
                        读取样例失败：{previewState.message}
                      </div>
                    ) : previewState.status === "loading" ? (
                      <div className="text-[11px] text-slate-500">正在读取样例…</div>
                    ) : null}

                    <Block title="Input" text={inputText} meta={inputMeta} className={[frame.blockBg, frame.blockBorder].join(" ")} />

                    <Block
                      title="Expected"
                      text={tc.expected_rel ? expectedText : ""}
                      meta={expectedMeta}
                      className={[frame.blockBg, frame.blockBorder].join(" ")}
                    />

                    <Block title="Actual (stdout)" text={r ? actualText : ""} meta={actualMeta} className={[frame.blockBg, frame.blockBorder].join(" ")} />

                    {stderrText.trim() ? (
                      <Block title="stderr" text={stderrText} className={[frame.blockBg, frame.blockBorder].join(" ")} />
                    ) : null}

                    {diffMsg ? (
                      <div className="rounded-lg border border-black/5 bg-white/55 px-3 py-2 text-[11px] text-slate-700">
                        diff: {diffMsg}
                      </div>
                    ) : null}
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
