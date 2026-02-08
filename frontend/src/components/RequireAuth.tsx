"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { me, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !me) router.replace("/login");
  }, [loading, me, router]);

  if (loading) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <div className="glass-panel px-4 py-3 text-sm text-slate-600">加载中…</div>
      </div>
    );
  }
  if (!me) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <div className="glass-panel px-4 py-3 text-sm text-slate-600">未登录</div>
      </div>
    );
  }
  return <>{children}</>;
}
