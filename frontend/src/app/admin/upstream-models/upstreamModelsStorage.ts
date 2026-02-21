"use client";

// localStorage 读写与缓存恢复逻辑。
//
// 注意：本页为“运维/排障”工具，localStorage 失败不应阻断页面使用，因此统一降级并记录 warn。

import type {
  CachedModelsSnapshot,
  ChannelFetchResult,
  UpstreamChannelFormItem,
} from "./upstreamModelsTypes";
import {
  AUTO_REFRESH_STORAGE_KEY,
  MODELS_CACHE_STORAGE_KEY,
} from "./upstreamModelsTypes";

export function channelKey(channel: string): string {
  return channel || "__default__";
}

export function readAutoRefreshSecondsFromStorage(): number | null {
  try {
    const raw = localStorage.getItem(AUTO_REFRESH_STORAGE_KEY);
    if (!raw) return null;
    const n = Number(raw);
    if (!Number.isFinite(n) || n < 0) return null;
    return Math.trunc(n);
  } catch (error: unknown) {
    console.warn("[admin/upstream-models] read auto refresh seconds failed", error);
    return null;
  }
}

export function readModelsCacheFromStorage(): CachedModelsSnapshot | null {
  try {
    const raw = localStorage.getItem(MODELS_CACHE_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedModelsSnapshot;
    if (!parsed || typeof parsed !== "object") return null;
    if (!Number.isFinite(parsed.ts)) return null;
    if (!Array.isArray(parsed.items)) return null;
    return parsed;
  } catch (error: unknown) {
    console.warn("[admin/upstream-models] read models cache failed", error);
    return null;
  }
}

export function writeModelsCacheToStorage(items: ChannelFetchResult[]): number {
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
  } catch (error: unknown) {
    console.warn("[admin/upstream-models] write models cache failed", error);
    return ts;
  }
  return ts;
}

export function restoreModelsFromCache(
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

export function persistAutoRefreshSecondsToStorage(value: number): void {
  try {
    localStorage.setItem(AUTO_REFRESH_STORAGE_KEY, String(value));
  } catch (error: unknown) {
    console.warn("[admin/upstream-models] persist auto refresh seconds failed", error);
  }
}

