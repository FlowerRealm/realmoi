"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

type BillingFilters = {
  start: string;
  end: string;
  limit: number;
};

type BillingCostSummary = {
  currency: string;
  cost_microusd: number | null;
  amount: string | null;
  priced_records: number;
  unpriced_records: number;
};

type BillingWindow = {
  window: string;
  since: string;
  until: string;
  records: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cache_ratio: number;
  cost: BillingCostSummary;
};

type BillingWindowsResponse = {
  now: string;
  query: {
    start: string;
    end: string;
  };
  windows: BillingWindow[];
};

type BillingDailyPoint = {
  day: string;
  records: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cache_ratio: number;
  cost: BillingCostSummary;
};

type BillingDailyResponse = {
  query: {
    start: string;
    end: string;
  };
  points: BillingDailyPoint[];
};

type BillingEventCost = {
  currency: string;
  cost_microusd: number;
  amount: string;
};

type BillingEvent = {
  id: string;
  created_at: string;
  job_id: string;
  stage: string;
  model: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cost: BillingEventCost | null;
};

type BillingEventsResponse = {
  query: {
    start: string;
    end: string;
    limit: number;
    before_id: string | null;
  };
  events: BillingEvent[];
  next_before_id: string | null;
};

type BillingPricingSnapshot = {
  currency: string;
  input_microusd_per_1m_tokens: number;
  cached_input_microusd_per_1m_tokens: number;
  output_microusd_per_1m_tokens: number;
  cached_output_microusd_per_1m_tokens: number;
};

type BillingCostBreakdownLine = {
  tokens: number;
  price_microusd_per_1m_tokens: number;
  cost_microusd: number;
  amount: string;
};

type BillingCostBreakdown = {
  non_cached_input: BillingCostBreakdownLine;
  non_cached_output: BillingCostBreakdownLine;
  cached_input: BillingCostBreakdownLine;
  cached_output: BillingCostBreakdownLine;
  computed_total_microusd: number;
  computed_total_amount: string;
};

type BillingEventDetail = BillingEvent & {
  pricing: BillingPricingSnapshot | null;
  breakdown: BillingCostBreakdown | null;
};

const FILTER_STORAGE_KEY = "realmoi.billing.filters.v1";
const LIMIT_OPTIONS = [20, 50, 100, 200];

function toDateInputValue(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function daysShift(base: Date, offset: number): Date {
  const next = new Date(base);
  next.setDate(next.getDate() + offset);
  return next;
}

function clampLimit(limit: number): number {
  return LIMIT_OPTIONS.includes(limit) ? limit : 50;
}

function buildDefaultFilters(): BillingFilters {
  const today = new Date();
  return {
    start: toDateInputValue(daysShift(today, -6)),
    end: toDateInputValue(today),
    limit: 50,
  };
}

function parseStoredFilters(raw: string | null): BillingFilters | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const start = typeof (parsed as { start?: unknown }).start === "string"
      ? (parsed as { start: string }).start
      : "";
    const end = typeof (parsed as { end?: unknown }).end === "string"
      ? (parsed as { end: string }).end
      : "";
    const limitRaw = (parsed as { limit?: unknown }).limit;
    const limit = typeof limitRaw === "number" ? limitRaw : Number(limitRaw);
    if (!start || !end || !Number.isFinite(limit)) return null;
    return {
      start,
      end,
      limit: clampLimit(limit),
    };
  } catch {
    return null;
  }
}

