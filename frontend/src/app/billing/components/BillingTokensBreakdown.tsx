"use client";

// Token 结构：按 input/output 与 cached/non-cached 做简单拆解。

import React from "react";
import type { BillingWindow } from "../billingTypes";
import { fmtInt } from "../billingUtils";

type BillingTokensBreakdownProps = {
  windowData: BillingWindow;
};

export function BillingTokensBreakdown({ windowData }: BillingTokensBreakdownProps) {
  return (
    <div className="glass-panel p-4">
      <div className="font-semibold text-slate-900 mb-3">Token 结构</div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 text-sm">
        <div className="glass-panel p-3">
          <div className="text-slate-500">input tokens</div>
          <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.input_tokens)}</div>
        </div>
        <div className="glass-panel p-3">
          <div className="text-slate-500">cached input</div>
          <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.cached_input_tokens)}</div>
        </div>
        <div className="glass-panel p-3">
          <div className="text-slate-500">output tokens</div>
          <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.output_tokens)}</div>
        </div>
        <div className="glass-panel p-3">
          <div className="text-slate-500">cached output</div>
          <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.cached_output_tokens)}</div>
        </div>
      </div>
    </div>
  );
}

