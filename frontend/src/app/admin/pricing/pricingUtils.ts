import type { PricingItem } from "./pricingTypes";

export function parseIntOrNull(v: string): number | null {
  const s = v.trim();
  if (!s) return null;
  const n = Number(s);
  if (!Number.isFinite(n)) return null;
  return Math.trunc(n);
}

export function numberToInputValue(v: number | null): string {
  return v === null ? "" : String(v);
}

export function prefixedModelName(model: string, channel: string): string {
  const channelText = channel.trim() || "未分配";
  return `[${channelText}] ${model}`;
}

export function hasAnyMissingPriceField(row: PricingItem): boolean {
  return (
    row.input_microusd_per_1m_tokens === null ||
    row.cached_input_microusd_per_1m_tokens === null ||
    row.output_microusd_per_1m_tokens === null ||
    row.cached_output_microusd_per_1m_tokens === null
  );
}

export function fmtNullableInt(v: number | null): string {
  if (v === null) return "—";
  return new Intl.NumberFormat().format(v);
}

