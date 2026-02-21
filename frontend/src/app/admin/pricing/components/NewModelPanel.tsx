"use client";

import React from "react";

type NewModelPanelProps = {
  newModel: string;
  newUpstreamChannel: string;
  setNewModel: (value: string) => void;
  setNewUpstreamChannel: (value: string) => void;
  isSaving: boolean;
  onCreate: () => void;
};

export function NewModelPanel({
  isSaving,
  newModel,
  newUpstreamChannel,
  onCreate,
  setNewModel,
  setNewUpstreamChannel,
}: NewModelPanelProps) {
  return (
    <div className="glass-panel p-4 lg:col-span-7">
      <div className="flex items-center gap-2 mb-3">
        <div className="text-sm font-semibold text-slate-900">新增模型（创建 / 占位）</div>
        <div className="ml-auto text-xs text-slate-500">
          启用前需填齐 4 个字段（in / cached_in / out / cached_out）
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
        <label className="md:col-span-7 space-y-1">
          <div className="text-[11px] font-medium text-slate-600">model</div>
          <input
            value={newModel}
            onChange={(e) => setNewModel(e.target.value)}
            placeholder="例如 gpt-4o-mini"
            className="glass-input text-sm font-mono"
          />
        </label>
        <label className="md:col-span-3 space-y-1">
          <div className="text-[11px] font-medium text-slate-600">渠道</div>
          <input
            value={newUpstreamChannel}
            onChange={(e) => setNewUpstreamChannel(e.target.value)}
            placeholder="例如 openai"
            className="glass-input text-sm"
          />
        </label>
        <div className="md:col-span-2 flex items-end">
          <button
            type="button"
            onClick={onCreate}
            disabled={!newModel.trim() || isSaving}
            className="glass-btn w-full whitespace-nowrap"
          >
            {isSaving ? "创建中…" : "创建"}
          </button>
        </div>
      </div>
    </div>
  );
}

