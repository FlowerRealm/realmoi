// AUTO_COMMENT_HEADER_V1: useMcpSubscription.ts
// 说明：Cockpit MCP 订阅（job.subscribe → agent_status / terminal 通知）。

"use client";

import { useEffect } from "react";
import { getMcpClient } from "@/lib/mcp";
import type { AgentStatusLine } from "./agentLive";
import { b64ToBytes } from "./encoding";
import type { StreamRefs } from "./controllerTypes";

export function useMcpSubscription(args: {
  activeJobId: string | null;
  pushAgentStatusStream: (jobId: string, line: AgentStatusLine) => void;
  pushTerminalTokenStream: (jobId: string, chunkText: string) => void;
  streamRefs: StreamRefs;
}) {
  const { activeJobId, pushAgentStatusStream, pushTerminalTokenStream, streamRefs } = args;

  useEffect(() => {
    if (!activeJobId) return;
    let cancelled = false;
    const decoder = new TextDecoder();
    let agentOffset = 0;
    let terminalOffset = 0;

    const client = getMcpClient();
    const unsubscribe = client.onNotification((method, params) => {
      if (!params || typeof params !== "object") return;
      const payload = params as Record<string, unknown>;
      if (String(payload["job_id"] ?? "") !== activeJobId) return;
      if (streamRefs.sealedJobsRef.current[activeJobId]) return;

      if (method === "agent_status") {
        try {
          const nextOffset = Number(payload["offset"]);
          if (Number.isFinite(nextOffset) && nextOffset >= agentOffset) {
            agentOffset = nextOffset;
          }
          const item = payload["item"] as AgentStatusLine;
          if (!streamRefs.hasAgentStatusEventRef.current[activeJobId]) {
            streamRefs.hasAgentStatusEventRef.current[activeJobId] = true;
            streamRefs.terminalStreamTextRef.current[activeJobId] = "";
          }
          pushAgentStatusStream(activeJobId, item);
        } catch {
          // 忽略单条通知解析错误，避免整个订阅链路被打断
        }
        return;
      }

      if (method === "terminal") {
        try {
          const nextOffset = Number(payload["offset"]);
          if (Number.isFinite(nextOffset) && nextOffset >= terminalOffset) {
            terminalOffset = nextOffset;
          }
          if (streamRefs.hasAgentStatusEventRef.current[activeJobId]) return;
          const bytes = b64ToBytes(String(payload["chunk_b64"] ?? ""));
          const chunkText = decoder.decode(bytes);
          pushTerminalTokenStream(activeJobId, chunkText);
        } catch {
          // 同上：忽略单条通知解析错误
        }
      }
    });

    const loop = async () => {
      while (!cancelled) {
        try {
          await client.callTool("job.subscribe", {
            job_id: activeJobId,
            streams: ["agent_status", "terminal"],
            agent_status_offset: agentOffset,
            terminal_offset: terminalOffset,
          });
          await client.waitForDisconnect();
        } catch {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    };

    loop();
    return () => {
      cancelled = true;
      unsubscribe();
      client.callTool("job.unsubscribe", { job_id: activeJobId }).catch(() => null);
    };
  }, [activeJobId, pushAgentStatusStream, pushTerminalTokenStream, streamRefs]);
}

