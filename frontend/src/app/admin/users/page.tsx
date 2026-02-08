"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { FluidBackground } from "@/components/assistant/FluidBackground";
import { apiFetch, getErrorMessage } from "@/lib/api";

type UserItem = {
  id: string;
  username: string;
  role: "user" | "admin";
  is_disabled: boolean;
  created_at: string;
};

type UsersListResponse = {
  items: UserItem[];
  total: number;
};

function fmt(ts?: string | null) {
  if (!ts) return "-";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString();
}

export default function AdminUsersPage() {
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  const [data, setData] = useState<UsersListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);

  const total = data?.total ?? 0;
  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  const load = useCallback(async () => {
    setLoading(true);
    setErrorText(null);
    try {
      const qs = new URLSearchParams();
      if (q.trim()) qs.set("q", q.trim());
      qs.set("limit", String(limit));
      qs.set("offset", String(offset));
      const d = await apiFetch<UsersListResponse>(`/admin/users?${qs.toString()}`);
      setData(d);
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [q, limit, offset]);

  useEffect(() => {
    load();
  }, [load]);

  const patchUser = async (userId: string, body: Record<string, unknown>) => {
    try {
      await apiFetch(`/admin/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      await load();
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    }
  };

  const resetPassword = async (userId: string) => {
    const newPwd = window.prompt("输入新密码（8-72 字符）：");
    if (!newPwd) return;
    try {
      await apiFetch(`/admin/users/${userId}/reset_password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: newPwd }),
      });
      window.alert("已重置密码");
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    }
  };

  const items = useMemo(() => data?.items || [], [data?.items]);

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-screen min-h-[100dvh] box-border pt-14 overflow-hidden text-slate-800 selection:bg-indigo-500/20">
          <FluidBackground />
          <AppHeader mode="overlay" />
          <main className="mx-auto max-w-6xl px-4 pt-8 pb-6 space-y-4 relative z-10">
          <div className="glass-panel-strong p-4 md:p-5 flex items-center gap-3">
            <div>
              <h1 className="text-xl font-semibold text-slate-900">Admin / Users</h1>
              <p className="text-xs text-slate-500 mt-1">用户检索、角色调整、禁用与重置密码</p>
            </div>
            <button
              type="button"
              onClick={load}
              className="ml-auto glass-btn"
            >
              刷新
            </button>
          </div>

          <div className="glass-panel p-4 flex flex-wrap items-center gap-2">
            <input
              value={q}
              onChange={(e) => {
                setOffset(0);
                setQ(e.target.value);
              }}
              placeholder="搜索用户名…"
              className="glass-input w-64 max-w-full text-sm"
            />
            <select
              value={limit}
              onChange={(e) => {
                setOffset(0);
                setLimit(Number(e.target.value));
              }}
              className="glass-input w-28 text-sm"
            >
              {[20, 50, 100].map((n) => (
                <option key={n} value={n}>
                  {n} / 页
                </option>
              ))}
            </select>
            <div className="ml-auto flex items-center gap-2">
              <button
                type="button"
                onClick={() => setOffset((v) => Math.max(0, v - limit))}
                disabled={!canPrev}
                className="glass-btn glass-btn-secondary"
              >
                上一页
              </button>
              <button
                type="button"
                onClick={() => setOffset((v) => v + limit)}
                disabled={!canNext}
                className="glass-btn glass-btn-secondary"
              >
                下一页
              </button>
              <div className="text-xs text-slate-500">
                offset={offset} / total={total}
              </div>
            </div>
          </div>

          {errorText ? (
            <div className="glass-alert glass-alert-error">
              {errorText}
            </div>
          ) : null}

          {loading ? (
            <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
          ) : (
            <div className="glass-table overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead className="text-slate-600">
                  <tr>
                    <th className="text-left font-semibold px-3 py-2">username</th>
                    <th className="text-left font-semibold px-3 py-2">role</th>
                    <th className="text-left font-semibold px-3 py-2">disabled</th>
                    <th className="text-left font-semibold px-3 py-2">created_at</th>
                    <th className="text-left font-semibold px-3 py-2">actions</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((u) => (
                    <tr key={u.id}>
                      <td className="px-3 py-2">
                        <div className="font-semibold text-slate-900">{u.username}</div>
                        <div className="font-mono text-xs text-slate-500 break-all">{u.id}</div>
                      </td>
                      <td className="px-3 py-2">
                        <select
                          value={u.role}
                          onChange={(e) => patchUser(u.id, { role: e.target.value })}
                          className="glass-input w-24 text-sm py-1.5"
                        >
                          <option value="user">user</option>
                          <option value="admin">admin</option>
                        </select>
                      </td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => patchUser(u.id, { is_disabled: !u.is_disabled })}
                          className={[
                            "text-xs px-2 py-1 rounded-md border",
                            u.is_disabled
                              ? "border-rose-200 bg-rose-50/80 text-rose-700 hover:bg-rose-100"
                              : "border-emerald-200 bg-emerald-50/80 text-emerald-700 hover:bg-emerald-100",
                          ].join(" ")}
                        >
                          {u.is_disabled ? "已禁用" : "正常"}
                        </button>
                      </td>
                      <td className="px-3 py-2">{fmt(u.created_at)}</td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => resetPassword(u.id)}
                          className="glass-btn glass-btn-secondary text-xs px-2 py-1.5"
                        >
                          重置密码
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}
