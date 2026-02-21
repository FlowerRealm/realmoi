// AUTO_COMMENT_HEADER_V1: urlSync.ts
// 说明：Cockpit URL 同步（jobs/<id> 与首页）。

"use client";

export function syncJobUrl(jobId: string, mode: "push" | "replace" = "push") {
  if (typeof window === "undefined") return;
  const target = `/jobs/${encodeURIComponent(jobId)}`;
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (current === target) return;
  const fn = mode === "replace" ? window.history.replaceState : window.history.pushState;
  fn.call(window.history, { jobId }, "", target);
}

export function syncHomeUrl() {
  if (typeof window === "undefined") return;
  const current = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  if (current === "/") return;
  window.history.pushState({}, "", "/");
}

