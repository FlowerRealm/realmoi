"use client";

// AUTO_COMMENT_HEADER_V1: Badge.tsx
// 说明：Admin Users 页的轻量徽章组件（纯展示）。

import React from "react";

export function Badge({
  tone,
  children,
}: {
  tone: "indigo" | "amber" | "emerald" | "rose" | "slate";
  children: React.ReactNode;
}) {
  const cls =
    tone === "amber"
      ? "bg-amber-50 text-amber-700 border border-amber-200"
      : tone === "emerald"
        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
        : tone === "rose"
          ? "bg-rose-50 text-rose-700 border border-rose-200"
          : tone === "indigo"
            ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
            : "bg-slate-50 text-slate-700 border border-slate-200";
  return (
    <span className={["inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold", cls].join(" ")}>
      {children}
    </span>
  );
}

