"use client";

// 管理员上游渠道/模型探测页（/admin/upstream-models）。
//
// 拆分目标：降低单文件体积与函数长度，避免工具将 localStorage 失败标记为“忽略错误”。

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

import type {
  ChannelFetchResult,
  PrefixedModelRow,
  UpstreamChannelFormItem,
  UpstreamChannelItem,
} from "./upstreamModelsTypes";
import { DEFAULT_AUTO_REFRESH_SECONDS } from "./upstreamModelsTypes";
import {
  persistAutoRefreshSecondsToStorage,
  readAutoRefreshSecondsFromStorage,
  readModelsCacheFromStorage,
  restoreModelsFromCache,
  writeModelsCacheToStorage,
} from "./upstreamModelsStorage";
import {
  formatUpstreamError,
  isRecommendedModelName,
  normalizeModelsPath,
  prefixedModelName,
  withFormState,
} from "./upstreamModelsUtils";
import { UpstreamModelsHeader } from "./components/UpstreamModelsHeader";
import { ChannelConfigPanel } from "./components/ChannelConfigPanel";
import { CreateChannelModal, type CreateChannelDraft } from "./components/CreateChannelModal";
import { PrefixedModelsPanel } from "./components/PrefixedModelsPanel";
import { RawJsonDetails } from "./components/RawJsonDetails";

const DEFAULT_DRAFT: CreateChannelDraft = {
  channel: "",
  displayName: "",
  baseUrl: "",
  apiKey: "",
  modelsPath: "/v1/models",
  isEnabled: true,
};

