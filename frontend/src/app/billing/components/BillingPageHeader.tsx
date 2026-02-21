"use client";

import React from "react";

type BillingPageHeaderProps = {
  loading: boolean;
  refreshing: boolean;
  onRefresh: () => void;
};

export function BillingPageHeader({ loading, refreshing, onRefresh }: BillingPageHeaderProps) {
  return (
    <div className="glass-panel-strong p-4 md:p-5 flex flex-wrap items-center gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Billing</h1>
        <p className="text-xs text-slate-500 mt-1">
          先看关键指标，再看请求明细和单条费用拆解。
        </p>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <div className="text-xs text-slate-500">
          {refreshing ? "正在后台刷新…" : "每 60 秒自动刷新"}
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="glass-btn"
          disabled={loading || refreshing}
        >
          刷新
        </button>
      </div>
    </div>
  );
}

