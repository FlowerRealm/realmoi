"use client";

import React from "react";

export type CreateChannelDraft = {
  channel: string;
  displayName: string;
  baseUrl: string;
  apiKey: string;
  modelsPath: string;
  isEnabled: boolean;
};

type CreateChannelModalProps = {
  open: boolean;
  isSaving: boolean;
  draft: CreateChannelDraft;
  onDraftChange: (patch: Partial<CreateChannelDraft>) => void;
  onClose: () => void;
  onCreate: () => void;
};

export function CreateChannelModal({
  draft,
  isSaving,
  onClose,
  onCreate,
  onDraftChange,
  open,
}: CreateChannelModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 backdrop-blur-[2px] px-4"
      onClick={onClose}
    >
      <div
        className="glass-panel-strong w-full max-w-3xl p-5 space-y-4 bg-white/95 border border-slate-200 shadow-[0_24px_70px_rgba(15,23,42,0.28)]"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="新增渠道"
      >
        <div className="flex items-center gap-2">
          <div>
            <div className="text-base font-semibold text-slate-900">新增渠道</div>
            <div className="text-xs text-slate-500 mt-1">填写渠道信息后保存，保存成功会自动关闭弹窗。</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto text-xs px-2.5 py-1.5 rounded-md border border-slate-200 bg-white/80 text-slate-600 hover:bg-white"
          >
            关闭
          </button>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-600">渠道标识（channel）</div>
            <input
              value={draft.channel}
              onChange={(e) => onDraftChange({ channel: e.target.value })}
              placeholder="例如 openai-cn"
              className="glass-input text-sm"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-600">展示名称（display_name）</div>
            <input
              value={draft.displayName}
              onChange={(e) => onDraftChange({ displayName: e.target.value })}
              placeholder="例如 OpenAI 中国"
              className="glass-input text-sm"
            />
          </label>
          <label className="space-y-1 md:col-span-2">
            <div className="text-xs font-medium text-slate-600">Base URL</div>
            <input
              value={draft.baseUrl}
              onChange={(e) => onDraftChange({ baseUrl: e.target.value })}
              placeholder="例如 https://api.example.com/v1"
              className="glass-input text-sm"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-600">API Key（必填）</div>
            <input
              value={draft.apiKey}
              onChange={(e) => onDraftChange({ apiKey: e.target.value })}
              placeholder="请输入 API Key"
              className="glass-input text-sm"
            />
          </label>
          <label className="space-y-1">
            <div className="text-xs font-medium text-slate-600">Models Path</div>
            <input
              value={draft.modelsPath}
              onChange={(e) => onDraftChange({ modelsPath: e.target.value })}
              placeholder="/v1/models"
              className="glass-input text-sm"
            />
          </label>
        </div>
        <div className="flex items-center gap-3 pt-1">
          <label className="inline-flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={draft.isEnabled}
              onChange={(e) => onDraftChange({ isEnabled: e.target.checked })}
            />
            启用
          </label>
          <button type="button" onClick={onCreate} disabled={isSaving} className="glass-btn">
            {isSaving ? "保存中…" : "新增渠道"}
          </button>
          <button type="button" onClick={onClose} className="glass-btn glass-btn-secondary">
            取消
          </button>
        </div>
      </div>
    </div>
  );
}

