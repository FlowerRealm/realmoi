"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { FluidBackground } from "@/components/assistant/FluidBackground";
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

export default function AdminPricingPage() {
  const [rows, setRows] = useState<PricingItem[]>([]);
  const [liveModels, setLiveModels] = useState<LiveModelItem[]>([]);
  const [liveReady, setLiveReady] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

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
      await refreshLiveModels();
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setRows([]);
      setLiveModels([]);
      setLiveReady(true);
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
      await load();
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    }
  };

  const createModel = async () => {
    const model = newModel.trim();
    if (!model) return;
    setErrorText(null);
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
    }
  };

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-screen min-h-[100dvh] box-border pt-14 overflow-hidden text-slate-800 selection:bg-indigo-500/20">
          <FluidBackground />
          <AppHeader mode="overlay" />
          <main className="mx-auto max-w-6xl px-4 pt-8 pb-6 space-y-4 relative z-10">
          <div className="glass-panel-strong p-4 md:p-5 flex items-center gap-3">
            <div>
              <h1 className="text-xl font-semibold text-slate-900">Admin / Pricing</h1>
              <p className="text-xs text-slate-500 mt-1">管理可用模型与四类 token 单价</p>
            </div>
            <button
              type="button"
              onClick={load}
              className="ml-auto glass-btn"
            >
              刷新（实时模型）
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="glass-panel p-4">
              <div className="text-sm font-semibold text-slate-900 mb-2">新增模型（创建/占位）</div>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={newModel}
                  onChange={(e) => setNewModel(e.target.value)}
                  placeholder="model 名称，例如 gpt-4o-mini"
                  className="glass-input w-72 max-w-full text-sm"
                />
                <input
                  value={newUpstreamChannel}
                  onChange={(e) => setNewUpstreamChannel(e.target.value)}
                  placeholder="上游渠道，例如 openai"
                  className="glass-input w-40 text-sm"
                />
                <input
                  value={newCurrency}
                  onChange={(e) => setNewCurrency(e.target.value)}
                  className="glass-input w-24 text-sm"
                />
                <button
                  type="button"
                  onClick={createModel}
                  className="glass-btn"
                >
                  创建
                </button>
              </div>
              <div className="mt-2 text-xs text-slate-500">
                提示：激活（is_active=true）前必须填齐 4 个价格字段，否则后端会 422。
              </div>
            </div>

            <div className="glass-panel p-4">
              <div className="text-sm font-semibold text-slate-900 mb-2">过滤</div>
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="按 model 名称过滤…"
                className="glass-input text-sm"
              />
              <div className="mt-2 text-xs text-slate-500">显示 {visibleRows.length} / {realtimeRows.length}</div>
            </div>
          </div>

          <div className="glass-panel p-4 text-xs text-slate-500">
            当前列表自动聚合全部已启用渠道的实时 model id，不再显示来源选择字段。
          </div>

          {errorText ? (
            <div className="glass-alert glass-alert-error">
              {errorText}
            </div>
          ) : null}

          {loading ? (
            <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
          ) : (
            <div className="glass-table overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-slate-600">
                  <tr>
                    <th className="text-left font-semibold px-3 py-2">model</th>
                    <th className="text-left font-semibold px-3 py-2">upstream_channel</th>
                    <th className="text-left font-semibold px-3 py-2">active</th>
                    <th className="text-left font-semibold px-3 py-2">currency</th>
                    <th className="text-left font-semibold px-3 py-2">unit</th>
                    <th className="text-left font-semibold px-3 py-2">in</th>
                    <th className="text-left font-semibold px-3 py-2">cached_in</th>
                    <th className="text-left font-semibold px-3 py-2">out</th>
                    <th className="text-left font-semibold px-3 py-2">cached_out</th>
                    <th className="text-left font-semibold px-3 py-2">actions</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((r) => (
                    <tr key={r.model}>
                      <td className="px-3 py-2">
                        <div className="font-mono text-xs text-slate-900">{prefixedModelName(r.model, r.upstream_channel || "")}</div>
                        <div className="font-mono text-[10px] text-slate-500 mt-1">{r.model}</div>
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={r.upstream_channel || ""}
                          onChange={(e) => updateRow(r.model, { upstream_channel: e.target.value })}
                          className="glass-input w-40 text-sm py-1.5"
                          placeholder="渠道"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={!!r.is_active}
                          onChange={(e) => updateRow(r.model, { is_active: e.target.checked })}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={r.currency || ""}
                          onChange={(e) => updateRow(r.model, { currency: e.target.value })}
                          className="glass-input w-20 text-sm py-1.5"
                        />
                      </td>
                      <td className="px-3 py-2 text-xs text-slate-500">{r.unit}</td>
                      <td className="px-3 py-2">
                        <input
                          value={numberToInputValue(r.input_microusd_per_1m_tokens)}
                          onChange={(e) =>
                            updateRow(r.model, { input_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                          }
                          className="glass-input w-32 text-sm py-1.5 font-mono"
                          placeholder="microusd"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={numberToInputValue(r.cached_input_microusd_per_1m_tokens)}
                          onChange={(e) =>
                            updateRow(r.model, { cached_input_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                          }
                          className="glass-input w-32 text-sm py-1.5 font-mono"
                          placeholder="microusd"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={numberToInputValue(r.output_microusd_per_1m_tokens)}
                          onChange={(e) =>
                            updateRow(r.model, { output_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                          }
                          className="glass-input w-32 text-sm py-1.5 font-mono"
                          placeholder="microusd"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <input
                          value={numberToInputValue(r.cached_output_microusd_per_1m_tokens)}
                          onChange={(e) =>
                            updateRow(r.model, { cached_output_microusd_per_1m_tokens: parseIntOrNull(e.target.value) })
                          }
                          className="glass-input w-32 text-sm py-1.5 font-mono"
                          placeholder="microusd"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => saveRow(r)}
                          className="glass-btn glass-btn-secondary text-xs px-2 py-1.5"
                        >
                          保存
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}
