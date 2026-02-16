"use client";

import React, { useEffect, useState } from "react";
import { getErrorMessage } from "@/lib/api";
import { getMcpClient } from "@/lib/mcp";
import { GlassPanel } from "./GlassPanel";
import { LiquidInput } from "./LiquidInput";
import type { AssistantSession, ModelItem, PromptData } from "./types";

const MODELS_CACHE_STORAGE_KEY = "realmoi_admin_upstream_models_cache_v1";
const MODELS_CACHE_TTL_MS = 180_000;

type CachedModelsSnapshot = {
  ts: number;
  items: Array<{
    channel: string;
    payload: unknown | null;
    errorText: string | null;
  }>;
};

function toPrefixedModel(channel: string, model: string): ModelItem {
  return {
    model,
    upstream_channel: channel,
    display_name: `[${channel}] ${model}`,
  };
}

function normalizeModels(items: ModelItem[]): ModelItem[] {
  const dedup = new Map<string, ModelItem>();
  items.forEach((item) => {
    const model = String(item.model || "").trim();
    const channel = String(item.upstream_channel || "").trim();
    if (!model || !channel) return;
    const key = `${channel}::${model}`;
    if (!dedup.has(key)) {
      dedup.set(key, toPrefixedModel(channel, model));
    }
  });
  return Array.from(dedup.values()).sort((a, b) => {
    const ac = String(a.upstream_channel || "").toLowerCase();
    const bc = String(b.upstream_channel || "").toLowerCase();
    if (ac === bc) {
      return a.model.localeCompare(b.model);
    }
    return ac.localeCompare(bc);
  });
}

function readModelsSnapshot(): CachedModelsSnapshot | null {
  try {
    const raw = localStorage.getItem(MODELS_CACHE_STORAGE_KEY);
    if (!raw) return null;
    const snapshot = JSON.parse(raw) as CachedModelsSnapshot;
    if (!snapshot || !Array.isArray(snapshot.items)) return null;
    return snapshot;
  } catch {
    return null;
  }
}

function extractModelsFromSnapshot(snapshot: CachedModelsSnapshot | null): ModelItem[] {
  if (!snapshot) return [];
  const rows: ModelItem[] = [];
  snapshot.items.forEach((item) => {
    const channel = String(item.channel || "").trim();
    const payload = item.payload as { data?: Array<{ id?: string }> };
    if (!channel || !Array.isArray(payload?.data)) return;
    payload.data.forEach((entry) => {
      const model = String(entry?.id || "").trim();
      if (!model) return;
      rows.push(toPrefixedModel(channel, model));
    });
  });
  return normalizeModels(rows);
}

