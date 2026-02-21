"use client";

import React from "react";

type FilterPanelProps = {
  filter: string;
  liveReady: boolean;
  missingActive: number;
  onFilterChange: (value: string) => void;
};

export function FilterPanel({ filter, liveReady, missingActive, onFilterChange }: FilterPanelProps) {
  return (
    <div className="glass-panel p-4 lg:col-span-5">
      <div className="flex items-center gap-2 mb-3">
        <div className="text-sm font-semibold text-slate-900">过滤</div>
        <div className="ml-auto text-xs text-slate-500">
          {missingActive > 0 ? `⚠️ active 且缺失定价：${missingActive}` : liveReady ? "实时就绪" : "拉取中…"}
        </div>
      </div>
      <input
        value={filter}
        onChange={(e) => onFilterChange(e.target.value)}
        placeholder="按 model 名称过滤…"
        className="glass-input text-sm"
      />
      <div className="mt-2 text-xs text-slate-500">
        列表自动聚合全部已启用渠道的实时 model id；点击「编辑」进入编辑态后才可修改字段并保存。
      </div>
    </div>
  );
}

