"use client";

import React, { useMemo, useState } from "react";
import { Button, Empty, Form, Input, Modal, Select } from "@douyinfe/semi-ui";
import { IconSearch } from "@douyinfe/semi-icons";
import { IllustrationNoResult, IllustrationNoResultDark } from "@douyinfe/semi-illustrations";
import { CheckSquare, RefreshCcw } from "lucide-react";

export function UpstreamRatioSync() {
  const [modalVisible, setModalVisible] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState("");
  const [ratioTypeFilter, setRatioTypeFilter] = useState("");

  const emptyDescription = useMemo(() => {
    if (searchKeyword.trim()) return "未找到匹配的模型";
    return "请先选择同步渠道";
  }, [searchKeyword]);

  const header = (
    <div className="flex flex-col w-full">
      <div className="flex flex-col md:flex-row justify-between items-center gap-4 w-full">
        <div className="flex flex-col md:flex-row gap-2 w-full md:w-auto order-2 md:order-1">
          <Button
            icon={<RefreshCcw size={14} />}
            className="w-full md:w-auto mt-2"
            onClick={() => setModalVisible(true)}
          >
            选择同步渠道
          </Button>

          <Button
            icon={<CheckSquare size={14} />}
            type="secondary"
            disabled
            className="w-full md:w-auto mt-2"
          >
            应用同步
          </Button>

          <div className="flex flex-col sm:flex-row gap-2 w-full md:w-auto mt-2">
            <Input
              prefix={<IconSearch size="small" />}
              placeholder="搜索模型名称"
              value={searchKeyword}
              onChange={(value) => setSearchKeyword(String(value ?? ""))}
              className="w-full sm:w-64"
              showClear
            />

            <Select
              placeholder="按倍率类型筛选"
              value={ratioTypeFilter}
              onChange={(value) => setRatioTypeFilter(String(value ?? ""))}
              className="w-full sm:w-48"
              showClear
              onClear={() => setRatioTypeFilter("")}
            >
              <Select.Option value="model_ratio">模型倍率</Select.Option>
              <Select.Option value="completion_ratio">补全倍率</Select.Option>
              <Select.Option value="cache_ratio">缓存倍率</Select.Option>
              <Select.Option value="model_price">固定价格</Select.Option>
            </Select>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <>
      <Form.Section text={header}>
        <Empty
          image={<IllustrationNoResult style={{ width: 150, height: 150 }} />}
          darkModeImage={<IllustrationNoResultDark style={{ width: 150, height: 150 }} />}
          description={emptyDescription}
          style={{ padding: 30 }}
        />
      </Form.Section>

      <Modal
        title="选择同步渠道"
        visible={modalVisible}
        onCancel={() => setModalVisible(false)}
        onOk={() => setModalVisible(false)}
      >
        <Empty
          description="暂无可选渠道（UI 对齐占位）"
          style={{ padding: 20 }}
        />
      </Modal>
    </>
  );
}
