"use client";

import Link from "next/link";
import React from "react";

export function AuthCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: React.ReactNode;
  footer: React.ReactNode;
}) {
  return (
    <div className="max-w-md w-full mx-auto">
      <div className="glass-panel-strong p-7 md:p-8">
        <h1
          className="text-2xl font-semibold tracking-tight"
          style={{ color: "var(--text-primary)" }}
        >
          {title}
        </h1>
        <div className="mt-6">{children}</div>
        <div className="mt-6 text-sm" style={{ color: "var(--text-secondary)" }}>
          {footer}
        </div>
      </div>
      <div className="mt-4 text-xs text-center" style={{ color: "var(--text-muted)" }}>
        <Link href="https://github.com/" className="underline underline-offset-4">
          realmoi
        </Link>{" "}
        MVP
      </div>
    </div>
  );
}
