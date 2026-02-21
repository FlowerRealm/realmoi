"use client";

// 窗口汇总：费用、记录数、缓存命中率、Tokens 等一屏关键指标。

import React, { useMemo } from "react";
import type { BillingFilters, BillingWindow } from "../billingTypes";
import { fmtInt, fmtPercent, fmtUsd } from "../billingUtils";

type BillingSummaryCardsProps = {
  appliedFilters: BillingFilters;
  windowData: BillingWindow;
};

export function BillingSummaryCards({ appliedFilters, windowData }: BillingSummaryCardsProps) {
  const pricingCoverage = useMemo(() => {
    const totalRecords = windowData.records ?? 0;
    const pricedRecords = windowData.cost.priced_records ?? 0;
    return totalRecords > 0 ? pricedRecords / totalRecords : 0;
  }, [windowData.cost.priced_records, windowData.records]);

  const totalTokens = windowData.total_tokens ?? 0;
  const interactiveTokens = windowData.input_tokens + windowData.output_tokens;
  const cachedTokens = windowData.cached_input_tokens + windowData.cached_output_tokens;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      <div className="glass-panel p-4">
        <div className="text-xs text-slate-500">总费用（已定价记录）</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">
          {fmtUsd(windowData.cost.amount, windowData.cost.currency)}
        </div>
        <div className="mt-1 text-xs text-slate-500 font-mono">
          microusd={windowData.cost.cost_microusd ?? "-"}
        </div>
      </div>
      <div className="glass-panel p-4">
        <div className="text-xs text-slate-500">使用记录数</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">{fmtInt(windowData.records)}</div>
        <div className="mt-1 text-xs text-slate-500">
          已定价 {fmtInt(windowData.cost.priced_records)} / 未定价 {fmtInt(windowData.cost.unpriced_records)}
        </div>
      </div>
      <div className="glass-panel p-4">
        <div className="text-xs text-slate-500">查询窗口 / 覆盖率</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">
          {fmtPercent(windowData.cache_ratio)}
        </div>
        <div className="mt-1 text-xs text-slate-500">
          定价覆盖率 {fmtPercent(pricingCoverage)}
        </div>
        <div className="mt-1 text-xs text-slate-500 font-mono">
          {appliedFilters.start} ~ {appliedFilters.end}
        </div>
      </div>
      <div className="glass-panel p-4">
        <div className="text-xs text-slate-500">总 Tokens</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">
          {fmtInt(totalTokens)}
        </div>
      </div>
      <div className="glass-panel p-4">
        <div className="text-xs text-slate-500">交互 Tokens（input + output）</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">
          {fmtInt(interactiveTokens)}
        </div>
      </div>
      <div className="glass-panel p-4">
        <div className="text-xs text-slate-500">缓存 Tokens</div>
        <div className="mt-1 text-lg font-semibold text-slate-900">
          {fmtInt(cachedTokens)}
        </div>
      </div>
    </div>
  );
}

