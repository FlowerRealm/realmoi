"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard } from "@/components/AuthCard";
import { Button, Input, Label } from "@/components/Form";
import { apiFetch, getErrorMessage } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { useSession } from "@/lib/session";
import { FluidBackground } from "@/components/assistant/FluidBackground";

export default function SignupPage() {
  const router = useRouter();
  const { refresh } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch<{
        access_token: string;
        token_type: string;
        user: { id: string; username: string; role: string };
      }>("/auth/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      setToken(data.access_token);
      await refresh();
      router.replace("/");
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative w-screen h-[100dvh] box-border overflow-hidden text-slate-800 selection:bg-indigo-500/20 flex items-center justify-center px-4 py-10">
      <FluidBackground />
      <div className="w-full max-w-md relative z-10">
        <div className="text-center mb-6">
          <h1 className="text-4xl font-light tracking-tight text-slate-800">
            Realm <span className="font-semibold text-indigo-600">OI</span>
          </h1>
          <p className="text-sm text-slate-500 mt-1">创建账号，开启你的空间化调题流程</p>
        </div>
        <AuthCard
          title="注册"
          footer={
            <div className="flex items-center justify-between">
              <span>已有账号？</span>
              <Link href="/login" className="underline underline-offset-4 hover:text-indigo-600">
                去登录
              </Link>
            </div>
          }
        >
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label>用户名（3-32，字母数字 _ . -）</Label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
            </div>
            <div className="space-y-1.5">
              <Label>密码（8-72）</Label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            {error ? <div className="glass-alert glass-alert-error">{error}</div> : null}
            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "注册中…" : "注册"}
            </Button>
          </form>
        </AuthCard>
      </div>
    </div>
  );
}
