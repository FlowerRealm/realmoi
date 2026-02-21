// AUTO_COMMENT_HEADER_V1: adminUsersUtils.ts
// 说明：Admin Users 页的局部工具函数（拆分自原 page.tsx）。

import type { UserRole } from "./adminUsersTypes";

export function formatCreatedAt(raw: string): string {
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleString();
}

export function roleLabel(role: UserRole): string {
  return role === "admin" ? "管理员" : "普通用户";
}

export function statusLabel(isDisabled: boolean): string {
  return isDisabled ? "已禁用" : "已启用";
}

export function generatePassword(length = 18): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
  const out: string[] = [];
  for (let i = 0; i < length; i++) {
    out.push(alphabet[Math.floor(Math.random() * alphabet.length)]);
  }
  return out.join("");
}

