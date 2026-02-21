// AUTO_COMMENT_HEADER_V1: useStreamingMessages.ts
// 说明：Cockpit 消息流写入（terminal/agent_status → Message）。

"use client";

import React, { useCallback, useRef } from "react";
import type { Message } from "../types";
import type { AgentLiveState, AgentStatusLine, ReasoningBufferState } from "./agentLive";
import {
  applyAgentStatusLineToState,
  buildAgentLiveContent,
  flushReasoningBuffer,
  getAgentLiveState,
  getReasoningBufferState,
  parseNumericMeta,
} from "./agentLive";
import type { StreamRefs } from "./controllerTypes";
import { normalizeTerminalChunk } from "./terminal";

export function useStreamingMessages(args: {
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
}): {
  upsertAssistantMessage: (message: Message) => void;
  pushTerminalTokenStream: (jobId: string, chunkText: string) => void;
  pushAgentStatusStream: (jobId: string, line: AgentStatusLine) => void;
  finalizeLiveTokenStream: (jobId: string) => void;
  streamRefs: StreamRefs;
} {
  const { setMessages } = args;

  const terminalStreamTextRef = useRef<Record<string, string>>({});
  const agentLiveStateRef = useRef<Record<string, AgentLiveState>>({});
  const reasoningBufferRef = useRef<Record<string, ReasoningBufferState>>({});
  const hasAgentStatusEventRef = useRef<Record<string, boolean>>({});
  const lastAgentStatusSeqRef = useRef<Record<string, number>>({});
  const sealedJobsRef = useRef<Record<string, boolean>>({});

  const upsertAssistantMessage = useCallback(
    (message: Message) => {
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
    },
    [setMessages]
  );

  const pushTerminalTokenStream = useCallback(
    (jobId: string, chunkText: string) => {
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
    },
    [upsertAssistantMessage]
  );

  const pushAgentStatusStream = useCallback(
    (jobId: string, line: AgentStatusLine) => {
      if (sealedJobsRef.current[jobId]) return;
      const seq = parseNumericMeta(line.seq);
      if (seq !== null) {
        const lastSeq = lastAgentStatusSeqRef.current[jobId] ?? 0;
        if (seq <= lastSeq) return;
        lastAgentStatusSeqRef.current[jobId] = seq;
      }

      const state = getAgentLiveState(agentLiveStateRef.current, jobId);
      const stream = getReasoningBufferState(reasoningBufferRef.current, jobId);
      const { state: nextState, stream: nextStream } = applyAgentStatusLineToState({ state, stream, line });
      reasoningBufferRef.current[jobId] = nextStream;
      agentLiveStateRef.current[jobId] = nextState;

      const content = buildAgentLiveContent(nextState);
      if (!content.trim()) return;
      upsertAssistantMessage({
        role: "assistant",
        jobId,
        messageKey: `job-token-${jobId}`,
        streaming: true,
        content,
      });
    },
    [upsertAssistantMessage]
  );

  const finalizeTerminalTokenStream = useCallback(
    (jobId: string) => {
      const current = terminalStreamTextRef.current[jobId] ?? "";
      if (!current.trim()) return;
      upsertAssistantMessage({
        role: "assistant",
        jobId,
        messageKey: `job-token-${jobId}`,
        streaming: false,
        content: current,
      });
    },
    [upsertAssistantMessage]
  );

  const finalizeLiveTokenStream = useCallback(
    (jobId: string) => {
      const usedAgentStream = Boolean(hasAgentStatusEventRef.current[jobId]);
      if (!usedAgentStream) {
        finalizeTerminalTokenStream(jobId);
        return;
      }
      const state = getAgentLiveState(agentLiveStateRef.current, jobId);
      const stream = getReasoningBufferState(reasoningBufferRef.current, jobId);
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
    },
    [finalizeTerminalTokenStream, upsertAssistantMessage]
  );

  return {
    upsertAssistantMessage,
    pushTerminalTokenStream,
    pushAgentStatusStream,
    finalizeLiveTokenStream,
    streamRefs: {
      terminalStreamTextRef,
      agentLiveStateRef,
      reasoningBufferRef,
      hasAgentStatusEventRef,
      lastAgentStatusSeqRef,
      sealedJobsRef,
    },
  };
}

