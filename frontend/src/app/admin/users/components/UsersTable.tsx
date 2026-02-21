"use client";

// AUTO_COMMENT_HEADER_V1: UsersTable.tsx
// 说明：Admin Users 页表格 + 分页区。

import React from "react";

import type { UserItem } from "../adminUsersTypes";
import { formatCreatedAt, roleLabel, statusLabel } from "../adminUsersUtils";
import { Badge } from "./Badge";

export function UsersTable({
  items,
  loading,
  selectedUserId,
  onSelectUser,
  activePage,
  totalPages,
  total,
  pageSize,
  onChangePageSize,
  onPrevPage,
  onNextPage,
}: {
  items: UserItem[];
  loading: boolean;
  selectedUserId: string | null;
  onSelectUser: (userId: string) => void;
  activePage: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onChangePageSize: (pageSize: number) => void;
  onPrevPage: () => void;
  onNextPage: () => void;
}) {
  if (loading) {
    return <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>;
  }
  if (items.length === 0) {
    return <div className="glass-panel p-4 text-sm text-slate-600">无数据</div>;
  }

  return (
    <div className="glass-panel p-4">
      <div className="glass-table overflow-x-auto">
        <table className="min-w-full w-full text-sm">
          <thead className="text-slate-600">
            <tr>
              <th className="text-left font-semibold px-3 py-2">用户名</th>
              <th className="text-left font-semibold px-3 py-2">角色</th>
              <th className="text-left font-semibold px-3 py-2">状态</th>
              <th className="hidden md:table-cell text-right font-semibold px-3 py-2">创建时间</th>
              <th className="text-right font-semibold px-3 py-2">操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => {
              const isSelected = selectedUserId === u.id;
              return (
                <tr key={u.id} className={isSelected ? "bg-indigo-50/60" : ""}>
                  <td className="px-3 py-2 text-slate-900 font-semibold whitespace-nowrap">{u.username}</td>
                  <td className="px-3 py-2">
                    <Badge tone={u.role === "admin" ? "amber" : "indigo"}>{roleLabel(u.role)}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    <Badge tone={u.is_disabled ? "rose" : "emerald"}>{statusLabel(u.is_disabled)}</Badge>
                  </td>
                  <td className="hidden md:table-cell px-3 py-2 text-right text-xs text-slate-600 whitespace-nowrap">
                    {formatCreatedAt(u.created_at)}
                  </td>
                  <td className="px-3 py-2 text-right whitespace-nowrap">
                    <button
                      type="button"
                      onClick={() => onSelectUser(u.id)}
                      className="glass-btn glass-btn-secondary text-xs px-2.5 py-1.5 whitespace-nowrap"
                    >
                      管理
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex flex-col md:flex-row md:items-center gap-2">
        <div className="text-xs text-slate-500">
          第 {activePage} / {totalPages} 页 · 共 {total} 条
        </div>
        <div className="md:ml-auto flex flex-wrap items-center gap-2">
          <label className="text-xs text-slate-600">每页</label>
          <select
            value={pageSize}
            onChange={(e) => onChangePageSize(Number(e.target.value))}
            className="glass-input text-sm w-24"
          >
            {[10, 20, 50, 100].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={onPrevPage}
            disabled={activePage <= 1}
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5 whitespace-nowrap"
          >
            上一页
          </button>
          <button
            type="button"
            onClick={onNextPage}
            disabled={activePage >= totalPages}
            className="glass-btn glass-btn-secondary text-xs px-3 py-1.5 whitespace-nowrap"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  );
}

