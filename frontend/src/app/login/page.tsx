"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Mail, Lock } from "lucide-react";
import { apiFetch, getErrorMessage } from "@/lib/api";
import { setToken } from "@/lib/auth";
import { useSession } from "@/lib/session";
import { AuthCard } from "@/components/AuthCard";
import { Button, Input, Label } from "@/components/Form";

export default function LoginPage() {
  const router = useRouter();
  const { refresh } = useSession();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError(null);
    setLoading(true);
    try {
      const data = await apiFetch<{
        access_token: string;
        token_type: string;
        user: { id: string; username: string; role: string };
      }>("/auth/login", {
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
    <div className="min-h-[100dvh] flex items-center justify-center px-4 py-10">
      <AuthCard
        title="登录"
        footer={
          <div className="flex items-center justify-between gap-4">
            <span>
              没有账户？{" "}
              <Link
                href="/signup"
                className="underline underline-offset-4"
                style={{ color: "var(--accent)" }}
              >
                注册
              </Link>
            </span>
            <button
              type="button"
              className="text-xs underline underline-offset-4"
              style={{ color: "var(--text-muted)" }}
              onClick={() => window.alert("暂无找回密码功能")}
            >
              忘记密码
            </button>
          </div>
        }
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="space-y-3"
        >
          <div className="space-y-2">
            <Label>用户名或邮箱</Label>
            <div className="relative">
              <Mail
                size={16}
                className="realm-icon-muted absolute left-3 top-1/2 -translate-y-1/2"
                aria-hidden="true"
              />
              <Input
                name="username"
                autoComplete="username"
                placeholder="例如：linche / linche@example.com"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="!pl-10"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label>密码</Label>
            <div className="relative">
              <Lock
                size={16}
                className="realm-icon-muted absolute left-3 top-1/2 -translate-y-1/2"
                aria-hidden="true"
              />
              <Input
                name="password"
                type="password"
                autoComplete="current-password"
                placeholder="请输入密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="!pl-10"
              />
            </div>
          </div>

          {error ? (
            <div className="text-sm px-1" style={{ color: "var(--danger)" }}>
              {error}
            </div>
          ) : null}

          <div className="pt-2">
            <Button
              type="submit"
              disabled={loading}
              className="w-full !rounded-full"
            >
              {loading ? "登录中…" : "继续"}
            </Button>
          </div>
        </form>
      </AuthCard>
    </div>
  );
}
