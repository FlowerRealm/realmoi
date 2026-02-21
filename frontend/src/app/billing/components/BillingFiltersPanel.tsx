"use client";

// 筛选条件：草稿/已应用两套状态；应用后会触发重新拉取并写入 localStorage。

import React from "react";
import type { BillingFilters } from "../billingTypes";
import { LIMIT_OPTIONS, clampLimit } from "../billingUtils";

type BillingFiltersPanelProps = {
  appliedFilters: BillingFilters;
  draftFilters: BillingFilters;
  hasPendingChanges: boolean;
  loading: boolean;
  onApplyFilters: () => void;
  onQuickRange: (preset: "today" | "yesterday" | "last7days") => void;
  setDraftFilters: React.Dispatch<React.SetStateAction<BillingFilters>>;
};

export function BillingFiltersPanel({
  appliedFilters,
  draftFilters,
  hasPendingChanges,
  loading,
  onApplyFilters,
  onQuickRange,
  setDraftFilters,
}: BillingFiltersPanelProps) {
  return (
    <details className="glass-panel p-4">
      <summary className="cursor-pointer list-none flex items-center gap-2">
        <span className="text-sm font-semibold text-slate-900">筛选条件（可折叠）</span>
        <span className="text-xs text-slate-500">
          当前：{appliedFilters.start} ~ {appliedFilters.end} / 每页 {appliedFilters.limit} 条
        </span>
        {hasPendingChanges ? <span className="text-xs text-amber-600">草稿未应用</span> : null}
      </summary>
      <div className="mt-3 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-xs text-slate-500">快捷范围</div>
          <button
            type="button"
            onClick={() => onQuickRange("today")}
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
          >
            今天
          </button>
          <button
            type="button"
            onClick={() => onQuickRange("yesterday")}
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
          >
            昨天
          </button>
          <button
            type="button"
            onClick={() => onQuickRange("last7days")}
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
          >
            近 7 天
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <div className="text-xs text-slate-500">开始日期</div>
            <input
              type="date"
              value={draftFilters.start}
              onChange={(e) =>
                setDraftFilters((prev) => ({
                  ...prev,
                  start: e.target.value,
                }))
              }
              className="glass-input mt-1 text-sm"
            />
          </div>
          <div>
            <div className="text-xs text-slate-500">结束日期</div>
            <input
              type="date"
              value={draftFilters.end}
              onChange={(e) =>
                setDraftFilters((prev) => ({
                  ...prev,
                  end: e.target.value,
                }))
              }
              className="glass-input mt-1 text-sm"
            />
          </div>
          <div>
            <div className="text-xs text-slate-500">每页条数</div>
            <select
              value={draftFilters.limit}
              onChange={(e) =>
                setDraftFilters((prev) => ({
                  ...prev,
                  limit: clampLimit(Number(e.target.value)),
                }))
              }
              className="glass-input mt-1 text-sm"
            >
              {LIMIT_OPTIONS.map((limit) => (
                <option key={limit} value={limit}>
                  {limit}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              type="button"
              onClick={onApplyFilters}
              className="glass-btn glass-btn-secondary w-full"
              disabled={!hasPendingChanges || loading}
            >
              {hasPendingChanges ? "应用筛选" : "筛选已生效"}
            </button>
          </div>
        </div>
      </div>
    </details>
  );
}

