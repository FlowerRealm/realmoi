"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch, API_BASE, getErrorMessage } from "@/lib/api";
import { connectSse } from "@/lib/sse";
import { GlassPanel } from "./GlassPanel";
import type { JobRun, JobState, Message, PromptData } from "./types";
import { buildTestsZip } from "./testsZip";

type ReportArtifact = {
  summary?: {
    first_failure?: string;
    first_failure_verdict?: string;
    first_failure_message?: string;
  };
};

type JobStatusMeta = {
  lifecycle: "running" | "finished" | "waiting" | "unknown";
  headline: string;
  phase: string;
  raw: string;
  badgeClassName: string;
  dotClassName: string;
};

function resolveJobStatusMeta(status: string | null | undefined): JobStatusMeta {
  const normalized = (status ?? "").trim().toLowerCase();
  const raw = normalized || "-";

  if (!normalized) {
    return {
      lifecycle: "waiting",
      headline: "等待中",
      phase: "尚未开始",
      raw,
      badgeClassName: "bg-slate-100 text-slate-600 border border-slate-200",
      dotClassName: "bg-slate-400",
    };
  }

  if (normalized === "created" || normalized === "queued") {
    return {
      lifecycle: "waiting",
      headline: "等待中",
      phase: normalized === "queued" ? "已排队，等待测评机" : "已创建，待启动",
      raw,
      badgeClassName: "bg-amber-50 text-amber-700 border border-amber-200",
      dotClassName: "bg-amber-500",
    };
  }

  if (normalized.startsWith("running")) {
    let phase = "执行中";
    if (normalized === "running_generate") phase = "生成中";
    if (normalized === "running_test") phase = "测试中";
    return {
      lifecycle: "running",
      headline: "进行中",
      phase,
      raw,
      badgeClassName: "bg-indigo-50 text-indigo-700 border border-indigo-200",
      dotClassName: "bg-indigo-500",
    };
  }

  if (normalized === "succeeded") {
    return {
      lifecycle: "finished",
      headline: "已结束",
      phase: "成功",
      raw,
      badgeClassName: "bg-emerald-50 text-emerald-700 border border-emerald-200",
      dotClassName: "bg-emerald-500",
    };
  }

  if (normalized === "failed") {
    return {
      lifecycle: "finished",
      headline: "已结束",
      phase: "失败",
      raw,
      badgeClassName: "bg-rose-50 text-rose-700 border border-rose-200",
      dotClassName: "bg-rose-500",
    };
  }

  if (normalized === "cancelled") {
    return {
      lifecycle: "finished",
      headline: "已结束",
      phase: "已取消",
      raw,
      badgeClassName: "bg-orange-50 text-orange-700 border border-orange-200",
      dotClassName: "bg-orange-500",
    };
  }

  return {
    lifecycle: "unknown",
    headline: "状态未知",
    phase: normalized,
    raw,
    badgeClassName: "bg-slate-100 text-slate-600 border border-slate-200",
    dotClassName: "bg-slate-500",
  };
}

function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function buildStatementWithUserMessage(statement: string, userMessage?: string): string {
  if (!userMessage?.trim()) return statement;
  return `${statement}\n\n---\n\n### 用户追加指令\n${userMessage.trim()}\n`;
}

function formatJobError(error: unknown): string | null {
  if (!error) return null;
  if (typeof error === "string") return error;
  if (typeof error === "object") {
    const payload = error as { code?: unknown; message?: unknown };
    const code = typeof payload.code === "string" ? payload.code : null;
    const message = typeof payload.message === "string" ? payload.message : null;
    if (code && message) return `${code}: ${message}`;
    if (message) return message;
    if (code) return code;
  }
  return null;
}

function normalizeTerminalChunk(chunkText: string): string {
  const withoutAnsi = chunkText.replace(/\x1b\[[0-9;?]*[ -/]*[@-~]/g, "");
  const withoutCtrl = withoutAnsi.replace(/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/g, "");
  return withoutCtrl.replace(/\r/g, "");
}

type TokenStreamView = {
  items: TokenStreamItem[];
};

type TokenStreamItem = {
  kind: "thinking" | "stage" | "result" | "usage" | "backend" | "other";
  title: string;
  content: string;
};

type AgentStatusLine = {
  seq?: number | string;
  stage?: string;
  summary?: string;
  kind?: string;
  delta?: string;
  meta?: Record<string, unknown>;
};

type AgentLiveState = {
  reasoning: string;
  execution: string;
  result: string;
};

type ReasoningBufferState = {
  buffer: string;
  summaryIndex: number | null;
};

function parseNumericMeta(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) return null;
    const num = Number(text);
    if (Number.isFinite(num)) return num;
  }
  return null;
}

