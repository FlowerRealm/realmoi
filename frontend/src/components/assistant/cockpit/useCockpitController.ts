// AUTO_COMMENT_HEADER_V1: useCockpitController.ts
// 说明：Cockpit controller 聚合层（组合各个 hooks，输出 CockpitView 需要的 vm）。

"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getErrorMessage } from "@/lib/api";
import { getMcpClient } from "@/lib/mcp";
import type { JobRun, JobState, JobTestMeta, Message, PromptData, ReportArtifact, SolutionArtifact } from "../types";
import type { CockpitControllerArgs } from "./controllerTypes";
import { resetStreamsForJob } from "./streamReset";
import { syncHomeUrl, syncJobUrl } from "./urlSync";
import { resolveJobStatusMeta } from "./jobStatus";
import { buildVisibleMessages } from "./messages";
import { useJobCreator } from "./useJobCreator";
import { useJobPolling } from "./useJobPolling";
import { useJobTestsLoader } from "./useJobTestsLoader";
import { useMcpSubscription } from "./useMcpSubscription";
import { useStreamingMessages } from "./useStreamingMessages";

export function useCockpitController(args: CockpitControllerArgs) {
  const { initialPrompt, initialJobId, messages, setMessages, runs, setRuns, onBack } = args;

  const [activeJobId, setActiveJobId] = useState<string | null>(initialJobId ?? runs[0]?.jobId ?? null);
  const [job, setJob] = useState<JobState | null>(null);
  const [mainCpp, setMainCpp] = useState<string | null>(null);
  const [report, setReport] = useState<ReportArtifact | null>(null);
  const [jobTests, setJobTests] = useState<JobTestMeta[] | null>(null);
  const [jobTestsError, setJobTestsError] = useState<string | null>(null);
  const [solution, setSolution] = useState<SolutionArtifact | null>(null);
  const [codeView, setCodeView] = useState<"final" | "diff">("final");

  const [isLoading, setIsLoading] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [errorText, setErrorText] = useState<string | null>(null);

  const chatScrollRef = useRef<HTMLDivElement | null>(null);
  const lastMainCppRef = useRef<string>("");

  const { upsertAssistantMessage, pushTerminalTokenStream, pushAgentStatusStream, finalizeLiveTokenStream, streamRefs } =
    useStreamingMessages({ setMessages });

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

  const activateJob = useCallback((jobId: string, mode: "push" | "replace" = "replace") => {
    setActiveJobId(jobId);
    syncJobUrl(jobId, mode);
  }, []);

  const handleBack = useCallback(() => {
    onBack();
    syncHomeUrl();
  }, [onBack]);

  const { startInitialRunIfNeeded, sendMessage } = useJobCreator({
    initialPrompt,
    runs,
    setRuns,
    setMessages,
    activateJob,
    lastMainCppRef,
    isLoading,
    setIsLoading,
    inputValue,
    setInputValue,
    setErrorText,
  });

  useEffect(() => {
    startInitialRunIfNeeded();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialPrompt]);

  useEffect(() => {
    if (!activeJobId) return;
    setMainCpp(null);
    setReport(null);
    setSolution(null);
    setJob(null);
    setCodeView("final");
    setJobTests(null);
    setJobTestsError(null);
    resetStreamsForJob(streamRefs, activeJobId);
  }, [activeJobId, streamRefs]);

  useJobTestsLoader({
    activeJobId,
    setJobTests: (v) => setJobTests(v),
    setJobTestsError: (v) => setJobTestsError(v),
  });

  useMcpSubscription({ activeJobId, pushAgentStatusStream, pushTerminalTokenStream, streamRefs });

  useJobPolling({
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
  });

  const cancelJob = useCallback(async () => {
    if (!activeJobId) return;
    try {
      const client = getMcpClient();
      await client.callTool("job.cancel", { job_id: activeJobId });
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    }
  }, [activeJobId]);

  const canContinueChat = Boolean(initialPrompt);
  const visibleMessages = useMemo(() => buildVisibleMessages(messages, activeJobId), [messages, activeJobId]);
  const currentRunStatus = runs.find((run) => run.jobId === activeJobId)?.status;
  const statusMeta = resolveJobStatusMeta(job?.status ?? currentRunStatus);
  const isRunningStatus = statusMeta.lifecycle === "running";
  const diffText = solution?.seed_code_full_diff?.trim() || solution?.seed_code_fix_diff?.trim() || "";
  const hasDiff = Boolean(diffText);

  const vm = useMemo(
    () => ({
      activeJobId,
      errorText,
      visibleMessages,

      isLoading,
      canContinueChat,
      inputValue,
      onInputValueChange: setInputValue,
      onSendMessage: sendMessage,

      codeView,
      onSetCodeView: setCodeView,
      mainCpp,
      diffText,
      hasDiff,
      report,

      jobTests,
      jobTestsError,

      statusMeta,
      modelLabel: job?.model ?? initialPrompt?.model ?? "-",
      reasoningEffortLabel: job?.reasoning_effort ?? initialPrompt?.reasoningEffort ?? "medium",
      isRunningStatus,

      chatScrollRef,

      onCancelJob: cancelJob,
      onBack: handleBack,
    }),
    [
      activeJobId,
      cancelJob,
      canContinueChat,
      codeView,
      diffText,
      errorText,
      handleBack,
      hasDiff,
      initialPrompt?.model,
      initialPrompt?.reasoningEffort,
      inputValue,
      isLoading,
      isRunningStatus,
      job?.model,
      job?.reasoning_effort,
      jobTests,
      jobTestsError,
      mainCpp,
      report,
      sendMessage,
      solution,
      statusMeta,
      visibleMessages,
    ]
  );

  return { vm };
}

