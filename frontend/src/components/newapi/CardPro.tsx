"use client";

import React, { useMemo } from "react";
import { Card, Divider } from "@douyinfe/semi-ui";

export type CardProType = "type1" | "type2" | "type3";

type SemiCardProps = React.ComponentProps<typeof Card>;

type CardProProps = {
  type?: CardProType;
  className?: string;
  children: React.ReactNode;
  statsArea?: React.ReactNode;
  descriptionArea?: React.ReactNode;
  tabsArea?: React.ReactNode;
  actionsArea?: React.ReactNode | React.ReactNode[];
  searchArea?: React.ReactNode;
  paginationArea?: React.ReactNode;
  shadows?: SemiCardProps["shadows"];
  bordered?: boolean;
  style?: React.CSSProperties;
} & Omit<SemiCardProps, "title" | "footer" | "children" | "className" | "style">;

export function CardPro({
  type = "type1",
  className = "",
  children,
  statsArea,
  descriptionArea,
  tabsArea,
  actionsArea,
  searchArea,
  paginationArea,
  shadows,
  bordered = true,
  style,
  ...props
}: CardProProps) {
  const headerContent = useMemo(() => {
    const hasContent =
      statsArea || descriptionArea || tabsArea || actionsArea || searchArea;
    if (!hasContent) return null;

    return (
      <div className="flex flex-col w-full">
        {type === "type2" && statsArea ? <>{statsArea}</> : null}

        {(type === "type1" || type === "type3") && descriptionArea ? (
          <>{descriptionArea}</>
        ) : null}

        {(((type === "type1" || type === "type3") && descriptionArea) ||
          (type === "type2" && statsArea)) && <Divider margin="12px" />}

        {type === "type3" && tabsArea ? <>{tabsArea}</> : null}

        <div className="flex flex-col gap-2">
          {(type === "type1" || type === "type3") && actionsArea ? (
            Array.isArray(actionsArea) ? (
              actionsArea.map((area, idx) => (
                <React.Fragment key={idx}>
                  {idx !== 0 ? <Divider /> : null}
                  <div className="w-full">{area}</div>
                </React.Fragment>
              ))
            ) : (
              <div className="w-full">{actionsArea}</div>
            )
          ) : null}

          {actionsArea && searchArea ? <Divider /> : null}

          {searchArea ? <div className="w-full">{searchArea}</div> : null}
        </div>
      </div>
    );
  }, [actionsArea, descriptionArea, searchArea, statsArea, tabsArea, type]);

  const footerContent = useMemo(() => {
    if (!paginationArea) return null;

    return (
      <div
        className="flex w-full pt-4 border-t justify-between items-center"
        style={{ borderColor: "var(--semi-color-border)" }}
      >
        {paginationArea}
      </div>
    );
  }, [paginationArea]);

  return (
    <Card
      className={`table-scroll-card !rounded-2xl ${className}`}
      title={headerContent}
      footer={footerContent}
      shadows={shadows}
      bordered={bordered}
      style={style}
      {...props}
    >
      {children}
    </Card>
  );
}
