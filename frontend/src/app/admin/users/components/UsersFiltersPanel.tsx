"use client";

// AUTO_COMMENT_HEADER_V1: UsersFiltersPanel.tsx
// 说明：Admin Users 页筛选面板（draft -> apply）。

import React from "react";

import type { Filters } from "../adminUsersTypes";

export function UsersFiltersPanel({
  filtersDraft,
  setFiltersDraft,
  filters,
  total,
  loading,
  onApply,
  onReset,
}: {
  filtersDraft: Filters;
  setFiltersDraft: React.Dispatch<React.SetStateAction<Filters>>;
  filters: Filters;
  total: number;
  loading: boolean;
  onApply: () => void;
  onReset: () => void;
}) {
  return (
    <div className="glass-panel p-4">
      <div className="grid grid-cols-1 md:grid-cols-12 gap-2 items-end">
        <label className="md:col-span-6 space-y-1">
          <div className="text-xs font-medium text-slate-600">搜索</div>
          <input
            value={filtersDraft.q}
            onChange={(e) => setFiltersDraft((p) => ({ ...p, q: e.target.value }))}
            placeholder="用户名包含…（like）"
            className="glass-input text-sm"
          />
        </label>
        <label className="md:col-span-3 space-y-1">
          <div className="text-xs font-medium text-slate-600">角色</div>
          <select
            value={filtersDraft.role}
            onChange={(e) => setFiltersDraft((p) => ({ ...p, role: e.target.value as Filters["role"] }))}
            className="glass-input text-sm"
          >
            <option value="all">全部</option>
            <option value="admin">管理员</option>
            <option value="user">普通用户</option>
          </select>
        </label>
        <label className="md:col-span-3 space-y-1">
          <div className="text-xs font-medium text-slate-600">状态</div>
          <select
            value={filtersDraft.status}
            onChange={(e) => setFiltersDraft((p) => ({ ...p, status: e.target.value as Filters["status"] }))}
            className="glass-input text-sm"
          >
            <option value="all">全部</option>
            <option value="enabled">已启用</option>
            <option value="disabled">已禁用</option>
          </select>
        </label>
        <div className="md:col-span-12 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onApply}
            disabled={loading}
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
          >
            查询
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={loading}
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
          >
            重置
          </button>
          <div className="ml-auto text-xs text-slate-500 px-1">
            {filters.q.trim() ? `筛选：${filters.q.trim()} · ` : ""}
            {filters.role !== "all" ? `role=${filters.role} · ` : ""}
            {filters.status !== "all" ? `status=${filters.status} · ` : ""}
            共 {total} 条
          </div>
        </div>
      </div>
    </div>
  );
}

