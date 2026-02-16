"use client";

import React, { useState } from "react";
import { Button, Col, Form, Row, Spin } from "@douyinfe/semi-ui";
import type { RatioOptions } from "./types";

const SemiForm = Form as unknown as React.ComponentType<any>;

export function GroupRatioSettings({
  options,
  setOptions,
  onSave,
}: {
  options: RatioOptions;
  setOptions: React.Dispatch<React.SetStateAction<RatioOptions>>;
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

  return (
    <Spin spinning={loading}>
      <SemiForm values={options} style={{ marginBottom: 15 }}>
        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <div className="newapi-pricing-textarea">
              <Form.TextArea
                label="分组倍率"
                placeholder="为一个 JSON 文本，键为分组名称，值为倍率"
                extraText='分组倍率设置，可以在此处新增分组或修改现有分组的倍率，格式为 JSON 字符串，例如：{"vip": 0.5, "test": 1}，表示 vip 分组的倍率为 0.5，test 分组的倍率为 1'
                field="GroupRatio"
                autosize={{ minRows: 6, maxRows: 12 }}
                trigger="blur"
                stopValidateWithError
                onChange={(value) => set({ GroupRatio: String(value ?? "") })}
              />
            </div>
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="用户可选分组"
              placeholder="为一个 JSON 文本，键为分组名称，值为分组描述"
              extraText='用户新建令牌时可选的分组，格式为 JSON 字符串，例如：{"vip": "VIP 用户", "test": "测试"}，表示用户可以选择 vip 分组和 test 分组'
              field="UserUsableGroups"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ UserUsableGroups: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="分组特殊倍率"
              placeholder="为一个 JSON 文本"
              extraText='键为分组名称，值为另一个 JSON 对象，键为分组名称，值为该分组的用户的特殊分组倍率，例如：{"vip": {"default": 0.5, "test": 1}}，表示 vip 分组的用户在使用default分组的令牌时倍率为0.5，使用test分组时倍率为1'
              field="GroupGroupRatio"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ GroupGroupRatio: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="分组特殊可用分组"
              placeholder="为一个 JSON 文本"
              extraText='键为用户分组名称，值为操作映射对象。内层键以"+:"开头表示添加指定分组（键值为分组名称，值为描述），以"-:"开头表示移除指定分组（键值为分组名称），不带前缀的键直接添加该分组。例如：{"vip": {"+:premium": "高级分组", "special": "特殊分组", "-:default": "默认分组"}}，表示 vip 分组的用户可以使用 premium 和 special 分组，同时移除 default 分组的访问权限'
              field="group_ratio_setting.group_special_usable_group"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) =>
                set({ "group_ratio_setting.group_special_usable_group": String(value ?? "") })
              }
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col xs={24} sm={16}>
            <Form.TextArea
              label="自动分组auto，从第一个开始选择"
              placeholder="为一个 JSON 文本"
              field="AutoGroups"
              autosize={{ minRows: 6, maxRows: 12 }}
              trigger="blur"
              stopValidateWithError
              onChange={(value) => set({ AutoGroups: String(value ?? "") })}
            />
          </Col>
        </Row>

        <Row gutter={16}>
          <Col span={16}>
            <Form.Switch
              label="创建令牌默认选择auto分组，初始令牌也将设为auto（否则留空，为用户默认分组）"
              field="DefaultUseAutoGroup"
              onChange={(value) => set({ DefaultUseAutoGroup: Boolean(value) })}
            />
          </Col>
        </Row>
      </SemiForm>

      <Button onClick={handleSave}>保存分组倍率设置</Button>
    </Spin>
  );
}
