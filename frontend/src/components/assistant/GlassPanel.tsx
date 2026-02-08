"use client";

import React from "react";

export function GlassPanel({
  children,
  className = "",
  innerClassName = "",
  intensity = "medium",
}: {
  children: React.ReactNode;
  className?: string;
  innerClassName?: string;
  intensity?: "low" | "medium" | "high";
}) {
  const intensities: Record<string, string> = {
    low: "bg-white/74 border-slate-200/70 backdrop-blur-sm",
    medium: "bg-white/82 border-slate-200/80 backdrop-blur-md",
    high: "bg-white/90 border-slate-200/90 backdrop-blur-lg",
  };

  return (
    <div
      className={[
        intensities[intensity] ?? intensities.medium,
        "border border-solid",
        "shadow-[0_10px_28px_rgba(15,23,42,0.08)]",
        "rounded-2xl overflow-hidden transition-all duration-300",
        className,
      ].join(" ")}
    >
      <div className={["w-full h-full", innerClassName].join(" ")}>
        {children}
      </div>
    </div>
  );
}
