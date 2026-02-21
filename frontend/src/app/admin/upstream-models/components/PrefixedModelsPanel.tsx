"use client";

import React from "react";
import type { PrefixedModelRow } from "../upstreamModelsTypes";

type PrefixedModelsPanelProps = {
  showAllModels: boolean;
  onShowAllModelsChange: (value: boolean) => void;
  visiblePrefixedModels: PrefixedModelRow[];
};

export function PrefixedModelsPanel({
  onShowAllModelsChange,
  showAllModels,
  visiblePrefixedModels,
}: PrefixedModelsPanelProps) {
  return (
    <div className="glass-panel p-4">
      <div className="flex items-center gap-3 mb-2">
        <div className="text-sm font-semibold text-slate-900">模型名（已加渠道前缀）</div>
        <label className="ml-auto inline-flex items-center gap-2 text-xs text-slate-600">
          <input
            type="checkbox"
            checked={showAllModels}
            onChange={(e) => onShowAllModelsChange(e.target.checked)}
          />
          显示全部模型（含 embedding / tts / realtime 等）
        </label>
      </div>
      {!showAllModels ? (
        <div className="text-xs text-slate-500 mb-2">
          当前仅显示常见对话模型；如需排查全部模型请勾选“显示全部模型”。
        </div>
      ) : null}
      {visiblePrefixedModels.length === 0 ? (
        <div className="text-sm text-slate-600">无数据</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {visiblePrefixedModels.map((row) => (
            <div key={`${row.channel}/${row.model}`} className="rounded-lg border border-white/60 bg-white/50 px-3 py-2">
              <div className="font-mono text-xs text-slate-900">{row.prefixed}</div>
              <div className="text-[11px] text-slate-500 mt-1">原始模型: {row.model}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

