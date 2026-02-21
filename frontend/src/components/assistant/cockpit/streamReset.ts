// AUTO_COMMENT_HEADER_V1: streamReset.ts
// 说明：Cockpit 每个 job 的流状态重置（terminal / agent_status）。

"use client";

import type { StreamRefs } from "./controllerTypes";

export function resetStreamsForJob(refs: StreamRefs, jobId: string) {
  refs.sealedJobsRef.current[jobId] = false;
  refs.terminalStreamTextRef.current[jobId] = "";
  refs.agentLiveStateRef.current[jobId] = { reasoning: "", execution: "", result: "" };
  refs.reasoningBufferRef.current[jobId] = { buffer: "", summaryIndex: null };
  refs.hasAgentStatusEventRef.current[jobId] = false;
  refs.lastAgentStatusSeqRef.current[jobId] = 0;
}

