"use client";

// AUTO_COMMENT_HEADER_V1: useAdminUsersPageController.ts
// 说明：Admin Users 页控制器逻辑（状态 + 数据加载 + 交互动作）。

import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { apiFetch, getErrorMessage } from "@/lib/api";

import type {
  AlertKind,
  CreateUserDraft,
  Filters,
  MeResponse,
  ResetPasswordDraft,
  UserItem,
  UserPatch,
  UsersListResponse,
  UsersStats,
} from "../adminUsersTypes";
import { generatePassword } from "../adminUsersUtils";

const EMPTY_FILTERS: Filters = { q: "", role: "all", status: "all" };
const EMPTY_CREATE_DRAFT: CreateUserDraft = { username: "", password: "", role: "user", is_disabled: false };
const EMPTY_RESET_DRAFT: ResetPasswordDraft = { user_id: "", username: "", new_password: "" };

export type AdminUsersPageViewModel = {
  me: MeResponse | null;
  filtersDraft: Filters;
  setFiltersDraft: Dispatch<SetStateAction<Filters>>;
  filters: Filters;
  activePage: number;
  setActivePage: Dispatch<SetStateAction<number>>;
  pageSize: number;
  setPageSize: Dispatch<SetStateAction<number>>;
  data: UsersListResponse | null;
  items: UserItem[];
  selectedUserId: string | null;
  setSelectedUserId: Dispatch<SetStateAction<string | null>>;
  selectedUser: UserItem | null;
  stats: UsersStats;
  total: number;
  totalPages: number;
  loading: boolean;
  errorText: string | null;
  setErrorText: Dispatch<SetStateAction<string | null>>;
  alertText: string | null;
  setAlertText: Dispatch<SetStateAction<string | null>>;
  alertKind: AlertKind;
  setAlertKind: Dispatch<SetStateAction<AlertKind>>;
  showCreateModal: boolean;
  setShowCreateModal: Dispatch<SetStateAction<boolean>>;
  createDraft: CreateUserDraft;
  setCreateDraft: Dispatch<SetStateAction<CreateUserDraft>>;
  showResetModal: boolean;
  setShowResetModal: Dispatch<SetStateAction<boolean>>;
  resetDraft: ResetPasswordDraft;
  setResetDraft: Dispatch<SetStateAction<ResetPasswordDraft>>;
  mutatingUserId: string | null;
  creatingUser: boolean;
  resettingUserId: string | null;
  load: () => Promise<void>;
  openCreateModal: () => void;
  applyFilters: () => void;
  resetFilters: () => void;
  handlePrevPage: () => void;
  handleNextPage: () => void;
  patchUser: (userId: string, patch: UserPatch) => Promise<void>;
  openResetPassword: (u: UserItem) => void;
  resetPassword: () => Promise<void>;
  createUser: () => Promise<void>;
};

export function useAdminUsersPageController(): AdminUsersPageViewModel {
  // 当前登录用户（用于展示/容错；鉴权由 RequireAuth/RequireAdmin 执行）
  const [me, setMe] = useState<MeResponse | null>(null);

  // filtersDraft = 表单输入；filters = 已提交的筛选条件（触发 load）
  const [filtersDraft, setFiltersDraft] = useState<Filters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);

  // 分页控制
  const [activePage, setActivePage] = useState(1);
  const [pageSize, setPageSize] = useState(20);

  // 列表数据与全局状态
  const [data, setData] = useState<UsersListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [alertText, setAlertText] = useState<string | null>(null);
  const [alertKind, setAlertKind] = useState<AlertKind>("success");

  // 列表选中（用于右侧详情/操作面板）
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null);

  // 创建用户弹窗
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createDraft, setCreateDraft] = useState<CreateUserDraft>(EMPTY_CREATE_DRAFT);

  // 重置密码弹窗
  const [showResetModal, setShowResetModal] = useState(false);
  const [resetDraft, setResetDraft] = useState<ResetPasswordDraft>(EMPTY_RESET_DRAFT);

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
      setErrorText(getErrorMessage(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [activePage, filters.q, filters.role, filters.status, pageSize]);

  useEffect(() => {
    void load();
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
    return { visible: items.length, adminCount, disabledCount } satisfies UsersStats;
  }, [items]);

  const openCreateModal = useCallback(() => {
    setSelectedUserId(null);
    setErrorText(null);
    setAlertText(null);
    setShowCreateModal(true);
  }, []);

  const applyFilters = useCallback(() => {
    setFilters({
      q: filtersDraft.q.trim(),
      role: filtersDraft.role,
      status: filtersDraft.status,
    });
    setActivePage(1);
  }, [filtersDraft.q, filtersDraft.role, filtersDraft.status]);

  const resetFilters = useCallback(() => {
    setFiltersDraft(EMPTY_FILTERS);
    setFilters(EMPTY_FILTERS);
    setActivePage(1);
  }, []);

  const handlePrevPage = useCallback(() => setActivePage((p) => Math.max(1, p - 1)), []);
  const handleNextPage = useCallback(() => setActivePage((p) => Math.min(totalPages, p + 1)), [totalPages]);

  const patchUser = useCallback(
    async (userId: string, patch: UserPatch) => {
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
    },
    [load]
  );

  const openResetPassword = useCallback((u: UserItem) => {
    setErrorText(null);
    setAlertText(null);
    setResetDraft({ user_id: u.id, username: u.username, new_password: generatePassword(18) });
    setShowResetModal(true);
  }, []);

  const resetPassword = useCallback(async () => {
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
  }, [resetDraft.new_password, resetDraft.user_id, resetDraft.username]);

  const createUser = useCallback(async () => {
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
      setCreateDraft(EMPTY_CREATE_DRAFT);
      setFiltersDraft({ q: created.username, role: "all", status: "all" });
      setFilters({ q: created.username, role: "all", status: "all" });
      setActivePage(1);
    } catch (e: unknown) {
      setErrorText(getErrorMessage(e));
    } finally {
      setCreatingUser(false);
    }
  }, [createDraft.is_disabled, createDraft.password, createDraft.role, createDraft.username]);

  return {
    me,
    filtersDraft,
    setFiltersDraft,
    filters,
    activePage,
    setActivePage,
    pageSize,
    setPageSize,
    data,
    items,
    selectedUserId,
    setSelectedUserId,
    selectedUser,
    stats,
    total,
    totalPages,
    loading,
    errorText,
    setErrorText,
    alertText,
    setAlertText,
    alertKind,
    setAlertKind,
    showCreateModal,
    setShowCreateModal,
    createDraft,
    setCreateDraft,
    showResetModal,
    setShowResetModal,
    resetDraft,
    setResetDraft,
    mutatingUserId,
    creatingUser,
    resettingUserId,
    load,
    openCreateModal,
    applyFilters,
    resetFilters,
    handlePrevPage,
    handleNextPage,
    patchUser,
    openResetPassword,
    resetPassword,
    createUser,
  };
}
