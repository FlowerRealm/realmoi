"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useMemo } from "react";
import { clearToken } from "@/lib/auth";
import { useSession } from "@/lib/session";

type HeaderMode = "page" | "overlay";

function NavLink({
  href,
  label,
  isActive,
}: {
  href: string;
  label: string;
  isActive: boolean;
}) {
  return (
    <Link
      href={href}
      className={[
        "px-3 py-1.5 rounded-full text-sm font-medium transition-all",
        isActive
          ? "bg-indigo-600 text-white shadow-[0_8px_20px_rgba(79,70,229,0.26)]"
          : "text-slate-700 hover:bg-white/80",
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

export function AppHeader({ mode = "page" }: { mode?: HeaderMode }) {
  const { me } = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const isAssistantRoute = pathname === "/" || pathname.startsWith("/jobs");

  const links = useMemo(() => {
    const base = [
      { href: "/", label: "助手" },
      { href: "/billing", label: "账单" },
      { href: "/settings/codex", label: "设置" },
    ];

    if (me?.role === "admin") {
      base.push(
        { href: "/admin/users", label: "用户" },
        { href: "/admin/pricing", label: "价格" },
        { href: "/admin/upstream-models", label: "上游模型" },
        { href: "/admin/billing", label: "Admin 账单" }
      );
    }
    return base;
  }, [me?.role]);

  const logout = () => {
    clearToken();
    router.replace("/login");
    router.refresh();
  };

  const wrapperClass =
    mode === "overlay"
      ? "fixed top-0 left-0 right-0 z-50"
      : "sticky top-0 z-50";

  const barClass =
    mode === "overlay"
      ? "mx-2 mt-2 md:mx-3 md:mt-3 rounded-2xl border border-slate-200/75 bg-white/86 backdrop-blur-md shadow-[0_10px_24px_rgba(15,23,42,0.08)]"
      : "mx-2 mt-2 md:mx-3 md:mt-3 rounded-2xl border border-slate-200/75 bg-white/90 backdrop-blur-md shadow-[0_10px_24px_rgba(15,23,42,0.08)]";

  return (
    <header className={wrapperClass}>
      <div className={barClass}>
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-4">
          <Link href="/" className="font-semibold tracking-tight text-slate-900 text-base">
            Realm OI
          </Link>

          <nav className="flex flex-wrap items-center gap-1.5 rounded-full bg-slate-100/80 p-1 border border-slate-200/90">
            {links.map((l) => (
              <NavLink
                key={l.href}
                href={l.href}
                label={l.label}
                isActive={
                  l.href === "/"
                    ? isAssistantRoute
                    : pathname === l.href || pathname.startsWith(l.href)
                }
              />
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            {me ? (
              <div className="hidden md:block text-sm text-slate-600 rounded-full px-3 py-1.5 border border-slate-200/90 bg-white/90">
                {me.username} <span className="text-slate-400">({me.role})</span>
              </div>
            ) : null}
            <button
              type="button"
              onClick={logout}
              className="glass-btn glass-btn-secondary"
            >
              退出
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