export function AdminUpstreamModelsPageClient() {
  const [channels, setChannels] = useState<UpstreamChannelFormItem[]>([]);
  const [results, setResults] = useState<ChannelFetchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [savingChannel, setSavingChannel] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAllModels, setShowAllModels] = useState(false);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(DEFAULT_AUTO_REFRESH_SECONDS);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);
  const [createDraft, setCreateDraft] = useState<CreateChannelDraft>(DEFAULT_DRAFT);

  const fetchModels = useCallback(async (channelList: UpstreamChannelFormItem[]) => {
    const activeChannels = channelList.filter((item) => item.is_enabled);
    if (activeChannels.length === 0) {
      return [] as ChannelFetchResult[];
    }

    const fetched = await Promise.all(
      activeChannels.map(async (item) => {
        try {
          const query = new URLSearchParams();
          if (item.channel) {
            query.set("channel", item.channel);
          }
          const suffix = query.toString();
          const url = suffix ? `/admin/upstream/models?${suffix}` : "/admin/upstream/models";
          const payload = await apiFetch<unknown>(url);
          return { channel: item, payload, errorText: null } satisfies ChannelFetchResult;
        } catch (e: unknown) {
          return {
            channel: item,
            payload: null,
            errorText: getErrorMessage(e),
          } satisfies ChannelFetchResult;
        }
      })
    );

    return fetched;
  }, []);

  const loadAll = useCallback(
    async (opts?: { force?: boolean }) => {
      setLoading(true);
      setErrorText(null);
      try {
        const rawItems = await apiFetch<UpstreamChannelItem[]>("/admin/upstream/channels");
        const items = withFormState(rawItems || []);
        setChannels(items);
        const activeChannels = items.filter((item) => item.is_enabled);
        if (activeChannels.length === 0) {
          setResults([]);
          setErrorText("当前没有可查询渠道，请至少启用一个渠道。");
          setLastUpdatedAt(null);
          return;
        }

        if (!opts?.force) {
          const cached = readModelsCacheFromStorage();
          const maxAgeSeconds = autoRefreshSeconds > 0 ? autoRefreshSeconds : DEFAULT_AUTO_REFRESH_SECONDS;
          const maxAgeMs = maxAgeSeconds * 1000;
          if (cached && Date.now() - cached.ts <= maxAgeMs) {
            const restored = restoreModelsFromCache(activeChannels, cached);
            if (restored && restored.length > 0) {
              setResults(restored);
              setLastUpdatedAt(cached.ts);
              const failedFromCache = restored.filter((x) => !!x.errorText);
              if (failedFromCache.length > 0) {
                const summary = failedFromCache
                  .map((x) => `[${x.channel.display_name}] ${formatUpstreamError(x.errorText || "")}`)
                  .join("；");
                setErrorText(`部分渠道获取失败（缓存）：${summary}`);
              }
              return;
            }
          }
        }

        const fetched = await fetchModels(items);
        setResults(fetched);
        setLastUpdatedAt(writeModelsCacheToStorage(fetched));
        const failed = fetched.filter((x) => !!x.errorText);
        if (failed.length > 0) {
          const summary = failed
            .map((x) => `[${x.channel.display_name}] ${formatUpstreamError(x.errorText || "")}`)
            .join("；");
          setErrorText(`部分渠道获取失败：${summary}`);
        }
      } catch (e: unknown) {
        setErrorText(getErrorMessage(e));
        setChannels([]);
        setResults([]);
        setLastUpdatedAt(null);
      } finally {
        setLoading(false);
      }
    },
    [autoRefreshSeconds, fetchModels]
  );

  useEffect(() => {
    const saved = readAutoRefreshSecondsFromStorage();
    if (saved !== null) {
      setAutoRefreshSeconds(saved);
    }
  }, []);

  useEffect(() => {
    persistAutoRefreshSecondsToStorage(autoRefreshSeconds);
  }, [autoRefreshSeconds]);

  useEffect(() => {
    void loadAll({ force: false });
  }, [loadAll]);

  useEffect(() => {
    if (autoRefreshSeconds <= 0) return;
    const timer = window.setInterval(() => {
      void loadAll({ force: true });
    }, autoRefreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [autoRefreshSeconds, loadAll]);

  const prefixedModels = useMemo(() => {
    const rows: PrefixedModelRow[] = [];
    results.forEach((item) => {
      if (!item.payload) return;
      const channelDisplay = item.channel.display_name || "default";
      const data = item.payload as { data?: Array<{ id?: string }> };
      const modelItems = Array.isArray(data?.data) ? data.data : [];
      modelItems.forEach((modelItem) => {
        const modelName = String(modelItem?.id || "").trim();
        if (!modelName) return;
        rows.push({
          channel: channelDisplay,
          model: modelName,
          prefixed: prefixedModelName(channelDisplay, modelName),
        });
      });
    });
    rows.sort((a, b) => a.prefixed.localeCompare(b.prefixed));
    return rows;
  }, [results]);

  const visiblePrefixedModels = useMemo(() => {
    if (showAllModels) return prefixedModels;
    return prefixedModels.filter((row) => isRecommendedModelName(row.model));
  }, [prefixedModels, showAllModels]);

  const updateChannelField = useCallback((channel: string, patch: Partial<UpstreamChannelFormItem>) => {
    setChannels((prev) => prev.map((item) => (item.channel === channel ? { ...item, ...patch } : item)));
  }, []);

  const saveChannel = useCallback(
    async (channel: string) => {
      const row = channels.find((x) => x.channel === channel);
      if (!row || row.is_default) return;

      const body: Record<string, unknown> = {
        display_name: row.display_name,
        base_url: row.base_url,
        models_path: normalizeModelsPath(row.models_path),
        is_enabled: row.is_enabled,
      };
      const apiKeyText = row.api_key_input.trim();
      if (apiKeyText) {
        body.api_key = apiKeyText;
      }

      setSavingChannel(channel);
      setErrorText(null);
      try {
        await apiFetch(`/admin/upstream/channels/${encodeURIComponent(channel)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        await loadAll({ force: true });
      } catch (e: unknown) {
        setErrorText(getErrorMessage(e));
      } finally {
        setSavingChannel(null);
      }
    },
    [channels, loadAll]
  );

  const deleteChannel = useCallback(
    async (channel: string) => {
      if (!window.confirm(`确认删除渠道 "${channel}" 吗？`)) return;
      setSavingChannel(channel);
      setErrorText(null);
      try {
        await apiFetch(`/admin/upstream/channels/${encodeURIComponent(channel)}`, {
          method: "DELETE",
        });
        await loadAll({ force: true });
      } catch (e: unknown) {
        setErrorText(getErrorMessage(e));
      } finally {
        setSavingChannel(null);
      }
    },
    [loadAll]
  );

  const onDraftChange = useCallback((patch: Partial<CreateChannelDraft>) => {
    setCreateDraft((prev) => ({ ...prev, ...patch }));
  }, []);

  const resetDraftAndClose = useCallback(() => {
    setCreateDraft(DEFAULT_DRAFT);
    setShowCreateModal(false);
  }, []);

  const createChannel = useCallback(async () => {
    const channel = createDraft.channel.trim();
    if (!channel) {
      setErrorText("请先填写渠道名称。");
      return;
    }
    const apiKeyText = createDraft.apiKey.trim();
    if (!apiKeyText) {
      setErrorText("新增渠道必须填写 API Key。");
      return;
    }

    setSavingChannel("__new__");
    setErrorText(null);
    try {
      await apiFetch(`/admin/upstream/channels/${encodeURIComponent(channel)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          display_name: (createDraft.displayName || channel).trim(),
          base_url: createDraft.baseUrl,
          api_key: apiKeyText,
          models_path: normalizeModelsPath(createDraft.modelsPath),
          is_enabled: createDraft.isEnabled,
        }),
      });
      resetDraftAndClose();
      await loadAll({ force: true });
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
    } finally {
      setSavingChannel(null);
    }
  }, [createDraft, loadAll, resetDraftAndClose]);

  const onRefreshAll = useCallback(() => {
    void loadAll({ force: true });
  }, [loadAll]);

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-full min-h-[100dvh] box-border pt-14 overflow-x-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
            <UpstreamModelsHeader
              autoRefreshSeconds={autoRefreshSeconds}
              onAutoRefreshSecondsChange={setAutoRefreshSeconds}
              onRefreshAll={onRefreshAll}
            />

            <div className="text-xs text-slate-500 px-1">
              最近更新时间：{lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "暂无"}
            </div>

            <ChannelConfigPanel
              channels={channels}
              deleteChannel={(channel) => void deleteChannel(channel)}
              onOpenCreateModal={() => setShowCreateModal(true)}
              saveChannel={(channel) => void saveChannel(channel)}
              savingChannel={savingChannel}
              updateChannelField={updateChannelField}
            />

            <CreateChannelModal
              open={showCreateModal}
              isSaving={savingChannel === "__new__"}
              draft={createDraft}
              onDraftChange={onDraftChange}
              onClose={resetDraftAndClose}
              onCreate={createChannel}
            />

            {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}

            {loading ? (
              <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
            ) : (
              <>
                <PrefixedModelsPanel
                  showAllModels={showAllModels}
                  onShowAllModelsChange={setShowAllModels}
                  visiblePrefixedModels={visiblePrefixedModels}
                />
                <RawJsonDetails results={results} />
              </>
            )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}

