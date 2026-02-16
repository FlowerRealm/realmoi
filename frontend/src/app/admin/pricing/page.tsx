"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

type PricingItem = {
  model: string;
  upstream_channel: string;
  currency: string;
  unit: string;
  is_active: boolean;
  input_microusd_per_1m_tokens: number | null;
  cached_input_microusd_per_1m_tokens: number | null;
  output_microusd_per_1m_tokens: number | null;
  cached_output_microusd_per_1m_tokens: number | null;
};

type UpsertPricingRequest = {
  upstream_channel?: string | null;
  currency?: string;
  is_active?: boolean;
  input_microusd_per_1m_tokens?: number | null;
  cached_input_microusd_per_1m_tokens?: number | null;
  output_microusd_per_1m_tokens?: number | null;
  cached_output_microusd_per_1m_tokens?: number | null;
};

type UpstreamChannelItem = {
  channel: string;
  display_name: string;
  is_enabled: boolean;
  is_default: boolean;
};

type LiveModelItem = {
  model: string;
  upstream_channel: string;
};

function parseIntOrNull(v: string): number | null {
  const s = v.trim();
  if (!s) return null;
  const n = Number(s);
  if (!Number.isFinite(n)) return null;
  return Math.trunc(n);
}

function numberToInputValue(v: number | null): string {
  return v === null ? "" : String(v);
}

function prefixedModelName(model: string, channel: string): string {
  const channelText = channel.trim() || "未分配";
  return `[${channelText}] ${model}`;
}

function hasAnyMissingPriceField(row: PricingItem): boolean {
  return (
    row.input_microusd_per_1m_tokens === null ||
    row.cached_input_microusd_per_1m_tokens === null ||
    row.output_microusd_per_1m_tokens === null ||
    row.cached_output_microusd_per_1m_tokens === null
  );
}

function Toggle({
  checked,
  onChange,
  disabled,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={[
        "relative inline-flex h-6 w-11 items-center rounded-full border transition-all",
        "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/25",
        disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer",
        checked
          ? "bg-emerald-500/90 border-emerald-200 shadow-[0_10px_25px_rgba(16,185,129,0.25)]"
          : "bg-slate-200/80 border-white/70 shadow-[0_10px_25px_rgba(15,23,42,0.08)]",
      ].join(" ")}
    >
      <span
        aria-hidden="true"
        className={[
          "inline-block h-5 w-5 rounded-full bg-white shadow-[0_8px_18px_rgba(15,23,42,0.18)] transition-transform",
          checked ? "translate-x-5" : "translate-x-0.5",
        ].join(" ")}
      />
    </button>
  );
}

function fmtNullableInt(v: number | null): string {
  if (v === null) return "—";
  return new Intl.NumberFormat().format(v);
}

function ReadonlyField({
  label,
  value,
  mono,
  danger,
}: {
  label: string;
  value: string;
  mono?: boolean;
  danger?: boolean;
}) {
  return (
    <div className="space-y-1">
      <div className="text-[11px] font-medium text-slate-600">{label}</div>
      <div
        className={[
          "rounded-xl border px-3 py-2 text-xs",
          mono ? "font-mono" : "",
          danger
            ? "border-rose-200 bg-rose-50/70 text-rose-700"
            : "border-white/60 bg-white/50 text-slate-800",
        ].join(" ")}
      >
        {value}
      </div>
    </div>
  );
}

