export type PricingItem = {
  model: string;
  upstream_channel: string;
  currency: string;
  unit: string;
  is_active: boolean;
  input_microusd_per_1m_tokens: number | null;
  cached_input_microusd_per_1m_tokens: number | null;
  output_microusd_per_1m_tokens: number | null;
  cached_output_microusd_per_1m_tokens: number | null;
};

export type UpsertPricingRequest = {
  upstream_channel?: string | null;
  currency?: string;
  is_active?: boolean;
  input_microusd_per_1m_tokens?: number | null;
  cached_input_microusd_per_1m_tokens?: number | null;
  output_microusd_per_1m_tokens?: number | null;
  cached_output_microusd_per_1m_tokens?: number | null;
};

export type UpstreamChannelItem = {
  channel: string;
  display_name: string;
  is_enabled: boolean;
  is_default: boolean;
};

export type LiveModelItem = {
  model: string;
  upstream_channel: string;
};

export type PricingStats = {
  total: number;
  visible: number;
  activeCount: number;
  dirtyCount: number;
  missingActive: number;
  missingAny: number;
  discovered: number;
};

