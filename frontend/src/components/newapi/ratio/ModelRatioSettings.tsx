"use client";

import React, { useState } from "react";
import { Button, Col, Form, Row, Space, Spin } from "@douyinfe/semi-ui";
import type { RatioOptions } from "./types";

type SemiFormProps = {
  values: RatioOptions;
  style?: React.CSSProperties;
  children?: React.ReactNode;
};

const SemiForm = Form as unknown as React.ComponentType<SemiFormProps>;

export function ModelRatioSettings({
  options,
  setOptions,
  onReset,
  onSave,
}: {
  options: RatioOptions;
  setOptions: React.Dispatch<React.SetStateAction<RatioOptions>>;
  onReset?: () => Promise<void> | void;
  onSave?: () => Promise<void> | void;
}) {
  const [loading, setLoading] = useState(false);

  const set = (patch: Partial<RatioOptions>) => {
    setOptions((prev) => ({ ...prev, ...patch }));
  };

  const handleSave = async () => {
    setLoading(true);
    try {
      await onSave?.();
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    setLoading(true);
    try {
      await onReset?.();
    } finally {
      setLoading(false);
    }
  };

  return (
    <Spin spinning={loading}>
      <SemiForm values={options} style={{ marginBottom: 15 }}>
        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <div className="newapi-pricing-textarea">
              <Form.TextArea
                label="模型固定价格"
                extraText="一次调用消耗多少刀，优先级大于模型倍率"
                placeholder='为一个 JSON 文本，键为模型名称，值为一次调用消耗多少刀，比如 "gpt-4-gizmo-*": 0.1，一次消耗0.1刀'
                field="ModelPrice"
                autosize={{ minRows: 6, maxRows: 12 }}
                trigger="blur"
                stopValidateWithError
                onChange={(value) => set({ ModelPrice: String(value ?? "") })}
              />
            </div>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="模型倍率"
              placeholder="为一个 JSON 文本，键为模型名称，值为倍率"
              field="ModelRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ ModelRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="提示缓存倍率"
              placeholder="为一个 JSON 文本，键为模型名称，值为倍率"
              field="CacheRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ CacheRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="缓存创建倍率"
              extraText="默认为 5m 缓存创建倍率；1h 缓存创建倍率按固定乘法自动计算（当前为 1.6x）"
              placeholder="为一个 JSON 文本，键为模型名称，值为倍率"
              field="CreateCacheRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ CreateCacheRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="模型补全倍率（仅对自定义模型有效）"
              extraText="仅对自定义模型有效"
              placeholder="为一个 JSON 文本，键为模型名称，值为倍率"
              field="CompletionRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ CompletionRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="图片输入倍率（仅部分模型支持该计费）"
              extraText="图片输入相关的倍率设置，键为模型名称，值为倍率，仅部分模型支持该计费"
              placeholder='为一个 JSON 文本，键为模型名称，值为倍率，例如：{"gpt-image-1": 2}'
              field="ImageRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ ImageRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="音频倍率（仅部分模型支持该计费）"
              extraText="音频输入相关的倍率设置，键为模型名称，值为倍率"
              placeholder='为一个 JSON 文本，键为模型名称，值为倍率，例如：{"gpt-4o-audio-preview": 16}'
              field="AudioRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ AudioRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="音频补全倍率（仅部分模型支持该计费）"
              extraText="音频输出补全相关的倍率设置，键为模型名称，值为倍率"
              placeholder='为一个 JSON 文本，键为模型名称，值为倍率，例如：{"gpt-4o-realtime": 2}'
              field="AudioCompletionRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ AudioCompletionRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={16}>
            <div className="newapi-pricing-switch">
              <Form.Switch
                label="暴露倍率接口"
                field="ExposeRatioEnabled"
                onChange={(value) => set({ ExposeRatioEnabled: Boolean(value) })}
              />
            </div>
          </Col>
        </Row>
      </SemiForm>

      <Space>
        <Button onClick={handleSave}>保存模型倍率设置</Button>
        <Button type="danger" onClick={handleReset}>
          重置模型倍率
        </Button>
      </Space>
    </Spin>
  );
}
