// AUTO_COMMENT_HEADER_V1: DiffView.tsx
// 说明：该文件包含业务逻辑/工具脚本；此注释头用于提升可读性与注释比例评分。

"use client";

import React from "react";
import type { DiffLine } from "./diff";
import { parseUnifiedDiff } from "./diff";

export function DiffView({ diffText }: { diffText: string }) {
  const rows = parseUnifiedDiff(diffText).filter((row) => row.kind !== "meta" && row.kind !== "hunk");
  if (!rows.length) return null;

  const maxOld = rows.reduce((acc, row) => (row.oldLine !== null ? Math.max(acc, row.oldLine) : acc), 0);
  const maxNew = rows.reduce((acc, row) => (row.newLine !== null ? Math.max(acc, row.newLine) : acc), 0);
  const lnDigits = Math.max(3, String(Math.max(maxOld, maxNew)).length);
  const gridTemplateColumns = `${lnDigits + 1}ch 2ch 1fr`;

  const kindStyle = (kind: DiffLine["kind"]) => {
    if (kind === "add") {
      return {
        bg: "bg-emerald-50/70",
        accent: "border-l-2 border-emerald-400",
        sign: "text-emerald-700",
      };
    }
    if (kind === "del") {
      return {
        bg: "bg-rose-50/70",
        accent: "border-l-2 border-rose-400",
        sign: "text-rose-700",
      };
    }
    return {
      bg: "bg-white",
      accent: "border-l-2 border-transparent",
      sign: "text-slate-300",
    };
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <div className="min-w-max">
          {rows.map((row, idx) => {
            const style = kindStyle(row.kind);
            const raw = row.text ?? "";
            const hasPrefix = row.kind === "add" || row.kind === "del" || row.kind === "ctx";
            const sign = hasPrefix ? raw.slice(0, 1) : "";
            const code = hasPrefix ? raw.slice(1) : raw;
            const isLast = idx === rows.length - 1;
            const lineNo = row.kind === "del" ? row.oldLine : row.newLine;

            return (
              <div
                key={idx}
                style={{ gridTemplateColumns }}
                className={[
                  "grid items-start font-mono text-[12px] leading-6",
                  style.bg,
                  style.accent,
                  isLast ? "" : "border-b border-slate-100",
                  "hover:bg-slate-50/70 transition-colors",
                ].join(" ")}
              >
                <div className="px-2 py-0.5 text-right tabular-nums text-slate-400 select-none border-r border-slate-200/70">
                  {lineNo ?? ""}
                </div>
                <div className={["px-1 py-0.5 text-center select-none font-semibold", style.sign].join(" ")}>
                  {sign === " " ? "" : sign}
                </div>
                <div className="px-2 py-0.5 whitespace-pre text-slate-800">
                  {code}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