function writeModelsToCache(channelRows: Array<{ channel: string; models: string[] }>): void {
  const payload: CachedModelsSnapshot = {
    ts: Date.now(),
    items: channelRows.map((item) => ({
      channel: item.channel,
      payload: { data: item.models.map((model) => ({ id: model })) },
      errorText: null,
    })),
  };
  try {
    localStorage.setItem(MODELS_CACHE_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    return;
  }
}

function snapshotRowsForCache(rows: ModelItem[]): Array<{ channel: string; models: string[] }> {
  const grouped = new Map<string, string[]>();
  rows.forEach((row) => {
    const channel = String(row.upstream_channel || "").trim();
    const model = String(row.model || "").trim();
    if (!channel || !model) return;
    const list = grouped.get(channel) ?? [];
    list.push(model);
    grouped.set(channel, list);
  });
  return Array.from(grouped.entries()).map(([channel, models]) => ({ channel, models }));
}

function initialCachedModels(): ModelItem[] {
  if (typeof window === "undefined") return [];
  return extractModelsFromSnapshot(readModelsSnapshot());
}

export function Portal({
  onStart,
  history,
  onResume,
}: {
  onStart: (data: PromptData) => void;
  history: AssistantSession[];
  onResume: (session: AssistantSession) => void;
}) {
  const [isWarping, setIsWarping] = useState(false);
  const [isInputExpanded, setIsInputExpanded] = useState(false);
  const [models, setModels] = useState<ModelItem[]>(initialCachedModels);
  const [modelsError, setModelsError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const snapshot = readModelsSnapshot();
      const cachedModels = extractModelsFromSnapshot(snapshot);
      const cacheAgeMs = snapshot ? Date.now() - Number(snapshot.ts || 0) : Number.POSITIVE_INFINITY;
      const cacheFresh = cachedModels.length > 0 && cacheAgeMs >= 0 && cacheAgeMs <= MODELS_CACHE_TTL_MS;
      if (cacheFresh) {
        return;
      }

      try {
        const client = getMcpClient();
        const livePayload = await client.callTool<{ items?: ModelItem[] }>("models.list", { live: true });
        const liveRows = normalizeModels(livePayload?.items ?? []);
        if (cancelled) return;
        if (liveRows.length > 0) {
          writeModelsToCache(snapshotRowsForCache(liveRows));
          setModels(liveRows);
          setModelsError(null);
          return;
        }
      } catch {
        // Ignore and fallback to non-live list.
      }

      try {
        const client = getMcpClient();
        const fallbackPayload = await client.callTool<{ items?: ModelItem[] }>("models.list", { live: false });
        const fallbackRows = normalizeModels(fallbackPayload?.items ?? []);
        if (cancelled) return;
        if (cachedModels.length > 0) {
          setModels(cachedModels);
          setModelsError("实时模型不可用，已优先使用缓存模型。");
          return;
        }
        if (fallbackRows.length > 0) {
          writeModelsToCache(snapshotRowsForCache(fallbackRows));
          setModels(fallbackRows);
          setModelsError(null);
          return;
        }
        if (cachedModels.length === 0) {
          setModelsError("暂无可用模型，请先在管理端启用渠道或刷新模型缓存。");
        }
      } catch (e: unknown) {
        if (cancelled) return;
        if (cachedModels.length > 0) {
          setModelsError(`实时拉取失败，已使用缓存：${getErrorMessage(e)}`);
          return;
        }
        setModels([]);
        setModelsError(getErrorMessage(e));
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSend = (data: PromptData) => {
    setIsWarping(true);
    setTimeout(() => {
      onStart(data);
    }, 800);
  };

  return (
    <div
      className={[
        "relative flex items-center justify-center w-full h-full transition-all duration-1000 px-4 md:px-6",
        isWarping ? "scale-[1.1] opacity-0 blur-3xl" : "scale-100 opacity-100 blur-0",
      ].join(" ")}
    >
      <div className="w-full max-w-[1280px] flex items-stretch xl:items-center justify-center gap-6 xl:gap-8">
        {!isInputExpanded ? (
          <div className="hidden xl:block w-72 h-[70vh] animate-in fade-in slide-in-from-left-6 duration-700 shrink-0">
            <GlassPanel intensity="medium" className="h-full flex flex-col p-5">
              <div className="text-sm font-semibold text-slate-500 mb-4 px-1">
                历史会话
              </div>
              <div className="flex-1 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
                {history.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center px-4 opacity-60">
                    <p className="text-sm font-medium text-slate-500">无历史记录</p>
                  </div>
                ) : (
                  history.map((session) => (
                    <button
                      key={session.id}
                      onClick={() => onResume(session)}
                      className="w-full text-left p-3 rounded-2xl glass-panel hover:opacity-90 transition-opacity group"
                    >
                      <div className="text-sm font-medium text-slate-700 truncate mb-1 group-hover:text-indigo-600">
                        {session.title}
                      </div>
                      <div className="text-xs text-slate-500">
                        {new Date(session.timestamp).toLocaleString()}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </GlassPanel>
          </div>
        ) : null}

        <div className="flex flex-col items-center justify-center w-full max-w-5xl relative z-10 transition-all duration-700">
          <div
            className={[
              "text-center transition-all duration-700 ease-[cubic-bezier(0.23,1,0.32,1)] relative z-10 overflow-hidden",
              isInputExpanded ? "max-h-0 mb-0 opacity-0 pointer-events-none" : "max-h-96 mb-10 opacity-100",
            ].join(" ")}
          >
            <h1 className="text-5xl md:text-6xl font-semibold tracking-tight mb-3 text-slate-800">
              Realm{" "}
              <span className="text-indigo-600 font-semibold">
                OI
              </span>
            </h1>
            <p className="text-slate-500 text-base max-w-md mx-auto leading-relaxed">
              AI 驱动的调题助手
            </p>
          </div>

          <div className="w-full max-w-4xl relative z-10">
            <LiquidInput onSend={handleSend} onToggleExpand={setIsInputExpanded} models={models} />
            {modelsError ? (
              <div className="mt-3 text-center text-sm text-rose-600">
                模型列表加载失败：{modelsError}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
