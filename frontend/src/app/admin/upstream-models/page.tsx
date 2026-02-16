"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

type UpstreamChannelItem = {
  channel: string;
  display_name: string;
  base_url: string;
  api_key_masked: string;
  has_api_key: boolean;
  models_path: string;
  is_default: boolean;
  is_enabled: boolean;
  source: string;
};

type UpstreamChannelFormItem = UpstreamChannelItem & {
  api_key_input: string;
};

type ChannelFetchResult = {
  channel: UpstreamChannelFormItem;
  payload: unknown | null;
  errorText: string | null;
};

type CachedChannelFetchItem = {
  channel: string;
  payload: unknown | null;
  errorText: string | null;
};

type CachedModelsSnapshot = {
  ts: number;
  items: CachedChannelFetchItem[];
};

const AUTO_REFRESH_STORAGE_KEY = "realmoi_admin_upstream_auto_refresh_seconds";
const MODELS_CACHE_STORAGE_KEY = "realmoi_admin_upstream_models_cache_v1";
const DEFAULT_AUTO_REFRESH_SECONDS = 180;

function channelKey(channel: string): string {
  return channel || "__default__";
}

function readAutoRefreshSecondsFromStorage(): number | null {
  try {
    const raw = localStorage.getItem(AUTO_REFRESH_STORAGE_KEY);
    if (!raw) return null;
    const n = Number(raw);
    if (!Number.isFinite(n) || n < 0) return null;
    return Math.trunc(n);
  } catch {
    return null;
  }
}

