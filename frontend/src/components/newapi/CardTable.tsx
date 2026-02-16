"use client";

import React from "react";
import { Table } from "@douyinfe/semi-ui";

type SemiTableProps = React.ComponentProps<typeof Table>;

type CardTableProps = SemiTableProps & {
  hidePagination?: boolean;
};

export function CardTable({ hidePagination = false, ...tableProps }: CardTableProps) {
  const finalTableProps = hidePagination
    ? ({ ...tableProps, pagination: false } as SemiTableProps)
    : tableProps;

  return <Table {...finalTableProps} />;
}
