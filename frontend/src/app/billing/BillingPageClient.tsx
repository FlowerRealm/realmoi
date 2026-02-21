"use client";

// Billing page (client-side).
//
// 结构说明：
// - 顶部：筛选条件（日期范围 + 每页条数）
// - 中部：窗口汇总（Tokens、缓存命中率、费用覆盖率）
// - 趋势：按天 Tokens（柱）+ Cost（折线）
// - 明细：events 列表 + 单条费用拆解

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAuth } from "@/components/RequireAuth";
import { getErrorMessage } from "@/lib/api";

import type {
  BillingEventDetail,
  BillingEventsResponse,
  BillingFilters,
  BillingDailyResponse,
  BillingWindow,
} from "./billingTypes";
import {
  FILTER_STORAGE_KEY,
  applyRangePreset,
  buildDefaultFilters,
  clampLimit,
  parseStoredFilters,
} from "./billingUtils";
import { useBillingData, useBillingDetailLoader } from "./billingHooks";
import { BillingPageHeader } from "./components/BillingPageHeader";
import { BillingFiltersPanel } from "./components/BillingFiltersPanel";
import { BillingSummaryCards } from "./components/BillingSummaryCards";
import { BillingTrendPanel } from "./components/BillingTrendPanel";
import { BillingTokensBreakdown } from "./components/BillingTokensBreakdown";
import { BillingEventsPanel } from "./components/BillingEventsPanel";

export function BillingPageClient() {
  const defaults = useMemo(() => buildDefaultFilters(), []);
  const [filtersReady, setFiltersReady] = useState(false);
  const [draftFilters, setDraftFilters] = useState<BillingFilters>(defaults);
  const [appliedFilters, setAppliedFilters] = useState<BillingFilters>(defaults);

  const [beforeId, setBeforeId] = useState<string | null>(null);
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([]);

  const [expandedRecordId, setExpandedRecordId] = useState<string | null>(null);
  const [detailById, setDetailById] = useState<Record<string, BillingEventDetail>>({});
  const [detailLoadingMap, setDetailLoadingMap] = useState<Record<string, boolean>>({});
  const [detailErrorMap, setDetailErrorMap] = useState<Record<string, string>>({});

  const {
    windowData,
    dailyData,
    eventsData,
    loading,
    refreshing,
    errorText,
    setErrorText,
    refresh,
  } = useBillingData({
    appliedFilters,
    beforeId,
    filtersReady,
  });

  const loadDetail = useBillingDetailLoader({
    detailById,
    detailLoadingMap,
    setDetailById,
    setDetailLoadingMap,
    setDetailErrorMap,
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const stored = parseStoredFilters(window.localStorage.getItem(FILTER_STORAGE_KEY));
    if (stored) {
      setDraftFilters(stored);
      setAppliedFilters(stored);
    }
    setFiltersReady(true);
  }, []);

  useEffect(() => {
    if (!filtersReady || typeof window === "undefined") return;
    try {
      window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(appliedFilters));
    } catch (error: unknown) {
      // localStorage 可能在隐私模式/配额限制下失败；不应阻断页面使用。
      console.warn("[billing] persist filters failed", error);
    }
  }, [appliedFilters, filtersReady]);

  const hasPendingChanges =
    draftFilters.start.trim() !== appliedFilters.start ||
    draftFilters.end.trim() !== appliedFilters.end ||
    clampLimit(draftFilters.limit) !== appliedFilters.limit;

  const onApplyFilters = useCallback(() => {
    const next: BillingFilters = {
      start: draftFilters.start.trim(),
      end: draftFilters.end.trim(),
      limit: clampLimit(draftFilters.limit),
    };
    if (!next.start || !next.end) {
      setErrorText("开始日期和结束日期不能为空。");
      return;
    }
    if (next.start > next.end) {
      setErrorText("开始日期不能晚于结束日期。");
      return;
    }
    setErrorText(null);
    setDraftFilters(next);
    setAppliedFilters(next);
    setBeforeId(null);
    setCursorStack([]);
    setExpandedRecordId(null);
  }, [draftFilters.end, draftFilters.limit, draftFilters.start, setErrorText]);

  const onQuickRange = useCallback(
    (preset: "today" | "yesterday" | "last7days") => {
      const next = applyRangePreset(preset, clampLimit(draftFilters.limit));
      setDraftFilters(next);
    },
    [draftFilters.limit]
  );

  const onRefresh = useCallback(() => {
    if (!filtersReady) return;
    refresh(true).catch((error: unknown) => {
      setErrorText(getErrorMessage(error));
    });
  }, [filtersReady, refresh, setErrorText]);

  const onNextPage = useCallback(() => {
    if (!eventsData?.next_before_id) return;
    setCursorStack((prev) => [...prev, beforeId]);
    setBeforeId(eventsData.next_before_id);
    setExpandedRecordId(null);
  }, [beforeId, eventsData?.next_before_id]);

  const onPrevPage = useCallback(() => {
    if (cursorStack.length == 0) return;
    const target = cursorStack[cursorStack.length - 1];
    setCursorStack((prev) => prev.slice(0, -1));
    setBeforeId(target);
    setExpandedRecordId(null);
  }, [cursorStack]);

  const onToggleDetail = useCallback(
    (recordId: string) => {
      setExpandedRecordId((prev) => (prev === recordId ? null : recordId));
      loadDetail(recordId).catch((error: unknown) => {
        setDetailErrorMap((prev) => ({ ...prev, [recordId]: getErrorMessage(error) }));
      });
    },
    [loadDetail]
  );

  const hasPrevPage = cursorStack.length > 0;
  const hasNextPage = Boolean(eventsData?.next_before_id);

  return (
    <RequireAuth>
      <div className="relative w-full min-h-[100dvh] box-border pt-14 overflow-x-hidden">
        <AppHeader mode="overlay" />
        <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
          <BillingPageHeader
            loading={loading}
            refreshing={refreshing}
            onRefresh={onRefresh}
          />

          <BillingFiltersPanel
            appliedFilters={appliedFilters}
            draftFilters={draftFilters}
            hasPendingChanges={hasPendingChanges}
            loading={loading}
            onApplyFilters={onApplyFilters}
            onQuickRange={onQuickRange}
            setDraftFilters={setDraftFilters}
          />

          {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}

          {loading ? (
            <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
          ) : windowData ? (
            <BillingMainBody
              appliedFilters={appliedFilters}
              beforeId={beforeId}
              dailyData={dailyData}
              detailById={detailById}
              detailErrorMap={detailErrorMap}
              detailLoadingMap={detailLoadingMap}
              eventsData={eventsData}
              expandedRecordId={expandedRecordId}
              hasNextPage={hasNextPage}
              hasPrevPage={hasPrevPage}
              onNextPage={onNextPage}
              onPrevPage={onPrevPage}
              onToggleDetail={onToggleDetail}
              windowData={windowData}
            />
          ) : (
            <div className="glass-panel p-4 text-sm text-slate-600">暂无账单数据。</div>
          )}
        </main>
      </div>
    </RequireAuth>
  );
}

