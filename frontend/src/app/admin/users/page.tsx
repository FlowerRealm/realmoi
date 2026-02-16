"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

type UserRole = "user" | "admin";

type UserItem = {
  id: string;
  username: string;
  role: UserRole;
  is_disabled: boolean;
  created_at: string;
};

type UsersListResponse = {
  items: UserItem[];
  total: number;
};

type MeResponse = {
  id: string;
  username: string;
  role: UserRole;
  is_disabled: boolean;
};

type Filters = {
  q: string;
  role: "all" | UserRole;
  status: "all" | "enabled" | "disabled";
};

type AlertKind = "error" | "success";

function formatCreatedAt(raw: string): string {
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

function roleLabel(role: UserRole): string {
  return role === "admin" ? "管理员" : "普通用户";
}

function statusLabel(isDisabled: boolean): string {
  return isDisabled ? "已禁用" : "已启用";
}

function generatePassword(length = 18): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const out: string[] = [];
  for (let i = 0; i < length; i++) {
    out.push(alphabet[Math.floor(Math.random() * alphabet.length)]);
  }
  return out.join("");
}

function Badge({
  tone,
  children,
}: {
  tone: "indigo" | "amber" | "emerald" | "rose" | "slate";
  children: React.ReactNode;
}) {
  const cls =
    tone === "amber"
      ? "bg-amber-50 text-amber-700 border border-amber-200"
      : tone === "emerald"
        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
        : tone === "rose"
          ? "bg-rose-50 text-rose-700 border border-rose-200"
          : tone === "indigo"
            ? "bg-indigo-50 text-indigo-700 border border-indigo-200"
            : "bg-slate-50 text-slate-700 border border-slate-200";
  return (
    <span className={["inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold", cls].join(" ")}>
      {children}
    </span>
  );
}

