"use client";

import React from "react";
import type { PricingItem } from "../pricingTypes";
import { PricingModelCard } from "./PricingModelCard";

type PricingModelListProps = {
  rows: PricingItem[];
  dirtyModels: Set<string>;
  savingModels: Set<string>;
  editingModels: Set<string>;
  beginEdit: (row: PricingItem) => void;
  cancelEdit: (model: string) => void;
  saveRow: (row: PricingItem) => void;
  updateRow: (model: string, patch: Partial<PricingItem>) => void;
};

export function PricingModelList({
  beginEdit,
  cancelEdit,
  dirtyModels,
  editingModels,
  rows,
  saveRow,
  savingModels,
  updateRow,
}: PricingModelListProps) {
  return (
    <div className="space-y-3">
      {rows.length === 0 ? (
        <div className="glass-panel p-4 text-sm text-slate-600">无匹配结果。</div>
      ) : null}

      {rows.map((row) => (
        <PricingModelCard
          key={row.model}
          row={row}
          isEditing={editingModels.has(row.model)}
          isDirty={dirtyModels.has(row.model)}
          isSaving={savingModels.has(row.model)}
          beginEdit={beginEdit}
          cancelEdit={cancelEdit}
          saveRow={saveRow}
          updateRow={updateRow}
        />
      ))}
    </div>
  );
}

