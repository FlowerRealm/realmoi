"use client";

// 表格主体：明细行在展开时渲染；明细数据由外层 hook 管理（按需加载）。

import React from "react";
import type { BillingEvent, BillingEventDetail } from "../billingTypes";
import { fmtDate, fmtInt, fmtUsd } from "../billingUtils";
import { BillingEventDetailBlock } from "./BillingEventDetailBlock";

type BillingEventsTableProps = {
  events: BillingEvent[];
  expandedRecordId: string | null;
  onToggleDetail: (recordId: string) => void;
  detailById: Record<string, BillingEventDetail>;
  detailLoadingMap: Record<string, boolean>;
  detailErrorMap: Record<string, string>;
};

export function BillingEventsTable({
  detailById,
  detailErrorMap,
  detailLoadingMap,
  events,
  expandedRecordId,
  onToggleDetail,
}: BillingEventsTableProps) {
  return (
    <div className="glass-table overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="text-slate-600">
          <tr>
            <th className="text-left font-semibold px-3 py-2">时间</th>
            <th className="text-left font-semibold px-3 py-2">模型 / 阶段</th>
            <th className="text-left font-semibold px-3 py-2">Job</th>
            <th className="text-right font-semibold px-3 py-2">输入</th>
            <th className="text-right font-semibold px-3 py-2">输出</th>
            <th className="text-right font-semibold px-3 py-2">缓存</th>
            <th className="text-right font-semibold px-3 py-2">费用</th>
            <th className="text-right font-semibold px-3 py-2">操作</th>
          </tr>
        </thead>
        <tbody>
          {events.map((event) => {
            const expanded = expandedRecordId === event.id;
            const detail = detailById[event.id];
            const detailLoading = Boolean(detailLoadingMap[event.id]);
            const detailError = detailErrorMap[event.id];
            return (
              <React.Fragment key={event.id}>
                <tr>
                  <td className="px-3 py-2 text-slate-700 whitespace-nowrap">{fmtDate(event.created_at)}</td>
                  <td className="px-3 py-2">
                    <div className="font-medium text-slate-900">{event.model}</div>
                    <div className="text-xs text-slate-500">{event.stage}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-mono text-[11px] text-slate-500 break-all">{event.job_id}</div>
                  </td>
                  <td className="px-3 py-2 text-right text-slate-700">{fmtInt(event.input_tokens)}</td>
                  <td className="px-3 py-2 text-right text-slate-700">{fmtInt(event.output_tokens)}</td>
                  <td className="px-3 py-2 text-right text-slate-700">{fmtInt(event.cached_tokens)}</td>
                  <td className="px-3 py-2 text-right text-slate-900 font-medium">
                    {fmtUsd(event.cost?.amount ?? null, event.cost?.currency ?? "USD")}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                      onClick={() => onToggleDetail(event.id)}
                    >
                      {expanded ? "收起" : "展开"}
                    </button>
                  </td>
                </tr>
                {expanded ? (
                  <tr>
                    <td colSpan={8} className="px-3 py-3 bg-slate-50/80">
                      <BillingEventDetailBlock
                        detail={detail}
                        detailError={detailError}
                        detailLoading={detailLoading}
                      />
                    </td>
                  </tr>
                ) : null}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

