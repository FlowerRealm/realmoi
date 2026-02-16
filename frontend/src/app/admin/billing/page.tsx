"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

type BillingCostSummary = {
  currency: string;
  cost_microusd: number | null;
  amount: string | null;
  priced_records: number;
  unpriced_records: number;
};

type BillingTotalSummary = {
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  records: number;
  unique_users: number;
  unique_models: number;
  cost: BillingCostSummary;
};

type BillingBreakdownItem = {
  key: string;
  label: string | null;
  records: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  cost_microusd: number | null;
  amount: string | null;
  priced_records: number;
  unpriced_records: number;
};

type BillingRecentRecord = {
  id: string;
  created_at: string;
  owner_user_id: string;
  username: string | null;
  job_id: string;
  stage: string;
  model: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  cost_microusd: number | null;
  amount: string | null;
};

type AdminBillingSummary = {
  query: {
    owner_user_id: string | null;
    model: string | null;
    range_days: number | null;
    top_limit: number;
    recent_limit: number;
    since: string | null;
  };
  total: BillingTotalSummary;
  top_users: BillingBreakdownItem[];
  top_models: BillingBreakdownItem[];
  recent_records: BillingRecentRecord[];
};

type BillingFilters = {
  ownerUserId: string;
  model: string;
  rangeDays: string;
  topLimit: number;
  recentLimit: number;
};

const RANGE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "7", label: "近 7 天" },
  { value: "30", label: "近 30 天" },
  { value: "90", label: "近 90 天" },
  { value: "all", label: "全部时间" },
];

