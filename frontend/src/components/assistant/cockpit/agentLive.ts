// AUTO_COMMENT_HEADER_V1: agentLive.ts
// 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

import { stageLabelZh } from "./stage";

export type AgentStatusLine = {
  seq?: number | string;
  stage?: string;
  summary?: string;
  kind?: string;
  delta?: string;
  meta?: Record<string, unknown>;
};

export type AgentLiveState = {
  reasoning: string;
  execution: string;
  result: string;
};

export type ReasoningBufferState = {
  buffer: string;
  summaryIndex: number | null;
};

export function parseNumericMeta(value: unknown): number | null {
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

export function flushReasoningBuffer(state: AgentLiveState, stream: ReasoningBufferState, force: boolean): void {
  const { lines, rest } = splitReasoningSegments(stream.buffer, force);
  appendReasoningLines(state, lines);
  stream.buffer = rest;
}

export function buildAgentLiveContent(state: AgentLiveState): string {
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

export function getReasoningBufferState(
  buffersByJobId: Record<string, ReasoningBufferState>,
  jobId: string
): ReasoningBufferState {
  return buffersByJobId[jobId] || { buffer: "", summaryIndex: null };
}

export function getAgentLiveState(statesByJobId: Record<string, AgentLiveState>, jobId: string): AgentLiveState {
  return statesByJobId[jobId] || { reasoning: "", execution: "", result: "" };
}

export function applyAgentStatusLineToState(args: {
  state: AgentLiveState;
  stream: ReasoningBufferState;
  line: AgentStatusLine;
}): { state: AgentLiveState; stream: ReasoningBufferState } {
  const { state, stream, line } = args;
  const kind = String(line.kind || "").trim();
  const delta = String(line.delta || "").replace(/\r/g, "");
  const meta: Record<string, unknown> = line.meta && typeof line.meta === "object" ? line.meta : {};

  const flushBufferedReasoning = (force: boolean) => {
    if (!stream.buffer) return;
    flushReasoningBuffer(state, stream, force);
  };

  if (kind === "reasoning_summary_delta") {
    const nextSummaryIndex = parseNumericMeta(meta.summary_index);
    if (nextSummaryIndex !== null && stream.summaryIndex !== null && stream.summaryIndex !== nextSummaryIndex) {
      flushReasoningBuffer(state, stream, true);
    }
    if (nextSummaryIndex !== null) {
      stream.summaryIndex = nextSummaryIndex;
    }
    stream.buffer += delta;
    flushReasoningBuffer(state, stream, false);
    return { state, stream };
  }

  if (kind === "reasoning_summary_boundary") {
    const nextSummaryIndex = parseNumericMeta(meta.summary_index);
    if (nextSummaryIndex !== null) {
      stream.summaryIndex = nextSummaryIndex;
    }
    flushReasoningBuffer(state, stream, true);
    return { state, stream };
  }

  flushBufferedReasoning(true);

  if (kind === "command_output_delta") {
    state.execution += delta;
    return { state, stream };
  }

  if (kind === "agent_message_delta") {
    state.result += delta;
    return { state, stream };
  }

  const summary = String(line.summary || "").trim();
  if (!summary) return { state, stream };

  const stage = String(line.stage || "").trim();
  const label = stage ? stageLabelZh(stage) : "状态";
  state.reasoning += `${state.reasoning ? "\n" : ""}【${label}】${summary}`;
  return { state, stream };
}
