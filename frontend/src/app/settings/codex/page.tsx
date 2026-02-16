"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAuth } from "@/components/RequireAuth";
import { apiFetch, getErrorMessage } from "@/lib/api";

type CodexSettingsResponse = {
  user_id: string;
  user_overrides_toml: string;
  effective_config_toml: string;
  allowed_keys: string[];
  updated_at: string | null;
};

export default function CodexSettingsPage() {
  const [data, setData] = useState<CodexSettingsResponse | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [okText, setOkText] = useState<string | null>(null);

  const allowedKeysText = useMemo(() => (data?.allowed_keys || []).join(", "), [data?.allowed_keys]);

  const load = useCallback(async () => {
    setLoading(true);
    setErrorText(null);
    setOkText(null);
    try {
      const d = await apiFetch<CodexSettingsResponse>("/settings/codex");
      setData(d);
      setDraft(d.user_overrides_toml || "");
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setData(null);
      setDraft("");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setErrorText(null);
    setOkText(null);
    try {
      const d = await apiFetch<CodexSettingsResponse>("/settings/codex", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_overrides_toml: draft }),
      });
      setData(d);
      setDraft(d.user_overrides_toml || "");
      setOkText("已保存");
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
    } finally {
      setSaving(false);
    }
  };

  return (
    <RequireAuth>
      <div className="relative w-full min-h-[100dvh] box-border pt-14 overflow-x-hidden">
        <AppHeader mode="overlay" />
        <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
          <div className="glass-panel-strong p-4 md:p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-center">
              <div className="min-w-0">
                <h1 className="text-xl font-semibold text-slate-900">Codex 设置</h1>
                <p className="text-xs text-slate-500 mt-1">管理个人 overrides 与最终生效配置</p>
              </div>
              <div className="flex w-full items-center justify-end gap-2 md:w-auto md:ml-auto">
                <button
                  type="button"
                  onClick={load}
                  className="glass-btn glass-btn-secondary"
                  disabled={loading || saving}
                >
                  重新加载
                </button>
                <button
                  type="button"
                  onClick={save}
                  className="glass-btn"
                  disabled={loading || saving}
                >
                  {saving ? "保存中…" : "保存"}
                </button>
              </div>
            </div>
          </div>

          {errorText ? (
            <div className="glass-alert glass-alert-error">{errorText}</div>
          ) : null}
          {okText ? <div className="glass-alert glass-alert-success">{okText}</div> : null}

          {loading ? (
            <div className="glass-panel p-4 text-sm text-slate-600">加载中…</div>
          ) : !data ? (
            <div className="glass-panel p-4 text-sm text-slate-600">无数据</div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="glass-panel p-4 md:p-5">
                <div className="text-xs uppercase tracking-[0.2em] text-slate-500 font-black">allowed_keys</div>
                <div className="mt-2 text-xs font-mono text-slate-900 break-words">{allowedKeysText || "-"}</div>
                <div className="mt-4 text-sm font-semibold text-slate-900">user_overrides_toml</div>
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  className="glass-input glass-code mt-2 h-[50vh] text-xs"
                  spellCheck={false}
                />
                <div className="mt-2 text-xs text-slate-500">updated_at: {data.updated_at || "-"}</div>
              </div>

              <div className="glass-panel p-4 md:p-5">
                <div className="text-sm font-semibold text-slate-900">effective_config_toml（只读）</div>
                <pre className="glass-code custom-scrollbar mt-2 w-full h-[60vh] overflow-auto px-3 py-2 text-xs whitespace-pre-wrap">
                  {data.effective_config_toml || ""}
                </pre>
                <div className="mt-2 text-xs text-slate-500">user_id: {data.user_id}</div>
              </div>
            </div>
          )}
        </main>
      </div>
    </RequireAuth>
  );
}
