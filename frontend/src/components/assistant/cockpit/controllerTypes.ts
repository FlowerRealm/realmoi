// AUTO_COMMENT_HEADER_V1: controllerTypes.ts
// 说明：Cockpit controller 类型定义（与 UI 解耦）。

"use client";

import type React from "react";
import type { JobRun, Message, PromptData } from "../types";
import type { AgentLiveState, ReasoningBufferState } from "./agentLive";

export type CockpitControllerArgs = {
  initialPrompt: PromptData | null;
  initialJobId?: string | null;
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  runs: JobRun[];
  setRuns: React.Dispatch<React.SetStateAction<JobRun[]>>;
  onBack: () => void;
};

export type StreamRefs = {
  terminalStreamTextRef: React.MutableRefObject<Record<string, string>>;
  agentLiveStateRef: React.MutableRefObject<Record<string, AgentLiveState>>;
  reasoningBufferRef: React.MutableRefObject<Record<string, ReasoningBufferState>>;
  hasAgentStatusEventRef: React.MutableRefObject<Record<string, boolean>>;
  lastAgentStatusSeqRef: React.MutableRefObject<Record<string, number>>;
  sealedJobsRef: React.MutableRefObject<Record<string, boolean>>;
};

