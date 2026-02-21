"use client";

// Billing page hooks.
//
// 目标：把数据加载/明细加载的状态机从 UI 组件中拆出来，降低 page 入口文件复杂度。

import { useCallback, useEffect, useState } from "react";
import { apiFetch, getErrorMessage } from "@/lib/api";

import type {
  BillingDailyResponse,
  BillingEventDetail,
  BillingEventsResponse,
  BillingFilters,
  BillingWindow,
  BillingWindowsResponse,
} from "./billingTypes";

type UseBillingDataArgs = {
  appliedFilters: BillingFilters;
  beforeId: string | null;
  filtersReady: boolean;
};

type UseBillingDataResult = {
  windowData: BillingWindow | null;
  dailyData: BillingDailyResponse | null;
  eventsData: BillingEventsResponse | null;
  loading: boolean;
  refreshing: boolean;
  errorText: string | null;
  setErrorText: (value: string | null) => void;
  refresh: (background: boolean) => Promise<void>;
};

export function useBillingData({
  appliedFilters,
  beforeId,
  filtersReady,
}: UseBillingDataArgs): UseBillingDataResult {
  const [windowData, setWindowData] = useState<BillingWindow | null>(null);
  const [dailyData, setDailyData] = useState<BillingDailyResponse | null>(null);
  const [eventsData, setEventsData] = useState<BillingEventsResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  const refresh = useCallback(
    async (background: boolean) => {
      if (background) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setErrorText(null);
      try {
        const windowsParams = new URLSearchParams({
          start: appliedFilters.start,
          end: appliedFilters.end,
        });
        const eventsParams = new URLSearchParams({
          start: appliedFilters.start,
          end: appliedFilters.end,
          limit: String(appliedFilters.limit),
        });
        if (beforeId) {
          eventsParams.set("before_id", beforeId);
        }

        const [windowsResp, dailyResp, eventsResp] = await Promise.all([
          apiFetch<BillingWindowsResponse>(`/billing/windows?${windowsParams.toString()}`),
          apiFetch<BillingDailyResponse>(`/billing/daily?${windowsParams.toString()}`),
          apiFetch<BillingEventsResponse>(`/billing/events?${eventsParams.toString()}`),
        ]);
        setWindowData(windowsResp.windows[0] ?? null);
        setDailyData(dailyResp);
        setEventsData(eventsResp);
      } catch (error: unknown) {
        setErrorText(getErrorMessage(error));
      } finally {
        if (background) {
          setRefreshing(false);
        } else {
          setLoading(false);
        }
      }
    },
    [appliedFilters.end, appliedFilters.limit, appliedFilters.start, beforeId]
  );

  useEffect(() => {
    if (!filtersReady) return;
    refresh(false).catch((error: unknown) => {
      setErrorText(getErrorMessage(error));
    });
  }, [filtersReady, refresh]);

  useEffect(() => {
    if (!filtersReady) return;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        refresh(true).catch((error: unknown) => {
          setErrorText(getErrorMessage(error));
        });
      }
    }, 60_000);
    return () => window.clearInterval(intervalId);
  }, [filtersReady, refresh]);

  return {
    windowData,
    dailyData,
    eventsData,
    loading,
    refreshing,
    errorText,
    setErrorText,
    refresh,
  };
}

type UseBillingDetailLoaderArgs = {
  detailById: Record<string, BillingEventDetail>;
  detailLoadingMap: Record<string, boolean>;
  setDetailById: (updater: (prev: Record<string, BillingEventDetail>) => Record<string, BillingEventDetail>) => void;
  setDetailLoadingMap: (updater: (prev: Record<string, boolean>) => Record<string, boolean>) => void;
  setDetailErrorMap: (updater: (prev: Record<string, string>) => Record<string, string>) => void;
};

export function useBillingDetailLoader({
  detailById,
  detailLoadingMap,
  setDetailById,
  setDetailLoadingMap,
  setDetailErrorMap,
}: UseBillingDetailLoaderArgs) {
  return useCallback(
    async (recordId: string) => {
      if (detailById[recordId] || detailLoadingMap[recordId]) return;
      setDetailLoadingMap((prev) => ({ ...prev, [recordId]: true }));
      setDetailErrorMap((prev) => {
        const next = { ...prev };
        delete next[recordId];
        return next;
      });
      try {
        const detail = await apiFetch<BillingEventDetail>(`/billing/events/${recordId}/detail`);
        setDetailById((prev) => ({ ...prev, [recordId]: detail }));
      } catch (error: unknown) {
        setDetailErrorMap((prev) => ({ ...prev, [recordId]: getErrorMessage(error) }));
      } finally {
        setDetailLoadingMap((prev) => ({ ...prev, [recordId]: false }));
      }
    },
    [detailById, detailLoadingMap, setDetailById, setDetailErrorMap, setDetailLoadingMap]
  );
}