function normalizeReasoningParagraph(text: string): string {
  return text.replace(/[\r\n]+/g, " ").replace(/\s+/g, " ").trim();
}

function splitReasoningSegments(buffer: string, force: boolean): { lines: string[]; rest: string } {
  const lines: string[] = [];
  const pushParagraph = (segment: string) => {
    const normalized = normalizeReasoningParagraph(segment);
    if (normalized) lines.push(normalized);
  };

  let remaining = buffer.replace(/\r/g, "");
  while (true) {
    const match = remaining.match(/\n\s*\n/);
    if (!match || typeof match.index !== "number") break;
    pushParagraph(remaining.slice(0, match.index));
    remaining = remaining.slice(match.index + match[0].length);
  }

  let rest = remaining;
  if (force) {
    pushParagraph(rest);
    rest = "";
  }
  return { lines, rest };
}

function appendReasoningLines(state: AgentLiveState, lines: string[]): void {
  if (!lines.length) return;
  const merged = lines.join("\n");
  state.reasoning = state.reasoning ? `${state.reasoning}\n${merged}` : merged;
}

function flushReasoningBuffer(state: AgentLiveState, stream: ReasoningBufferState, force: boolean): void {
  const { lines, rest } = splitReasoningSegments(stream.buffer, force);
  appendReasoningLines(state, lines);
  stream.buffer = rest;
}

function buildAgentLiveContent(state: AgentLiveState): string {
  const blocks: string[] = [];
  const reasoning = state.reasoning.trim();
  const execution = state.execution.trim();

  if (reasoning) {
    const reasoningLines = reasoning
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    for (const line of reasoningLines) {
      if (/^【[^】]+】/.test(line)) {
        blocks.push(line);
      } else {
        blocks.push(`【思考】${line}`);
      }
    }
  }

  if (execution) {
    const executionLines = execution
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    for (const line of executionLines) {
      blocks.push(`【执行】${line}`);
    }
  }

  return blocks.join("\n\n");
}

function stageLabelZh(stage: string): string {
  const s = stage.trim().toLowerCase();
  if (s === "analysis") return "分析";
  if (s === "plan") return "方案";
  if (s === "search") return "检索";
  if (s === "coding") return "编码";
  if (s === "repair") return "修复";
  if (s === "done") return "完成";
  if (s === "error") return "错误";
  return s ? s.toUpperCase() : "思考";
}

function parseStatusUpdateLine(line: string): string | null {
  if (!line.startsWith("[status]")) {
    return null;
  }

  let stage = "";
  let summary = "";
  const stageSummaryFormat = line.match(/\[status\]\s*stage=([A-Za-z_]+)\s+summary=(.+)$/);
  const legacyFormat = line.match(/\[status\]\s*([A-Za-z_]+)\s*:\s*(.+)$/);
  if (stageSummaryFormat) {
    stage = (stageSummaryFormat[1] ?? "").trim();
    summary = (stageSummaryFormat[2] ?? "").trim();
  } else if (legacyFormat) {
    stage = (legacyFormat[1] ?? "").trim();
    summary = (legacyFormat[2] ?? "").trim();
  } else {
    return null;
  }

  if (!stage && !summary) return null;
  const label = stage ? stageLabelZh(stage) : "思考";
  return summary ? `【${label}】${summary}` : `【${label}】`;
}

function cleanTokenText(text: string): string {
  const normalized = text
    .replace(/\[(codex|runner)\]\s*/g, "")
    .replace(/^Job\s+[A-Za-z0-9_-]+\s+Token级流式输出.*$/gm, "");

  const lines = normalized.split("\n");
  const kept: string[] = [];
  let inHereDoc = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      kept.push("");
      continue;
    }
    const thought = parseStatusUpdateLine(line);
    if (thought) {
      kept.push(thought);
      continue;
    }
    if (/^MODE=/.test(line)) continue;
    if (/^exit=\d+/.test(line)) continue;
    if (/^\$\s+/.test(line)) {
      if (line.includes("<<'PY'") || line.includes("<<\"PY\"")) {
        inHereDoc = true;
      }
      continue;
    }
    if (inHereDoc) {
      if (line === "PY" || line === "PY'" || line === 'PY"') {
        inHereDoc = false;
      }
      continue;
    }
    if (line.startsWith("status_update(")) continue;
    if (line.startsWith("from runner_generate import status_update")) continue;
    if (line === "PY" || line === "PY'" || line === 'PY"') continue;
    kept.push(raw);
  }

  return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

