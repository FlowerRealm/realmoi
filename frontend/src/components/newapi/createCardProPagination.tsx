"use client";

import React from "react";
import { Pagination } from "@douyinfe/semi-ui";

export function createCardProPagination({
  currentPage,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOpts = [10, 20, 50, 100],
  showSizeChanger = true,
}: {
  currentPage: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  pageSizeOpts?: number[];
  showSizeChanger?: boolean;
}) {
  if (!total || total <= 0) return null;

  const start = (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, total);
  const totalText = `显示第 ${start} 条 - 第 ${end} 条，共 ${total} 条`;

  return (
    <>
      <span
        className="text-sm select-none hidden md:block"
        style={{ color: "var(--semi-color-text-2)" }}
      >
        {totalText}
      </span>
      <Pagination
        currentPage={currentPage}
        pageSize={pageSize}
        total={total}
        pageSizeOpts={pageSizeOpts}
        showSizeChanger={showSizeChanger}
        onPageSizeChange={onPageSizeChange}
        onPageChange={onPageChange}
        size="default"
        showTotal
      />
    </>
  );
}
