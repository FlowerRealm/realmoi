/**
 * Billing page helper utilities (date range, formatting, localStorage).
 */

import type { BillingFilters } from "./billingTypes";

export const FILTER_STORAGE_KEY = "realmoi.billing.filters.v1";
export const LIMIT_OPTIONS = [20, 50, 100, 200];

export function toDateInputValue(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function daysShift(base: Date, offset: number): Date {
  const next = new Date(base);
  next.setDate(next.getDate() + offset);
  return next;
}

export function clampLimit(limit: number): number {
  return LIMIT_OPTIONS.includes(limit) ? limit : 50;
}

export function buildDefaultFilters(): BillingFilters {
  const today = new Date();
  return {
    start: toDateInputValue(daysShift(today, -6)),
    end: toDateInputValue(today),
    limit: 50,
  };
}

export function parseStoredFilters(raw: string | null): BillingFilters | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const start =
      typeof (parsed as { start?: unknown }).start === "string"
        ? (parsed as { start: string }).start
        : "";
    const end =
      typeof (parsed as { end?: unknown }).end === "string"
        ? (parsed as { end: string }).end
        : "";
    const limitRaw = (parsed as { limit?: unknown }).limit;
    const limit = typeof limitRaw === "number" ? limitRaw : Number(limitRaw);
    if (!start || !end || !Number.isFinite(limit)) return null;
    return {
      start,
      end,
      limit: clampLimit(limit),
    };
  } catch {
    return null;
  }
}

export function fmtInt(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function fmtPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function fmtDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function fmtUsd(amount: string | null, currency: string = "USD"): string {
  if (!amount) return "未定价";
  return `${currency} ${amount}`;
}

export function applyRangePreset(
  preset: "today" | "yesterday" | "last7days",
  limit: number
): BillingFilters {
  const today = new Date();
  const todayText = toDateInputValue(today);
  if (preset === "today") {
    return { start: todayText, end: todayText, limit };
  }
  if (preset === "yesterday") {
    const yesterday = toDateInputValue(daysShift(today, -1));
    return { start: yesterday, end: yesterday, limit };
  }
  return {
    start: toDateInputValue(daysShift(today, -6)),
    end: todayText,
    limit,
  };
}

