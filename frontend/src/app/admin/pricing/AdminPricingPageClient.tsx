"use client";

// 管理员定价管理页（/admin/pricing）。
//
// 设计要点：
// - 实时模型列表用于“发现新模型”，定价列表用于“持久化配置”；两者按 model 名聚合。
// - 保存/刷新都应为显式操作；异步 handler 对外暴露为同步函数，避免“未处理的 Promise”被工具计为忽略错误。

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

import type { LiveModelItem, PricingItem, PricingStats, UpsertPricingRequest, UpstreamChannelItem } from "./pricingTypes";
import { hasAnyMissingPriceField } from "./pricingUtils";
import { PricingHeader } from "./components/PricingHeader";
import { NewModelPanel } from "./components/NewModelPanel";
import { FilterPanel } from "./components/FilterPanel";
import { PricingModelList } from "./components/PricingModelList";

export function AdminPricingPageClient() {
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

  const refreshLiveModelsAsync = useCallback(async () => {
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

      const sortedChannels =
        enabledChannels.length > 0
          ? [...enabledChannels]
              .sort((a, b) => Number(a.is_default) - Number(b.is_default))
              .map((item) => item.channel)
          : [""];
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

  const loadAsync = useCallback(async () => {
    setLoading(true);
    setErrorText(null);
    try {
      const pricingRows = await apiFetch<PricingItem[]>("/admin/pricing/models");
      setRows(pricingRows || []);
      setDirtyModels(new Set());
      setEditingModels(new Set());
      setEditSnapshots(new Map());
      await refreshLiveModelsAsync();
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
      setRows([]);
      setLiveModels([]);
      setLiveReady(true);
      setDirtyModels(new Set());
      setEditingModels(new Set());
      setEditSnapshots(new Map());
    } finally {
      setLoading(false);
    }
  }, [refreshLiveModelsAsync]);

  const load = useCallback(() => {
    void loadAsync();
  }, [loadAsync]);

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

  const updateRow = useCallback(
    (model: string, patch: Partial<PricingItem>) => {
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
    },
    [realtimeRows]
  );

  const beginEdit = useCallback(
    (row: PricingItem) => {
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
    },
    [rows]
  );

  const cancelEdit = useCallback(
    (model: string) => {
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
    },
    [editSnapshots]
  );

  const saveRowAsync = useCallback(async (row: PricingItem) => {
    if (
      row.is_active &&
      (row.input_microusd_per_1m_tokens === null ||
        row.cached_input_microusd_per_1m_tokens === null ||
        row.output_microusd_per_1m_tokens === null ||
        row.cached_output_microusd_per_1m_tokens === null)
    ) {
      setErrorText("启用模型前请先填写 4 个价格字段（in / cached_in / out / cached_out）。");
      return;
    }

    setErrorText(null);
    setSavingModels((prev) => new Set(prev).add(row.model));
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
      setErrorText(getErrorMessage(e));
    } finally {
      setSavingModels((prev) => {
        const next = new Set(prev);
        next.delete(row.model);
        return next;
      });
    }
  }, []);

  const saveRow = useCallback(
    (row: PricingItem) => {
      void saveRowAsync(row);
    },
    [saveRowAsync]
  );

  const createModelAsync = useCallback(async () => {
    const model = newModel.trim();
    if (!model) return;
    setErrorText(null);
    setSavingModels((prev) => new Set(prev).add("__new__"));
    try {
      await apiFetch(`/admin/pricing/models/${encodeURIComponent(model)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          upstream_channel: newUpstreamChannel,
          is_active: false,
        }),
      });
      setNewModel("");
      setNewUpstreamChannel("");
      await loadAsync();
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
    } finally {
      setSavingModels((prev) => {
        const next = new Set(prev);
        next.delete("__new__");
        return next;
      });
    }
  }, [loadAsync, newModel, newUpstreamChannel]);

  const createModel = useCallback(() => {
    void createModelAsync();
  }, [createModelAsync]);

  const stats = useMemo((): PricingStats => {
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
        <div className="relative w-full min-h-[100dvh] box-border pt-14 overflow-x-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
            <PricingHeader loading={loading} stats={stats} onRefresh={load} />

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-3">
              <NewModelPanel
                newModel={newModel}
                newUpstreamChannel={newUpstreamChannel}
                setNewModel={setNewModel}
                setNewUpstreamChannel={setNewUpstreamChannel}
                isSaving={savingModels.has("__new__")}
                onCreate={createModel}
              />
              <FilterPanel
                filter={filter}
                liveReady={liveReady}
                missingActive={stats.missingActive}
                onFilterChange={setFilter}
              />
            </div>

            {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}

            {loading ? (
              <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
            ) : (
              <PricingModelList
                rows={visibleRows}
                dirtyModels={dirtyModels}
                savingModels={savingModels}
                editingModels={editingModels}
                beginEdit={beginEdit}
                cancelEdit={cancelEdit}
                saveRow={saveRow}
                updateRow={updateRow}
              />
            )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}

