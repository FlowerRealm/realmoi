"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Checkbox,
  Form,
  Input,
  Modal,
  Radio,
  RadioGroup,
  Space,
  Table,
  Tag,
} from "@douyinfe/semi-ui";
import { IconDelete, IconEdit, IconPlus, IconSave, IconSearch } from "@douyinfe/semi-icons";
import type { RatioOptions } from "./types";

type ModelRow = {
  name: string;
  price: string;
  ratio: string;
  completionRatio: string;
  hasConflict: boolean;
};

function safeParseObject(text: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(text || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
    return {};
  } catch {
    return {};
  }
}

export function ModelSettingsVisualEditor({
  options,
  setOptions,
}: {
  options: RatioOptions;
  setOptions: React.Dispatch<React.SetStateAction<RatioOptions>>;
}) {
  const [models, setModels] = useState<ModelRow[]>([]);
  const [visible, setVisible] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [currentModel, setCurrentModel] = useState<Partial<ModelRow> & { pricingMode?: string; pricingSubMode?: string }>({});
  const [searchText, setSearchText] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [conflictOnly, setConflictOnly] = useState(false);
  const pageSize = 10;

  const formRef = useRef<{ setValues?: (values: Record<string, unknown>) => void } | null>(null);

  useEffect(() => {
    const modelPrice = safeParseObject(options.ModelPrice);
    const modelRatio = safeParseObject(options.ModelRatio);
    const completionRatio = safeParseObject(options.CompletionRatio);

    const names = new Set<string>([
      ...Object.keys(modelPrice),
      ...Object.keys(modelRatio),
      ...Object.keys(completionRatio),
    ]);

    const rows: ModelRow[] = Array.from(names).map((name) => {
      const priceVal = modelPrice[name];
      const ratioVal = modelRatio[name];
      const compVal = completionRatio[name];
      const price = priceVal === undefined ? "" : String(priceVal);
      const ratio = ratioVal === undefined ? "" : String(ratioVal);
      const completion = compVal === undefined ? "" : String(compVal);
      const hasConflict = price !== "" && (ratio !== "" || completion !== "");
      return { name, price, ratio, completionRatio: completion, hasConflict };
    });
    // This effect syncs derived local editing state from persisted options.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setModels(rows);
  }, [options.CompletionRatio, options.ModelPrice, options.ModelRatio]);

  const filtered = useMemo(() => {
    return models.filter((m) => {
      const keywordMatch = searchText ? m.name.includes(searchText) : true;
      const conflictMatch = conflictOnly ? m.hasConflict : true;
      return keywordMatch && conflictMatch;
    });
  }, [conflictOnly, models, searchText]);

  const paged = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [currentPage, filtered]);

  const updateModel = (name: string, field: keyof Pick<ModelRow, "price" | "ratio" | "completionRatio">, value: string) => {
    setModels((prev) =>
      prev.map((m) => (m.name === name ? { ...m, [field]: value } : m))
    );
  };

  const resetModalState = () => {
    setIsEditMode(false);
    setCurrentModel({ pricingMode: "per-token", pricingSubMode: "ratio", name: "", price: "", ratio: "", completionRatio: "" });
    formRef.current?.setValues?.({
      name: "",
      pricingMode: "per-token",
      pricingSubMode: "ratio",
      ratioInput: "",
      completionRatioInput: "",
      priceInput: "",
      modelTokenPrice: "",
      completionTokenPrice: "",
    });
  };

  const addOrUpdateModel = (row: Partial<ModelRow>) => {
    const name = row.name;
    if (!name) return;
    setModels((prev) => {
      const exists = prev.some((m) => m.name === name);
      const nextRow: ModelRow = {
        name,
        price: row.price ?? "",
        ratio: row.ratio ?? "",
        completionRatio: row.completionRatio ?? "",
        hasConflict: Boolean(row.price) && (Boolean(row.ratio) || Boolean(row.completionRatio)),
      };
      if (!exists) return [nextRow, ...prev];
      return prev.map((m) => (m.name === name ? nextRow : m));
    });
  };

  const deleteModel = (name: string) => {
    setModels((prev) => prev.filter((m) => m.name !== name));
  };

  const editModel = (row: ModelRow) => {
    setIsEditMode(true);
    setCurrentModel({ ...row, pricingMode: "per-token", pricingSubMode: "ratio" });
    setVisible(true);
    formRef.current?.setValues?.({
      name: row.name,
      pricingMode: "per-token",
      pricingSubMode: "ratio",
      ratioInput: row.ratio,
      completionRatioInput: row.completionRatio,
      priceInput: row.price,
    });
  };

  const submitData = () => {
    const outputPrice: Record<string, number> = {};
    const outputRatio: Record<string, number> = {};
    const outputCompletion: Record<string, number> = {};

    models.forEach((m) => {
      if (m.price !== "") {
        const n = Number(m.price);
        if (!Number.isNaN(n)) outputPrice[m.name] = n;
        return;
      }
      if (m.ratio !== "") {
        const n = Number(m.ratio);
        if (!Number.isNaN(n)) outputRatio[m.name] = n;
      }
      if (m.completionRatio !== "") {
        const n = Number(m.completionRatio);
        if (!Number.isNaN(n)) outputCompletion[m.name] = n;
      }
    });

    setOptions((prev) => ({
      ...prev,
      ModelPrice: JSON.stringify(outputPrice, null, 2),
      ModelRatio: JSON.stringify(outputRatio, null, 2),
      CompletionRatio: JSON.stringify(outputCompletion, null, 2),
    }));
  };

  const columns = useMemo(
    () => [
      {
        title: "模型名称",
        dataIndex: "name",
        key: "name",
        render: (text: string, record: ModelRow) => (
          <span>
            {text}
            {record.hasConflict ? (
              <Tag color="red" shape="circle" className="ml-2">
                矛盾
              </Tag>
            ) : null}
          </span>
        ),
      },
      {
        title: "模型固定价格",
        dataIndex: "price",
        key: "price",
        render: (text: string, record: ModelRow) => (
          <Input
            value={text}
            placeholder="按量计费"
            onChange={(v) => updateModel(record.name, "price", String(v ?? ""))}
          />
        ),
      },
      {
        title: "模型倍率",
        dataIndex: "ratio",
        key: "ratio",
        render: (text: string, record: ModelRow) => (
          <Input
            value={text}
            placeholder={record.price !== "" ? "模型倍率" : "默认补全倍率"}
            disabled={record.price !== ""}
            onChange={(v) => updateModel(record.name, "ratio", String(v ?? ""))}
          />
        ),
      },
      {
        title: "补全倍率",
        dataIndex: "completionRatio",
        key: "completionRatio",
        render: (text: string, record: ModelRow) => (
          <Input
            value={text}
            placeholder={record.price !== "" ? "补全倍率" : "默认补全倍率"}
            disabled={record.price !== ""}
            onChange={(v) => updateModel(record.name, "completionRatio", String(v ?? ""))}
          />
        ),
      },
      {
        title: "操作",
        key: "action",
        render: (_: unknown, record: ModelRow) => (
          <Space>
            <Button type="primary" icon={<IconEdit />} onClick={() => editModel(record)} />
            <Button icon={<IconDelete />} type="danger" onClick={() => deleteModel(record.name)} />
          </Space>
        ),
      },
    ],
    []
  );

  return (
    <>
      <Space vertical align="start" style={{ width: "100%" }}>
        <Space className="mt-2">
          <Button
            icon={<IconPlus />}
            onClick={() => {
              resetModalState();
              setVisible(true);
            }}
          >
            添加模型
          </Button>
          <Button type="primary" icon={<IconSave />} onClick={submitData}>
            应用更改
          </Button>
          <Input
            prefix={<IconSearch />}
            placeholder="搜索模型名称"
            value={searchText}
            onChange={(value) => {
              setSearchText(String(value ?? ""));
              setCurrentPage(1);
            }}
            style={{ width: 200 }}
            showClear
          />
          <Checkbox
            checked={conflictOnly}
            onChange={(e) => {
              setConflictOnly(Boolean(e.target.checked));
              setCurrentPage(1);
            }}
          >
            仅显示矛盾倍率
          </Checkbox>
        </Space>
        <Table
          columns={columns}
          dataSource={paged}
          rowKey="name"
          pagination={{
            currentPage,
            pageSize,
            total: filtered.length,
            onPageChange: (page) => setCurrentPage(Number(page)),
            showTotal: true,
            showSizeChanger: false,
          }}
        />
      </Space>

      <Modal
        title={isEditMode ? "编辑模型" : "添加模型"}
        visible={visible}
        onCancel={() => {
          resetModalState();
          setVisible(false);
        }}
        onOk={() => {
          addOrUpdateModel(currentModel);
          resetModalState();
          setVisible(false);
        }}
      >
        <Form getFormApi={(api) => (formRef.current = api)}>
          <Form.Input
            field="name"
            label="模型名称"
            placeholder="strawberry"
            required
            disabled={isEditMode}
            onChange={(value) => setCurrentModel((prev) => ({ ...prev, name: String(value ?? "") }))}
          />

          <Form.Section text="定价模式">
            <div style={{ marginBottom: 16 }}>
              <RadioGroup
                type="button"
                value={currentModel.pricingMode ?? "per-token"}
                onChange={(e) => setCurrentModel((prev) => ({ ...prev, pricingMode: String(e.target.value) }))}
              >
                <Radio value="per-token">按量计费</Radio>
                <Radio value="per-request">按次计费</Radio>
              </RadioGroup>
            </div>
          </Form.Section>

          {(currentModel.pricingMode ?? "per-token") === "per-token" ? (
            <>
              <Form.Section text="价格设置方式">
                <div style={{ marginBottom: 16 }}>
                  <RadioGroup
                    type="button"
                    value={currentModel.pricingSubMode ?? "ratio"}
                    onChange={(e) =>
                      setCurrentModel((prev) => ({ ...prev, pricingSubMode: String(e.target.value) }))
                    }
                  >
                    <Radio value="ratio">按倍率设置</Radio>
                    <Radio value="token-price">按价格设置</Radio>
                  </RadioGroup>
                </div>
              </Form.Section>

              {(currentModel.pricingSubMode ?? "ratio") === "ratio" ? (
                <>
                  <Form.Input
                    field="ratioInput"
                    label="模型倍率"
                    placeholder="输入模型倍率"
                    onChange={(value) =>
                      setCurrentModel((prev) => ({ ...prev, ratio: String(value ?? "") }))
                    }
                  />
                  <Form.Input
                    field="completionRatioInput"
                    label="补全倍率"
                    placeholder="输入补全倍率"
                    onChange={(value) =>
                      setCurrentModel((prev) => ({ ...prev, completionRatio: String(value ?? "") }))
                    }
                  />
                </>
              ) : (
                <>
                  <Form.Input
                    field="modelTokenPrice"
                    label="模型价格"
                    placeholder="输入模型价格"
                    onChange={(value) =>
                      setCurrentModel((prev) => ({ ...prev, ratio: String(value ?? "") }))
                    }
                  />
                  <Form.Input
                    field="completionTokenPrice"
                    label="补全价格"
                    placeholder="输入补全价格"
                    onChange={(value) =>
                      setCurrentModel((prev) => ({ ...prev, completionRatio: String(value ?? "") }))
                    }
                  />
                </>
              )}
            </>
          ) : (
            <Form.Input
              field="priceInput"
              label="固定价格(每次)"
              placeholder="输入每次价格"
              onChange={(value) => setCurrentModel((prev) => ({ ...prev, price: String(value ?? "") }))}
            />
          )}
        </Form>
      </Modal>
    </>
  );
}
