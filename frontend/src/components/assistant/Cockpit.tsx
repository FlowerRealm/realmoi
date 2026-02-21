// AUTO_COMMENT_HEADER_V1: Cockpit.tsx
// 说明：Cockpit 入口组件；数据层与通讯层已下沉到 `cockpit/useCockpitController.ts`。

"use client";

import React from "react";
import type { JobRun, Message, PromptData } from "./types";
import { CockpitView } from "./CockpitView";
import { useCockpitController } from "./cockpit/useCockpitController";

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
  const { vm } = useCockpitController({
    initialPrompt,
    initialJobId,
    messages,
    setMessages,
    runs,
    setRuns,
    onBack,
  });
  return (
    <CockpitView vm={vm} />
  );
}
