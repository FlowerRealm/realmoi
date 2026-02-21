// AUTO_COMMENT_HEADER_V1: useJobTestsLoader.ts
// 说明：Cockpit tests 列表加载（job.get_tests）。

"use client";

import { useEffect } from "react";
import { getErrorMessage } from "@/lib/api";
import { getMcpClient } from "@/lib/mcp";
import type { JobTestMeta } from "../types";

export function useJobTestsLoader(args: {
  activeJobId: string | null;
  setJobTests: (v: JobTestMeta[]) => void;
  setJobTestsError: (v: string | null) => void;
}) {
  const { activeJobId, setJobTests, setJobTestsError } = args;

  useEffect(() => {
    if (!activeJobId) return;
    let cancelled = false;

    const loadTests = async () => {
      try {
        const client = getMcpClient();
        const resp = await client.callTool<{ items?: JobTestMeta[] }>("job.get_tests", { job_id: activeJobId });
        if (cancelled) return;
        setJobTests(Array.isArray(resp?.items) ? (resp.items as JobTestMeta[]) : []);
        setJobTestsError(null);
      } catch (e: unknown) {
        if (cancelled) return;
        setJobTests([]);
        setJobTestsError(getErrorMessage(e));
      }
    };

    loadTests();
    return () => {
      cancelled = true;
    };
  }, [activeJobId, setJobTests, setJobTestsError]);
}