function fmtInt(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function fmtPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function fmtDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function fmtUsd(amount: string | null, currency: string = "USD"): string {
  if (!amount) return "未定价";
  return `${currency} ${amount}`;
}

function applyRangePreset(
  preset: "today" | "yesterday" | "last7days",
  limit: number
): BillingFilters {
  const today = new Date();
  const todayText = toDateInputValue(today);
  if (preset === "today") {
    return { start: todayText, end: todayText, limit };
  }
  if (preset === "yesterday") {
    const yesterday = toDateInputValue(daysShift(today, -1));
    return { start: yesterday, end: yesterday, limit };
  }
  return {
    start: toDateInputValue(daysShift(today, -6)),
    end: todayText,
    limit,
  };
}

export default function BillingPage() {
  const defaults = useMemo(() => buildDefaultFilters(), []);
  const [filtersReady, setFiltersReady] = useState(false);
  const [draftFilters, setDraftFilters] = useState<BillingFilters>(defaults);
  const [appliedFilters, setAppliedFilters] = useState<BillingFilters>(defaults);

  const [beforeId, setBeforeId] = useState<string | null>(null);
  const [cursorStack, setCursorStack] = useState<Array<string | null>>([]);

  const [windowData, setWindowData] = useState<BillingWindow | null>(null);
  const [dailyData, setDailyData] = useState<BillingDailyResponse | null>(null);
  const [eventsData, setEventsData] = useState<BillingEventsResponse | null>(null);

  const [expandedRecordId, setExpandedRecordId] = useState<string | null>(null);
  const [detailById, setDetailById] = useState<Record<string, BillingEventDetail>>({});
  const [detailLoadingMap, setDetailLoadingMap] = useState<Record<string, boolean>>({});
  const [detailErrorMap, setDetailErrorMap] = useState<Record<string, string>>({});

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  const loadData = useCallback(
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

  const loadDetail = useCallback(async (recordId: string) => {
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
  }, [detailById, detailLoadingMap]);

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
    window.localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(appliedFilters));
  }, [appliedFilters, filtersReady]);

  useEffect(() => {
    if (!filtersReady) return;
    void loadData(false);
  }, [filtersReady, loadData]);

  useEffect(() => {
    if (!filtersReady) return;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void loadData(true);
      }
    }, 60_000);
    return () => window.clearInterval(intervalId);
  }, [filtersReady, loadData]);

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
  }, [draftFilters.end, draftFilters.limit, draftFilters.start]);

  const onQuickRange = useCallback((preset: "today" | "yesterday" | "last7days") => {
    const next = applyRangePreset(preset, clampLimit(draftFilters.limit));
    setDraftFilters(next);
  }, [draftFilters.limit]);

  const onRefresh = useCallback(() => {
    if (!filtersReady) return;
    void loadData(true);
  }, [filtersReady, loadData]);

  const onNextPage = useCallback(() => {
    if (!eventsData?.next_before_id) return;
    setCursorStack((prev) => [...prev, beforeId]);
    setBeforeId(eventsData.next_before_id);
    setExpandedRecordId(null);
  }, [beforeId, eventsData?.next_before_id]);

  const onPrevPage = useCallback(() => {
    if (cursorStack.length === 0) return;
    const target = cursorStack[cursorStack.length - 1];
    setCursorStack((prev) => prev.slice(0, -1));
    setBeforeId(target);
    setExpandedRecordId(null);
  }, [cursorStack]);

  const onToggleDetail = useCallback((recordId: string) => {
    setExpandedRecordId((prev) => (prev === recordId ? null : recordId));
    void loadDetail(recordId);
  }, [loadDetail]);

  const hasPrevPage = cursorStack.length > 0;
  const hasNextPage = Boolean(eventsData?.next_before_id);

  const totalRecords = windowData?.records ?? 0;
  const pricedRecords = windowData?.cost.priced_records ?? 0;
  const pricingCoverage = totalRecords > 0 ? pricedRecords / totalRecords : 0;
  const totalTokens = windowData?.total_tokens ?? 0;
  const interactiveTokens = windowData ? windowData.input_tokens + windowData.output_tokens : 0;
  const cachedTokens = windowData ? windowData.cached_input_tokens + windowData.cached_output_tokens : 0;
  const hasPendingChanges =
    draftFilters.start.trim() !== appliedFilters.start ||
    draftFilters.end.trim() !== appliedFilters.end ||
    clampLimit(draftFilters.limit) !== appliedFilters.limit;
  const dailyPoints = dailyData?.points ?? [];
  const dailyMaxTokens = Math.max(
    1,
    ...dailyPoints.map((point) => point.total_tokens)
  );
  const dailyMaxCostMicrousd = Math.max(
    1,
    ...dailyPoints.map((point) => point.cost.cost_microusd ?? 0)
  );
  const trendSlotWidth = 64;
  const trendChartHeight = 112;
  const trendChartWidth = Math.max(trendSlotWidth, dailyPoints.length * trendSlotWidth);
  const trendCostLinePoints = dailyPoints.map((point, index) => {
    const x = index * trendSlotWidth + trendSlotWidth / 2;
    const normalizedCost = (point.cost.cost_microusd ?? 0) / dailyMaxCostMicrousd;
    const y = trendChartHeight - Math.round(normalizedCost * (trendChartHeight - 12)) - 6;
    return `${x},${y}`;
  }).join(" ");

  return (
    <RequireAuth>
      <div className="relative w-screen min-h-[100dvh] box-border pt-14 overflow-hidden">
        <AppHeader mode="overlay" />
        <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
          <div className="glass-panel-strong p-4 md:p-5 flex flex-wrap items-center gap-3">
            <div>
              <h1 className="text-xl font-semibold text-slate-900">Billing</h1>
              <p className="text-xs text-slate-500 mt-1">
                先看关键指标，再看请求明细和单条费用拆解。
              </p>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <div className="text-xs text-slate-500">
                {refreshing ? "正在后台刷新…" : "每 60 秒自动刷新"}
              </div>
              <button
                type="button"
                onClick={onRefresh}
                className="glass-btn"
                disabled={loading || refreshing}
              >
                刷新
              </button>
            </div>
          </div>

          <details className="glass-panel p-4">
            <summary className="cursor-pointer list-none flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-900">筛选条件（可折叠）</span>
              <span className="text-xs text-slate-500">
                当前：{appliedFilters.start} ~ {appliedFilters.end} / 每页 {appliedFilters.limit} 条
              </span>
              {hasPendingChanges ? <span className="text-xs text-amber-600">草稿未应用</span> : null}
            </summary>
            <div className="mt-3 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <div className="text-xs text-slate-500">快捷范围</div>
                <button
                  type="button"
                  onClick={() => onQuickRange("today")}
                  className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                >
                  今天
                </button>
                <button
                  type="button"
                  onClick={() => onQuickRange("yesterday")}
                  className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                >
                  昨天
                </button>
                <button
                  type="button"
                  onClick={() => onQuickRange("last7days")}
                  className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                >
                  近 7 天
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div>
                  <div className="text-xs text-slate-500">开始日期</div>
                  <input
                    type="date"
                    value={draftFilters.start}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({
                        ...prev,
                        start: e.target.value,
                      }))
                    }
                    className="glass-input mt-1 text-sm"
                  />
                </div>
                <div>
                  <div className="text-xs text-slate-500">结束日期</div>
                  <input
                    type="date"
                    value={draftFilters.end}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({
                        ...prev,
                        end: e.target.value,
                      }))
                    }
                    className="glass-input mt-1 text-sm"
                  />
                </div>
                <div>
                  <div className="text-xs text-slate-500">每页条数</div>
                  <select
                    value={draftFilters.limit}
                    onChange={(e) =>
                      setDraftFilters((prev) => ({
                        ...prev,
                        limit: clampLimit(Number(e.target.value)),
                      }))
                    }
                    className="glass-input mt-1 text-sm"
                  >
                    {LIMIT_OPTIONS.map((limit) => (
                      <option key={limit} value={limit}>
                        {limit}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex items-end">
                  <button
                    type="button"
                    onClick={onApplyFilters}
                    className="glass-btn glass-btn-secondary w-full"
                    disabled={!hasPendingChanges || loading}
                  >
                    {hasPendingChanges ? "应用筛选" : "筛选已生效"}
                  </button>
                </div>
              </div>
            </div>
          </details>

          {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}

          {loading ? (
            <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
          ) : windowData ? (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                <div className="glass-panel p-4">
                  <div className="text-xs text-slate-500">总费用（已定价记录）</div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {fmtUsd(windowData.cost.amount, windowData.cost.currency)}
                  </div>
                  <div className="mt-1 text-xs text-slate-500 font-mono">
                    microusd={windowData.cost.cost_microusd ?? "-"}
                  </div>
                </div>
                <div className="glass-panel p-4">
                  <div className="text-xs text-slate-500">使用记录数</div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">{fmtInt(windowData.records)}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    已定价 {fmtInt(windowData.cost.priced_records)} / 未定价 {fmtInt(windowData.cost.unpriced_records)}
                  </div>
                </div>
                <div className="glass-panel p-4">
                  <div className="text-xs text-slate-500">查询窗口 / 覆盖率</div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {fmtPercent(windowData.cache_ratio)}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    定价覆盖率 {fmtPercent(pricingCoverage)}
                  </div>
                  <div className="mt-1 text-xs text-slate-500 font-mono">
                    {appliedFilters.start} ~ {appliedFilters.end}
                  </div>
                </div>
                <div className="glass-panel p-4">
                  <div className="text-xs text-slate-500">总 Tokens</div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {fmtInt(totalTokens)}
                  </div>
                </div>
                <div className="glass-panel p-4">
                  <div className="text-xs text-slate-500">交互 Tokens（input + output）</div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {fmtInt(interactiveTokens)}
                  </div>
                </div>
                <div className="glass-panel p-4">
                  <div className="text-xs text-slate-500">缓存 Tokens</div>
                  <div className="mt-1 text-lg font-semibold text-slate-900">
                    {fmtInt(cachedTokens)}
                  </div>
                </div>
              </div>

              <div className="glass-panel p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-900">按天趋势</div>
                    <div className="text-xs text-slate-500 mt-1">
                      双轴趋势：柱高代表 Tokens（左轴），折线代表费用（右轴）。
                    </div>
                  </div>
                  <div className="text-xs text-slate-500">
                    {dailyData ? `${dailyData.query.start} ~ ${dailyData.query.end}` : "-"}
                  </div>
                </div>
                {!dailyData || dailyData.points.length === 0 ? (
                  <div className="mt-3 text-sm text-slate-600">暂无可绘制的趋势数据。</div>
                ) : (
                  <div className="mt-3 space-y-2">
                    <div className="text-[11px] text-slate-500 flex items-center gap-3">
                      <span className="inline-flex items-center gap-1">
                        <span className="w-3 h-3 rounded-sm bg-indigo-500/70 border border-indigo-400/60" />
                        Tokens（左轴）
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <span className="w-3 h-[2px] rounded-full bg-emerald-500" />
                        Cost（右轴）
                      </span>
                    </div>
                    <div className="overflow-x-auto pb-1">
                      <div className="min-w-max" style={{ width: `${trendChartWidth}px` }}>
                        <div className="relative h-32">
                          <div className="absolute inset-0 flex items-end">
                            {dailyPoints.map((point) => {
                              const tokenHeight = Math.max(
                                10,
                                Math.round((point.total_tokens / dailyMaxTokens) * 100)
                              );
                              return (
                                <div
                                  key={`${point.day}-bar`}
                                  className="h-full flex items-end justify-center shrink-0"
                                  style={{ width: `${trendSlotWidth}px` }}
                                  title={`${point.day}
Tokens: ${point.total_tokens}
Cost: ${fmtUsd(point.cost.amount, point.cost.currency)}
缓存命中率: ${fmtPercent(point.cache_ratio)}`}
                                >
                                  <div
                                    className="w-8 rounded-t-md bg-indigo-500/70 border border-indigo-400/60"
                                    style={{ height: `${tokenHeight}%` }}
                                  />
                                </div>
                              );
                            })}
                          </div>
                          <svg
                            className="absolute top-0 left-0 pointer-events-none"
                            width={trendChartWidth}
                            height={trendChartHeight}
                            viewBox={`0 0 ${trendChartWidth} ${trendChartHeight}`}
                            preserveAspectRatio="none"
                          >
                            <polyline
                              points={trendCostLinePoints}
                              fill="none"
                              stroke="rgb(16 185 129)"
                              strokeWidth="2"
                              strokeLinejoin="round"
                              strokeLinecap="round"
                            />
                            {dailyPoints.map((point, index) => {
                              const x = index * trendSlotWidth + trendSlotWidth / 2;
                              const normalizedCost = (point.cost.cost_microusd ?? 0) / dailyMaxCostMicrousd;
                              const y = trendChartHeight - Math.round(normalizedCost * (trendChartHeight - 12)) - 6;
                              return (
                                <circle
                                  key={`${point.day}-dot`}
                                  cx={x}
                                  cy={y}
                                  r="2.5"
                                  fill="rgb(16 185 129)"
                                />
                              );
                            })}
                          </svg>
                        </div>
                        <div className="mt-2 flex">
                          {dailyPoints.map((point) => (
                            <div
                              key={`${point.day}-meta`}
                              className="shrink-0"
                              style={{ width: `${trendSlotWidth}px` }}
                            >
                              <div className="text-[10px] text-slate-700 text-center">
                                {point.day.slice(5)}
                              </div>
                              <div className="text-[10px] text-slate-500 text-center">
                                {fmtInt(point.total_tokens)} tok
                              </div>
                              <div className="text-[10px] text-slate-500 text-center">
                                {fmtUsd(point.cost.amount, point.cost.currency)}
                              </div>
                              <div className="text-[10px] text-slate-500 text-center">
                                {fmtPercent(point.cache_ratio)}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="glass-panel p-4">
                <div className="font-semibold text-slate-900 mb-3">Token 结构</div>
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3 text-sm">
                  <div className="glass-panel p-3">
                    <div className="text-slate-500">input tokens</div>
                    <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.input_tokens)}</div>
                  </div>
                  <div className="glass-panel p-3">
                    <div className="text-slate-500">cached input</div>
                    <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.cached_input_tokens)}</div>
                  </div>
                  <div className="glass-panel p-3">
                    <div className="text-slate-500">output tokens</div>
                    <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.output_tokens)}</div>
                  </div>
                  <div className="glass-panel p-3">
                    <div className="text-slate-500">cached output</div>
                    <div className="mt-1 font-semibold text-slate-900">{fmtInt(windowData.cached_output_tokens)}</div>
                  </div>
                </div>
              </div>

              <div className="glass-panel p-4 space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div>
                    <div className="font-semibold text-slate-900">请求明细</div>
                    <div className="text-xs text-slate-500 mt-1">
                      点击“展开”查看单条记录的价格快照与费用拆解。
                    </div>
                  </div>
                  <div className="ml-auto flex items-center gap-2">
                    <button
                      type="button"
                      className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                      onClick={onPrevPage}
                      disabled={!hasPrevPage || loading}
                    >
                      上一页
                    </button>
                    <button
                      type="button"
                      className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                      onClick={onNextPage}
                      disabled={!hasNextPage || loading}
                    >
                      下一页
                    </button>
                  </div>
                </div>

                {!eventsData || eventsData.events.length === 0 ? (
                  <div className="text-sm text-slate-600">这个时间范围内还没有 usage 记录。</div>
                ) : (
                  <div className="glass-table overflow-x-auto">
                    <table className="min-w-full text-sm">
                      <thead className="text-slate-600">
                        <tr>
                          <th className="text-left font-semibold px-3 py-2">时间</th>
                          <th className="text-left font-semibold px-3 py-2">模型 / 阶段</th>
                          <th className="text-left font-semibold px-3 py-2">Job</th>
                          <th className="text-right font-semibold px-3 py-2">输入</th>
                          <th className="text-right font-semibold px-3 py-2">输出</th>
                          <th className="text-right font-semibold px-3 py-2">缓存</th>
                          <th className="text-right font-semibold px-3 py-2">费用</th>
                          <th className="text-right font-semibold px-3 py-2">操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {eventsData.events.map((event) => {
                          const expanded = expandedRecordId === event.id;
                          const detail = detailById[event.id];
                          const detailLoading = Boolean(detailLoadingMap[event.id]);
                          const detailError = detailErrorMap[event.id];
                          return (
                            <React.Fragment key={event.id}>
                              <tr>
                                <td className="px-3 py-2 text-slate-700 whitespace-nowrap">{fmtDate(event.created_at)}</td>
                                <td className="px-3 py-2">
                                  <div className="font-medium text-slate-900">{event.model}</div>
                                  <div className="text-xs text-slate-500">{event.stage}</div>
                                </td>
                                <td className="px-3 py-2">
                                  <div className="font-mono text-[11px] text-slate-500 break-all">{event.job_id}</div>
                                </td>
                                <td className="px-3 py-2 text-right text-slate-700">{fmtInt(event.input_tokens)}</td>
                                <td className="px-3 py-2 text-right text-slate-700">{fmtInt(event.output_tokens)}</td>
                                <td className="px-3 py-2 text-right text-slate-700">{fmtInt(event.cached_tokens)}</td>
                                <td className="px-3 py-2 text-right text-slate-900 font-medium">
                                  {fmtUsd(event.cost?.amount ?? null, event.cost?.currency ?? "USD")}
                                </td>
                                <td className="px-3 py-2 text-right">
                                  <button
                                    type="button"
                                    className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                                    onClick={() => onToggleDetail(event.id)}
                                  >
                                    {expanded ? "收起" : "展开"}
                                  </button>
                                </td>
                              </tr>
                              {expanded ? (
                                <tr>
                                  <td colSpan={8} className="px-3 py-3 bg-slate-50/80">
                                    {detailLoading ? (
                                      <div className="text-sm text-slate-600">明细加载中…</div>
                                    ) : detailError ? (
                                      <div className="glass-alert glass-alert-error">{detailError}</div>
                                    ) : detail ? (
                                      <div className="space-y-3">
                                        <div className="text-xs text-slate-500 font-mono break-all">
                                          record_id: {detail.id}
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-2 text-xs">
                                          <div className="glass-panel p-3">
                                            <div className="text-slate-500">non-cached input</div>
                                            <div className="text-slate-900 mt-1">
                                              {fmtInt(detail.breakdown?.non_cached_input.tokens ?? 0)} tokens
                                            </div>
                                            <div className="text-slate-500">
                                              单价 {detail.breakdown?.non_cached_input.price_microusd_per_1m_tokens ?? 0}
                                            </div>
                                            <div className="font-medium text-slate-900">
                                              {fmtUsd(
                                                detail.breakdown?.non_cached_input.amount ?? null,
                                                detail.pricing?.currency ?? "USD"
                                              )}
                                            </div>
                                          </div>
                                          <div className="glass-panel p-3">
                                            <div className="text-slate-500">non-cached output</div>
                                            <div className="text-slate-900 mt-1">
                                              {fmtInt(detail.breakdown?.non_cached_output.tokens ?? 0)} tokens
                                            </div>
                                            <div className="text-slate-500">
                                              单价 {detail.breakdown?.non_cached_output.price_microusd_per_1m_tokens ?? 0}
                                            </div>
                                            <div className="font-medium text-slate-900">
                                              {fmtUsd(
                                                detail.breakdown?.non_cached_output.amount ?? null,
                                                detail.pricing?.currency ?? "USD"
                                              )}
                                            </div>
                                          </div>
                                          <div className="glass-panel p-3">
                                            <div className="text-slate-500">cached input</div>
                                            <div className="text-slate-900 mt-1">
                                              {fmtInt(detail.breakdown?.cached_input.tokens ?? 0)} tokens
                                            </div>
                                            <div className="text-slate-500">
                                              单价 {detail.breakdown?.cached_input.price_microusd_per_1m_tokens ?? 0}
                                            </div>
                                            <div className="font-medium text-slate-900">
                                              {fmtUsd(
                                                detail.breakdown?.cached_input.amount ?? null,
                                                detail.pricing?.currency ?? "USD"
                                              )}
                                            </div>
                                          </div>
                                          <div className="glass-panel p-3">
                                            <div className="text-slate-500">cached output</div>
                                            <div className="text-slate-900 mt-1">
                                              {fmtInt(detail.breakdown?.cached_output.tokens ?? 0)} tokens
                                            </div>
                                            <div className="text-slate-500">
                                              单价 {detail.breakdown?.cached_output.price_microusd_per_1m_tokens ?? 0}
                                            </div>
                                            <div className="font-medium text-slate-900">
                                              {fmtUsd(
                                                detail.breakdown?.cached_output.amount ?? null,
                                                detail.pricing?.currency ?? "USD"
                                              )}
                                            </div>
                                          </div>
                                        </div>
                                        <div className="text-sm text-slate-700">
                                          计算总价（computed）：
                                          <span className="font-semibold text-slate-900 ml-1">
                                            {fmtUsd(
                                              detail.breakdown?.computed_total_amount ?? null,
                                              detail.pricing?.currency ?? "USD"
                                            )}
                                          </span>
                                          <span className="text-xs text-slate-500 ml-2">
                                            microusd={detail.breakdown?.computed_total_microusd ?? 0}
                                          </span>
                                        </div>
                                      </div>
                                    ) : (
                                      <div className="text-sm text-slate-600">暂无可展示的明细。</div>
                                    )}
                                  </td>
                                </tr>
                              ) : null}
                            </React.Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="text-xs text-slate-500 flex items-center justify-between">
                  <span>
                    当前页记录：{fmtInt(eventsData?.events.length ?? 0)} / 每页上限 {appliedFilters.limit}
                  </span>
                  <span>
                    {beforeId ? "历史页" : "最新页"} ·
                    {hasNextPage ? " 可继续翻页" : " 已到末页"}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="glass-panel p-4 text-sm text-slate-600">暂无账单数据。</div>
          )}
        </main>
      </div>
    </RequireAuth>
  );
}
