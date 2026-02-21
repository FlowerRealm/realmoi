"use client";

// 按天趋势：柱高代表 Tokens，折线代表费用（Cost）。

import React, { useMemo } from "react";
import type { BillingDailyResponse, BillingDailyPoint } from "../billingTypes";
import { fmtInt, fmtPercent, fmtUsd } from "../billingUtils";

type BillingTrendPanelProps = {
  dailyData: BillingDailyResponse | null;
};

type TrendGeometry = {
  chartHeight: number;
  chartWidth: number;
  slotWidth: number;
  maxTokens: number;
  maxCostMicrousd: number;
  costLinePoints: string;
};

function buildTrendGeometry(points: BillingDailyPoint[]): TrendGeometry {
  const slotWidth = 64;
  const chartHeight = 112;
  const chartWidth = Math.max(slotWidth, points.length * slotWidth);
  const maxTokens = Math.max(1, ...points.map((point) => point.total_tokens));
  const maxCostMicrousd = Math.max(1, ...points.map((point) => point.cost.cost_microusd ?? 0));
  const costLinePoints = points
    .map((point, index) => {
      const x = index * slotWidth + slotWidth / 2;
      const normalizedCost = (point.cost.cost_microusd ?? 0) / maxCostMicrousd;
      const y = chartHeight - Math.round(normalizedCost * (chartHeight - 12)) - 6;
      return `${x},${y}`;
    })
    .join(" ");

  return {
    chartHeight,
    chartWidth,
    slotWidth,
    maxTokens,
    maxCostMicrousd,
    costLinePoints,
  };
}

export function BillingTrendPanel({ dailyData }: BillingTrendPanelProps) {
  const points = dailyData?.points ?? [];
  const geometry = useMemo(() => buildTrendGeometry(points), [points]);

  return (
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
            <div className="min-w-max" style={{ width: `${geometry.chartWidth}px` }}>
              <div className="relative h-32">
                <div className="absolute inset-0 flex items-end">
                  {points.map((point) => {
                    const tokenHeight = Math.max(
                      10,
                      Math.round((point.total_tokens / geometry.maxTokens) * 100)
                    );
                    return (
                      <div
                        key={`${point.day}-bar`}
                        className="h-full flex items-end justify-center shrink-0"
                        style={{ width: `${geometry.slotWidth}px` }}
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
                  width={geometry.chartWidth}
                  height={geometry.chartHeight}
                  viewBox={`0 0 ${geometry.chartWidth} ${geometry.chartHeight}`}
                  preserveAspectRatio="none"
                >
                  <polyline
                    points={geometry.costLinePoints}
                    fill="none"
                    stroke="rgb(16 185 129)"
                    strokeWidth="2"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                  {points.map((point, index) => {
                    const x = index * geometry.slotWidth + geometry.slotWidth / 2;
                    const normalizedCost = (point.cost.cost_microusd ?? 0) / geometry.maxCostMicrousd;
                    const y =
                      geometry.chartHeight -
                      Math.round(normalizedCost * (geometry.chartHeight - 12)) -
                      6;
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
                {points.map((point) => (
                  <div
                    key={`${point.day}-meta`}
                    className="shrink-0"
                    style={{ width: `${geometry.slotWidth}px` }}
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
  );
}

