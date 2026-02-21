"use client";

import React from "react";
import { GlassPanel } from "./GlassPanel";
import { JobTestsPanel } from "./JobTestsPanel";
import type { JobTestMeta, Message, ReportArtifact } from "./types";
import { DiffView } from "./cockpit/DiffView";
import { resolveJobStatusMeta } from "./cockpit/jobStatus";
import { cleanTokenText, splitTokenStreamContent } from "./cockpit/tokenStream";

export type CockpitViewModel = {
  activeJobId: string | null;
  errorText: string | null;
  visibleMessages: Message[];

  isLoading: boolean;
  canContinueChat: boolean;
  inputValue: string;
  onInputValueChange: (value: string) => void;
  onSendMessage: () => void;

  codeView: "final" | "diff";
  onSetCodeView: (next: "final" | "diff") => void;
  mainCpp: string | null;
  diffText: string;
  hasDiff: boolean;
  report: ReportArtifact | null;

  jobTests: JobTestMeta[] | null;
  jobTestsError: string | null;

  statusMeta: ReturnType<typeof resolveJobStatusMeta>;
  modelLabel: string;
  reasoningEffortLabel: string;
  isRunningStatus: boolean;

  chatScrollRef: React.MutableRefObject<HTMLDivElement | null>;

  onCancelJob: () => void;
  onBack: () => void;
};