function isLegacyJobNotice(message: Message): boolean {
  if (message.role !== "assistant") return false;
  const text = message.content.trim();
  if (!text) return false;
  if (text.startsWith("已创建 Job：")) return true;
  if (text.includes("正在启动并追踪终端输出")) return true;
  if (text.includes("我会基于上一轮代码与“追加指令”进行修复/迭代")) return true;
  return false;
}

function buildVisibleMessages(messages: Message[], activeJobId: string | null): Message[] {
  const filtered = messages.filter((m) => {
    if (m.messageKey?.startsWith("job-stream-")) return false;
    if (isLegacyJobNotice(m)) return false;
    if (!m.jobId) return true;
    return Boolean(activeJobId) && m.jobId === activeJobId;
  });

  const deduped: Message[] = [];
  const seenKeyIndex = new Map<string, number>();
  for (const message of filtered) {
    const key = message.messageKey?.trim();
    if (!key) {
      deduped.push(message);
      continue;
    }
    const existingIndex = seenKeyIndex.get(key);
    if (existingIndex === undefined) {
      seenKeyIndex.set(key, deduped.length);
      deduped.push(message);
      continue;
    }
    deduped[existingIndex] = message;
  }
  return deduped;
}

function clipText(text: string, maxLen: number): string {
  const brief = text.replace(/\s+/g, " ").trim();
  if (!brief) return "";
  if (brief.length <= maxLen) return brief;
  return `${brief.slice(0, maxLen)}…`;
}

function isTokenBoundaryLine(line: string): boolean {
  if (!line) return false;
  if (/^【[^】]+】/.test(line)) return true;
  if (/^\[结果\]/.test(line)) return true;
  if (/^完成，Token统计：/.test(line)) return true;
  if (/^\[backend\]\s*attempt\s+\d+\s+failed/i.test(line)) return true;
  return false;
}

function buildTokenItem(block: string, index: number): TokenStreamItem {
  const firstLine = block.split("\n").find((line) => line.trim())?.trim() ?? "";
  const stageMatch = firstLine.match(/^【([^】]+)】\s*(.*)$/);
  if (stageMatch) {
    const stage = stageMatch[1].trim();
    const summary = clipText(stageMatch[2] || "", 36);
    if (stage === "思考") {
      const thinkingContent = block
        .replace(/^【思考】\s*/m, "")
        .trim();
      return {
        kind: "thinking",
        title: summary ? `思考 · ${summary}` : "思考",
        content: thinkingContent || summary || "思考中…",
      };
    }
    return {
      kind: "stage",
      title: summary ? `${stage} · ${summary}` : stage,
      content: block,
    };
  }
  if (firstLine.startsWith("[结果]")) {
    const summary = clipText(firstLine.replace(/^\[结果\]\s*/, ""), 36);
    return {
      kind: "result",
      title: summary ? `结果 · ${summary}` : "结果",
      content: block,
    };
  }
  if (firstLine.startsWith("完成，Token统计：")) {
    return {
      kind: "usage",
      title: "Token统计",
      content: block,
    };
  }
  const backendRetryMatch = firstLine.match(/^\[backend\]\s*attempt\s+(\d+)\s+failed(?:,\s*retrying\s*\(([^)]+)\))?/i);
  if (backendRetryMatch) {
    const attempt = backendRetryMatch[1];
    const retryMode = clipText(String(backendRetryMatch[2] || ""), 16);
    return {
      kind: "backend",
      title: retryMode ? `后端重试 #${attempt} · ${retryMode}` : `后端重试 #${attempt}`,
      content: block,
    };
  }
  return {
    kind: "other",
    title: `步骤 ${index + 1}`,
    content: block,
  };
}

function splitTokenStreamContent(content: string): TokenStreamView {
  const cleaned = cleanTokenText(content.replace(/\r/g, "")).trim();
  if (!cleaned) return { items: [] };
  const lines = cleaned.split("\n");
  const blocks: string[] = [];
  let current: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (current.length > 0 && current[current.length - 1] !== "") current.push("");
      continue;
    }
    if (isTokenBoundaryLine(trimmed) && current.length > 0) {
      const block = current.join("\n").trim();
      if (block) blocks.push(block);
      current = [line];
      continue;
    }
    current.push(line);
  }
  const finalBlock = current.join("\n").trim();
  if (finalBlock) blocks.push(finalBlock);

  return {
    items: blocks.map((block, idx) => buildTokenItem(block, idx)),
  };
}

