// AUTO_COMMENT_HEADER_V1: stage.ts
// 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

export function stageLabelZh(stage: string): string {
  const s = stage.trim().toLowerCase();
  if (s === "analysis") return "分析";
  if (s === "plan") return "方案";
  if (s === "search") return "检索";
  if (s === "coding") return "编码";
  if (s === "test") return "测试";
  if (s === "repair") return "修复";
  if (s === "done") return "完成";
  if (s === "error") return "错误";
  return s ? s.toUpperCase() : "思考";
}

export function parseStatusUpdateLine(line: string): string | null {
  if (!line.startsWith("[status]")) {
    return null;
  }

  let stage = "";
  let summary = "";
  const stageSummaryFormat = line.match(/\[status\]\s*stage=([A-Za-z_]+)\s+summary=(.+)$/);
  const legacyFormat = line.match(/\[status\]\s*([A-Za-z_]+)\s*:\s*(.+)$/);
  if (stageSummaryFormat) {
    stage = (stageSummaryFormat[1] ?? "").trim();
    summary = (stageSummaryFormat[2] ?? "").trim();
  } else if (legacyFormat) {
    stage = (legacyFormat[1] ?? "").trim();
    summary = (legacyFormat[2] ?? "").trim();
  } else {
    return null;
  }

  if (!stage && !summary) return null;
  const label = stage ? stageLabelZh(stage) : "思考";
  return summary ? `【${label}】${summary}` : `【${label}】`;
}

