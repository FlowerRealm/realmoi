"use client";

// AUTO_COMMENT_HEADER_V1: ManageUserModal.tsx
// 说明：Admin Users 页“管理用户”弹窗（角色/状态修改 + 触发重置密码）。

import React from "react";

import type { AlertKind, MeResponse, UserItem, UserPatch, UserRole } from "../adminUsersTypes";
import { formatCreatedAt, roleLabel, statusLabel } from "../adminUsersUtils";
import { Badge } from "./Badge";
import { ModalShell } from "./ModalShell";

export function ManageUserModal({
  errorText,
  alertText,
  alertKind,
  me,
  selectedUser,
  mutating,
  resetting,
  onClose,
  onPatchUser,
  onOpenResetPassword,
}: {
  errorText: string | null;
  alertText: string | null;
  alertKind: AlertKind;
  me: MeResponse | null;
  selectedUser: UserItem | null;
  mutating: boolean;
  resetting: boolean;
  onClose: () => void;
  onPatchUser: (userId: string, patch: UserPatch) => void;
  onOpenResetPassword: (u: UserItem) => void;
}) {
  return (
    <ModalShell
      title="管理用户"
      subtitle="角色/状态修改会立即生效；重置密码会直接覆盖旧密码。"
      maxWidthClassName="max-w-2xl"
      onClose={onClose}
    >
      <>
        {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}
        {alertText ? (
          <div className={["glass-alert", alertKind === "success" ? "glass-alert-success" : "glass-alert-error"].join(" ")}>
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
                  onChange={(e) => void onPatchUser(selectedUser.id, { role: e.target.value as UserRole })}
                  disabled={mutating}
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
                  onClick={() => void onPatchUser(selectedUser.id, { is_disabled: !selectedUser.is_disabled })}
                  disabled={mutating || me?.id === selectedUser.id}
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
                onClick={() => onOpenResetPassword(selectedUser)}
                disabled={resetting}
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
  );
}