export function Cockpit({
  initialPrompt,
  initialJobId,
  messages,
  setMessages,
  runs,
  setRuns,
  onBack,
}: {
  initialPrompt: PromptData | null;
  initialJobId?: string | null;
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  runs: JobRun[];
  setRuns: React.Dispatch<React.SetStateAction<JobRun[]>>;
  onBack: () => void;
}) {
  const [activeJobId, setActiveJobId] = useState<string | null>(initialJobId ?? runs[0]?.jobId ?? null);
  const [job, setJob] = useState<JobState | null>(null);
  const [mainCpp, setMainCpp] = useState<string | null>(null);
  const [report, setReport] = useState<ReportArtifact | null>(null);

  const [isLoading, setIsLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);

  const initialRunStartedRef = useRef(false);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const terminalStreamTextRef = useRef<Record<string, string>>({});
  const agentLiveStateRef = useRef<Record<string, AgentLiveState>>({});
  const reasoningBufferRef = useRef<Record<string, ReasoningBufferState>>({});
  const hasAgentStatusEventRef = useRef<Record<string, boolean>>({});
  const lastAgentStatusSeqRef = useRef<Record<string, number>>({});
  const sealedJobsRef = useRef<Record<string, boolean>>({});

  const syncJobUrl = (jobId: string, mode: "push" | "replace" = "push") => {
    if (typeof window === "undefined") return;
    const target = `/jobs/${encodeURIComponent(jobId)}`;
    const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (current === target) return;
    const fn = mode === "replace" ? window.history.replaceState : window.history.pushState;
    fn.call(window.history, { jobId }, "", target);
  };

  const syncHomeUrl = () => {
    if (typeof window === "undefined") return;
    const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    if (current === "/") return;
    window.history.pushState({}, "", "/");
  };

  const activateJob = (jobId: string, mode: "push" | "replace" = "replace") => {
    setActiveJobId(jobId);
    syncJobUrl(jobId, mode);
  };

  const upsertAssistantMessage = useCallback((message: Message) => {
    if (!message.messageKey) {
      setMessages((prev) => [...prev, message]);
      return;
    }
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.messageKey === message.messageKey);
      if (idx < 0) return [...prev, message];
      const next = [...prev];
      next[idx] = message;
      return next;
    });
  }, [setMessages]);

  const pushTerminalTokenStream = useCallback((jobId: string, chunkText: string) => {
    if (sealedJobsRef.current[jobId]) return;
    const clean = normalizeTerminalChunk(chunkText);
    if (!clean.trim()) return;
    const prev = terminalStreamTextRef.current[jobId] ?? "";
    let next = prev + clean;
    const maxChars = 6000;
    if (next.length > maxChars) {
      next = `...(已截断，仅保留最近 ${maxChars} 字符)\n` + next.slice(-maxChars);
    }
    terminalStreamTextRef.current[jobId] = next;
    upsertAssistantMessage({
      role: "assistant",
      jobId,
      messageKey: `job-token-${jobId}`,
      streaming: true,
      content: next,
    });
  }, [upsertAssistantMessage]);

  const pushAgentStatusStream = useCallback((jobId: string, line: AgentStatusLine) => {
    if (sealedJobsRef.current[jobId]) return;
    const seq = parseNumericMeta(line.seq);
    if (seq !== null) {
      const lastSeq = lastAgentStatusSeqRef.current[jobId] ?? 0;
      if (seq <= lastSeq) return;
      lastAgentStatusSeqRef.current[jobId] = seq;
    }

    const state = agentLiveStateRef.current[jobId] || { reasoning: "", execution: "", result: "" };
    const kind = String(line.kind || "").trim();
    const delta = String(line.delta || "").replace(/\r/g, "");
    const meta: Record<string, unknown> = line.meta && typeof line.meta === "object" ? line.meta : {};
    const stream = reasoningBufferRef.current[jobId] || { buffer: "", summaryIndex: null };

    if (kind === "reasoning_summary_delta") {
      const nextSummaryIndex = parseNumericMeta(meta.summary_index);
      if (
        nextSummaryIndex !== null
        && stream.summaryIndex !== null
        && stream.summaryIndex !== nextSummaryIndex
      ) {
        flushReasoningBuffer(state, stream, true);
      }
      if (nextSummaryIndex !== null) {
        stream.summaryIndex = nextSummaryIndex;
      }
      stream.buffer += delta;
      flushReasoningBuffer(state, stream, false);
    } else if (kind === "reasoning_summary_boundary") {
      const nextSummaryIndex = parseNumericMeta(meta.summary_index);
      if (nextSummaryIndex !== null) {
        stream.summaryIndex = nextSummaryIndex;
      }
      flushReasoningBuffer(state, stream, true);
    } else {
      if (stream.buffer) {
        flushReasoningBuffer(state, stream, true);
      }
      if (kind === "command_output_delta") {
        state.execution += delta;
      } else if (kind === "agent_message_delta") {
        state.result += delta;
      } else {
        const summary = String(line.summary || "").trim();
        const stage = String(line.stage || "").trim();
        if (summary) {
          const label = stage ? stageLabelZh(stage) : "状态";
          state.reasoning += `${state.reasoning ? "\n" : ""}【${label}】${summary}`;
        }
      }
    }

    reasoningBufferRef.current[jobId] = stream;
    agentLiveStateRef.current[jobId] = state;

    const content = buildAgentLiveContent(state);
    if (!content.trim()) return;
    upsertAssistantMessage({
      role: "assistant",
      jobId,
      messageKey: `job-token-${jobId}`,
      streaming: true,
      content,
    });
  }, [upsertAssistantMessage]);

  const finalizeTerminalTokenStream = useCallback((jobId: string) => {
    const current = terminalStreamTextRef.current[jobId] ?? "";
    if (!current.trim()) return;
    upsertAssistantMessage({
      role: "assistant",
      jobId,
      messageKey: `job-token-${jobId}`,
      streaming: false,
      content: current,
    });
  }, [upsertAssistantMessage]);

  const finalizeLiveTokenStream = useCallback((jobId: string) => {
    const usedAgentStream = Boolean(hasAgentStatusEventRef.current[jobId]);
    if (!usedAgentStream) {
      finalizeTerminalTokenStream(jobId);
      return;
    }
    const state = agentLiveStateRef.current[jobId] || { reasoning: "", execution: "", result: "" };
    const stream = reasoningBufferRef.current[jobId] || { buffer: "", summaryIndex: null };
    flushReasoningBuffer(state, stream, true);
    reasoningBufferRef.current[jobId] = stream;
    const content = buildAgentLiveContent(state);
    if (!content.trim()) return;
    upsertAssistantMessage({
      role: "assistant",
      jobId,
      messageKey: `job-token-${jobId}`,
      streaming: false,
      content,
    });
  }, [finalizeTerminalTokenStream, upsertAssistantMessage]);

  const lastMainCppRef = useRef<string>("");
  useEffect(() => {
    if (mainCpp) lastMainCppRef.current = mainCpp;
  }, [mainCpp]);

  useEffect(() => {
    if (!initialJobId) return;
    setActiveJobId(initialJobId);
    setRuns((prev) => {
      if (prev.some((r) => r.jobId === initialJobId)) return prev;
      return [{ jobId: initialJobId, createdAt: Date.now() }, ...prev];
    });
    if (typeof window !== "undefined") {
      const target = `/jobs/${encodeURIComponent(initialJobId)}`;
      const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
      if (current !== target) {
        window.history.replaceState({ jobId: initialJobId }, "", target);
      }
    }
  }, [initialJobId, setRuns]);

  useEffect(() => {
    if (!activeJobId) return;
    syncJobUrl(activeJobId, "replace");
  }, [activeJobId]);

  useEffect(() => {
    const host = chatScrollRef.current;
    if (!host) return;
    host.scrollTop = host.scrollHeight;
  }, [messages, isLoading, activeJobId]);

  const createAndStartJob = async ({
    prompt,
    userMessage,
    seedMainCpp,
  }: {
    prompt: PromptData;
    userMessage?: string;
    seedMainCpp?: string;
  }) => {
    const fd = new FormData();
    fd.set("model", prompt.model);
    if (prompt.upstreamChannel) {
      fd.set("upstream_channel", prompt.upstreamChannel);
    }
    fd.set("reasoning_effort", prompt.reasoningEffort || "medium");
    fd.set("statement_md", buildStatementWithUserMessage(prompt.problemDescription, userMessage));
    fd.set("current_code_cpp", seedMainCpp ?? prompt.code ?? "");
    fd.set("time_limit_ms", String(prompt.timeLimitMs));
    fd.set("memory_limit_mb", String(prompt.memoryLimitMb));

    const zip = await buildTestsZip(prompt.testCases);
    if (zip) {
      fd.set("tests_zip", zip);
      fd.set("tests_format", "in_out_pairs");
    }

    const created = await apiFetch<{ job_id: string }>("/jobs", { method: "POST", body: fd });
    await apiFetch(`/jobs/${created.job_id}/start`, { method: "POST" });
    return created.job_id;
  };

  const startInitialRunIfNeeded = async () => {
    if (!initialPrompt) return;
    if (runs.length > 0) return;
    if (initialRunStartedRef.current) return;
    initialRunStartedRef.current = true;

    setIsLoading(true);
    setErrorText(null);
    try {
      const jobId = await createAndStartJob({ prompt: initialPrompt });
      const run: JobRun = { jobId, createdAt: Date.now() };
      setRuns([run]);
      activateJob(jobId, "push");
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      initialRunStartedRef.current = false;
      setErrorText(msg);
      setMessages([{ role: "assistant", content: `创建 Job 失败：${msg}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    startInitialRunIfNeeded();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPrompt]);

  useEffect(() => {
    if (!activeJobId) return;
    setMainCpp(null);
    setReport(null);
    setJob(null);
    sealedJobsRef.current[activeJobId] = false;
    terminalStreamTextRef.current[activeJobId] = "";
    agentLiveStateRef.current[activeJobId] = { reasoning: "", execution: "", result: "" };
    reasoningBufferRef.current[activeJobId] = { buffer: "", summaryIndex: null };
    hasAgentStatusEventRef.current[activeJobId] = false;
    lastAgentStatusSeqRef.current[activeJobId] = 0;
  }, [activeJobId]);

  const sendMessage = async () => {
    const userMsg = inputValue.trim();
    if (!userMsg || isLoading || !initialPrompt) return;

    setInputValue("");
    setErrorText(null);
    setIsLoading(true);

    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);

    try {
      const seed = lastMainCppRef.current || initialPrompt.code || "";
      const jobId = await createAndStartJob({ prompt: initialPrompt, userMessage: userMsg, seedMainCpp: seed });
      const run: JobRun = { jobId, createdAt: Date.now(), userMessage: userMsg };
      setRuns((prev) => [run, ...prev]);
      activateJob(jobId, "push");
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setMessages((prev) => [...prev, { role: "assistant", content: `创建 Job 失败：${msg}` }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Structured realtime stream from runner/appserver.
  useEffect(() => {
    if (!activeJobId) return;
    let statusOffset = 0;
    const controller = new AbortController();

    const loop = async () => {
      while (!controller.signal.aborted) {
        const url = `${API_BASE}/jobs/${activeJobId}/agent_status.sse?offset=${statusOffset}`;
        try {
          await connectSse(
            url,
            (event, data) => {
              if (event !== "agent_status") return;
              if (sealedJobsRef.current[activeJobId]) return;
              try {
                const obj = JSON.parse(data);
                const nextOffset = Number(obj.offset);
                if (Number.isFinite(nextOffset) && nextOffset >= statusOffset) {
                  statusOffset = nextOffset;
                }
                const item = obj.item as AgentStatusLine;
                if (!hasAgentStatusEventRef.current[activeJobId]) {
                  hasAgentStatusEventRef.current[activeJobId] = true;
                  terminalStreamTextRef.current[activeJobId] = "";
                }
                pushAgentStatusStream(activeJobId, item);
              } catch {}
            },
            controller.signal
          );
        } catch {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    };

    loop();
    return () => {
      controller.abort();
    };
  }, [activeJobId, pushAgentStatusStream]);

  // Terminal stream fallback (for older runners that do not emit agent_status deltas).
  useEffect(() => {
    if (!activeJobId) return;
    const decoder = new TextDecoder();
    let terminalOffset = 0;
    const controller = new AbortController();

    const loop = async () => {
      while (!controller.signal.aborted) {
        const url = `${API_BASE}/jobs/${activeJobId}/terminal.sse?offset=${terminalOffset}`;
        try {
          await connectSse(
            url,
            (event, data) => {
              if (event !== "terminal") return;
              if (sealedJobsRef.current[activeJobId]) return;
              try {
                const obj = JSON.parse(data);
                const nextOffset = Number(obj.offset);
                if (Number.isFinite(nextOffset) && nextOffset >= terminalOffset) {
                  terminalOffset = nextOffset;
                }
                if (hasAgentStatusEventRef.current[activeJobId]) return;
                const bytes = b64ToBytes(obj.chunk_b64);
                const chunkText = decoder.decode(bytes);
                pushTerminalTokenStream(activeJobId, chunkText);
              } catch {}
            },
            controller.signal
          );
        } catch {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    };

    loop();
    return () => {
      controller.abort();
    };
  }, [activeJobId, pushTerminalTokenStream]);

  // Poll job state; fetch artifacts on completion.
  useEffect(() => {
    if (!activeJobId) return;
    let cancelled = false;
    let finalized = false;
    let t: ReturnType<typeof setInterval> | null = null;

    const loadJob = async () => {
      try {
        if (finalized) return;
        const st = await apiFetch<JobState>(`/jobs/${activeJobId}`);
        if (cancelled) return;
        setJob(st);

        setRuns((prev) =>
          prev.map((r) => (r.jobId === activeJobId ? { ...r, status: st.status } : r))
        );

        const normalizedStatus = String(st.status || "").trim().toLowerCase();
        const isTerminalStatus = normalizedStatus === "succeeded" || normalizedStatus === "failed" || normalizedStatus === "cancelled";
        if (!isTerminalStatus) return;

        finalized = true;
        sealedJobsRef.current[activeJobId] = true;
        if (t) clearInterval(t);
        finalizeLiveTokenStream(activeJobId);

        if (st.status === "succeeded") {
          const [cpp, rep] = await Promise.all([
            apiFetch<string>(`/jobs/${activeJobId}/artifacts/main.cpp`).catch(() => null),
            apiFetch<ReportArtifact>(`/jobs/${activeJobId}/artifacts/report.json`).catch(() => null),
          ]);
          if (cancelled) return;
          setMainCpp(cpp);
          setReport(rep);

          upsertAssistantMessage({
            role: "assistant",
            jobId: activeJobId,
            messageKey: `job-final-${activeJobId}`,
            content: `Job 已结束（status=${st.status}）。代码与测试详情请查看右侧面板。`,
          });
        } else {
          const errorHint = formatJobError(st.error);
          if (cancelled) return;
          setMainCpp(null);
          setReport(null);
          upsertAssistantMessage({
            role: "assistant",
            jobId: activeJobId,
            messageKey: `job-final-${activeJobId}`,
            content: errorHint
              ? `Job 已结束（status=${st.status}）。失败原因：${errorHint}`
              : `Job 已结束（status=${st.status}）。`,
          });
        }
      } catch (e: unknown) {
        if (cancelled) return;
        const msg = getErrorMessage(e);
        setErrorText(msg);
      }
    };

    loadJob();
    t = setInterval(loadJob, 2000);
    return () => {
      cancelled = true;
      if (t) clearInterval(t);
    };
  }, [activeJobId, finalizeLiveTokenStream, setRuns, upsertAssistantMessage]);

  const cancelJob = async () => {
    if (!activeJobId) return;
    try {
      await apiFetch(`/jobs/${activeJobId}/cancel`, { method: "POST" });
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    }
  };

  const handleBack = () => {
    onBack();
    syncHomeUrl();
  };

  const canContinueChat = Boolean(initialPrompt);
  const visibleMessages = buildVisibleMessages(messages, activeJobId);
  const currentRunStatus = runs.find((run) => run.jobId === activeJobId)?.status;
  const statusMeta = resolveJobStatusMeta(job?.status ?? currentRunStatus);
  const isRunningStatus = statusMeta.lifecycle === "running";

  return (
    <div className="h-full w-full min-h-0 p-4 md:p-4 animate-in fade-in duration-500 bg-transparent overflow-hidden">
      <GlassPanel
        intensity="high"
        className="h-full min-h-0 flex flex-col border-slate-200 overflow-hidden"
        innerClassName="h-full min-h-0 flex flex-col"
      >
        <div className="shrink-0 border-b border-slate-200 bg-white/92 px-4 md:px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="text-[11px] uppercase tracking-wide text-slate-400 font-semibold">工作区</div>
              <div className="text-xs text-slate-700 font-mono truncate">{activeJobId ?? "暂无 Job"}</div>
              <div className="text-[11px] text-slate-500 mt-1">
                任务状态:
                <span
                  className={[
                    "ml-1.5 inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold",
                    statusMeta.badgeClassName,
                  ].join(" ")}
                >
                  <span
                    className={[
                      "h-1.5 w-1.5 rounded-full",
                      isRunningStatus ? "animate-pulse" : "",
                      statusMeta.dotClassName,
                    ].join(" ")}
                  />
                  {statusMeta.headline} · {statusMeta.phase}
                </span>
                <span className="mx-2 text-slate-300">|</span>
                原始状态: <span className="font-mono">{statusMeta.raw}</span>
                <span className="mx-2 text-slate-300">|</span>
                模型: <span className="font-mono">{job?.model ?? initialPrompt?.model ?? "-"}</span>
                <span className="mx-2 text-slate-300">|</span>
                思考量: <span className="font-mono">{job?.reasoning_effort ?? initialPrompt?.reasoningEffort ?? "medium"}</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={cancelJob}
                disabled={!isRunningStatus}
                className={[
                  "px-3.5 py-2 rounded-lg text-xs font-semibold border",
                  isRunningStatus
                    ? "text-slate-600 bg-white border-slate-200 hover:text-rose-600"
                    : "text-slate-400 bg-slate-100/80 border-slate-200 cursor-not-allowed",
                ].join(" ")}
              >
                取消任务
              </button>
              <button
                onClick={handleBack}
                className="px-3.5 py-2 rounded-lg text-xs font-semibold text-slate-600 bg-white border border-slate-200 hover:text-indigo-600"
              >
                返回大厅
              </button>
            </div>
          </div>
        </div>

        {errorText ? (
          <div className="mx-4 md:mx-5 mt-4 rounded-xl border border-rose-200 bg-rose-50/70 px-4 py-3 text-sm text-rose-700">
            {errorText}
          </div>
        ) : null}

        <div className="flex-1 min-h-0 grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(360px,42%)] bg-slate-50/[0.08]">
          <div className="min-h-0 flex flex-col xl:border-r border-slate-200/80">
            <div
              ref={chatScrollRef}
              className="flex-1 min-h-0 overflow-y-auto space-y-3 px-4 md:px-5 py-4 md:py-5 scroll-smooth custom-scrollbar"
            >
              {visibleMessages.map((m, i) => {
                const isTokenStream = m.messageKey?.startsWith("job-token-") ?? false;
                const tokenView = isTokenStream ? splitTokenStreamContent(m.content) : null;
                return (
                  <div
                    key={i}
                    className={`flex flex-col ${m.role === "user" ? "items-end" : "items-start"} animate-in slide-in-from-bottom-2 duration-500`}
                  >
                    <div
                      className={[
                        isTokenStream ? "w-full max-w-full rounded-2xl" : "max-w-[92%] rounded-2xl",
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
                                        <div
                                          className={[
                                            "px-3 py-2.5 text-[11px] leading-5 text-slate-400 bg-[#fbfcfd] space-y-1",
                                          ].join(" ")}
                                        >
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
              {isLoading ? (
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

            <div className="shrink-0 border-t border-slate-200 px-4 md:px-5 py-2.5 md:py-3 bg-white/92">
              <div className="h-12 rounded-xl border border-slate-200 bg-white px-3 md:px-4 flex items-center gap-2 shadow-sm">
                <input
                  className="flex-1 min-w-0 bg-transparent border-none outline-none text-slate-800 placeholder:text-slate-400 text-sm disabled:opacity-40"
                  placeholder={canContinueChat ? "继续对话（会创建新 Job 进行修复/迭代）..." : "当前为只读 Job 追踪，返回大厅后可继续对话"}
                  value={inputValue}
                  disabled={!canContinueChat}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                />
                <button
                  onClick={sendMessage}
                  disabled={!canContinueChat || isLoading || !inputValue.trim()}
                  className="icon-wrap w-9 h-9 shrink-0 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/20 transition-all disabled:opacity-20"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.4}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h11m-5-5 5 5-5 5m7-10v10" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <div className="min-h-0 flex flex-col bg-white/58">
            <div className="shrink-0 px-4 md:px-5 py-3 border-b border-slate-200/80 bg-white/90">
              <div className="text-xs font-semibold text-slate-600 uppercase tracking-wide">代码</div>
              <div className="text-[11px] text-slate-500 mt-1">main.cpp（最新产物）</div>
            </div>

            <div className="flex-1 min-h-0 overflow-auto custom-scrollbar">
              <pre className="p-4 md:p-5 text-slate-700 whitespace-pre font-mono leading-relaxed text-xs md:text-sm">
{mainCpp ?? "// 暂无代码（可能尚未生成或已清理）"}
              </pre>
            </div>

            {report?.summary?.first_failure ? (
              <div className="shrink-0 border-t border-rose-200 bg-rose-50/70 px-4 md:px-5 py-2.5 text-[11px] text-rose-700">
                首个失败用例: {report.summary.first_failure} ({report.summary.first_failure_verdict}) {report.summary.first_failure_message}
              </div>
            ) : null}
          </div>
        </div>
      </GlassPanel>
    </div>
  );
}
