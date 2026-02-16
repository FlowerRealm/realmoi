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
          ? "text-[color:var(--text-primary)] bg-[color:var(--surface-2)]"
          : "text-[color:var(--text-secondary)] hover:opacity-85",
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
    "mx-2 mt-2 md:mx-3 md:mt-3 rounded-2xl shadow-[var(--shadow-soft)]";

  return (
    <header className={wrapperClass} data-app-header="1">
      <div
        className={barClass}
        style={{
          background: "color-mix(in hsl, var(--surface) 78%, white)",
        }}
      >
        <div className="mx-auto max-w-6xl px-5 py-3 flex items-center gap-4">
          <Link
            href="/"
            className="font-semibold tracking-tight text-base"
            style={{ color: "var(--text-primary)" }}
          >
            Realm OI
          </Link>

          <nav
            className="flex flex-1 min-w-0 flex-nowrap items-center gap-1.5 rounded-full p-1 overflow-x-auto whitespace-nowrap custom-scrollbar"
            style={{
              background: "var(--surface)",
            }}
            aria-label="主导航"
          >
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
              <div
                className="hidden md:block text-sm rounded-full px-3 py-1.5"
                style={{
                  color: "var(--text-secondary)",
                  background: "var(--surface)",
                }}
              >
                {me.username}{" "}
                <span style={{ color: "var(--text-muted)" }}>
                  ({me.role})
                </span>
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
