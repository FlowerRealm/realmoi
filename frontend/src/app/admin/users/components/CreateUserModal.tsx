"use client";

// AUTO_COMMENT_HEADER_V1: CreateUserModal.tsx
// 说明：Admin Users 页“新建用户”弹窗（表单 + 提交）。

import React from "react";

import type { AlertKind, CreateUserDraft, UserRole } from "../adminUsersTypes";
import { generatePassword } from "../adminUsersUtils";
import { ModalShell } from "./ModalShell";

export function CreateUserModal({
  errorText,
  alertText,
  alertKind,
  creatingUser,
  draft,
  setDraft,
  onClose,
  onSubmit,
}: {
  errorText: string | null;
  alertText: string | null;
  alertKind: AlertKind;
  creatingUser: boolean;
  draft: CreateUserDraft;
  setDraft: React.Dispatch<React.SetStateAction<CreateUserDraft>>;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <ModalShell title="新建用户" subtitle="创建后可在列表中点击“管理”打开用户管理窗口。" onClose={onClose}>
      {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}
      {alertText ? (
        <div className={["glass-alert", alertKind === "success" ? "glass-alert-success" : "glass-alert-error"].join(" ")}>
          {alertText}
        </div>
      ) : null}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="space-y-1">
          <div className="text-xs font-medium text-slate-600">用户名</div>
          <input
            value={draft.username}
            onChange={(e) => setDraft((p) => ({ ...p, username: e.target.value }))}
            placeholder="例如 alice"
            className="glass-input text-sm"
          />
        </label>
        <label className="space-y-1">
          <div className="text-xs font-medium text-slate-600">角色</div>
          <select
            value={draft.role}
            onChange={(e) => setDraft((p) => ({ ...p, role: e.target.value as UserRole }))}
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
              value={draft.password}
              onChange={(e) => setDraft((p) => ({ ...p, password: e.target.value }))}
              placeholder="8–72 位"
              className="glass-input text-sm"
            />
            <button
              type="button"
              onClick={() => setDraft((p) => ({ ...p, password: generatePassword(18) }))}
              className="glass-btn glass-btn-secondary text-xs px-3 py-2 whitespace-nowrap"
            >
              随机生成
            </button>
          </div>
        </label>
        <label className="inline-flex items-center gap-2 text-sm text-slate-700 md:col-span-2">
          <input
            type="checkbox"
            checked={draft.is_disabled}
            onChange={(e) => setDraft((p) => ({ ...p, is_disabled: e.target.checked }))}
          />
          创建后立即禁用
        </label>
      </div>
      <div className="flex items-center gap-2 pt-1">
        <button type="button" onClick={onSubmit} disabled={creatingUser} className="glass-btn whitespace-nowrap">
          {creatingUser ? "创建中…" : "创建用户"}
        </button>
        <button type="button" onClick={onClose} className="glass-btn glass-btn-secondary whitespace-nowrap">
          取消
        </button>
      </div>
    </ModalShell>
  );
}

