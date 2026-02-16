"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import type { ModelItem, PromptData, TestCase } from "./types";

type ModelChoice = {
  value: string;
  model: string;
  channel: string;
};

const REASONING_EFFORT_OPTIONS: Array<{ value: "low" | "medium" | "high" | "xhigh"; label: string }> = [
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
  { value: "xhigh", label: "xhigh" },
];

export function LiquidInput({
  onSend,
  onToggleExpand,
  models,
}: {
  onSend: (data: PromptData) => void;
  onToggleExpand?: (isExpanded: boolean) => void;
  models: ModelItem[];
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [text, setText] = useState("");
  const [code, setCode] = useState("");
  const [testCases, setTestCases] = useState<TestCase[]>([{ input: "", output: "" }]);
  const [activeTab, setActiveTab] = useState<"prompt" | "code" | "data" | "settings">("prompt");

  const [modelValue, setModelValue] = useState<string>("");
  const [reasoningEffort, setReasoningEffort] = useState<"low" | "medium" | "high" | "xhigh">("medium");
  const [timeLimitMs, setTimeLimitMs] = useState<string>("2000");
  const [memoryLimitMb, setMemoryLimitMb] = useState<string>("1024");

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    onToggleExpand?.(isExpanded);
  }, [isExpanded, onToggleExpand]);

  const choices = useMemo<ModelChoice[]>(() => {
    const dedup = new Map<string, ModelChoice>();
    models.forEach((item) => {
      const channel = String(item.upstream_channel || "").trim();
      const model = String(item.model || "").trim();
      if (!channel || !model) return;
      const value = `${channel}::${model}`;
      if (!dedup.has(value)) {
        dedup.set(value, { value, channel, model });
      }
    });
    return Array.from(dedup.values()).sort((a, b) => {
      if (a.channel.toLowerCase() === b.channel.toLowerCase()) {
        return a.model.localeCompare(b.model);
      }
      return a.channel.localeCompare(b.channel);
    });
  }, [models]);

  const resolvedChoice = useMemo<ModelChoice | null>(() => {
    if (choices.length === 0) return null;
    const existed = choices.find((item) => item.value === modelValue);
    return existed || choices[0];
  }, [choices, modelValue]);

  const handleFocus = () => setIsExpanded(true);

  const handleSend = () => {
    if (!text.trim()) return;
    if (!resolvedChoice) return;

    onSend({
      problemDescription: text,
      code,
      testCases: testCases.filter((tc) => tc.input.trim() || tc.output.trim()),
      model: resolvedChoice.model,
      upstreamChannel: resolvedChoice.channel,
      reasoningEffort,
      timeLimitMs: Number(timeLimitMs || "2000"),
      memoryLimitMb: Number(memoryLimitMb || "1024"),
    });
  };

  const addTestCase = () => setTestCases((prev) => [...prev, { input: "", output: "" }]);

  const updateTestCase = (index: number, field: keyof TestCase, value: string) => {
    setTestCases((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  const removeTestCase = (index: number) => {
    setTestCases((prev) => {
      if (prev.length <= 1) return prev;
      return prev.filter((_, i) => i !== index);
    });
  };

  return (
    <div
      className={[
        "relative mx-auto transition-all duration-700 ease-[cubic-bezier(0.23,1,0.32,1)]",
        "glass-panel-strong rounded-3xl",
        isExpanded ? "w-full h-[78vh] md:h-[620px] p-4 md:p-6" : "w-[92vw] max-w-[560px] h-[64px] p-2",
        "flex flex-col",
      ].join(" ")}
    >
      <div className="flex-1 flex flex-col overflow-hidden relative">
        {!isExpanded ? (
          <div className="flex items-center w-full h-full px-4 md:px-5 group cursor-pointer" onClick={handleFocus}>
            <div className="w-1.5 h-1.5 rounded-full bg-indigo-500 mr-4 opacity-40 group-hover:scale-150 transition-transform duration-500" />
            <input
              type="text"
              readOnly
              placeholder="在此输入您的调题需求..."
              className="bg-transparent border-none outline-none text-slate-500 w-full cursor-pointer text-sm md:text-base"
            />
            <div className="icon-wrap w-10 h-10 shrink-0 rounded-xl bg-indigo-500/10 group-hover:bg-indigo-600 group-hover:text-white transition-all duration-300 shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.6}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14m-4-4 4 4-4 4" />
              </svg>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-1 mb-4 md:mb-5 bg-slate-50/80 p-1 rounded-2xl self-center">
              {(["prompt", "code", "data", "settings"] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={[
                    "px-4 md:px-5 py-2 rounded-lg text-sm font-medium transition-all duration-200",
                    activeTab === tab ? "bg-slate-200/80 text-slate-900" : "text-slate-500 hover:text-slate-700",
                  ].join(" ")}
                >
                  {tab === "prompt" ? "题面" : tab === "code" ? "源码" : tab === "data" ? "数据" : "参数"}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto pr-1 custom-scrollbar">
              <div className="w-full h-full flex flex-col items-center">
                {activeTab === "prompt" ? (
                  <textarea
                    autoFocus
                    className="realm-field flex-1 w-full text-sm md:text-base p-4 md:p-5"
                    placeholder="粘贴题面内容或描述逻辑..."
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                ) : null}

                {activeTab === "code" ? (
                  <textarea
                    className="realm-field flex-1 w-full font-mono text-xs md:text-sm p-4 md:p-5"
                    placeholder="// 在此粘贴 C++ 代码..."
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                ) : null}

                {activeTab === "data" ? (
                  <div className="w-full space-y-4 pb-2 animate-in fade-in zoom-in-95 duration-500">
                    <div className="grid grid-cols-1 gap-4">
                      {testCases.map((tc, index) => (
                        <div
                          key={index}
                          className="group relative flex flex-col md:flex-row overflow-hidden rounded-2xl glass-panel transition-opacity"
                        >
                          <div className="flex-1 p-4 md:p-5 flex flex-col gap-2">
                            <span className="text-xs font-semibold text-slate-500">
                              Input #{index + 1}
                            </span>
                            <textarea
                              className="w-full bg-transparent border-none rounded-none text-xs md:text-sm font-mono text-slate-700 outline-none min-h-[80px] md:min-h-[110px] leading-relaxed"
                              value={tc.input}
                              onChange={(e) => updateTestCase(index, "input", e.target.value)}
                              placeholder="输入..."
                            />
                          </div>
                          <div className="flex-1 p-4 md:p-5 flex flex-col gap-2 bg-slate-50/60">
                            <span className="text-xs font-semibold text-slate-500">
                              Expected
                            </span>
                            <textarea
                              className="w-full bg-transparent border-none rounded-none text-xs md:text-sm font-mono text-slate-700 outline-none min-h-[80px] md:min-h-[110px] leading-relaxed"
                              value={tc.output}
                              onChange={(e) => updateTestCase(index, "output", e.target.value)}
                              placeholder="预期（可留空：仅运行不比对）..."
                            />
                          </div>
                          {testCases.length > 1 ? (
                            <button
                              onClick={() => removeTestCase(index)}
                              className="icon-wrap absolute top-3 right-3 w-7 h-7 bg-slate-50/80 shadow-sm rounded-full text-slate-400 hover:text-red-500 opacity-100 md:opacity-0 md:group-hover:opacity-100 transition-opacity"
                              aria-label="删除样例"
                            >
                              <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.6}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="m6 6 12 12M6 18 18 6" />
                              </svg>
                            </button>
                          ) : null}
                        </div>
                      ))}
                    </div>
                    <button onClick={addTestCase} className="w-full py-3 border border-dashed border-indigo-200 rounded-2xl text-sm font-medium text-slate-500 hover:text-indigo-600 transition-all">
                      + 添加样例
                    </button>
                  </div>
                ) : null}

                {activeTab === "settings" ? (
                  <div className="w-full space-y-4 pb-2 animate-in fade-in zoom-in-95 duration-500">
                    <div className="glass-panel p-4 md:p-5">
                      <div className="text-sm font-semibold text-slate-600 mb-3">
                        后端参数
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label className="space-y-1">
                          <div className="text-xs font-semibold text-slate-500">
                            Model
                          </div>
                          <select
                            className="realm-field text-sm px-3 py-2"
                            value={resolvedChoice?.value || ""}
                            onChange={(e) => setModelValue(e.target.value)}
                          >
                            {choices.map((item) => (
                              <option key={item.value} value={item.value}>
                                [{item.channel}] {item.model}
                              </option>
                            ))}
                          </select>
                          {choices.length === 0 ? (
                            <div className="text-xs text-slate-500">
                              暂无可用模型（请检查渠道配置或稍后刷新）。
                            </div>
                          ) : null}
                        </label>

                        <label className="space-y-1">
                          <div className="text-xs font-semibold text-slate-500">
                            思考量
                          </div>
                          <select
                            className="realm-field text-sm px-3 py-2"
                            value={reasoningEffort}
                            onChange={(e) => setReasoningEffort(e.target.value as "low" | "medium" | "high" | "xhigh")}
                          >
                            {REASONING_EFFORT_OPTIONS.map((item) => (
                              <option key={item.value} value={item.value}>
                                {item.label}
                              </option>
                            ))}
                          </select>
                          <div className="text-[11px] text-slate-500">
                            适用于 GPT 系列模型；部分模型可能不支持 xhigh。
                          </div>
                        </label>

                        <label className="space-y-1">
                          <div className="text-xs font-semibold text-slate-500">
                            Time Limit (ms)
                          </div>
                          <input
                            type="number"
                            inputMode="numeric"
                            className="realm-field text-sm px-3 py-2"
                            value={timeLimitMs}
                            onChange={(e) => setTimeLimitMs(e.target.value)}
                          />
                        </label>

                        <label className="space-y-1">
                          <div className="text-xs font-semibold text-slate-500">
                            Memory (MB)
                          </div>
                          <input
                            type="number"
                            inputMode="numeric"
                            className="realm-field text-sm px-3 py-2"
                            value={memoryLimitMb}
                            onChange={(e) => setMemoryLimitMb(e.target.value)}
                          />
                        </label>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="flex items-center justify-between mt-4 md:mt-6 pt-4 md:pt-5 border-t border-slate-100/50 shrink-0">
              <button
                onClick={() => fileInputRef.current?.click()}
                className="icon-wrap w-10 h-10 md:w-11 md:h-11 rounded-xl bg-slate-50/80 hover:opacity-90 transition-opacity text-slate-600 shadow-sm"
                title={activeTab === "code" ? "导入代码" : "导入文本"}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
                  />
                </svg>
              </button>
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  const reader = new FileReader();
                  reader.onload = (ev) => {
                    const res = (ev.target?.result as string) ?? "";
                    if (activeTab === "code") setCode(res);
                    else setText((prev) => prev + "\n" + res);
                  };
                  reader.readAsText(file);
                }}
              />

              <div className="flex items-center gap-4 md:gap-6">
                <button
                  onClick={() => setIsExpanded(false)}
                  className="text-sm text-slate-500 hover:text-slate-700 font-medium"
                >
                  取消
                </button>
                <button
                  onClick={handleSend}
                  disabled={!text.trim() || !resolvedChoice}
                  className="glass-btn px-6 md:px-8 py-2.5 md:py-3 rounded-xl text-sm font-medium disabled:opacity-20"
                >
                  开始调试
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