function ModalShell({
  title,
  subtitle,
  onClose,
  children,
  maxWidthClassName = "max-w-3xl",
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidthClassName?: string;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 backdrop-blur-[2px] px-4"
      onClick={onClose}
    >
      <div
        className={[
          "glass-panel-strong w-full p-5 space-y-4 bg-white/95 border border-slate-200 shadow-[0_24px_70px_rgba(15,23,42,0.28)]",
          maxWidthClassName,
        ].join(" ")}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center gap-2">
          <div>
            <div className="text-base font-semibold text-slate-900">{title}</div>
            {subtitle ? <div className="text-xs text-slate-500 mt-1">{subtitle}</div> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto text-xs px-2.5 py-1.5 rounded-md border border-slate-200 bg-white/80 text-slate-600 hover:bg-white whitespace-nowrap"
          >
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export default function AdminUsersPage() {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [filtersDraft, setFiltersDraft] = useState<Filters>({ q: "", role: "all", status: "all" });
  const [filters, setFilters] = useState<Filters>({ q: "", role: "all", status: "all" });

  const [activePage, setActivePage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  const [data, setData] = useState<UsersListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [alertText, setAlertText] = useState<string | null>(null);
  const [alertKind, setAlertKind] = useState<AlertKind>("success");

  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createDraft, setCreateDraft] = useState<{ username: string; password: string; role: UserRole; is_disabled: boolean }>(
    {
      username: "",
      password: "",
      role: "user",
      is_disabled: false,
    }
  );

  const [showResetModal, setShowResetModal] = useState(false);
  const [resetDraft, setResetDraft] = useState<{ user_id: string; username: string; new_password: string }>({
    user_id: "",
    username: "",
    new_password: "",
  });

  const [mutatingUserId, setMutatingUserId] = useState<string | null>(null);
  const [creatingUser, setCreatingUser] = useState(false);
  const [resettingUserId, setResettingUserId] = useState<string | null>(null);

  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));

  const load = useCallback(async () => {
    setLoading(true);
    setErrorText(null);
    try {
      const qs = new URLSearchParams();
      if (filters.q.trim()) qs.set("q", filters.q.trim());
      if (filters.role !== "all") qs.set("role", filters.role);
      if (filters.status !== "all") qs.set("is_disabled", filters.status === "disabled" ? "true" : "false");
      qs.set("limit", String(pageSize));
      qs.set("offset", String(Math.max(0, (activePage - 1) * pageSize)));
      const d = await apiFetch<UsersListResponse>(`/admin/users?${qs.toString()}`);
      setData(d);
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [activePage, filters.q, filters.role, filters.status, pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (activePage > totalPages) setActivePage(totalPages);
  }, [activePage, totalPages]);

  useEffect(() => {
    const loadMe = async () => {
      try {
        const d = await apiFetch<MeResponse>("/auth/me");
        setMe(d);
      } catch {
        setMe(null);
      }
    };
    void loadMe();
  }, []);

  const items = useMemo(() => data?.items || [], [data?.items]);
  const selectedUser = useMemo(() => items.find((u) => u.id === selectedUserId) || null, [items, selectedUserId]);

  const stats = useMemo(() => {
    const adminCount = items.filter((u) => u.role === "admin").length;
    const disabledCount = items.filter((u) => u.is_disabled).length;
    return { visible: items.length, adminCount, disabledCount };
  }, [items]);

  const applyFilters = () => {
    setFilters({
      q: filtersDraft.q.trim(),
      role: filtersDraft.role,
      status: filtersDraft.status,
    });
    setActivePage(1);
  };

  const resetFilters = () => {
    setFiltersDraft({ q: "", role: "all", status: "all" });
    setFilters({ q: "", role: "all", status: "all" });
    setActivePage(1);
  };

  const handlePrevPage = () => setActivePage((p) => Math.max(1, p - 1));
  const handleNextPage = () => setActivePage((p) => Math.min(totalPages, p + 1));

  const patchUser = async (userId: string, patch: { role?: UserRole; is_disabled?: boolean }) => {
    setMutatingUserId(userId);
    setErrorText(null);
    setAlertText(null);
    try {
      await apiFetch(`/admin/users/${encodeURIComponent(userId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      setAlertKind("success");
      setAlertText("已保存。");
      await load();
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
    } finally {
      setMutatingUserId(null);
    }
  };

  const openResetPassword = (u: UserItem) => {
    setErrorText(null);
    setAlertText(null);
    setResetDraft({ user_id: u.id, username: u.username, new_password: generatePassword(18) });
    setShowResetModal(true);
  };

  const resetPassword = async () => {
    const userId = resetDraft.user_id;
    if (!userId) return;
    setResettingUserId(userId);
    setErrorText(null);
    setAlertText(null);
    try {
      await apiFetch(`/admin/users/${encodeURIComponent(userId)}/reset_password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_password: resetDraft.new_password }),
      });
      setAlertKind("success");
      setAlertText(`已重置密码：${resetDraft.username}`);
      setShowResetModal(false);
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
    } finally {
      setResettingUserId(null);
    }
  };

  const createUser = async () => {
    setCreatingUser(true);
    setErrorText(null);
    setAlertText(null);
    try {
      const created = await apiFetch<UserItem>("/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: createDraft.username,
          password: createDraft.password,
          role: createDraft.role,
          is_disabled: createDraft.is_disabled,
        }),
      });
      setAlertKind("success");
      setAlertText(`已创建用户：${created.username}`);
      setShowCreateModal(false);
      setCreateDraft({ username: "", password: "", role: "user", is_disabled: false });
      setFiltersDraft({ q: created.username, role: "all", status: "all" });
      setFilters({ q: created.username, role: "all", status: "all" });
      setActivePage(1);
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
    } finally {
      setCreatingUser(false);
    }
  };

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-full min-h-[100dvh] box-border pt-14 overflow-x-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
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
                <button
                  type="button"
                  onClick={() => {
                    setSelectedUserId(null);
                    setErrorText(null);
                    setAlertText(null);
                    setShowCreateModal(true);
                  }}
                  className="glass-btn glass-btn-secondary"
                >
                  新建用户
                </button>
                <button
                  type="button"
                  onClick={load}
                  disabled={loading}
                  className="glass-btn"
                >
                  {loading ? "刷新中…" : "刷新"}
                </button>
              </div>
            </div>

            {showCreateModal ? (
              <ModalShell
                title="新建用户"
                subtitle="创建后可在列表中点击“管理”打开用户管理窗口。"
                onClose={() => setShowCreateModal(false)}
              >
                {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}
                {alertText ? (
                  <div
                    className={["glass-alert", alertKind === "success" ? "glass-alert-success" : "glass-alert-error"].join(
                      " "
                    )}
                  >
                    {alertText}
                  </div>
                ) : null}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <label className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">用户名</div>
                    <input
                      value={createDraft.username}
                      onChange={(e) => setCreateDraft((p) => ({ ...p, username: e.target.value }))}
                      placeholder="3–32 位，a-zA-Z0-9_.-"
                      className="glass-input text-sm"
                    />
                  </label>
                  <label className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">角色</div>
                    <select
                      value={createDraft.role}
                      onChange={(e) => setCreateDraft((p) => ({ ...p, role: e.target.value as UserRole }))}
                      className="glass-input text-sm"
                    >
                      <option value="user">普通用户</option>
                      <option value="admin">管理员</option>
                    </select>
                  </label>
                  <label className="space-y-1 md:col-span-2">
                    <div className="text-xs font-medium text-slate-600">初始密码</div>
                    <div className="flex items-center gap-2">
                      <input
                        value={createDraft.password}
                        onChange={(e) => setCreateDraft((p) => ({ ...p, password: e.target.value }))}
                        placeholder="8–72 位"
                        className="glass-input text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setCreateDraft((p) => ({ ...p, password: generatePassword(18) }))}
                        className="glass-btn glass-btn-secondary text-xs px-3 py-2 whitespace-nowrap"
                      >
                        随机生成
                      </button>
                    </div>
                  </label>
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700 md:col-span-2">
                    <input
                      type="checkbox"
                      checked={createDraft.is_disabled}
                      onChange={(e) => setCreateDraft((p) => ({ ...p, is_disabled: e.target.checked }))}
                    />
                    创建后立即禁用
                  </label>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={createUser}
                    disabled={creatingUser}
                    className="glass-btn whitespace-nowrap"
                  >
                    {creatingUser ? "创建中…" : "创建用户"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowCreateModal(false)}
                    className="glass-btn glass-btn-secondary whitespace-nowrap"
                  >
                    取消
                  </button>
                </div>
              </ModalShell>
            ) : null}

            {showResetModal ? (
              <ModalShell
                title="重置密码"
                subtitle="重置后请把新密码安全地交付给用户（或让用户立即修改）。"
                onClose={() => setShowResetModal(false)}
              >
                {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}
                {alertText ? (
                  <div
                    className={["glass-alert", alertKind === "success" ? "glass-alert-success" : "glass-alert-error"].join(
                      " "
                    )}
                  >
                    {alertText}
                  </div>
                ) : null}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">目标用户</div>
                    <div className="rounded-xl border border-white/60 bg-white/50 px-3 py-2 text-sm text-slate-900 font-medium">
                      {resetDraft.username}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-xs font-medium text-slate-600">用户 ID</div>
                    <div className="rounded-xl border border-white/60 bg-white/50 px-3 py-2 text-xs text-slate-700 font-mono">
                      {resetDraft.user_id}
                    </div>
                  </div>
                  <label className="space-y-1 md:col-span-2">
                    <div className="text-xs font-medium text-slate-600">新密码</div>
                    <div className="flex items-center gap-2">
                      <input
                        value={resetDraft.new_password}
                        onChange={(e) => setResetDraft((p) => ({ ...p, new_password: e.target.value }))}
                        placeholder="8–72 位"
                        className="glass-input text-sm"
                      />
                      <button
                        type="button"
                        onClick={() => setResetDraft((p) => ({ ...p, new_password: generatePassword(18) }))}
                        className="glass-btn glass-btn-secondary text-xs px-3 py-2 whitespace-nowrap"
                      >
                        随机生成
                      </button>
                    </div>
                  </label>
                </div>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <button
                    type="button"
                    onClick={resetPassword}
                    disabled={Boolean(resettingUserId)}
                    className="glass-btn glass-btn-danger whitespace-nowrap"
                  >
                    {resettingUserId ? "重置中…" : "确认重置"}
                  </button>
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(resetDraft.new_password);
                        setAlertKind("success");
                        setAlertText("已复制新密码到剪贴板。");
                      } catch {
                        setErrorText("复制失败：浏览器拒绝剪贴板权限。");
                      }
                    }}
                    className="glass-btn glass-btn-secondary whitespace-nowrap"
                  >
                    复制新密码
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowResetModal(false)}
                    className="glass-btn glass-btn-secondary whitespace-nowrap"
                  >
                    取消
                  </button>
                </div>
              </ModalShell>
            ) : null}

            {selectedUserId ? (
              <ModalShell
                title="管理用户"
                subtitle="角色/状态修改会立即生效；重置密码会直接覆盖旧密码。"
                maxWidthClassName="max-w-2xl"
                onClose={() => setSelectedUserId(null)}
              >
                <>
                  {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}
                  {alertText ? (
                    <div
                      className={[
                        "glass-alert",
                        alertKind === "success" ? "glass-alert-success" : "glass-alert-error",
                      ].join(" ")}
                    >
                      {alertText}
                    </div>
                  ) : null}
                  {!selectedUser ? (
                    <div className="text-sm text-slate-700">
                      目标用户不在当前列表中（可能已翻页或筛选条件变化）。请关闭后重新从列表选择。
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="rounded-xl border border-white/60 bg-white/50 p-3 space-y-2">
                        <div className="flex items-center gap-2">
                          <div className="text-base font-semibold text-slate-900">{selectedUser.username}</div>
                          {me?.id === selectedUser.id ? <Badge tone="slate">当前登录</Badge> : null}
                          <div className="ml-auto flex items-center gap-2">
                            <Badge tone={selectedUser.role === "admin" ? "amber" : "indigo"}>{roleLabel(selectedUser.role)}</Badge>
                            <Badge tone={selectedUser.is_disabled ? "rose" : "emerald"}>{statusLabel(selectedUser.is_disabled)}</Badge>
                          </div>
                        </div>
                        <div className="text-xs text-slate-600 font-mono break-all">{selectedUser.id}</div>
                        <div className="text-[11px] text-slate-500">创建于 {formatCreatedAt(selectedUser.created_at)}</div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="space-y-2">
                          <div className="text-xs font-semibold text-slate-700">角色</div>
                          <select
                            value={selectedUser.role}
                            onChange={(e) => void patchUser(selectedUser.id, { role: e.target.value as UserRole })}
                            disabled={mutatingUserId === selectedUser.id}
                            className="glass-input text-sm"
                          >
                            <option value="user">普通用户</option>
                            <option value="admin">管理员</option>
                          </select>
                          <div className="text-[11px] text-slate-500">角色变更会立即生效；请谨慎操作。</div>
                        </div>

                        <div className="space-y-2">
                          <div className="text-xs font-semibold text-slate-700">状态</div>
                          <button
                            type="button"
                            onClick={() => void patchUser(selectedUser.id, { is_disabled: !selectedUser.is_disabled })}
                            disabled={mutatingUserId === selectedUser.id || me?.id === selectedUser.id}
                            className={[
                              "glass-btn w-full justify-center whitespace-nowrap",
                              selectedUser.is_disabled ? "glass-btn" : "glass-btn-danger",
                            ].join(" ")}
                          >
                            {selectedUser.is_disabled ? "启用用户" : "禁用用户"}
                          </button>
                          {me?.id === selectedUser.id ? (
                            <div className="text-[11px] text-amber-700">不能禁用自己（后端也会拦截）。</div>
                          ) : (
                            <div className="text-[11px] text-slate-500">禁用后用户无法登录。</div>
                          )}
                        </div>
                      </div>

                      <div className="space-y-2">
                        <div className="text-xs font-semibold text-slate-700">密码</div>
                        <button
                          type="button"
                          onClick={() => {
                            openResetPassword(selectedUser);
                            setSelectedUserId(null);
                          }}
                          disabled={resettingUserId === selectedUser.id}
                          className="glass-btn glass-btn-secondary whitespace-nowrap"
                        >
                          重置密码…
                        </button>
                        <div className="text-[11px] text-slate-500">重置密码会直接覆盖旧密码；建议重置后让用户立即修改。</div>
                      </div>
                    </div>
                  )}
                </>
              </ModalShell>
            ) : null}

            {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}
            {alertText ? (
              <div className={["glass-alert", alertKind === "success" ? "glass-alert-success" : "glass-alert-error"].join(" ")}>
                {alertText}
              </div>
            ) : null}

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
                    onClick={applyFilters}
                    disabled={loading}
                    className="glass-btn glass-btn-secondary text-xs px-3 py-1.5"
                  >
                    查询
                  </button>
                  <button
                    type="button"
                    onClick={resetFilters}
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

            {loading ? (
              <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
            ) : items.length === 0 ? (
              <div className="glass-panel p-4 text-sm text-slate-600">无数据</div>
            ) : (
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
                                  onClick={() => {
                                    setErrorText(null);
                                    setAlertText(null);
                                    setSelectedUserId(u.id);
                                  }}
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
                        onChange={(e) => {
                          setPageSize(Number(e.target.value));
                          setActivePage(1);
                        }}
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
                        onClick={handlePrevPage}
                        disabled={loading || activePage <= 1}
                        className="glass-btn glass-btn-secondary text-xs px-3 py-1.5 whitespace-nowrap"
                      >
                        上一页
                      </button>
                      <button
                        type="button"
                        onClick={handleNextPage}
                        disabled={loading || activePage >= totalPages}
                        className="glass-btn glass-btn-secondary text-xs px-3 py-1.5 whitespace-nowrap"
                      >
                        下一页
                      </button>
                    </div>
                  </div>
                </div>
            )}
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}