type BillingMainBodyProps = {
  appliedFilters: BillingFilters;
  beforeId: string | null;
  dailyData: BillingDailyResponse | null;
  detailById: Record<string, BillingEventDetail>;
  detailLoadingMap: Record<string, boolean>;
  detailErrorMap: Record<string, string>;
  eventsData: BillingEventsResponse | null;
  expandedRecordId: string | null;
  hasPrevPage: boolean;
  hasNextPage: boolean;
  onNextPage: () => void;
  onPrevPage: () => void;
  onToggleDetail: (recordId: string) => void;
  windowData: BillingWindow;
};

function BillingMainBody({
  appliedFilters,
  beforeId,
  dailyData,
  detailById,
  detailErrorMap,
  detailLoadingMap,
  eventsData,
  expandedRecordId,
  hasNextPage,
  hasPrevPage,
  onNextPage,
  onPrevPage,
  onToggleDetail,
  windowData,
}: BillingMainBodyProps) {
  return (
    <div className="space-y-4">
      <BillingSummaryCards appliedFilters={appliedFilters} windowData={windowData} />
      <BillingTrendPanel dailyData={dailyData} />
      <BillingTokensBreakdown windowData={windowData} />
      <BillingEventsPanel
        appliedFilters={appliedFilters}
        beforeId={beforeId}
        detailById={detailById}
        detailErrorMap={detailErrorMap}
        detailLoadingMap={detailLoadingMap}
        eventsData={eventsData}
        expandedRecordId={expandedRecordId}
        hasNextPage={hasNextPage}
        hasPrevPage={hasPrevPage}
        onNextPage={onNextPage}
        onPrevPage={onPrevPage}
        onToggleDetail={onToggleDetail}
      />
    </div>
  );
}

