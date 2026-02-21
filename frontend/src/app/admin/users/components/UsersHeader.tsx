"use client";

// AUTO_COMMENT_HEADER_V1: UsersHeader.tsx
// 说明：Admin Users 页顶栏（统计 + 刷新 + 新建用户入口）。

import React from "react";

import type { UsersStats } from "../adminUsersTypes";

export function UsersHeader({
  total,
  stats,
  loading,
  onCreateUser,
  onRefresh,
}: {
  total: number;
  stats: UsersStats;
  loading: boolean;
  onCreateUser: () => void;
  onRefresh: () => void;
}) {
  return (
    <div className="glass-panel-strong p-4 md:p-5 flex flex-wrap items-center gap-3">
      <div className="min-w-[12rem]">
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">Admin / Users</h1>
        <p className="text-xs mt-1 text-slate-500">用户管理 · 状态 / 角色 / 密码</p>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
        <span className="glass-chip px-2 py-1">
          Total <span className="font-semibold text-slate-900">{total}</span>
        </span>
        <span className="glass-chip px-2 py-1">
          Visible <span className="font-semibold text-slate-900">{stats.visible}</span>
        </span>
        <span className="glass-chip px-2 py-1">
          Admin <span className="font-semibold text-slate-900">{stats.adminCount}</span>
        </span>
        <span className="glass-chip px-2 py-1">
          Disabled <span className="font-semibold text-slate-900">{stats.disabledCount}</span>
        </span>
      </div>
      <div className="ml-auto flex items-center gap-2">
        <button type="button" onClick={onCreateUser} className="glass-btn glass-btn-secondary">
          新建用户
        </button>
        <button type="button" onClick={onRefresh} disabled={loading} className="glass-btn">
          {loading ? "刷新中…" : "刷新"}
        </button>
      </div>
    </div>
  );
}

