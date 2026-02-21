// AUTO_COMMENT_HEADER_V1: feedback.ts
// 说明：Cockpit 文本拼装（statement / feedback）。

import type { SolutionArtifact } from "../types";

export function buildStatementWithUserMessage(statement: string, userMessage?: string): string {
  if (!userMessage?.trim()) return statement;
  return `${statement}\n\n---\n\n### 用户追加指令\n${userMessage.trim()}\n`;
}

export function buildFeedbackMessageContent(solution: SolutionArtifact, hasDiff: boolean): string {
  const parts: string[] = [];
  parts.push("【解读与反馈】");

  const meta: string[] = [];
  const issueType = String(solution.seed_code_issue_type || "").trim();
  if (issueType) meta.push(`类型: ${issueType}`);
  const wrongLines = Array.isArray(solution.seed_code_wrong_lines) ? solution.seed_code_wrong_lines : [];
  if (wrongLines.length > 0) meta.push(`错误行: ${wrongLines.join(", ")}`);
  if (hasDiff) meta.push("右侧可查看差异");
  if (meta.length > 0) parts.push(meta.join(" · "));

  const pushOptionalSection = (title: string, body: string | undefined) => {
    const text = String(body || "").trim();
    if (!text) return;
    parts.push("");
    parts.push(`### ${title}`);
    parts.push(text);
  };

  parts.push("");
  parts.push("### 给用户的反馈");
  parts.push(String(solution.user_feedback_md || "").trim() || "本轮未生成“给用户的反馈”。");

  pushOptionalSection("解法思路", solution.solution_idea);
  pushOptionalSection("用户代码思路复盘", solution.seed_code_idea);
  pushOptionalSection("用户代码错误原因", solution.seed_code_bug_reason);

  return parts.join("\n").trim();
}
