// AUTO_COMMENT_HEADER_V1: jobStatus.ts
// 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

export type JobStatusMeta = {
  lifecycle: "running" | "finished" | "waiting" | "unknown";
  headline: string;
  phase: string;
  raw: string;
  badgeClassName: string;
  dotClassName: string;
};

export function resolveJobStatusMeta(status: string | null | undefined): JobStatusMeta {
  const normalized = (status ?? "").trim().toLowerCase();
  const raw = normalized || "-";

  if (!normalized) {
    return {
      lifecycle: "waiting",
      headline: "等待中",
      phase: "尚未开始",
      raw,
      badgeClassName: "bg-slate-100 text-slate-600 border border-slate-200",
      dotClassName: "bg-slate-400",
    };
  }

  if (normalized === "created" || normalized === "queued") {
    return {
      lifecycle: "waiting",
      headline: "等待中",
      phase: normalized === "queued" ? "已排队，等待测评机" : "已创建，待启动",
      raw,
      badgeClassName: "bg-amber-50 text-amber-700 border border-amber-200",
      dotClassName: "bg-amber-500",
    };
  }

  if (normalized.startsWith("running")) {
    let phase = "执行中";
    if (normalized === "running_generate") phase = "生成中";
    if (normalized === "running_test") phase = "测试中";
    return {
      lifecycle: "running",
      headline: "进行中",
      phase,
      raw,
      badgeClassName: "bg-indigo-50 text-indigo-700 border border-indigo-200",
      dotClassName: "bg-indigo-500",
    };
  }

  if (normalized === "succeeded") {
    return {
      lifecycle: "finished",
      headline: "已结束",
      phase: "成功",
      raw,
      badgeClassName: "bg-emerald-50 text-emerald-700 border border-emerald-200",
      dotClassName: "bg-emerald-500",
    };
  }

  if (normalized === "failed") {
    return {
      lifecycle: "finished",
      headline: "已结束",
      phase: "失败",
      raw,
      badgeClassName: "bg-rose-50 text-rose-700 border border-rose-200",
      dotClassName: "bg-rose-500",
    };
  }

  if (normalized === "cancelled") {
    return {
      lifecycle: "finished",
      headline: "已结束",
      phase: "已取消",
      raw,
      badgeClassName: "bg-orange-50 text-orange-700 border border-orange-200",
      dotClassName: "bg-orange-500",
    };
  }

  return {
    lifecycle: "unknown",
    headline: "状态未知",
    phase: normalized,
    raw,
    badgeClassName: "bg-slate-100 text-slate-600 border border-slate-200",
    dotClassName: "bg-slate-500",
  };
}

