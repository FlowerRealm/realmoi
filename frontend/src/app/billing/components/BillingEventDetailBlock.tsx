"use client";

// 单条记录费用拆解：展示 pricing 快照与 computed 总价。

import React from "react";
import type { BillingEventDetail } from "../billingTypes";
import { fmtInt, fmtUsd } from "../billingUtils";

type BillingEventDetailBlockProps = {
  detailLoading: boolean;
  detailError: string | undefined;
  detail: BillingEventDetail | undefined;
};

export function BillingEventDetailBlock({
  detail,
  detailError,
  detailLoading,
}: BillingEventDetailBlockProps) {
  if (detailLoading) {
    return <div className="text-sm text-slate-600">明细加载中…</div>;
  }
  if (detailError) {
    return <div className="glass-alert glass-alert-error">{detailError}</div>;
  }
  if (!detail) {
    return <div className="text-sm text-slate-600">暂无可展示的明细。</div>;
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-slate-500 font-mono break-all">record_id: {detail.id}</div>
      {detail.pricing ? (
        <div className="text-xs text-slate-700">
          pricing:{" "}
          <span className="font-mono text-slate-500">
            {detail.pricing.currency} · input={detail.pricing.input_microusd_per_1m_tokens} · cached_input=
            {detail.pricing.cached_input_microusd_per_1m_tokens} · output={detail.pricing.output_microusd_per_1m_tokens} ·
            cached_output={detail.pricing.cached_output_microusd_per_1m_tokens}
          </span>
        </div>
      ) : null}
      {detail.breakdown ? (
        <div className="space-y-2">
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2 text-xs">
            <BreakdownCard
              title="non-cached input"
              tokens={detail.breakdown.non_cached_input.tokens}
              microusdPerMillion={detail.breakdown.non_cached_input.price_microusd_per_1m_tokens}
              amount={detail.breakdown.non_cached_input.amount}
              currency={detail.pricing?.currency ?? "USD"}
            />
            <BreakdownCard
              title="non-cached output"
              tokens={detail.breakdown.non_cached_output.tokens}
              microusdPerMillion={detail.breakdown.non_cached_output.price_microusd_per_1m_tokens}
              amount={detail.breakdown.non_cached_output.amount}
              currency={detail.pricing?.currency ?? "USD"}
            />
            <BreakdownCard
              title="cached input"
              tokens={detail.breakdown.cached_input.tokens}
              microusdPerMillion={detail.breakdown.cached_input.price_microusd_per_1m_tokens}
              amount={detail.breakdown.cached_input.amount}
              currency={detail.pricing?.currency ?? "USD"}
            />
            <BreakdownCard
              title="cached output"
              tokens={detail.breakdown.cached_output.tokens}
              microusdPerMillion={detail.breakdown.cached_output.price_microusd_per_1m_tokens}
              amount={detail.breakdown.cached_output.amount}
              currency={detail.pricing?.currency ?? "USD"}
            />
          </div>
          <div className="text-sm text-slate-700">
            计算总价（computed）：
            <span className="font-semibold text-slate-900 ml-1">
              {fmtUsd(detail.breakdown.computed_total_amount, detail.pricing?.currency ?? "USD")}
            </span>
            <span className="text-xs text-slate-500 ml-2">
              microusd={detail.breakdown.computed_total_microusd ?? 0}
            </span>
          </div>
        </div>
      ) : (
        <div className="text-sm text-slate-600">暂无可展示的明细。</div>
      )}
    </div>
  );
}

type BreakdownCardProps = {
  title: string;
  tokens: number;
  microusdPerMillion: number;
  amount: string;
  currency: string;
};

function BreakdownCard({
  title,
  amount,
  currency,
  microusdPerMillion,
  tokens,
}: BreakdownCardProps) {
  return (
    <div className="glass-panel p-3">
      <div className="text-slate-500">{title}</div>
      <div className="text-slate-900 mt-1">{fmtInt(tokens)} tokens</div>
      <div className="text-slate-500">单价 {microusdPerMillion}</div>
      <div className="font-medium text-slate-900">{fmtUsd(amount, currency)}</div>
    </div>
  );
}

