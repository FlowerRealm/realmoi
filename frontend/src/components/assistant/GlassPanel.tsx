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
  const baseClass = intensity === "high" ? "glass-panel-strong" : "glass-panel";

  return (
    <div
      className={[
        baseClass,
        "overflow-hidden transition-all duration-300",
        className,
      ].join(" ")}
    >
      <div className={["w-full h-full", innerClassName].join(" ")}>
        {children}
      </div>
    </div>
  );
}
