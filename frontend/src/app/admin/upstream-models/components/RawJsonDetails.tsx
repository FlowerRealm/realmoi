"use client";

import React from "react";
import type { ChannelFetchResult } from "../upstreamModelsTypes";
import { channelKey } from "../upstreamModelsStorage";
import { formatUpstreamError } from "../upstreamModelsUtils";

type RawJsonDetailsProps = {
  results: ChannelFetchResult[];
};

export function RawJsonDetails({ results }: RawJsonDetailsProps) {
  return (
    <details className="glass-panel p-4">
      <summary className="cursor-pointer text-sm font-semibold text-slate-900">查看各渠道原始 JSON</summary>
      <div className="mt-3 space-y-3">
        {results.map((item) => {
          const key = channelKey(item.channel.channel);
          return (
            <div key={key}>
              <div className="text-xs font-mono text-slate-700 mb-1">
                [{item.channel.display_name}]
                {item.errorText ? (
                  <span className="text-rose-600 ml-2">
                    请求失败：{formatUpstreamError(item.errorText)}
                  </span>
                ) : null}
              </div>
              <pre className="glass-code custom-scrollbar text-xs p-3 overflow-auto max-h-[45vh]">
                {JSON.stringify(item.payload, null, 2)}
              </pre>
            </div>
          );
        })}
      </div>
    </details>
  );
}

