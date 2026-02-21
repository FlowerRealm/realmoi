"use client";

import React from "react";
import type { PricingStats } from "../pricingTypes";

type PricingHeaderProps = {
  loading: boolean;
  stats: PricingStats;
  onRefresh: () => void;
};

export function PricingHeader({ loading, onRefresh, stats }: PricingHeaderProps) {
  return (
    <div className="glass-panel-strong p-4 md:p-5 flex flex-wrap items-center gap-3">
      <div className="min-w-[12rem]">
        <h1 className="text-xl font-semibold tracking-tight" style={{ color: "var(--text-primary)" }}>
          Admin / Pricing
        </h1>
        <p className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
          只读浏览 · 按需编辑 · 实时发现
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
        <span className="glass-chip px-2 py-1">
          总数{" "}
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
            {stats.total}
          </span>
        </span>
        <span className="glass-chip px-2 py-1">
          可见{" "}
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
            {stats.visible}
          </span>
        </span>
        <span className="glass-chip px-2 py-1">
          Active{" "}
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
            {stats.activeCount}
          </span>
        </span>
        <span className="glass-chip px-2 py-1">
          待保存{" "}
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
            {stats.dirtyCount}
          </span>
        </span>
        <span className="glass-chip px-2 py-1">
          实时发现{" "}
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
            {stats.discovered}
          </span>
        </span>
        <span className="glass-chip px-2 py-1">
          缺失定价{" "}
          <span className="font-semibold" style={{ color: "var(--text-primary)" }}>
            {stats.missingAny}
          </span>
        </span>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <button type="button" onClick={onRefresh} className="glass-btn">
          {loading ? "刷新中…" : "刷新（实时模型）"}
        </button>
      </div>
    </div>
  );
}

