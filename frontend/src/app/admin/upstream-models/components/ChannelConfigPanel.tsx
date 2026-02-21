"use client";

import React from "react";
import type { UpstreamChannelFormItem } from "../upstreamModelsTypes";
import { channelKey } from "../upstreamModelsStorage";

type ChannelConfigPanelProps = {
  channels: UpstreamChannelFormItem[];
  savingChannel: string | null;
  onOpenCreateModal: () => void;
  updateChannelField: (channel: string, patch: Partial<UpstreamChannelFormItem>) => void;
  saveChannel: (channel: string) => void;
  deleteChannel: (channel: string) => void;
};

export function ChannelConfigPanel({
  channels,
  savingChannel,
  onOpenCreateModal,
  deleteChannel,
  saveChannel,
  updateChannelField,
}: ChannelConfigPanelProps) {
  return (
    <div className="glass-panel p-4 space-y-3">
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold text-slate-900">渠道配置（编辑 / 删除）</div>
        <button
          type="button"
          onClick={onOpenCreateModal}
          className="ml-auto inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50/90 text-indigo-700 hover:bg-indigo-100 px-3 py-2 text-sm font-medium transition-all"
          title="新增渠道"
          aria-label="新增渠道"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
          <span>新增渠道</span>
        </button>
      </div>

      <div className="space-y-2">
        {channels.map((item) => (
          <div key={channelKey(item.channel)} className="rounded-lg border border-white/60 bg-white/50 p-3">
            <div className="flex items-center gap-2 mb-2">
              <span className="font-mono text-xs text-slate-900">{item.channel || "default"}</span>
              <span className="text-[10px] text-slate-500">source={item.source}</span>
              {item.is_default ? (
                <span className="text-[10px] text-slate-500">系统默认渠道（只读）</span>
              ) : null}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
              <input
                value={item.display_name}
                onChange={(e) => updateChannelField(item.channel, { display_name: e.target.value })}
                disabled={item.is_default}
                className="glass-input text-sm md:col-span-1"
              />
              <input
                value={item.base_url}
                onChange={(e) => updateChannelField(item.channel, { base_url: e.target.value })}
                disabled={item.is_default}
                className="glass-input text-sm md:col-span-2"
              />
              <input
                value={item.api_key_input}
                onChange={(e) => updateChannelField(item.channel, { api_key_input: e.target.value })}
                disabled={item.is_default}
                placeholder={
                  item.has_api_key ? `保持不变（当前：${item.api_key_masked}）` : "请输入 API Key"
                }
                className="glass-input text-sm md:col-span-2"
              />
              <input
                value={item.models_path}
                onChange={(e) => updateChannelField(item.channel, { models_path: e.target.value })}
                disabled={item.is_default}
                className="glass-input text-sm md:col-span-1"
              />
            </div>
            <div className="mt-2 flex items-center gap-3">
              <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={item.is_enabled}
                  disabled={item.is_default}
                  onChange={(e) => updateChannelField(item.channel, { is_enabled: e.target.checked })}
                />
                启用
              </label>
              {!item.is_default ? (
                <>
                  <button
                    type="button"
                    onClick={() => saveChannel(item.channel)}
                    disabled={savingChannel === item.channel}
                    className="glass-btn glass-btn-secondary text-xs px-2 py-1.5"
                  >
                    {savingChannel === item.channel ? "保存中…" : "保存"}
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteChannel(item.channel)}
                    disabled={savingChannel === item.channel}
                    className="text-xs px-2 py-1.5 rounded-md border border-rose-200 bg-rose-50/80 text-rose-700 hover:bg-rose-100"
                  >
                    删除
                  </button>
                </>
              ) : null}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

