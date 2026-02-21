"use client";

// AUTO_COMMENT_HEADER_V1: ModalShell.tsx
// 说明：Admin Users 页的 Modal 容器（统一标题/关闭按钮/遮罩层）。

import React from "react";

export function ModalShell({
  title,
  subtitle,
  onClose,
  children,
  maxWidthClassName = "max-w-3xl",
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: React.ReactNode;
  maxWidthClassName?: string;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/55 backdrop-blur-[2px] px-4"
      onClick={onClose}
    >
      <div
        className={[
          "glass-panel-strong w-full p-5 space-y-4 bg-white/95 border border-slate-200 shadow-[0_24px_70px_rgba(15,23,42,0.28)]",
          maxWidthClassName,
        ].join(" ")}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="flex items-center gap-2">
          <div>
            <div className="text-base font-semibold text-slate-900">{title}</div>
            {subtitle ? <div className="text-xs text-slate-500 mt-1">{subtitle}</div> : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-auto text-xs px-2.5 py-1.5 rounded-md border border-slate-200 bg-white/80 text-slate-600 hover:bg-white whitespace-nowrap"
          >
            关闭
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