function readModelsCacheFromStorage(): CachedModelsSnapshot | null {
  try {
    const raw = localStorage.getItem(MODELS_CACHE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedModelsSnapshot;
    if (!parsed || typeof parsed !== "object") return null;
    if (!Number.isFinite(parsed.ts)) return null;
    if (!Array.isArray(parsed.items)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeModelsCacheToStorage(items: ChannelFetchResult[]): number {
  const ts = Date.now();
  const payload: CachedModelsSnapshot = {
    ts,
    items: items.map((item) => ({
      channel: item.channel.channel,
      payload: item.payload,
      errorText: item.errorText,
    })),
  };
  try {
    localStorage.setItem(MODELS_CACHE_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    return ts;
  }
  return ts;
}

function restoreModelsFromCache(
  activeChannels: UpstreamChannelFormItem[],
  snapshot: CachedModelsSnapshot
): ChannelFetchResult[] | null {
  const cacheMap = new Map(snapshot.items.map((item) => [item.channel, item]));
  const restored: ChannelFetchResult[] = [];
  for (const channel of activeChannels) {
    const cached = cacheMap.get(channel.channel);
    if (!cached) return null;
    restored.push({
      channel,
      payload: cached.payload,
      errorText: cached.errorText,
    });
  }
  return restored;
}

function prefixedModelName(channelDisplayName: string, modelName: string): string {
  return `[${channelDisplayName}] ${modelName}`;
}

function isRecommendedModelName(modelName: string): boolean {
  const text = modelName.toLowerCase();
  return /(gpt|o\d|codex|claude|gemini|deepseek|qwen|glm|llama|yi|moonshot|doubao|kimi)/.test(text);
}

function formatUpstreamError(message: string): string {
  const text = message.trim();
  if (!text) return "请求失败";
  if (text.includes("upstream_unavailable")) {
    return "上游服务不可达，请检查该渠道的 Base URL、网络连通性或代理配置。";
  }
  if (text.includes("upstream_unauthorized")) {
    return "上游鉴权失败，请检查该渠道 API Key 是否正确。";
  }
  if (text.includes("Unknown upstream channel")) {
    return "渠道不存在，请检查 upstream_channel 配置。";
  }
  if (text.includes("Disabled upstream channel")) {
    return "该渠道已被禁用，请启用后再拉取模型。";
  }
  return text;
}

function normalizeModelsPath(path: string): string {
  const text = path.trim();
  if (!text) return "/v1/models";
  if (text.startsWith("/")) return text;
  return `/${text}`;
}

function withFormState(items: UpstreamChannelItem[]): UpstreamChannelFormItem[] {
  return items.map((item) => ({ ...item, api_key_input: "" }));
}

export default function AdminUpstreamModelsPage() {
  const [channels, setChannels] = useState<UpstreamChannelFormItem[]>([]);
  const [results, setResults] = useState<ChannelFetchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [savingChannel, setSavingChannel] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showAllModels, setShowAllModels] = useState(false);
  const [autoRefreshSeconds, setAutoRefreshSeconds] = useState(DEFAULT_AUTO_REFRESH_SECONDS);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const [newChannel, setNewChannel] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [newBaseUrl, setNewBaseUrl] = useState("");
  const [newApiKey, setNewApiKey] = useState("");
  const [newModelsPath, setNewModelsPath] = useState("/v1/models");
  const [newIsEnabled, setNewIsEnabled] = useState(true);

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
          const payload = await apiFetch<unknown>(suffix ? `/admin/upstream/models?${suffix}` : "/admin/upstream/models");
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

  const loadAll = useCallback(async (opts?: { force?: boolean }) => {
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
        const summary = failed.map((x) => `[${x.channel.display_name}] ${formatUpstreamError(x.errorText || "")}`).join("；");
        setErrorText(`部分渠道获取失败：${summary}`);
      }
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setChannels([]);
      setResults([]);
      setLastUpdatedAt(null);
    } finally {
      setLoading(false);
    }
  }, [autoRefreshSeconds, fetchModels]);

  useEffect(() => {
    const saved = readAutoRefreshSecondsFromStorage();
    if (saved !== null) {
      setAutoRefreshSeconds(saved);
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(AUTO_REFRESH_STORAGE_KEY, String(autoRefreshSeconds));
    } catch {
      return;
    }
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
    const rows: Array<{ channel: string; model: string; prefixed: string }> = [];
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

  const updateChannelField = (channel: string, patch: Partial<UpstreamChannelFormItem>) => {
    setChannels((prev) => prev.map((item) => (item.channel === channel ? { ...item, ...patch } : item)));
  };

  const saveChannel = async (channel: string) => {
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
  };

  const deleteChannel = async (channel: string) => {
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
  };

  const createChannel = async () => {
    const channel = newChannel.trim();
    if (!channel) {
      setErrorText("请先填写渠道名称。");
      return;
    }
    const apiKeyText = newApiKey.trim();
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
          display_name: (newDisplayName || channel).trim(),
          base_url: newBaseUrl,
          api_key: apiKeyText,
          models_path: normalizeModelsPath(newModelsPath),
          is_enabled: newIsEnabled,
        }),
      });
      setNewChannel("");
      setNewDisplayName("");
      setNewBaseUrl("");
      setNewApiKey("");
      setNewModelsPath("/v1/models");
      setNewIsEnabled(true);
      setShowCreateModal(false);
      await loadAll({ force: true });
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
    } finally {
      setSavingChannel(null);
    }
  };

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-screen min-h-[100dvh] box-border pt-14 overflow-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
          <div className="glass-panel-strong p-4 md:p-5 flex items-center gap-3">
            <div>
              <h1 className="text-xl font-semibold text-slate-900">Admin / Upstream Models</h1>
              <p className="text-xs text-slate-500 mt-1">默认查询全部已启用渠道，支持手动刷新和自动延迟刷新</p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <label className="text-xs text-slate-600">自动刷新</label>
              <select
                value={autoRefreshSeconds}
                onChange={(e) => setAutoRefreshSeconds(Number(e.target.value))}
                className="glass-input text-sm w-40"
              >
                <option value={0}>关闭</option>
                <option value={60}>60 秒</option>
                <option value={180}>180 秒（默认）</option>
                <option value={300}>300 秒</option>
                <option value={600}>600 秒</option>
              </select>
            </div>
            <button
              type="button"
              onClick={() => void loadAll({ force: true })}
              className="glass-btn"
            >
              刷新（全部渠道）
            </button>
          </div>

          <div className="text-xs text-slate-500 px-1">
            最近更新时间：{lastUpdatedAt ? new Date(lastUpdatedAt).toLocaleString() : "暂无"}
          </div>

          <div className="glass-panel p-4 space-y-3">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold text-slate-900">渠道配置（编辑 / 删除）</div>
              <button
                type="button"
                onClick={() => setShowCreateModal(true)}
                className="ml-auto inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-indigo-50/90 text-indigo-700 hover:bg-indigo-100 px-3 py-2 text-sm font-medium transition-all"
                title="新增渠道"
                aria-label="新增渠道"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
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
                    {item.is_default ? <span className="text-[10px] text-slate-500">系统默认渠道（只读）</span> : null}
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
                      placeholder={item.has_api_key ? `保持不变（当前：${item.api_key_masked}）` : "请输入 API Key"}
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

          {showCreateModal ? (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 backdrop-blur-[2px] px-4"
              onClick={() => setShowCreateModal(false)}
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
                    onClick={() => setShowCreateModal(false)}
                    className="ml-auto text-xs px-2.5 py-1.5 rounded-md border border-slate-200 bg-white/80 text-slate-600 hover:bg-white"
                  >
                    关闭
                  </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">渠道标识（channel）</div>
                    <input
                      value={newChannel}
                      onChange={(e) => setNewChannel(e.target.value)}
                      placeholder="例如 openai-cn"
                      className="glass-input text-sm"
                    />
                  </label>
                  <label className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">展示名称（display_name）</div>
                    <input
                      value={newDisplayName}
                      onChange={(e) => setNewDisplayName(e.target.value)}
                      placeholder="例如 OpenAI 中国"
                      className="glass-input text-sm"
                    />
                  </label>
                  <label className="space-y-1 md:col-span-2">
                    <div className="text-xs font-medium text-slate-600">Base URL</div>
                    <input
                      value={newBaseUrl}
                      onChange={(e) => setNewBaseUrl(e.target.value)}
                      placeholder="例如 https://api.example.com/v1"
                      className="glass-input text-sm"
                    />
                  </label>
                  <label className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">API Key（必填）</div>
                    <input
                      value={newApiKey}
                      onChange={(e) => setNewApiKey(e.target.value)}
                      placeholder="请输入 API Key"
                      className="glass-input text-sm"
                    />
                  </label>
                  <label className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">Models Path</div>
                    <input
                      value={newModelsPath}
                      onChange={(e) => setNewModelsPath(e.target.value)}
                      placeholder="/v1/models"
                      className="glass-input text-sm"
                    />
                  </label>
                </div>
                <div className="flex items-center gap-3 pt-1">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={newIsEnabled}
                      onChange={(e) => setNewIsEnabled(e.target.checked)}
                    />
                    启用
                  </label>
                  <button
                    type="button"
                    onClick={createChannel}
                    disabled={savingChannel === "__new__"}
                    className="glass-btn"
                  >
                    {savingChannel === "__new__" ? "保存中…" : "新增渠道"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="glass-btn glass-btn-secondary"
                  >
                    取消
                  </button>
                </div>
              </div>
            </div>
          ) : null}

          {errorText ? (
            <div className="glass-alert glass-alert-error">
              {errorText}
            </div>
          ) : null}

          {loading ? (
            <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
          ) : (
            <>
              <div className="glass-panel p-4">
                <div className="flex items-center gap-3 mb-2">
                  <div className="text-sm font-semibold text-slate-900">模型名（已加渠道前缀）</div>
                  <label className="ml-auto inline-flex items-center gap-2 text-xs text-slate-600">
                    <input
                      type="checkbox"
                      checked={showAllModels}
                      onChange={(e) => setShowAllModels(e.target.checked)}
                    />
                    显示全部模型（含 embedding / tts / realtime 等）
                  </label>
                </div>
                {!showAllModels ? (
                  <div className="text-xs text-slate-500 mb-2">当前仅显示常见对话模型；如需排查全部模型请勾选“显示全部模型”。</div>
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

              <details className="glass-panel p-4">
                <summary className="cursor-pointer text-sm font-semibold text-slate-900">查看各渠道原始 JSON</summary>
                <div className="mt-3 space-y-3">
                  {results.map((item) => {
                    const key = channelKey(item.channel.channel);
                    return (
                      <div key={key}>
                        <div className="text-xs font-mono text-slate-700 mb-1">
                          [{item.channel.display_name}]
                          {item.errorText ? <span className="text-rose-600 ml-2">请求失败：{formatUpstreamError(item.errorText)}</span> : null}
                        </div>
                        <pre className="glass-code custom-scrollbar text-xs p-3 overflow-auto max-h-[45vh]">
                          {JSON.stringify(item.payload, null, 2)}
                        </pre>
                      </div>
                    );
                  })}
                </div>
              </details>
            </>
          )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}
