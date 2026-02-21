"use client";

import React from "react";
import type { PricingItem } from "../pricingTypes";
import { fmtNullableInt, hasAnyMissingPriceField, numberToInputValue, parseIntOrNull, prefixedModelName } from "../pricingUtils";
import { Toggle } from "./Toggle";
import { ReadonlyField } from "./ReadonlyField";

type PricingModelCardProps = {
  row: PricingItem;
  isEditing: boolean;
  isDirty: boolean;
  isSaving: boolean;
  beginEdit: (row: PricingItem) => void;
  cancelEdit: (model: string) => void;
  saveRow: (row: PricingItem) => void;
  updateRow: (model: string, patch: Partial<PricingItem>) => void;
};

export function PricingModelCard({
  beginEdit,
  cancelEdit,
  isDirty,
  isEditing,
  isSaving,
  row,
  saveRow,
  updateRow,
}: PricingModelCardProps) {
  const missingPrice = hasAnyMissingPriceField(row);
  const canSave = isDirty && !isSaving;
  const channelLabel = (row.upstream_channel || "").trim() || "未分配";

  return (
    <div
      className={[
        "glass-panel p-4 md:p-5 transition-all",
        "hover:shadow-[0_18px_50px_rgba(15,23,42,0.12)] hover:-translate-y-[1px]",
        row.is_active ? "ring-1 ring-emerald-400/25" : "ring-1 ring-slate-200/35",
        missingPrice && row.is_active ? "ring-2 ring-rose-400/25" : "",
      ].join(" ")}
    >
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-[16rem]">
          <div className="flex items-center gap-2">
            <div className="font-mono text-xs text-slate-900">{prefixedModelName(row.model, channelLabel)}</div>
            <span
              className={[
                "text-[10px] px-2 py-0.5 rounded-full border",
                row.is_active
                  ? "border-emerald-200 bg-emerald-50/80 text-emerald-700"
                  : "border-slate-200 bg-slate-50/80 text-slate-600",
              ].join(" ")}
            >
              {row.is_active ? "ACTIVE" : "INACTIVE"}
            </span>
            {isDirty ? (
              <span className="text-[10px] px-2 py-0.5 rounded-full border border-indigo-200 bg-indigo-50/80 text-indigo-700">
                待保存
              </span>
            ) : null}
          </div>
          <div className="font-mono text-[10px] text-slate-500 mt-1 break-all">{row.model}</div>
        </div>

        <div className="ml-auto flex items-center gap-3">
          {isEditing ? (
            <>
              <div className="flex items-center gap-2">
                <div className="text-[11px] text-slate-500">启用</div>
                <Toggle
                  checked={!!row.is_active}
                  onChange={(v) => updateRow(row.model, { is_active: v })}
                  label="启用模型"
                />
              </div>
              <button
                type="button"
                onClick={() => saveRow(row)}
                disabled={!canSave}
                className={["glass-btn text-xs px-3 py-2", canSave ? "" : "opacity-60 cursor-not-allowed"].join(" ")}
              >
                {isSaving ? "保存中…" : "保存"}
              </button>
              <button
                type="button"
                onClick={() => cancelEdit(row.model)}
                disabled={isSaving}
                className="glass-btn glass-btn-secondary text-xs px-3 py-2"
              >
                取消
              </button>
            </>
          ) : (
            <>
              <div className="text-[11px] text-slate-500">{row.is_active ? "已启用" : "未启用"}</div>
              <button
                type="button"
                onClick={() => beginEdit(row)}
                className="glass-btn glass-btn-secondary text-xs px-3 py-2"
              >
                编辑
              </button>
            </>
          )}
        </div>
      </div>

      {isEditing ? (
        <>
          <details className="mt-4 rounded-xl border border-white/60 bg-white/40 px-3 py-2">
            <summary className="cursor-pointer list-none flex items-center gap-2">
              <span className="text-xs font-semibold text-slate-900">高级字段</span>
              <span className="text-[11px] text-slate-500">仅在需要时修改渠道</span>
            </summary>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-12 gap-2">
              <label className="md:col-span-6 space-y-1">
                <div className="text-[11px] font-medium text-slate-600">渠道</div>
                <input
                  value={row.upstream_channel || ""}
                  onChange={(e) => updateRow(row.model, { upstream_channel: e.target.value })}
                  className="glass-input text-sm"
                  placeholder="例如 openai"
                />
              </label>
              <div className="md:col-span-6">
                <div className="text-[11px] font-medium text-slate-600">说明</div>
                <div className="mt-1 text-xs text-slate-500 leading-relaxed">
                  渠道为空会导致该模型不会出现在用户侧模型列表中；通常保持为实时发现的渠道即可。
                </div>
              </div>
            </div>
          </details>

          <div className="mt-3 grid grid-cols-1 md:grid-cols-12 gap-2">
            <label className="md:col-span-3 space-y-1">
              <div className="text-[11px] font-medium text-slate-600">in</div>
              <input
                value={numberToInputValue(row.input_microusd_per_1m_tokens)}
                onChange={(e) => updateRow(row.model, { input_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })}
                className={[
                  "glass-input text-sm py-2 font-mono",
                  row.is_active && row.input_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                ].join(" ")}
                placeholder="microusd"
              />
            </label>
            <label className="md:col-span-3 space-y-1">
              <div className="text-[11px] font-medium text-slate-600">cached_in</div>
              <input
                value={numberToInputValue(row.cached_input_microusd_per_1m_tokens)}
                onChange={(e) =>
                  updateRow(row.model, { cached_input_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                }
                className={[
                  "glass-input text-sm py-2 font-mono",
                  row.is_active && row.cached_input_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                ].join(" ")}
                placeholder="microusd"
              />
            </label>
            <label className="md:col-span-3 space-y-1">
              <div className="text-[11px] font-medium text-slate-600">out</div>
              <input
                value={numberToInputValue(row.output_microusd_per_1m_tokens)}
                onChange={(e) => updateRow(row.model, { output_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })}
                className={[
                  "glass-input text-sm py-2 font-mono",
                  row.is_active && row.output_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                ].join(" ")}
                placeholder="microusd"
              />
            </label>
            <label className="md:col-span-3 space-y-1">
              <div className="text-[11px] font-medium text-slate-600">cached_out</div>
              <input
                value={numberToInputValue(row.cached_output_microusd_per_1m_tokens)}
                onChange={(e) =>
                  updateRow(row.model, { cached_output_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                }
                className={[
                  "glass-input text-sm py-2 font-mono",
                  row.is_active && row.cached_output_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                ].join(" ")}
                placeholder="microusd"
              />
            </label>
          </div>
        </>
      ) : (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-12 gap-2">
          <div className="md:col-span-3">
            <ReadonlyField
              label="in"
              value={fmtNullableInt(row.input_microusd_per_1m_tokens)}
              mono
              danger={row.is_active && row.input_microusd_per_1m_tokens === null}
            />
          </div>
          <div className="md:col-span-3">
            <ReadonlyField
              label="cached_in"
              value={fmtNullableInt(row.cached_input_microusd_per_1m_tokens)}
              mono
              danger={row.is_active && row.cached_input_microusd_per_1m_tokens === null}
            />
          </div>
          <div className="md:col-span-3">
            <ReadonlyField
              label="out"
              value={fmtNullableInt(row.output_microusd_per_1m_tokens)}
              mono
              danger={row.is_active && row.output_microusd_per_1m_tokens === null}
            />
          </div>
          <div className="md:col-span-3">
            <ReadonlyField
              label="cached_out"
              value={fmtNullableInt(row.cached_output_microusd_per_1m_tokens)}
              mono
              danger={row.is_active && row.cached_output_microusd_per_1m_tokens === null}
            />
          </div>
        </div>
      )}

      {row.is_active && missingPrice ? (
        <div className="mt-3 text-xs text-rose-700 border border-rose-200 bg-rose-50/70 rounded-xl px-3 py-2">
          启用前必须填齐 4 个价格字段；否则保存会失败（后端 422）。
        </div>
      ) : null}
    </div>
  );
}

