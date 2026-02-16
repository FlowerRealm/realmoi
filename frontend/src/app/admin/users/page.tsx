"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button, Form, Modal, Tag, Typography } from "@douyinfe/semi-ui";
import { IconSearch, IconUserAdd } from "@douyinfe/semi-icons";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";
import { CardPro } from "@/components/newapi/CardPro";
import { CardTable } from "@/components/newapi/CardTable";
import { createCardProPagination } from "@/components/newapi/createCardProPagination";
import { apiFetch, getErrorMessage } from "@/lib/api";
import type { ColumnProps } from "@douyinfe/semi-ui/lib/es/table/interface";

type UserItem = {
  id: string;
  username: string;
  role: "user" | "admin";
  is_disabled: boolean;
  created_at: string;
};

type UsersListResponse = {
  items: UserItem[];
  total: number;
};

type SearchFormValues = {
  searchKeyword?: string;
  searchGroup?: string | null;
};

type SearchFormApi = {
  getValues?: () => SearchFormValues;
  reset?: () => void;
};

export default function AdminUsersPage() {
  const formApiRef = useRef<SearchFormApi | null>(null);

  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");

  const [activePage, setActivePage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const [data, setData] = useState<UsersListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState<string | null>(null);

  const [showAddUser, setShowAddUser] = useState(false);

  const groupOptions = useMemo(
    () => [
      { label: "default", value: "default" },
      { label: "vip", value: "vip" },
    ],
    []
  );

  const total = data?.total ?? 0;

  const load = useCallback(async () => {
    setLoading(true);
    setErrorText(null);
    try {
      const qs = new URLSearchParams();
      if (q.trim()) qs.set("q", q.trim());
      qs.set("limit", String(pageSize));
      qs.set("offset", String(Math.max(0, (activePage - 1) * pageSize)));
      const d = await apiFetch<UsersListResponse>(`/admin/users?${qs.toString()}`);
      setData(d);
    } catch (e: unknown) {
      const msg = getErrorMessage(e);
      setErrorText(msg);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [activePage, pageSize, q]);

  useEffect(() => {
    load();
  }, [load]);

  const handleQuery = () => {
    const values = formApiRef.current?.getValues?.() || {};
    const keyword = typeof values.searchKeyword === "string" ? values.searchKeyword : "";
    const nextGroup = typeof values.searchGroup === "string" ? values.searchGroup : "";

    setQ(keyword);
    setGroup(nextGroup);
    setActivePage(1);
  };

  const handleReset = () => {
    formApiRef.current?.reset?.();
    setQ("");
    setGroup("");
    setActivePage(1);
  };

  const items = useMemo(() => data?.items || [], [data?.items]);

  const columns = useMemo<ColumnProps<UserItem>[]>(
    () => [
      {
        title: "ID",
        dataIndex: "id",
        width: 120,
      },
      {
        title: "用户名",
        dataIndex: "username",
        width: 180,
      },
      {
        title: "状态",
        dataIndex: "is_disabled",
        width: 120,
        render: (_: unknown, record: UserItem) => {
          const enabled = !record.is_disabled;
          return (
            <Tag color={enabled ? "green" : "red"} shape="circle" size="small">
              {enabled ? "已启用" : "已禁用"}
            </Tag>
          );
        },
      },
      {
        title: "剩余额度/总额度",
        key: "quota_usage",
        width: 220,
        render: () => (
          <Tag color="white" shape="circle" className="!text-xs">
            0 / 0
          </Tag>
        ),
      },
      {
        title: "分组",
        dataIndex: "group",
        width: 120,
        render: () => <div>-</div>,
      },
      {
        title: "角色",
        dataIndex: "role",
        width: 140,
        render: (role: UserItem["role"]) => {
          const isAdmin = role === "admin";
          return (
            <Tag color={isAdmin ? "yellow" : "blue"} shape="circle">
              {isAdmin ? "管理员" : "普通用户"}
            </Tag>
          );
        },
      },
      {
        title: "邀请信息",
        dataIndex: "invite",
        width: 220,
        render: () => (
          <div className="flex flex-wrap gap-1">
            <Tag color="white" shape="circle" className="!text-xs">
              邀请: 0
            </Tag>
            <Tag color="white" shape="circle" className="!text-xs">
              收益: 0
            </Tag>
            <Tag color="white" shape="circle" className="!text-xs">
              无邀请人
            </Tag>
          </div>
        ),
      },
      {
        title: "",
        dataIndex: "operate",
        fixed: "right" as const,
        width: 200,
        render: (_: unknown, record: UserItem) => {
          return (
            <Button
              type="tertiary"
              size="small"
              onClick={() => window.alert(`用户：${record.username}`)}
            >
              操作
            </Button>
          );
        },
      },
    ],
    []
  );

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-screen min-h-[100dvh] box-border pt-14 overflow-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
            <Modal
              title="添加用户"
              visible={showAddUser}
              onCancel={() => setShowAddUser(false)}
              footer={null}
            >
              <div className="text-sm" style={{ color: "var(--semi-color-text-1)" }}>
                该仓库后端未提供与 new-api 完全一致的新增用户接口，这里仅保留对齐后的 UI。
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <Button type="tertiary" onClick={() => setShowAddUser(false)}>
                  关闭
                </Button>
              </div>
            </Modal>

            <CardPro
              type="type1"
              descriptionArea={
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-2 w-full">
                  <div className="flex items-center text-blue-500">
                    <IconUserAdd className="mr-2" />
                    <Typography.Text>用户管理</Typography.Text>
                  </div>
                </div>
              }
              actionsArea={
                <div className="flex flex-col md:flex-row justify-between items-center gap-2 w-full">
                  <div className="flex gap-2 w-full md:w-auto order-2 md:order-1">
                    <Button
                      className="w-full md:w-auto"
                      onClick={() => setShowAddUser(true)}
                      size="small"
                    >
                      添加用户
                    </Button>
                  </div>

                  <Form
                    initValues={{ searchKeyword: q, searchGroup: group }}
                    getFormApi={(api) => {
                      formApiRef.current = api;
                    }}
                    onSubmit={() => {
                      handleQuery();
                    }}
                    allowEmpty={true}
                    autoComplete="off"
                    layout="horizontal"
                    trigger="change"
                    stopValidateWithError={false}
                    className="w-full md:w-auto order-1 md:order-2"
                  >
                    <div className="flex flex-col md:flex-row items-center gap-2 w-full md:w-auto">
                      <div className="relative w-full md:w-64">
                        <Form.Input
                          field="searchKeyword"
                          prefix={<IconSearch />}
                          placeholder="支持搜索用户的 ID、用户名、显示名称和邮箱地址"
                          showClear
                          pure
                          size="small"
                        />
                      </div>
                      <div className="w-full md:w-48">
                        <Form.Select
                          field="searchGroup"
                          placeholder="选择分组"
                          optionList={groupOptions}
                          onChange={() => {
                            setTimeout(() => {
                              handleQuery();
                            }, 100);
                          }}
                          className="w-full"
                          showClear
                          pure
                          size="small"
                        />
                      </div>
                      <div className="flex gap-2 w-full md:w-auto">
                        <Button
                          type="tertiary"
                          htmlType="submit"
                          loading={loading}
                          className="flex-1 md:flex-initial md:w-auto"
                          size="small"
                        >
                          查询
                        </Button>
                        <Button
                          type="tertiary"
                          onClick={handleReset}
                          className="flex-1 md:flex-initial md:w-auto"
                          size="small"
                        >
                          重置
                        </Button>
                      </div>
                    </div>
                  </Form>
                </div>
              }
              paginationArea={
                createCardProPagination({
                  currentPage: activePage,
                  pageSize,
                  total,
                  onPageChange: (page) => setActivePage(page),
                  onPageSizeChange: (size) => {
                    setPageSize(size);
                    setActivePage(1);
                  },
                  pageSizeOpts: [10, 20, 50, 100],
                  showSizeChanger: true,
                })
              }
            >
              {errorText ? (
                <div className="text-sm text-red-600 px-1">{errorText}</div>
              ) : null}

              <CardTable
                columns={columns}
                dataSource={items}
                loading={loading}
                rowKey="id"
                hidePagination={true}
                className="overflow-hidden"
                size="middle"
                scroll={{ x: "max-content" }}
              />
            </CardPro>
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}
