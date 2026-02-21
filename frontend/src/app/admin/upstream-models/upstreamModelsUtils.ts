import type { UpstreamChannelItem, UpstreamChannelFormItem } from "./upstreamModelsTypes";

export function prefixedModelName(channelDisplayName: string, modelName: string): string {
  return `[${channelDisplayName}] ${modelName}`;
}

export function isRecommendedModelName(modelName: string): boolean {
  const text = modelName.toLowerCase();
  return /(gpt|o\\d|codex|claude|gemini|deepseek|qwen|glm|llama|yi|moonshot|doubao|kimi)/.test(
    text
  );
}

export function formatUpstreamError(message: string): string {
  const text = message.trim();
  if (!text) return "请求失败";
  if (text.includes("upstream_unavailable")) {
    return "上游服务不可达，请检查该渠道的 Base URL、网络连通性或代理配置。";
  }
  if (text.includes("upstream_unauthorized")) {
    return "上游鉴权失败，请检查该渠道 API Key 是否正确。";
  }
  if (text.includes("Unknown upstream channel")) {
    return "渠道不存在，请检查 upstream_channel 配置。";
  }
  if (text.includes("Disabled upstream channel")) {
    return "该渠道已被禁用，请启用后再拉取模型。";
  }
  return text;
}

export function normalizeModelsPath(path: string): string {
  const text = path.trim();
  if (!text) return "/v1/models";
  if (text.startsWith("/")) return text;
  return `/${text}`;
}

export function withFormState(items: UpstreamChannelItem[]): UpstreamChannelFormItem[] {
  return items.map((item) => ({ ...item, api_key_input: "" }));
}

