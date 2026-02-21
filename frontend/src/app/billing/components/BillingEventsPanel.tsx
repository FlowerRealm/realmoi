"use client";

// 请求明细：分页（before_id 游标）+ 单条 record 费用拆解（按需请求）。

import React from "react";
import type {
  BillingEventDetail,
  BillingEventsResponse,
  BillingFilters,
} from "../billingTypes";
import { fmtInt } from "../billingUtils";
import { BillingEventsTable } from "./BillingEventsTable";

type BillingEventsPanelProps = {
  appliedFilters: BillingFilters;
  beforeId: string | null;
  detailById: Record<string, BillingEventDetail>;
  detailLoadingMap: Record<string, boolean>;
  detailErrorMap: Record<string, string>;
  eventsData: BillingEventsResponse | null;
  expandedRecordId: string | null;
  hasPrevPage: boolean;
  hasNextPage: boolean;
  onNextPage: () => void;
  onPrevPage: () => void;
  onToggleDetail: (recordId: string) => void;
};

export function BillingEventsPanel({
  appliedFilters,
  beforeId,
  detailById,
  detailErrorMap,
  detailLoadingMap,
  eventsData,
  expandedRecordId,
  hasNextPage,
  hasPrevPage,
  onNextPage,
  onPrevPage,
  onToggleDetail,
}: BillingEventsPanelProps) {
  return (
    <div className="glass-panel p-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <div className="font-semibold text-slate-900">请求明细</div>
          <div className="text-xs text-slate-500 mt-1">
            点击“展开”查看单条记录的价格快照与费用拆解。
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
            onClick={onPrevPage}
            disabled={!hasPrevPage}
          >
            上一页
          </button>
          <button
            type="button"
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
            onClick={onNextPage}
            disabled={!hasNextPage}
          >
            下一页
          </button>
        </div>
      </div>

      {!eventsData || eventsData.events.length === 0 ? (
        <div className="text-sm text-slate-600">这个时间范围内还没有 usage 记录。</div>
      ) : (
        <BillingEventsTable
          detailById={detailById}
          detailErrorMap={detailErrorMap}
          detailLoadingMap={detailLoadingMap}
          events={eventsData.events}
          expandedRecordId={expandedRecordId}
          onToggleDetail={onToggleDetail}
        />
      )}

      <div className="text-xs text-slate-500 flex items-center justify-between">
        <span>
          当前页记录：{fmtInt(eventsData?.events.length ?? 0)} / 每页上限 {appliedFilters.limit}
        </span>
        <span>
          {beforeId ? "历史页" : "最新页"} ·{hasNextPage ? " 可继续翻页" : " 已到末页"}
        </span>
      </div>
    </div>
  );
}