export function CockpitView({ vm }: { vm: CockpitViewModel }) {
  // UI 被拆到单独文件的目的：
  // 1) 降低 Cockpit.tsx 的函数长度/文件长度；
  // 2) 让数据逻辑与渲染结构分离，便于后续维护；
  // 3) 在不改变行为的前提下，提高代码可读性与注释覆盖。

  return (
    <div className="h-full w-full min-h-0 p-4 md:p-4 animate-in fade-in duration-500 bg-transparent overflow-hidden">
      <GlassPanel
        intensity="high"
        className="h-full min-h-0 flex flex-col border-slate-200 overflow-hidden"
        innerClassName="h-full min-h-0 flex flex-col"
      >
        {/* 顶部状态栏 */}
        <div className="shrink-0 border-b border-slate-200 bg-white/92 px-4 md:px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wide text-slate-400 font-semibold">工作区</div>
              <div className="text-xs text-slate-700 font-mono truncate">{vm.activeJobId ?? "暂无 Job"}</div>
              <div className="text-[11px] text-slate-500 mt-1">
                任务状态:
                <span
                  className={[
                    "ml-1.5 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                    vm.statusMeta.badgeClassName,
                  ].join(" ")}
                >
                  <span
                    className={[
                      "h-1.5 w-1.5 rounded-full",
                      vm.isRunningStatus ? "animate-pulse" : "",
                      vm.statusMeta.dotClassName,
                    ].join(" ")}
                  />
                  {vm.statusMeta.headline} · {vm.statusMeta.phase}
                </span>
                <span className="mx-2 text-slate-300">|</span>
                原始状态: <span className="font-mono">{vm.statusMeta.raw}</span>
                <span className="mx-2 text-slate-300">|</span>
                模型: <span className="font-mono">{vm.modelLabel}</span>
                <span className="mx-2 text-slate-300">|</span>
                思考量: <span className="font-mono">{vm.reasoningEffortLabel}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={vm.onCancelJob}
                disabled={!vm.isRunningStatus}
                className={[
                  "px-3.5 py-2 rounded-lg text-xs font-semibold border",
                  vm.isRunningStatus
                    ? "text-slate-600 bg-white border-slate-200 hover:text-rose-600"
                    : "text-slate-400 bg-slate-100/80 border-slate-200 cursor-not-allowed",
                ].join(" ")}
              >
                取消任务
              </button>
              <button
                onClick={vm.onBack}
                className="px-3.5 py-2 rounded-lg text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:text-indigo-600"
              >
                返回大厅
              </button>
            </div>
          </div>
        </div>

        {/* 全局错误提示（网络/MCP 调用失败等） */}
        {vm.errorText ? (
          <div className="mx-4 md:mx-5 mt-4 rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3 text-sm text-rose-700">
            {vm.errorText}
          </div>
        ) : null}

        <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(340px,420px)] bg-slate-50/[0.08]">
          {/* 左侧：对话与实时输出 */}
          <div className="min-h-0 flex flex-col xl:border-r border-slate-200/80">
            <div
              ref={vm.chatScrollRef}
              className="flex-1 min-h-0 overflow-y-auto space-y-3 px-4 md:px-5 py-4 md:py-5 scroll-smooth custom-scrollbar"
            >
              {vm.visibleMessages.map((m, i) => {
                const isTokenStream = m.messageKey?.startsWith("job-token-") ?? false;
                const isFeedbackMessage = m.messageKey?.startsWith("job-feedback-") ?? false;
                const tokenView = isTokenStream ? splitTokenStreamContent(m.content) : null;

                return (
                  <div
                    key={i}
                    className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"} animate-in slide-in-from-bottom-2 duration-500`}
                  >
                    <div
                      className={[
                        isTokenStream || isFeedbackMessage ? "w-full max-w-full rounded-2xl" : "max-w-[92%] rounded-2xl",
                        m.role === "user"
                          ? "p-3 md:p-4 bg-indigo-600 text-white shadow-sm shadow-indigo-600/10 border border-indigo-500"
                          : isTokenStream
                            ? "p-0 bg-transparent border-0 shadow-none"
                            : "p-3 md:p-4 bg-white border border-slate-200 shadow-sm",
                      ].join(" ")}
                    >
                      {m.streaming && !isTokenStream ? (
                        <div
                          className={[
                            "mb-2 inline-flex items-center gap-2 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                            "bg-indigo-50 text-indigo-600",
                          ].join(" ")}
                        >
                          <span className="h-1.5 w-1.5 rounded-full animate-pulse bg-indigo-500" />
                          实时流式输出中
                        </div>
                      ) : null}

                      <div
                        className={[
                          "text-[13px] md:text-sm leading-relaxed whitespace-pre-wrap font-medium",
                          m.role === "user" ? "text-white" : "text-slate-700",
                        ].join(" ")}
                      >
                        {tokenView ? (
                          <div className="space-y-2.5">
                            {tokenView.items.length > 0 ? (
                              <details
                                className="group rounded-md bg-[#f6f8fa]"
                                open={m.streaming || tokenView.items.some((x) => x.kind === "thinking")}
                              >
                                <summary className="list-none cursor-pointer px-3 py-2 text-[11px] font-normal text-slate-400 tracking-wide flex items-center justify-end gap-2">
                                  <span className="sr-only">过程记录（{tokenView.items.length}）</span>
                                  <span className="text-[#8c959f] transition-transform group-open:rotate-180">⌄</span>
                                </summary>
                                <div className="bg-white">
                                  {tokenView.items.map((item, idx) => (
                                    item.kind === "thinking" ? (
                                      <details
                                        key={idx}
                                        className={[
                                          "group",
                                          idx > 0 ? "mt-1" : "",
                                        ].join(" ")}
                                      >
                                        <summary className="list-none cursor-pointer px-3 py-2 text-[11px] font-normal text-slate-400 flex items-center justify-between gap-2">
                                          <span className="min-w-0 whitespace-normal break-words">
                                            {item.title || `思考段落 ${idx + 1}`}
                                          </span>
                                          <span className="text-[#8c959f] transition-transform group-open:rotate-180">⌄</span>
                                        </summary>
                                        <div className="px-3 py-2.5 text-[11px] leading-5 text-slate-400 bg-[#fbfcfd] space-y-1">
                                          {item.content
                                            .split("\n")
                                            .map((line) => line.trim())
                                            .filter(Boolean)
                                            .map((line, lineIdx) => (
                                              <div key={lineIdx} className="whitespace-normal break-words">
                                                {line}
                                              </div>
                                            ))}
                                        </div>
                                      </details>
                                    ) : (
                                      <details
                                        key={idx}
                                        className={[
                                          "group",
                                          idx > 0 ? "mt-1" : "",
                                        ].join(" ")}
                                      >
                                        <summary className="list-none cursor-pointer px-3 py-2 text-[11px] font-normal text-slate-400 flex items-center justify-between gap-2">
                                          <span className="min-w-0 truncate">{item.title}</span>
                                          <span className="text-[#8c959f] transition-transform group-open:rotate-180">⌄</span>
                                        </summary>
                                        <div className="px-3 py-2.5 whitespace-pre-wrap break-words text-[12px] leading-5 text-[#24292f] font-mono bg-[#fdfefe]">
                                          {item.content}
                                        </div>
                                      </details>
                                    )
                                  ))}
                                </div>
                              </details>
                            ) : (
                              <div className="whitespace-pre-wrap break-words text-slate-700">{cleanTokenText(m.content)}</div>
                            )}
                          </div>
                        ) : (
                          m.content
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}

              {vm.isLoading ? (
                <div className="flex items-start animate-in zoom-in-95 duration-300">
                  <div className="bg-white border border-slate-200 p-3 md:p-4 rounded-xl shadow-sm flex gap-2 items-center">
                    <div className="flex gap-1">
                      <span className="w-1 h-1 bg-indigo-500 rounded-full animate-bounce" />
                      <span className="w-1 h-1 bg-indigo-500 rounded-full animate-bounce [animation-delay:0.2s]" />
                      <span className="w-1 h-1 bg-indigo-500 rounded-full animate-bounce [animation-delay:0.4s]" />
                    </div>
                  </div>
                </div>
              ) : null}
            </div>

            {/* 输入框 */}
            <div className="shrink-0 border-t border-slate-200 px-4 md:px-5 py-2.5 md:py-3 bg-white/92">
              <div className="h-12 rounded-xl border border-slate-200 bg-white px-3 md:px-4 flex items-center gap-2 shadow-sm">
                <input
                  className="flex-1 min-w-0 bg-transparent border-none outline-none text-slate-800 placeholder:text-slate-400 text-sm disabled:opacity-40"
                  placeholder={vm.canContinueChat ? "继续对话（会创建新 Job 进行修复/迭代）..." : "当前为只读 Job 追踪，返回大厅后可继续对话"}
                  value={vm.inputValue}
                  disabled={!vm.canContinueChat}
                  onChange={(e) => vm.onInputValueChange(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && vm.onSendMessage()}
                />
                <button
                  onClick={vm.onSendMessage}
                  disabled={!vm.canContinueChat || vm.isLoading || !vm.inputValue.trim()}
                  className="icon-wrap w-9 h-9 shrink-0 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 transition-all disabled:opacity-20"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2.4}
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h11m-5-5 5 5-5 5m7-10v10" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          {/* 中间：代码与 diff */}
          <div className="min-h-0 flex flex-col bg-white/58 xl:border-r border-slate-200/80">
            <div className="shrink-0 px-4 md:px-5 py-3 border-b border-slate-200/80 bg-white/90">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide">代码</div>
                  <div className="text-[11px] text-slate-500 mt-1">
                    {vm.codeView === "diff" ? "差异（diff）" : "最终代码（main.cpp）"}
                  </div>
                </div>
                <div className="shrink-0 flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
                  <button
                    onClick={() => vm.onSetCodeView("final")}
                    className={[
                      "px-2.5 py-1 rounded-md text-[11px] font-semibold",
                      vm.codeView === "final" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100",
                    ].join(" ")}
                  >
                    最终代码
                  </button>
                  <button
                    onClick={() => vm.onSetCodeView("diff")}
                    disabled={!vm.hasDiff}
                    className={[
                      "px-2.5 py-1 rounded-md text-[11px] font-semibold",
                      vm.codeView === "diff" ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-100",
                      !vm.hasDiff ? "opacity-40 cursor-not-allowed" : "",
                    ].join(" ")}
                  >
                    差异
                  </button>
                </div>
              </div>
            </div>

            <div className="flex-1 min-h-0 overflow-auto custom-scrollbar">
              {vm.codeView === "diff" ? (
                <div className="p-4 md:p-5">
                  {vm.hasDiff ? (
                    <DiffView diffText={vm.diffText} />
                  ) : (
                    <div className="text-[12px] text-slate-500">本轮没有可展示的差异（diff）。</div>
                  )}
                </div>
              ) : (
                <pre className="p-4 md:p-5 text-slate-700 whitespace-pre font-mono leading-relaxed text-xs md:text-sm">
{vm.mainCpp ?? "// 暂无代码（可能尚未生成或已清理）"}
                </pre>
              )}
            </div>

            {vm.report?.summary?.first_failure ? (
              <div className="shrink-0 border-t border-rose-200 bg-rose-50/70 px-4 md:px-5 py-2.5 text-[11px] text-rose-700">
                首个失败用例: {vm.report.summary.first_failure} ({vm.report.summary.first_failure_verdict}){" "}
                {vm.report.summary.first_failure_message}
              </div>
            ) : null}
          </div>

          {/* 右侧：测试面板 */}
          <div className="min-h-0 flex flex-col bg-white/58">
            <JobTestsPanel
              jobId={vm.activeJobId}
              tests={vm.jobTests}
              report={vm.report}
              loading={vm.jobTests === null}
              errorText={vm.jobTestsError}
            />
          </div>
        </div>
      </GlassPanel>
    </div>
  );
}

