"use client";

import React from "react";

export function Label({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="text-[11px] font-black uppercase tracking-[0.14em]"
      style={{ color: "var(--semi-color-text-2)" }}
    >
      {children}
    </div>
  );
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={[
        "glass-input text-sm font-medium",
        props.className || "",
      ].join(" ")}
    />
  );
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={[
        "glass-input text-sm font-medium min-h-24",
        props.className || "",
      ].join(" ")}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      {...props}
      className={[
        "glass-input text-sm font-medium",
        props.className || "",
      ].join(" ")}
    />
  );
}

export function Button({
  children,
  variant = "primary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const cls =
    variant === "danger"
      ? "glass-btn glass-btn-danger"
      : variant === "secondary"
      ? "glass-btn glass-btn-secondary"
      : "glass-btn";
  return (
    <button
      {...props}
      className={[
        "transition-all disabled:opacity-50 disabled:cursor-not-allowed",
        cls,
        props.className || "",
      ].join(" ")}
    >
      {children}
    </button>
  );
}
