"use client";

import React from "react";

type ToggleProps = {
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  label: string;
};

export function Toggle({ checked, disabled, label, onChange }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={[
        "relative inline-flex h-6 w-11 items-center rounded-full border transition-all",
        "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-indigo-500/25",
        disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer",
        checked
          ? "bg-emerald-500/90 border-emerald-200 shadow-[0_10px_25px_rgba(16,185,129,0.25)]"
          : "bg-slate-200/80 border-white/70 shadow-[0_10px_25px_rgba(15,23,42,0.08)]",
      ].join(" ")}
    >
      <span
        aria-hidden="true"
        className={[
          "inline-block h-5 w-5 rounded-full bg-white shadow-[0_8px_18px_rgba(15,23,42,0.18)] transition-transform",
          checked ? "translate-x-5" : "translate-x-0.5",
        ].join(" ")}
      />
    </button>
  );
}

