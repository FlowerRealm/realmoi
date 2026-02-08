"use client";

import { getToken } from "./auth";

type SseHandler = (event: string, data: string) => void;

export async function connectSse(url: string, onEvent: SseHandler, signal: AbortSignal) {
  const token = getToken();
  const resp = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  });
  if (!resp.ok || !resp.body) throw new Error(`SSE HTTP ${resp.status}`);

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let currentEvent = "message";
  let currentData: string[] = [];

  const flush = () => {
    if (currentData.length === 0) return;
    onEvent(currentEvent, currentData.join("\n"));
    currentEvent = "message";
    currentData = [];
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });

    while (true) {
      const idx = buf.indexOf("\n");
      if (idx === -1) break;
      const line = buf.slice(0, idx).replace(/\r$/, "");
      buf = buf.slice(idx + 1);

      if (line === "") {
        flush();
        continue;
      }

      if (line.startsWith("event:")) {
        currentEvent = line.slice("event:".length).trim();
        continue;
      }
      if (line.startsWith("data:")) {
        currentData.push(line.slice("data:".length).trimStart());
        continue;
      }
    }
  }
}

