"use client";

import React from "react";

type ReadonlyFieldProps = {
  label: string;
  value: string;
  mono?: boolean;
  danger?: boolean;
};

export function ReadonlyField({ danger, label, mono, value }: ReadonlyFieldProps) {
  const isEmpty = value.trim() === "—";
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-medium text-slate-600">{label}</div>
      <div
        className={[
          "text-sm leading-snug",
          mono ? "font-mono text-xs break-all" : "font-semibold",
          danger ? "text-rose-700" : isEmpty ? "text-slate-400" : "text-slate-900",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}

