/**
 * Billing domain types shared by the billing page UI.
 *
 * Keeping these in a separate module reduces the size/complexity of `page.tsx`.
 */

export type BillingFilters = {
  start: string;
  end: string;
  limit: number;
};

export type BillingCostSummary = {
  currency: string;
  cost_microusd: number | null;
  amount: string | null;
  priced_records: number;
  unpriced_records: number;
};

export type BillingWindow = {
  window: string;
  since: string;
  until: string;
  records: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cache_ratio: number;
  cost: BillingCostSummary;
};

export type BillingWindowsResponse = {
  now: string;
  query: {
    start: string;
    end: string;
  };
  windows: BillingWindow[];
};

export type BillingDailyPoint = {
  day: string;
  records: number;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cache_ratio: number;
  cost: BillingCostSummary;
};

export type BillingDailyResponse = {
  query: {
    start: string;
    end: string;
  };
  points: BillingDailyPoint[];
};

export type BillingEventCost = {
  currency: string;
  cost_microusd: number;
  amount: string;
};

export type BillingEvent = {
  id: string;
  created_at: string;
  job_id: string;
  stage: string;
  model: string;
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  cached_output_tokens: number;
  total_tokens: number;
  cached_tokens: number;
  cost: BillingEventCost | null;
};

export type BillingEventsResponse = {
  query: {
    start: string;
    end: string;
    limit: number;
    before_id: string | null;
  };
  events: BillingEvent[];
  next_before_id: string | null;
};

export type BillingPricingSnapshot = {
  currency: string;
  input_microusd_per_1m_tokens: number;
  cached_input_microusd_per_1m_tokens: number;
  output_microusd_per_1m_tokens: number;
  cached_output_microusd_per_1m_tokens: number;
};

export type BillingCostBreakdownLine = {
  tokens: number;
  price_microusd_per_1m_tokens: number;
  cost_microusd: number;
  amount: string;
};

export type BillingCostBreakdown = {
  non_cached_input: BillingCostBreakdownLine;
  non_cached_output: BillingCostBreakdownLine;
  cached_input: BillingCostBreakdownLine;
  cached_output: BillingCostBreakdownLine;
  computed_total_microusd: number;
  computed_total_amount: string;
};

export type BillingEventDetail = BillingEvent & {
  pricing: BillingPricingSnapshot | null;
  breakdown: BillingCostBreakdown | null;
};

