// AUTO_COMMENT_HEADER_V1: tokenStream.ts
// 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

import { parseStatusUpdateLine } from "./stage";

export type TokenStreamView = {
  items: TokenStreamItem[];
};

export type TokenStreamItem = {
  kind: "thinking" | "stage" | "result" | "usage" | "backend" | "other";
  title: string;
  content: string;
};

function clipText(text: string, maxLen: number): string {
  const brief = text.replace(/\s+/g, " ").trim();
  if (!brief) return "";
  if (brief.length <= maxLen) return brief;
  return `${brief.slice(0, maxLen)}…`;
}

function isTokenBoundaryLine(line: string): boolean {
  if (!line) return false;
  if (/^【[^】]+】/.test(line)) return true;
  if (/^\[结果\]/.test(line)) return true;
  if (/^完成，Token统计：/.test(line)) return true;
  if (/^\[backend\]\s*attempt\s+\d+\s+failed/i.test(line)) return true;
  return false;
}

function buildTokenItem(block: string, index: number): TokenStreamItem {
  const firstLine = block.split("\n").find((line) => line.trim())?.trim() ?? "";
  const stageMatch = firstLine.match(/^【([^】]+)】\s*(.*)$/);
  if (stageMatch) {
    const stage = stageMatch[1].trim();
    const summary = clipText(stageMatch[2]?.trim() ?? "", 36);
    if (stage === "思考") {
      const thinkingContent = block.replace(/^【思考】\s*/m, "").trim();
      return {
        kind: "thinking",
        title: summary ? `思考 · ${summary}` : "思考",
        content: thinkingContent || summary || "思考中…",
      };
    }
    return {
      kind: "stage",
      title: summary ? `${stage} · ${summary}` : stage,
      content: block,
    };
  }
  if (firstLine.startsWith("[结果]")) {
    const summary = clipText(firstLine.replace(/^\[结果\]\s*/, ""), 36);
    return {
      kind: "result",
      title: summary ? `结果 · ${summary}` : "结果",
      content: block,
    };
  }
  if (firstLine.startsWith("完成，Token统计：")) {
    return {
      kind: "usage",
      title: "Token统计",
      content: block,
    };
  }
  const backendRetryMatch = firstLine.match(/^\[backend\]\s*attempt\s+(\d+)\s+failed(?:,\s*retrying\s*\(([^)]+)\))?/i);
  if (backendRetryMatch) {
    const attempt = backendRetryMatch[1];
    const retryMode = clipText(String(backendRetryMatch[2] || ""), 16);
    return {
      kind: "backend",
      title: retryMode ? `后端重试 #${attempt} · ${retryMode}` : `后端重试 #${attempt}`,
      content: block,
    };
  }
  return {
    kind: "other",
    title: `步骤 ${index + 1}`,
    content: block,
  };
}

export function cleanTokenText(text: string): string {
  const normalized = text
    .replace(/\[(codex|runner)\]\s*/g, "")
    .replace(/^Job\s+[A-Za-z0-9_-]+\s+Token级流式输出.*$/gm, "");

  const lines = normalized.split("\n");
  const kept: string[] = [];
  let inHereDoc = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      kept.push("");
      continue;
    }
    const thought = parseStatusUpdateLine(line);
    if (thought) {
      kept.push(thought);
      continue;
    }
    if (/^MODE=/.test(line)) continue;
    if (/^exit=\d+/.test(line)) continue;
    if (/^\$\s+/.test(line)) {
      if (line.includes("<<'PY'") || line.includes("<<\"PY\"")) {
        inHereDoc = true;
      }
      continue;
    }
    if (inHereDoc) {
      if (line === "PY" || line === "PY'" || line === "PY\"") {
        inHereDoc = false;
      }
      continue;
    }
    if (line.startsWith("status_update(")) continue;
    if (line.startsWith("from runner_generate import status_update")) continue;
    if (line === "PY" || line === "PY'" || line === "PY\"") continue;
    kept.push(raw);
  }

  return kept.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function splitTokenStreamContent(content: string): TokenStreamView {
  const cleaned = cleanTokenText(content.replace(/\r/g, "")).trim();
  if (!cleaned) return { items: [] };
  const lines = cleaned.split("\n");
  const blocks: string[] = [];
  let current: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      if (current.length > 0 && current[current.length - 1] !== "") current.push("");
      continue;
    }
    if (isTokenBoundaryLine(trimmed) && current.length > 0) {
      const block = current.join("\n").trim();
      if (block) blocks.push(block);
      current = [line];
      continue;
    }
    current.push(line);
  }
  const finalBlock = current.join("\n").trim();
  if (finalBlock) blocks.push(finalBlock);

  return {
    items: blocks.map((block, idx) => buildTokenItem(block, idx)),
  };
}

