// AUTO_COMMENT_HEADER_V1: useJobCreator.ts
// 说明：Cockpit Job 创建与发送消息（job.create + job.start）。

"use client";

import React, { useCallback, useRef } from "react";
import { getErrorMessage } from "@/lib/api";
import { getMcpClient } from "@/lib/mcp";
import type { JobRun, Message, PromptData } from "../types";
import { buildTestsZip } from "../testsZip";
import { blobToBase64 } from "./blob";
import { buildStatementWithUserMessage } from "./feedback";

export function useJobCreator(args: {
  initialPrompt: PromptData | null;
  runs: JobRun[];
  setRuns: React.Dispatch<React.SetStateAction<JobRun[]>>;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  activateJob: (jobId: string, mode: "push" | "replace") => void;
  lastMainCppRef: React.MutableRefObject<string>;
  isLoading: boolean;
  setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
  inputValue: string;
  setInputValue: React.Dispatch<React.SetStateAction<string>>;
  setErrorText: React.Dispatch<React.SetStateAction<string | null>>;
}): {
  startInitialRunIfNeeded: () => void;
  sendMessage: () => Promise<void>;
} {
  const {
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
  } = args;

  const initialRunStartedRef = useRef(false);

  const createAndStartJob = useCallback(
    async (opts: { prompt: PromptData; userMessage?: string; seedMainCpp?: string }) => {
      const client = getMcpClient();
      const zip = await buildTestsZip(opts.prompt.testCases);
      const testsZipB64 = zip ? await blobToBase64(zip) : "";

      const created = await client.callTool<{ job_id: string }>("job.create", {
        model: opts.prompt.model,
        upstream_channel: opts.prompt.upstreamChannel || "",
        reasoning_effort: opts.prompt.reasoningEffort || "medium",
        statement_md: buildStatementWithUserMessage(opts.prompt.problemDescription, opts.userMessage),
        current_code_cpp: opts.seedMainCpp ?? opts.prompt.code ?? "",
        time_limit_ms: opts.prompt.timeLimitMs,
        memory_limit_mb: opts.prompt.memoryLimitMb,
        tests_zip_b64: testsZipB64,
        tests_format: zip ? "in_out_pairs" : "auto",
      });

      await client.callTool("job.start", { job_id: created.job_id });
      return created.job_id;
    },
    []
  );

  const startInitialRunIfNeeded = useCallback(() => {
    if (!initialPrompt) return;
    if (runs.length > 0) return;
    if (initialRunStartedRef.current) return;
    initialRunStartedRef.current = true;

    setIsLoading(true);
    setErrorText(null);
    createAndStartJob({ prompt: initialPrompt })
      .then((jobId) => {
        const run: JobRun = { jobId, createdAt: Date.now(), seedMainCpp: initialPrompt.code ?? "" };
        setRuns([run]);
        activateJob(jobId, "push");
      })
      .catch((e: unknown) => {
        const msg = getErrorMessage(e);
        initialRunStartedRef.current = false;
        setErrorText(msg);
        setMessages([{ role: "assistant", content: `创建 Job 失败：${msg}` }]);
      })
      .finally(() => {
        setIsLoading(false);
      });
  }, [activateJob, createAndStartJob, initialPrompt, runs.length, setErrorText, setIsLoading, setMessages, setRuns]);

  const sendMessage = useCallback(async () => {
    const userMsg = inputValue.trim();
    if (!userMsg || isLoading || !initialPrompt) return;

    setInputValue("");
    setErrorText(null);
    setIsLoading(true);
    setMessages((prev) => [...prev, { role: "user", content: userMsg }]);

    try {
      const seed = lastMainCppRef.current || initialPrompt.code || "";
      const jobId = await createAndStartJob({ prompt: initialPrompt, userMessage: userMsg, seedMainCpp: seed });
      const run: JobRun = { jobId, createdAt: Date.now(), userMessage: userMsg, seedMainCpp: seed };
      setRuns((prev) => [run, ...prev]);
      activateJob(jobId, "push");
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setMessages((prev) => [...prev, { role: "assistant", content: `创建 Job 失败：${msg}` }]);
    } finally {
      setIsLoading(false);
    }
  }, [
    activateJob,
    createAndStartJob,
    initialPrompt,
    inputValue,
    isLoading,
    lastMainCppRef,
    setErrorText,
    setInputValue,
    setIsLoading,
    setMessages,
    setRuns,
  ]);

  return { startInitialRunIfNeeded, sendMessage };
}

