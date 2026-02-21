// AUTO_COMMENT_HEADER_V1: useJobPolling.ts
// 说明：Cockpit Job 状态轮询（job.get_state + artifacts 拉取）。

"use client";

import React, { useEffect } from "react";
import { getErrorMessage } from "@/lib/api";
import { getMcpClient } from "@/lib/mcp";
import type { JobRun, JobState, Message, ReportArtifact, SolutionArtifact } from "../types";
import type { StreamRefs } from "./controllerTypes";
import { buildFeedbackMessageContent } from "./feedback";

export function useJobPolling(args: {
  activeJobId: string | null;
  finalizeLiveTokenStream: (jobId: string) => void;
  setJob: (v: JobState | null) => void;
  setRuns: React.Dispatch<React.SetStateAction<JobRun[]>>;
  setMainCpp: (v: string | null) => void;
  setSolution: (v: SolutionArtifact | null) => void;
  setReport: (v: ReportArtifact | null) => void;
  setErrorText: (v: string | null) => void;
  upsertAssistantMessage: (m: Message) => void;
  streamRefs: StreamRefs;
}) {
  const {
    activeJobId,
    finalizeLiveTokenStream,
    setJob,
    setRuns,
    setMainCpp,
    setSolution,
    setReport,
    setErrorText,
    upsertAssistantMessage,
    streamRefs,
  } = args;

  useEffect(() => {
    if (!activeJobId) return;
    let cancelled = false;
    let finalized = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const loadJob = async () => {
      try {
        if (finalized) return;
        const client = getMcpClient();
        const st = (await client.callTool("job.get_state", { job_id: activeJobId })) as JobState;
        if (cancelled) return;
        setJob(st);

        setRuns((prev) => prev.map((r) => (r.jobId === activeJobId ? { ...r, status: st.status } : r)));

        const normalizedStatus = String(st.status || "").trim().toLowerCase();
        const isTerminalStatus = normalizedStatus === "succeeded" || normalizedStatus === "failed" || normalizedStatus === "cancelled";
        if (!isTerminalStatus) return;

        finalized = true;
        streamRefs.sealedJobsRef.current[activeJobId] = true;
        if (timer) clearInterval(timer);
        finalizeLiveTokenStream(activeJobId);

        const artifacts = await client.callTool<{ items?: Record<string, unknown> }>("job.get_artifacts", {
          job_id: activeJobId,
          names: ["main.cpp", "solution.json", "report.json"],
        });
        const items = artifacts?.items ?? {};
        const cpp = (items["main.cpp"] as string | null) ?? null;
        const sol = (items["solution.json"] as SolutionArtifact | null) ?? null;
        const rep = (items["report.json"] as ReportArtifact | null) ?? null;
        if (cancelled) return;
        setMainCpp(cpp);
        setSolution(sol);
        setReport(rep);

        if (sol) {
          const hasDiffLocal = Boolean(String(sol.seed_code_full_diff || "").trim() || String(sol.seed_code_fix_diff || "").trim());
          const feedbackText = buildFeedbackMessageContent(sol, hasDiffLocal);
          if (feedbackText.trim()) {
            upsertAssistantMessage({
              role: "assistant",
              jobId: activeJobId,
              messageKey: `job-feedback-${activeJobId}`,
              streaming: false,
              content: feedbackText,
            });
          }
        }
      } catch (e: unknown) {
        if (cancelled) return;
        const msg = getErrorMessage(e);
        setErrorText(msg);
      }
    };

    loadJob();
    timer = setInterval(loadJob, 2000);
    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, [
    activeJobId,
    finalizeLiveTokenStream,
    setErrorText,
    setJob,
    setMainCpp,
    setReport,
    setRuns,
    setSolution,
    streamRefs,
    upsertAssistantMessage,
  ]);
}

