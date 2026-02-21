// AUTO_COMMENT_HEADER_V1: messages.ts
// 说明：Cockpit 消息流过滤/去重。

import type { Message } from "../types";

function isLegacyJobNotice(message: Message): boolean {
  if (message.role !== "assistant") return false;
  const text = message.content.trim();
  if (!text) return false;
  if (text.startsWith("已创建 Job：")) return true;
  if (text.includes("正在启动并追踪终端输出")) return true;
  if (text.includes("我会基于上一轮代码与“追加指令”进行修复/迭代")) return true;
  return false;
}

export function buildVisibleMessages(messages: Message[], activeJobId: string | null): Message[] {
  const filtered = messages.filter((m) => {
    if (m.messageKey?.startsWith("job-stream-")) return false;
    if (m.messageKey?.startsWith("job-final-")) return false;
    if (isLegacyJobNotice(m)) return false;
    if (!m.jobId) return true;
    return Boolean(activeJobId) && m.jobId === activeJobId;
  });

  const deduped: Message[] = [];
  const seenKeyIndex = new Map<string, number>();
  for (const message of filtered) {
    const key = message.messageKey?.trim();
    if (!key) {
      deduped.push(message);
      continue;
    }
    const existingIndex = seenKeyIndex.get(key);
    if (existingIndex === undefined) {
      seenKeyIndex.set(key, deduped.length);
      deduped.push(message);
      continue;
    }
    deduped[existingIndex] = message;
  }
  return deduped;
}
