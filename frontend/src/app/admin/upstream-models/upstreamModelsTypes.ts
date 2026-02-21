export type UpstreamChannelItem = {
  channel: string;
  display_name: string;
  base_url: string;
  api_key_masked: string;
  has_api_key: boolean;
  models_path: string;
  is_default: boolean;
  is_enabled: boolean;
  source: string;
};

export type UpstreamChannelFormItem = UpstreamChannelItem & {
  api_key_input: string;
};

export type ChannelFetchResult = {
  channel: UpstreamChannelFormItem;
  payload: unknown | null;
  errorText: string | null;
};

export type CachedChannelFetchItem = {
  channel: string;
  payload: unknown | null;
  errorText: string | null;
};

export type CachedModelsSnapshot = {
  ts: number;
  items: CachedChannelFetchItem[];
};

export type PrefixedModelRow = {
  channel: string;
  model: string;
  prefixed: string;
};

export const AUTO_REFRESH_STORAGE_KEY = "realmoi_admin_upstream_auto_refresh_seconds";
export const MODELS_CACHE_STORAGE_KEY = "realmoi_admin_upstream_models_cache_v1";
export const DEFAULT_AUTO_REFRESH_SECONDS = 180;

