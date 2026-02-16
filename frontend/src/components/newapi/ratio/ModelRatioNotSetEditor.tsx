"use client";

import React, { useEffect, useMemo, useState } from "react";
import {
  Button,
  Form,
  Input,
  Modal,
  Notification,
  Radio,
  Space,
  Table,
  Typography,
} from "@douyinfe/semi-ui";
import { IconBolt, IconPlus, IconSave, IconSearch } from "@douyinfe/semi-icons";
import type { RatioOptions } from "./types";

type UnsetModelRow = {
  name: string;
  price: string;
  ratio: string;
  completionRatio: string;
};

type SemiFormInputProps = {
  field?: string;
  label?: React.ReactNode;
  placeholder?: string;
  value?: unknown;
  onChange?: (value: unknown) => void;
};

const SemiFormInput = Form.Input as unknown as React.ComponentType<SemiFormInputProps>;

function safeParseObject(text: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(text || "{}");
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed as Record<string, unknown>;
    return {};
  } catch {
    return {};
  }
}

export function ModelRatioNotSetEditor({
  options,
  enabledModels = [],
}: {
  options: RatioOptions;
  enabledModels?: string[];
}) {
  const [models, setModels] = useState<UnsetModelRow[]>([]);
  const [visible, setVisible] = useState(false);
  const [batchVisible, setBatchVisible] = useState(false);
  const [currentModel, setCurrentModel] = useState<Partial<UnsetModelRow> & { priceMode?: boolean }>({});
  const [searchText, setSearchText] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [loading, setLoading] = useState(false);
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([]);
  const [batchFillType, setBatchFillType] = useState<"price" | "ratio" | "completionRatio" | "bothRatio">("ratio");
  const [batchFillValue, setBatchFillValue] = useState("");
  const [batchRatioValue, setBatchRatioValue] = useState("");
  const [batchCompletionRatioValue, setBatchCompletionRatioValue] = useState("");
  const pageSizeOptions = [10, 20, 50, 100];
  const { Text } = Typography;

  useEffect(() => {
    const modelPrice = safeParseObject(options.ModelPrice);
    const modelRatio = safeParseObject(options.ModelRatio);
    const completionRatio = safeParseObject(options.CompletionRatio);

    const unset = enabledModels.filter((name) => modelPrice[name] === undefined && modelRatio[name] === undefined);
    setModels(
      unset.map((name) => ({
        name,
        price: modelPrice[name] ? String(modelPrice[name]) : "",
        ratio: modelRatio[name] ? String(modelRatio[name]) : "",
        completionRatio: completionRatio[name] ? String(completionRatio[name]) : "",
      }))
    );
    setSelectedRowKeys([]);
  }, [enabledModels, options.CompletionRatio, options.ModelPrice, options.ModelRatio]);

  const filtered = useMemo(() => {
    return models.filter((m) => (searchText ? m.name.includes(searchText) : true));
  }, [models, searchText]);

  const paged = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [currentPage, filtered, pageSize]);

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    const totalPages = Math.ceil(filtered.length / size);
    if (currentPage > totalPages) setCurrentPage(totalPages || 1);
  };

  const updateModel = (name: string, field: keyof Pick<UnsetModelRow, "price" | "ratio" | "completionRatio">, value: string) => {
    setModels((prev) => prev.map((m) => (m.name === name ? { ...m, [field]: value } : m)));
  };

  const submitData = async () => {
    setLoading(true);
    try {
      // 仅用于 UI 对齐：此处不落库，避免破坏现有后端计费体系
      Notification.success({
        title: "保存成功",
        content: "已应用更改（仅 UI 对齐演示）",
        duration: 2,
      });
    } finally {
      setLoading(false);
    }
  };

  const addModel = (values: Partial<UnsetModelRow>) => {
    if (!values.name) return;
    if (models.some((m) => m.name === values.name)) {
      Notification.error({ title: "模型名称已存在", duration: 2 });
      return;
    }
    setModels((prev) => [
      {
        name: values.name!,
        price: values.price || "",
        ratio: values.ratio || "",
        completionRatio: values.completionRatio || "",
      },
      ...prev,
    ]);
    setVisible(false);
    Notification.success({ title: "添加成功", duration: 2 });
  };

  const handleBatchFill = () => {
    if (selectedRowKeys.length === 0) {
      Notification.error({ title: "请先选择需要批量设置的模型", duration: 2 });
      return;
    }

    setModels((prev) =>
      prev.map((m) => {
        if (!selectedRowKeys.includes(m.name)) return m;
        if (batchFillType === "price") return { ...m, price: batchFillValue, ratio: "", completionRatio: "" };
        if (batchFillType === "ratio") return { ...m, price: "", ratio: batchFillValue };
        if (batchFillType === "completionRatio") return { ...m, price: "", completionRatio: batchFillValue };
        return { ...m, price: "", ratio: batchRatioValue, completionRatio: batchCompletionRatioValue };
      })
    );

    setBatchVisible(false);
    Notification.success({
      title: "批量设置成功",
      content: `已为 ${selectedRowKeys.length} 个模型设置参数`,
      duration: 2,
    });
  };

  const columns = [
    { title: "模型名称", dataIndex: "name", key: "name" },
    {
      title: "模型固定价格",
      dataIndex: "price",
      key: "price",
      render: (text: string, record: UnsetModelRow) => (
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
      render: (text: string, record: UnsetModelRow) => (
        <Input
          value={text}
          placeholder={record.price !== "" ? "模型倍率" : "输入模型倍率"}
          disabled={record.price !== ""}
          onChange={(v) => updateModel(record.name, "ratio", String(v ?? ""))}
        />
      ),
    },
    {
      title: "补全倍率",
      dataIndex: "completionRatio",
      key: "completionRatio",
      render: (text: string, record: UnsetModelRow) => (
        <Input
          value={text}
          placeholder={record.price !== "" ? "补全倍率" : "输入补全倍率"}
          disabled={record.price !== ""}
          onChange={(v) => updateModel(record.name, "completionRatio", String(v ?? ""))}
        />
      ),
    },
  ];

  const rowSelection = {
    selectedRowKeys,
    onChange: (keys?: Array<string | number>) =>
      setSelectedRowKeys((keys ?? []).map(String)),
  };

  return (
    <>
      <Space vertical align="start" style={{ width: "100%" }}>
        <Space className="mt-2">
          <Button icon={<IconPlus />} onClick={() => setVisible(true)}>
            添加模型
          </Button>
          <Button
            icon={<IconBolt />}
            type="secondary"
            onClick={() => setBatchVisible(true)}
            disabled={selectedRowKeys.length === 0}
          >
            批量设置 ({selectedRowKeys.length})
          </Button>
          <Button type="primary" icon={<IconSave />} onClick={submitData} loading={loading}>
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
          />
        </Space>

        <Text>此页面仅显示未设置价格或倍率的模型，设置后将自动从列表中移除</Text>

        <Table
          columns={columns}
          dataSource={paged}
          rowSelection={rowSelection}
          rowKey="name"
          pagination={{
            currentPage,
            pageSize,
            total: filtered.length,
            onPageChange: (page) => setCurrentPage(Number(page)),
            onPageSizeChange: (size) => handlePageSizeChange(Number(size)),
            pageSizeOpts: pageSizeOptions,
            showTotal: true,
            showSizeChanger: true,
          }}
          empty={
            <div style={{ textAlign: "center", padding: 20 }}>
              没有未设置的模型
            </div>
          }
        />
      </Space>

      <Modal
        title="添加模型"
        visible={visible}
        onCancel={() => setVisible(false)}
        onOk={() => currentModel && addModel(currentModel)}
      >
        <Form>
          <Form.Input
            field="name"
            label="模型名称"
            placeholder="strawberry"
            required
            onChange={(value) => setCurrentModel((prev) => ({ ...prev, name: String(value ?? "") }))}
          />
          <Form.Switch
            field="priceMode"
            label={
              <>
                定价模式：{currentModel?.priceMode ? "固定价格" : "倍率模式"}
              </>
            }
            onChange={(checked) =>
              setCurrentModel((prev) => ({
                ...prev,
                price: "",
                ratio: "",
                completionRatio: "",
                priceMode: Boolean(checked),
              }))
            }
          />
          {currentModel?.priceMode ? (
            <Form.Input
              field="price"
              label="固定价格(每次)"
              placeholder="输入每次价格"
              onChange={(value) => setCurrentModel((prev) => ({ ...prev, price: String(value ?? "") }))}
            />
          ) : (
            <>
              <Form.Input
                field="ratio"
                label="模型倍率"
                placeholder="输入模型倍率"
                onChange={(value) => setCurrentModel((prev) => ({ ...prev, ratio: String(value ?? "") }))}
              />
              <Form.Input
                field="completionRatio"
                label="补全倍率"
                placeholder="输入补全价格"
                onChange={(value) =>
                  setCurrentModel((prev) => ({ ...prev, completionRatio: String(value ?? "") }))
                }
              />
            </>
          )}
        </Form>
      </Modal>

      <Modal
        title="批量设置模型参数"
        visible={batchVisible}
        onCancel={() => setBatchVisible(false)}
        onOk={handleBatchFill}
        width={500}
      >
        <Form>
          <Form.Section text="设置类型">
            <div style={{ marginBottom: 16 }}>
              <Space>
                <Radio checked={batchFillType === "price"} onChange={() => setBatchFillType("price")}>
                  固定价格
                </Radio>
                <Radio checked={batchFillType === "ratio"} onChange={() => setBatchFillType("ratio")}>
                  模型倍率
                </Radio>
                <Radio
                  checked={batchFillType === "completionRatio"}
                  onChange={() => setBatchFillType("completionRatio")}
                >
                  补全倍率
                </Radio>
                <Radio
                  checked={batchFillType === "bothRatio"}
                  onChange={() => setBatchFillType("bothRatio")}
                >
                  模型倍率和补全倍率同时设置
                </Radio>
              </Space>
            </div>
          </Form.Section>

          {batchFillType === "bothRatio" ? (
            <>
              <SemiFormInput
                field="batchRatioValue"
                label="模型倍率值"
                placeholder="请输入模型倍率"
                value={batchRatioValue}
                onChange={(value: unknown) => setBatchRatioValue(String(value ?? ""))}
              />
              <SemiFormInput
                field="batchCompletionRatioValue"
                label="补全倍率值"
                placeholder="请输入补全倍率"
                value={batchCompletionRatioValue}
                onChange={(value: unknown) => setBatchCompletionRatioValue(String(value ?? ""))}
              />
            </>
          ) : (
            <SemiFormInput
              field="batchFillValue"
              label={
                batchFillType === "price"
                  ? "固定价格值"
                  : batchFillType === "ratio"
                    ? "模型倍率值"
                    : "补全倍率值"
              }
              placeholder="请输入数值"
              value={batchFillValue}
              onChange={(value: unknown) => setBatchFillValue(String(value ?? ""))}
            />
          )}

          <Text type="tertiary">
            将为选中的 <Text strong>{selectedRowKeys.length}</Text> 个模型设置相同的值
          </Text>
          <div style={{ marginTop: 8 }}>
            <Text type="tertiary">
              当前设置类型：{" "}
              <Text strong>
                {batchFillType === "price"
                  ? "固定价格"
                  : batchFillType === "ratio"
                    ? "模型倍率"
                    : batchFillType === "completionRatio"
                      ? "补全倍率"
                      : "模型倍率和补全倍率"}
              </Text>
            </Text>
          </div>
        </Form>
      </Modal>
    </>
  );
}
