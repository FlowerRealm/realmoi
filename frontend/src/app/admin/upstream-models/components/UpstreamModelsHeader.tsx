"use client";

import React from "react";

type UpstreamModelsHeaderProps = {
  autoRefreshSeconds: number;
  onAutoRefreshSecondsChange: (value: number) => void;
  onRefreshAll: () => void;
};

export function UpstreamModelsHeader({
  autoRefreshSeconds,
  onAutoRefreshSecondsChange,
  onRefreshAll,
}: UpstreamModelsHeaderProps) {
  return (
    <div className="glass-panel-strong p-4 md:p-5 flex items-center gap-3">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">Admin / Upstream Models</h1>
        <p className="text-xs text-slate-500 mt-1">
          默认查询全部已启用渠道，支持手动刷新和自动延迟刷新
        </p>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <label className="text-xs text-slate-600">自动刷新</label>
        <select
          value={autoRefreshSeconds}
          onChange={(e) => onAutoRefreshSecondsChange(Number(e.target.value))}
          className="glass-input text-sm w-40"
        >
          <option value={0}>关闭</option>
          <option value={60}>60 秒</option>
          <option value={180}>180 秒（默认）</option>
          <option value={300}>300 秒</option>
          <option value={600}>600 秒</option>
        </select>
      </div>
      <button type="button" onClick={onRefreshAll} className="glass-btn">
        刷新（全部渠道）
      </button>
    </div>
  );
}