function fmtInt(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function fmtDate(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

function fmtUsd(amount: string | null, currency: string = "USD"): string {
  if (!amount) return "未定价";
  return `${currency} ${amount}`;
}

function fmtCoverage(priced: number, all: number): string {
  if (all <= 0) return "-";
  return `${((priced / all) * 100).toFixed(1)}%`;
}

export default function AdminBillingPage() {
  const [filters, setFilters] = useState<BillingFilters>({
    ownerUserId: "",
    model: "",
    rangeDays: "30",
    topLimit: 8,
    recentLimit: 20,
  });
  const [draftFilters, setDraftFilters] = useState<BillingFilters>({
    ownerUserId: "",
    model: "",
    rangeDays: "30",
    topLimit: 8,
    recentLimit: 20,
  });
  const [data, setData] = useState<AdminBillingSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErrorText(null);
    try {
      const qs = new URLSearchParams();
      if (filters.ownerUserId) qs.set("owner_user_id", filters.ownerUserId);
      if (filters.model) qs.set("model", filters.model);
      if (filters.rangeDays !== "all") qs.set("range_days", filters.rangeDays);
      qs.set("top_limit", String(filters.topLimit));
      qs.set("recent_limit", String(filters.recentLimit));
      const d = await apiFetch<AdminBillingSummary>(
        `/admin/billing/summary${qs.toString() ? `?${qs.toString()}` : ""}`
      );
      setData(d);
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [filters.model, filters.ownerUserId, filters.rangeDays, filters.recentLimit, filters.topLimit]);

  useEffect(() => {
    load();
  }, [load]);

  const hasPendingChanges =
    draftFilters.ownerUserId.trim() !== filters.ownerUserId ||
    draftFilters.model.trim() !== filters.model ||
    draftFilters.rangeDays !== filters.rangeDays ||
    draftFilters.topLimit !== filters.topLimit ||
    draftFilters.recentLimit !== filters.recentLimit;

  const applyFilters = () => {
    setFilters({
      ownerUserId: draftFilters.ownerUserId.trim(),
      model: draftFilters.model.trim(),
      rangeDays: draftFilters.rangeDays,
      topLimit: draftFilters.topLimit,
      recentLimit: draftFilters.recentLimit,
    });
  };

  const totalTokens = data
    ? data.total.input_tokens +
      data.total.cached_input_tokens +
      data.total.output_tokens +
      data.total.cached_output_tokens
    : 0;
  const interactiveTokens = data ? data.total.input_tokens + data.total.output_tokens : 0;
  const cachedTokens = data ? data.total.cached_input_tokens + data.total.cached_output_tokens : 0;

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-screen min-h-[100dvh] box-border pt-14 overflow-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
            <div className="glass-panel-strong p-4 md:p-5 flex items-center gap-3">
              <div>
                <h1 className="text-xl font-semibold text-slate-900">Admin / Billing</h1>
                <p className="text-xs text-slate-500 mt-1">全站费用、用户消耗排行与最近使用明细</p>
              </div>
              <button
                type="button"
                onClick={load}
                className="ml-auto glass-btn"
              >
                刷新
              </button>
            </div>

            {errorText ? (
              <div className="glass-alert glass-alert-error">
                {errorText}
              </div>
            ) : null}

            {loading ? (
              <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
            ) : data ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                  <div className="glass-panel p-4">
                    <div className="text-xs text-slate-500">总费用（已定价记录）</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">
                      {fmtUsd(data.total.cost.amount, data.total.cost.currency)}
                    </div>
                    <div className="mt-1 text-xs text-slate-500 font-mono">
                      microusd={data.total.cost.cost_microusd ?? "-"}
                    </div>
                  </div>
                  <div className="glass-panel p-4">
                    <div className="text-xs text-slate-500">使用记录数</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">{fmtInt(data.total.records)}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      已定价 {fmtInt(data.total.cost.priced_records)} / 未定价 {fmtInt(data.total.cost.unpriced_records)}
                    </div>
                  </div>
                  <div className="glass-panel p-4">
                    <div className="text-xs text-slate-500">活跃用户 / 模型</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">
                      {fmtInt(data.total.unique_users)} / {fmtInt(data.total.unique_models)}
                    </div>
                    <div className="mt-1 text-xs text-slate-500">
                      覆盖率 {fmtCoverage(data.total.cost.priced_records, data.total.records)}
                    </div>
                  </div>
                  <div className="glass-panel p-4">
                    <div className="text-xs text-slate-500">总 Tokens</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">{fmtInt(totalTokens)}</div>
                  </div>
                  <div className="glass-panel p-4">
                    <div className="text-xs text-slate-500">交互 Tokens（input + output）</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">{fmtInt(interactiveTokens)}</div>
                  </div>
                  <div className="glass-panel p-4">
                    <div className="text-xs text-slate-500">缓存 Tokens</div>
                    <div className="mt-1 text-lg font-semibold text-slate-900">{fmtInt(cachedTokens)}</div>
                  </div>
                </div>

                <details className="glass-panel p-4">
                  <summary className="cursor-pointer list-none flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">筛选条件（可折叠）</span>
                    <span className="text-xs text-slate-500">
                      当前：{filters.rangeDays === "all" ? "全部时间" : `近 ${filters.rangeDays} 天`} / owner={filters.ownerUserId || "全部"} / model={filters.model || "全部"}
                    </span>
                    {hasPendingChanges ? <span className="text-xs text-amber-600">草稿未应用</span> : null}
                  </summary>
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    <div>
                      <div className="text-xs text-slate-500">时间范围</div>
                      <select
                        value={draftFilters.rangeDays}
                        onChange={(e) =>
                          setDraftFilters((prev) => ({ ...prev, rangeDays: e.target.value }))
                        }
                        className="glass-input mt-1 text-sm"
                      >
                        {RANGE_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">owner_user_id（可选）</div>
                      <input
                        value={draftFilters.ownerUserId}
                        onChange={(e) =>
                          setDraftFilters((prev) => ({ ...prev, ownerUserId: e.target.value }))
                        }
                        className="glass-input mt-1 text-sm font-mono"
                        placeholder="输入完整用户 ID"
                      />
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">model（可选）</div>
                      <input
                        value={draftFilters.model}
                        onChange={(e) =>
                          setDraftFilters((prev) => ({ ...prev, model: e.target.value }))
                        }
                        className="glass-input mt-1 text-sm font-mono"
                        placeholder="例如 gpt-5.2-codex"
                      />
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">Top 列表条数</div>
                      <select
                        value={draftFilters.topLimit}
                        onChange={(e) =>
                          setDraftFilters((prev) => ({ ...prev, topLimit: Number(e.target.value) }))
                        }
                        className="glass-input mt-1 text-sm"
                      >
                        {[5, 8, 10, 20].map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <div className="text-xs text-slate-500">最近明细条数</div>
                      <select
                        value={draftFilters.recentLimit}
                        onChange={(e) =>
                          setDraftFilters((prev) => ({ ...prev, recentLimit: Number(e.target.value) }))
                        }
                        className="glass-input mt-1 text-sm"
                      >
                        {[10, 20, 50, 100].map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={applyFilters}
                        disabled={!hasPendingChanges}
                        className="glass-btn glass-btn-secondary w-full"
                      >
                        {hasPendingChanges ? "应用筛选" : "筛选已生效"}
                      </button>
                    </div>
                  </div>
                </details>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                  <div className="glass-panel p-4">
                    <div className="font-semibold text-slate-900 mb-3">Top 用户</div>
                    {data.top_users.length === 0 ? (
                      <div className="text-sm text-slate-600">暂无数据</div>
                    ) : (
                      <div className="glass-table overflow-x-auto">
                        <table className="min-w-full text-sm">
                          <thead className="text-slate-600">
                            <tr>
                              <th className="text-left font-semibold px-3 py-2">用户</th>
                              <th className="text-right font-semibold px-3 py-2">records</th>
                              <th className="text-right font-semibold px-3 py-2">input</th>
                              <th className="text-right font-semibold px-3 py-2">output</th>
                              <th className="text-right font-semibold px-3 py-2">费用</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.top_users.map((row) => (
                              <tr key={row.key}>
                                <td className="px-3 py-2">
                                  <div className="font-semibold text-slate-900">{row.label || "未知用户"}</div>
                                  <div className="font-mono text-[11px] text-slate-500 break-all">{row.key}</div>
                                </td>
                                <td className="px-3 py-2 text-right font-mono">{fmtInt(row.records)}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtInt(row.input_tokens)}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtInt(row.output_tokens)}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtUsd(row.amount)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>

                  <div className="glass-panel p-4">
                    <div className="font-semibold text-slate-900 mb-3">Top 模型</div>
                    {data.top_models.length === 0 ? (
                      <div className="text-sm text-slate-600">暂无数据</div>
                    ) : (
                      <div className="glass-table overflow-x-auto">
                        <table className="min-w-full text-sm">
                          <thead className="text-slate-600">
                            <tr>
                              <th className="text-left font-semibold px-3 py-2">模型</th>
                              <th className="text-right font-semibold px-3 py-2">records</th>
                              <th className="text-right font-semibold px-3 py-2">input</th>
                              <th className="text-right font-semibold px-3 py-2">output</th>
                              <th className="text-right font-semibold px-3 py-2">费用</th>
                            </tr>
                          </thead>
                          <tbody>
                            {data.top_models.map((row) => (
                              <tr key={row.key}>
                                <td className="px-3 py-2 font-mono text-xs text-slate-900 break-all">{row.key}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtInt(row.records)}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtInt(row.input_tokens)}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtInt(row.output_tokens)}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtUsd(row.amount)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </div>

                <div className="glass-panel p-4">
                  <div className="font-semibold text-slate-900 mb-3">最近使用记录</div>
                  {data.recent_records.length === 0 ? (
                    <div className="text-sm text-slate-600">当前筛选条件下无记录</div>
                  ) : (
                    <div className="glass-table overflow-x-auto">
                      <table className="min-w-full text-sm">
                        <thead className="text-slate-600">
                          <tr>
                            <th className="text-left font-semibold px-3 py-2">时间</th>
                            <th className="text-left font-semibold px-3 py-2">用户</th>
                            <th className="text-left font-semibold px-3 py-2">模型</th>
                            <th className="text-left font-semibold px-3 py-2">job / stage</th>
                            <th className="text-right font-semibold px-3 py-2">tokens</th>
                            <th className="text-right font-semibold px-3 py-2">费用</th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.recent_records.map((row) => {
                            const tokens =
                              row.input_tokens +
                              row.cached_input_tokens +
                              row.output_tokens +
                              row.cached_output_tokens;
                            return (
                              <tr key={row.id}>
                                <td className="px-3 py-2 whitespace-nowrap">{fmtDate(row.created_at)}</td>
                                <td className="px-3 py-2">
                                  <div className="font-semibold text-slate-900">{row.username || "未知用户"}</div>
                                  <div className="font-mono text-[11px] text-slate-500 break-all">{row.owner_user_id}</div>
                                </td>
                                <td className="px-3 py-2 font-mono text-xs text-slate-900 break-all">{row.model}</td>
                                <td className="px-3 py-2">
                                  <div className="font-mono text-xs text-slate-700 break-all">{row.job_id}</div>
                                  <div className="text-[11px] text-slate-500">{row.stage}</div>
                                </td>
                                <td className="px-3 py-2 text-right font-mono">{fmtInt(tokens)}</td>
                                <td className="px-3 py-2 text-right font-mono">{fmtUsd(row.amount)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="glass-panel p-4 text-sm text-slate-600">无数据</div>
            )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}