export default function AdminPricingPage() {
  const [rows, setRows] = useState<PricingItem[]>([]);
  const [liveModels, setLiveModels] = useState<LiveModelItem[]>([]);
  const [liveReady, setLiveReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [dirtyModels, setDirtyModels] = useState(() => new Set<string>());
  const [savingModels, setSavingModels] = useState(() => new Set<string>());
  const [editingModels, setEditingModels] = useState(() => new Set<string>());
  const [editSnapshots, setEditSnapshots] = useState(
    () => new Map<string, { snapshot: PricingItem; wasPersisted: boolean }>()
  );

  const [newModel, setNewModel] = useState("");
  const [newUpstreamChannel, setNewUpstreamChannel] = useState("");
  const [newCurrency, setNewCurrency] = useState("USD");

  const refreshLiveModels = useCallback(async () => {
    setLiveReady(false);
    setErrorText(null);
    try {
      const channels = await apiFetch<UpstreamChannelItem[]>("/admin/upstream/channels");
      const enabledChannels = (channels || []).filter((item) => item.is_enabled || item.is_default);
      const modelMap = new Map<string, LiveModelItem>();
      const channelErrors: string[] = [];

      const fetchOneChannel = async (targetChannel: string) => {
        try {
          const query = new URLSearchParams();
          if (targetChannel) query.set("channel", targetChannel);
          const suffix = query.toString();
          const payload = await apiFetch<{ data?: Array<{ id?: string }> }>(
            suffix ? `/admin/upstream/models?${suffix}` : "/admin/upstream/models"
          );
          const ids = (Array.isArray(payload?.data) ? payload.data : [])
            .map((item) => String(item?.id || "").trim())
            .filter(Boolean);
          ids.forEach((model) => {
            if (!modelMap.has(model)) {
              modelMap.set(model, { model, upstream_channel: targetChannel });
            }
          });
        } catch (e: unknown) {
          const channelLabel = targetChannel || "default";
          channelErrors.push(`[${channelLabel}] ${getErrorMessage(e)}`);
        }
      };

      const sortedChannels = (
        enabledChannels.length > 0
          ? [...enabledChannels].sort((a, b) => Number(a.is_default) - Number(b.is_default)).map((item) => item.channel)
          : [""]
      );
      await Promise.all(sortedChannels.map((item) => fetchOneChannel(item)));

      const items = Array.from(modelMap.values()).sort((a, b) => a.model.localeCompare(b.model));
      setLiveModels(items);
      setLiveReady(true);
      if (items.length === 0 && channelErrors.length > 0) {
        setErrorText(`实时模型拉取失败：${channelErrors.join("；")}`);
      } else if (channelErrors.length > 0) {
        setErrorText(`部分渠道拉取失败：${channelErrors.join("；")}`);
      }
    } catch (e: unknown) {
      setLiveModels([]);
      setLiveReady(true);
      setErrorText(getErrorMessage(e));
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setErrorText(null);
    try {
      const pricingRows = await apiFetch<PricingItem[]>("/admin/pricing/models");
      setRows(pricingRows || []);
      setDirtyModels(new Set());
      setEditingModels(new Set());
      setEditSnapshots(new Map());
      await refreshLiveModels();
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setRows([]);
      setLiveModels([]);
      setLiveReady(true);
      setDirtyModels(new Set());
      setEditingModels(new Set());
      setEditSnapshots(new Map());
    } finally {
      setLoading(false);
    }
  }, [refreshLiveModels]);

  useEffect(() => {
    load();
  }, [load]);

  const realtimeRows = useMemo(() => {
    if (!liveReady) return rows;
    if (liveModels.length === 0) return [];
    const byModel = new Map(rows.map((item) => [item.model, item]));
    return liveModels.map((item) => {
      const existed = byModel.get(item.model);
      if (existed) return existed;
      return {
        model: item.model,
        upstream_channel: item.upstream_channel || "",
        currency: "USD",
        unit: "microusd_per_1m_tokens",
        is_active: false,
        input_microusd_per_1m_tokens: null,
        cached_input_microusd_per_1m_tokens: null,
        output_microusd_per_1m_tokens: null,
        cached_output_microusd_per_1m_tokens: null,
      } satisfies PricingItem;
    });
  }, [liveModels, rows, liveReady]);

  const visibleRows = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return realtimeRows;
    return realtimeRows.filter((r) => r.model.toLowerCase().includes(q));
  }, [realtimeRows, filter]);

  const updateRow = (model: string, patch: Partial<PricingItem>) => {
    setDirtyModels((prev) => {
      const next = new Set(prev);
      next.add(model);
      return next;
    });
    setRows((prev) => {
      const existed = prev.find((r) => r.model === model);
      if (existed) {
        return prev.map((r) => (r.model === model ? { ...r, ...patch } : r));
      }
      const base = realtimeRows.find((r) => r.model === model);
      if (base) {
        return [...prev, { ...base, ...patch }];
      }
      return prev;
    });
  };

  const beginEdit = (row: PricingItem) => {
    const existed = rows.find((r) => r.model === row.model);
    setEditSnapshots((prev) => {
      const next = new Map(prev);
      next.set(row.model, { snapshot: existed ?? row, wasPersisted: !!existed });
      return next;
    });
    setEditingModels((prev) => {
      const next = new Set(prev);
      next.add(row.model);
      return next;
    });
    setErrorText(null);
  };

  const cancelEdit = (model: string) => {
    const snap = editSnapshots.get(model);
    setRows((prev) => {
      if (!snap) return prev;
      if (snap.wasPersisted) {
        return prev.map((r) => (r.model === model ? { ...snap.snapshot } : r));
      }
      return prev.filter((r) => r.model !== model);
    });
    setDirtyModels((prev) => {
      const next = new Set(prev);
      next.delete(model);
      return next;
    });
    setEditingModels((prev) => {
      const next = new Set(prev);
      next.delete(model);
      return next;
    });
    setEditSnapshots((prev) => {
      const next = new Map(prev);
      next.delete(model);
      return next;
    });
    setErrorText(null);
  };

  const saveRow = async (row: PricingItem) => {
    if (
      row.is_active &&
      (
        row.input_microusd_per_1m_tokens === null ||
        row.cached_input_microusd_per_1m_tokens === null ||
        row.output_microusd_per_1m_tokens === null ||
        row.cached_output_microusd_per_1m_tokens === null
      )
    ) {
      setErrorText("启用模型前请先填写 4 个价格字段（in / cached_in / out / cached_out）。");
      return;
    }

    setErrorText(null);
    setSavingModels((prev) => {
      const next = new Set(prev);
      next.add(row.model);
      return next;
    });
    try {
      const body: UpsertPricingRequest = {
        upstream_channel: row.upstream_channel,
        currency: row.currency,
        is_active: row.is_active,
        input_microusd_per_1m_tokens: row.input_microusd_per_1m_tokens,
        cached_input_microusd_per_1m_tokens: row.cached_input_microusd_per_1m_tokens,
        output_microusd_per_1m_tokens: row.output_microusd_per_1m_tokens,
        cached_output_microusd_per_1m_tokens: row.cached_output_microusd_per_1m_tokens,
      };
      await apiFetch(`/admin/pricing/models/${encodeURIComponent(row.model)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setDirtyModels((prev) => {
        const next = new Set(prev);
        next.delete(row.model);
        return next;
      });
      setEditingModels((prev) => {
        const next = new Set(prev);
        next.delete(row.model);
        return next;
      });
      setEditSnapshots((prev) => {
        const next = new Map(prev);
        next.delete(row.model);
        return next;
      });
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    } finally {
      setSavingModels((prev) => {
        const next = new Set(prev);
        next.delete(row.model);
        return next;
      });
    }
  };

  const createModel = async () => {
    const model = newModel.trim();
    if (!model) return;
    setErrorText(null);
    setSavingModels((prev) => {
      const next = new Set(prev);
      next.add("__new__");
      return next;
    });
    try {
      await apiFetch(`/admin/pricing/models/${encodeURIComponent(model)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upstream_channel: newUpstreamChannel,
          currency: newCurrency,
          is_active: false,
        }),
      });
      setNewModel("");
      setNewUpstreamChannel("");
      await load();
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    } finally {
      setSavingModels((prev) => {
        const next = new Set(prev);
        next.delete("__new__");
        return next;
      });
    }
  };

  const stats = useMemo(() => {
    const activeCount = realtimeRows.filter((r) => r.is_active).length;
    const dirtyCount = dirtyModels.size;
    const missingActive = realtimeRows.filter((r) => r.is_active && hasAnyMissingPriceField(r)).length;
    const missingAny = realtimeRows.filter((r) => hasAnyMissingPriceField(r)).length;
    const serverModelSet = new Set(rows.map((r) => r.model));
    const discovered = liveModels.filter((m) => !serverModelSet.has(m.model)).length;
    return {
      total: realtimeRows.length,
      visible: visibleRows.length,
      activeCount,
      dirtyCount,
      missingActive,
      missingAny,
      discovered,
    };
  }, [dirtyModels.size, liveModels, realtimeRows, rows, visibleRows.length]);

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-screen min-h-[100dvh] box-border pt-14 overflow-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
            <div className="glass-panel-strong p-4 md:p-5 flex flex-wrap items-center gap-3">
              <div className="min-w-[12rem]">
                <h1 className="text-xl font-semibold tracking-tight" style={{ color: "var(--text-primary)" }}>
                  Admin / Pricing
                </h1>
                <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                  只读浏览 · 按需编辑 · 实时发现
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
                <span className="glass-chip px-2 py-1">
                  总数 <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{stats.total}</span>
                </span>
                <span className="glass-chip px-2 py-1">
                  可见 <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{stats.visible}</span>
                </span>
                <span className="glass-chip px-2 py-1">
                  Active <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{stats.activeCount}</span>
                </span>
                <span className="glass-chip px-2 py-1">
                  待保存 <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{stats.dirtyCount}</span>
                </span>
                <span className="glass-chip px-2 py-1">
                  实时发现 <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{stats.discovered}</span>
                </span>
                <span className="glass-chip px-2 py-1">
                  缺失定价 <span className="font-semibold" style={{ color: "var(--text-primary)" }}>{stats.missingAny}</span>
                </span>
              </div>
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={load}
                  className="glass-btn"
                >
                  {loading ? "刷新中…" : "刷新（实时模型）"}
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
              <div className="glass-panel p-4 lg:col-span-7">
                <div className="flex items-center gap-2 mb-3">
                  <div className="text-sm font-semibold text-slate-900">新增模型（创建 / 占位）</div>
                  <div className="ml-auto text-xs text-slate-500">
                    启用前需填齐 4 个字段（in / cached_in / out / cached_out）
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-12 gap-2">
                  <label className="md:col-span-6 space-y-1">
                    <div className="text-[11px] font-medium text-slate-600">model</div>
                    <input
                      value={newModel}
                      onChange={(e) => setNewModel(e.target.value)}
                      placeholder="例如 gpt-4o-mini"
                      className="glass-input text-sm font-mono"
                    />
                  </label>
                  <label className="md:col-span-3 space-y-1">
                    <div className="text-[11px] font-medium text-slate-600">upstream_channel</div>
                    <input
                      value={newUpstreamChannel}
                      onChange={(e) => setNewUpstreamChannel(e.target.value)}
                      placeholder="例如 openai"
                      className="glass-input text-sm"
                    />
                  </label>
                  <label className="md:col-span-2 space-y-1">
                    <div className="text-[11px] font-medium text-slate-600">currency</div>
                    <input
                      value={newCurrency}
                      onChange={(e) => setNewCurrency(e.target.value)}
                      className="glass-input text-sm"
                    />
                  </label>
                  <div className="md:col-span-1 flex items-end">
                    <button
                      type="button"
                      onClick={createModel}
                      disabled={!newModel.trim() || savingModels.has("__new__")}
                      className="glass-btn w-full"
                    >
                      {savingModels.has("__new__") ? "创建中…" : "创建"}
                    </button>
                  </div>
                </div>
              </div>

              <div className="glass-panel p-4 lg:col-span-5">
                <div className="flex items-center gap-2 mb-3">
                  <div className="text-sm font-semibold text-slate-900">过滤</div>
                  <div className="ml-auto text-xs text-slate-500">
                    {stats.missingActive > 0 ? `⚠️ active 且缺失定价：${stats.missingActive}` : liveReady ? "实时就绪" : "拉取中…"}
                  </div>
                </div>
                <input
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  placeholder="按 model 名称过滤…"
                  className="glass-input text-sm"
                />
                <div className="mt-2 text-xs text-slate-500">
                  列表自动聚合全部已启用渠道的实时 model id；点击「编辑」进入编辑态后才可修改字段并保存。
                </div>
              </div>
            </div>

          {errorText ? (
            <div className="glass-alert glass-alert-error">
              {errorText}
            </div>
          ) : null}

          {loading ? (
            <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
          ) : (
            <div className="space-y-3">
              {visibleRows.length === 0 ? (
                <div className="glass-panel p-4 text-sm text-slate-600">无匹配结果。</div>
              ) : null}

              {visibleRows.map((r) => {
                const isEditing = editingModels.has(r.model);
                const isDirty = dirtyModels.has(r.model);
                const isSaving = savingModels.has(r.model);
                const missingPrice = hasAnyMissingPriceField(r);
                const canSave = isDirty && !isSaving;
                const channelLabel = (r.upstream_channel || "").trim() || "未分配";
                return (
                  <div
                    key={r.model}
                    className={[
                      "glass-panel p-4 md:p-5 transition-all",
                      "hover:shadow-[0_18px_50px_rgba(15,23,42,0.12)] hover:-translate-y-[1px]",
                      r.is_active ? "ring-1 ring-emerald-400/25" : "ring-1 ring-slate-200/35",
                      missingPrice && r.is_active ? "ring-2 ring-rose-400/25" : "",
                    ].join(" ")}
                  >
                    <div className="flex flex-wrap items-start gap-3">
                      <div className="min-w-[16rem]">
                        <div className="flex items-center gap-2">
                          <div className="font-mono text-xs text-slate-900">{prefixedModelName(r.model, channelLabel)}</div>
                          <span
                            className={[
                              "text-[10px] px-2 py-0.5 rounded-full border",
                              r.is_active
                                ? "border-emerald-200 bg-emerald-50/80 text-emerald-700"
                                : "border-slate-200 bg-slate-50/80 text-slate-600",
                            ].join(" ")}
                          >
                            {r.is_active ? "ACTIVE" : "INACTIVE"}
                          </span>
                          {isDirty ? (
                            <span className="text-[10px] px-2 py-0.5 rounded-full border border-indigo-200 bg-indigo-50/80 text-indigo-700">
                              待保存
                            </span>
                          ) : null}
                        </div>
                        <div className="font-mono text-[10px] text-slate-500 mt-1 break-all">{r.model}</div>
                      </div>

                      <div className="ml-auto flex items-center gap-3">
                        {isEditing ? (
                          <>
                            <div className="flex items-center gap-2">
                              <div className="text-[11px] text-slate-500">启用</div>
                              <Toggle
                                checked={!!r.is_active}
                                onChange={(v) => updateRow(r.model, { is_active: v })}
                                label="启用模型"
                              />
                            </div>
                            <button
                              type="button"
                              onClick={() => saveRow(r)}
                              disabled={!canSave}
                              className={[
                                "glass-btn text-xs px-3 py-2",
                                canSave ? "" : "opacity-60 cursor-not-allowed",
                              ].join(" ")}
                            >
                              {isSaving ? "保存中…" : "保存"}
                            </button>
                            <button
                              type="button"
                              onClick={() => cancelEdit(r.model)}
                              disabled={isSaving}
                              className="glass-btn glass-btn-secondary text-xs px-3 py-2"
                            >
                              取消
                            </button>
                          </>
                        ) : (
                          <>
                            <div className="text-[11px] text-slate-500">
                              {r.is_active ? "已启用" : "未启用"}
                            </div>
                            <button
                              type="button"
                              onClick={() => beginEdit(r)}
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
                        <div className="mt-4 grid grid-cols-1 md:grid-cols-12 gap-2">
                          <label className="md:col-span-4 space-y-1">
                            <div className="text-[11px] font-medium text-slate-600">upstream_channel</div>
                            <input
                              value={r.upstream_channel || ""}
                              onChange={(e) => updateRow(r.model, { upstream_channel: e.target.value })}
                              className="glass-input text-sm"
                              placeholder="渠道"
                            />
                          </label>
                          <label className="md:col-span-2 space-y-1">
                            <div className="text-[11px] font-medium text-slate-600">currency</div>
                            <input
                              value={r.currency || ""}
                              onChange={(e) => updateRow(r.model, { currency: e.target.value })}
                              className="glass-input text-sm"
                            />
                          </label>
                          <div className="md:col-span-6">
                            <div className="text-[11px] font-medium text-slate-600">unit</div>
                            <div className="mt-1 text-xs text-slate-500 font-mono rounded-xl border border-white/60 bg-white/50 px-3 py-2">
                              {r.unit}
                            </div>
                          </div>
                        </div>

                        <div className="mt-3 grid grid-cols-1 md:grid-cols-12 gap-2">
                          <label className="md:col-span-3 space-y-1">
                            <div className="text-[11px] font-medium text-slate-600">in</div>
                            <input
                              value={numberToInputValue(r.input_microusd_per_1m_tokens)}
                              onChange={(e) =>
                                updateRow(r.model, { input_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                              }
                              className={[
                                "glass-input text-sm py-2 font-mono",
                                r.is_active && r.input_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                              ].join(" ")}
                              placeholder="microusd"
                            />
                          </label>
                          <label className="md:col-span-3 space-y-1">
                            <div className="text-[11px] font-medium text-slate-600">cached_in</div>
                            <input
                              value={numberToInputValue(r.cached_input_microusd_per_1m_tokens)}
                              onChange={(e) =>
                                updateRow(r.model, { cached_input_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                              }
                              className={[
                                "glass-input text-sm py-2 font-mono",
                                r.is_active && r.cached_input_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                              ].join(" ")}
                              placeholder="microusd"
                            />
                          </label>
                          <label className="md:col-span-3 space-y-1">
                            <div className="text-[11px] font-medium text-slate-600">out</div>
                            <input
                              value={numberToInputValue(r.output_microusd_per_1m_tokens)}
                              onChange={(e) =>
                                updateRow(r.model, { output_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                              }
                              className={[
                                "glass-input text-sm py-2 font-mono",
                                r.is_active && r.output_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                              ].join(" ")}
                              placeholder="microusd"
                            />
                          </label>
                          <label className="md:col-span-3 space-y-1">
                            <div className="text-[11px] font-medium text-slate-600">cached_out</div>
                            <input
                              value={numberToInputValue(r.cached_output_microusd_per_1m_tokens)}
                              onChange={(e) =>
                                updateRow(r.model, { cached_output_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                              }
                              className={[
                                "glass-input text-sm py-2 font-mono",
                                r.is_active && r.cached_output_microusd_per_1m_tokens === null ? "border-rose-200 bg-rose-50/70" : "",
                              ].join(" ")}
                              placeholder="microusd"
                            />
                          </label>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="mt-4 grid grid-cols-1 md:grid-cols-12 gap-2">
                          <div className="md:col-span-4">
                            <ReadonlyField label="upstream_channel" value={channelLabel} mono />
                          </div>
                          <div className="md:col-span-2">
                            <ReadonlyField label="currency" value={(r.currency || "").trim() || "—"} />
                          </div>
                          <div className="md:col-span-6">
                            <ReadonlyField label="unit" value={r.unit || "—"} mono />
                          </div>
                        </div>
                        <div className="mt-3 grid grid-cols-1 md:grid-cols-12 gap-2">
                          <div className="md:col-span-3">
                            <ReadonlyField
                              label="in"
                              value={fmtNullableInt(r.input_microusd_per_1m_tokens)}
                              mono
                              danger={r.is_active && r.input_microusd_per_1m_tokens === null}
                            />
                          </div>
                          <div className="md:col-span-3">
                            <ReadonlyField
                              label="cached_in"
                              value={fmtNullableInt(r.cached_input_microusd_per_1m_tokens)}
                              mono
                              danger={r.is_active && r.cached_input_microusd_per_1m_tokens === null}
                            />
                          </div>
                          <div className="md:col-span-3">
                            <ReadonlyField
                              label="out"
                              value={fmtNullableInt(r.output_microusd_per_1m_tokens)}
                              mono
                              danger={r.is_active && r.output_microusd_per_1m_tokens === null}
                            />
                          </div>
                          <div className="md:col-span-3">
                            <ReadonlyField
                              label="cached_out"
                              value={fmtNullableInt(r.cached_output_microusd_per_1m_tokens)}
                              mono
                              danger={r.is_active && r.cached_output_microusd_per_1m_tokens === null}
                            />
                          </div>
                        </div>
                      </>
                    )}

                    {r.is_active && missingPrice ? (
                      <div className="mt-3 text-xs text-rose-700 border border-rose-200 bg-rose-50/70 rounded-xl px-3 py-2">
                        启用前必须填齐 4 个价格字段；否则保存会失败（后端 422）。
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}
