"use client";

// AUTO_COMMENT_HEADER_V1: ResetPasswordModal.tsx
// 说明：Admin Users 页“重置密码”弹窗（含复制到剪贴板）。

import React from "react";

import type { AlertKind, ResetPasswordDraft } from "../adminUsersTypes";
import { generatePassword } from "../adminUsersUtils";
import { ModalShell } from "./ModalShell";

export function ResetPasswordModal({
  errorText,
  setErrorText,
  alertText,
  setAlertText,
  alertKind,
  setAlertKind,
  resetting,
  draft,
  setDraft,
  onClose,
  onResetPassword,
}: {
  errorText: string | null;
  setErrorText: React.Dispatch<React.SetStateAction<string | null>>;
  alertText: string | null;
  setAlertText: React.Dispatch<React.SetStateAction<string | null>>;
  alertKind: AlertKind;
  setAlertKind: React.Dispatch<React.SetStateAction<AlertKind>>;
  resetting: boolean;
  draft: ResetPasswordDraft;
  setDraft: React.Dispatch<React.SetStateAction<ResetPasswordDraft>>;
  onClose: () => void;
  onResetPassword: () => void;
}) {
  return (
    <ModalShell
      title="重置密码"
      subtitle="重置后请把新密码安全地交付给用户（或让用户立即修改）。"
      onClose={onClose}
    >
      {errorText ? <div className="glass-alert glass-alert-error">{errorText}</div> : null}
      {alertText ? (
        <div className={["glass-alert", alertKind === "success" ? "glass-alert-success" : "glass-alert-error"].join(" ")}>
          {alertText}
        </div>
      ) : null}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-600">目标用户</div>
          <div className="rounded-xl border border-white/60 bg-white/50 px-3 py-2 text-sm text-slate-900 font-medium">
            {draft.username}
          </div>
        </div>
        <div className="space-y-1">
          <div className="text-xs font-medium text-slate-600">用户 ID</div>
          <div className="rounded-xl border border-white/60 bg-white/50 px-3 py-2 text-xs text-slate-700 font-mono">
            {draft.user_id}
          </div>
        </div>
        <label className="space-y-1 md:col-span-2">
          <div className="text-xs font-medium text-slate-600">新密码</div>
          <div className="flex items-center gap-2">
            <input
              value={draft.new_password}
              onChange={(e) => setDraft((p) => ({ ...p, new_password: e.target.value }))}
              placeholder="8–72 位"
              className="glass-input text-sm"
            />
            <button
              type="button"
              onClick={() => setDraft((p) => ({ ...p, new_password: generatePassword(18) }))}
              className="glass-btn glass-btn-secondary text-xs px-3 py-2 whitespace-nowrap"
            >
              随机生成
            </button>
          </div>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button type="button" onClick={onResetPassword} disabled={resetting} className="glass-btn glass-btn-danger whitespace-nowrap">
          {resetting ? "重置中…" : "确认重置"}
        </button>
        <button
          type="button"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(draft.new_password);
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
        <button type="button" onClick={onClose} className="glass-btn glass-btn-secondary whitespace-nowrap">
          取消
        </button>
      </div>
    </ModalShell>
  );
}

