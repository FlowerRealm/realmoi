"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";

export function RequireAdmin({ children }: { children: React.ReactNode }) {
  const { me, loading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    if (!me) return;
    if (me.role !== "admin") router.replace("/");
  }, [loading, me, router]);

  if (loading) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <div className="glass-panel px-4 py-3 text-sm" style={{ color: "var(--semi-color-text-2)" }}>
          加载中…
        </div>
      </div>
    );
  }
  if (!me) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <div className="glass-panel px-4 py-3 text-sm" style={{ color: "var(--semi-color-text-2)" }}>
          未登录
        </div>
      </div>
    );
  }
  if (me.role !== "admin") {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center">
        <div className="glass-panel px-4 py-3 text-sm" style={{ color: "var(--semi-color-text-2)" }}>
          无权限
        </div>
      </div>
    );
  }
  return <>{children}</>;
}
