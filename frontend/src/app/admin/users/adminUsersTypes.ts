// AUTO_COMMENT_HEADER_V1: adminUsersTypes.ts
// 说明：Admin Users 页的局部类型定义（拆分自原 page.tsx）。

export type UserRole = "user" | "admin";

export type UserItem = {
  id: string;
  username: string;
  role: UserRole;
  is_disabled: boolean;
  created_at: string;
};

export type UsersListResponse = {
  items: UserItem[];
  total: number;
};

export type MeResponse = {
  id: string;
  username: string;
  role: UserRole;
  is_disabled: boolean;
};

export type Filters = {
  q: string;
  role: "all" | UserRole;
  status: "all" | "enabled" | "disabled";
};

export type AlertKind = "error" | "success";

export type CreateUserDraft = {
  username: string;
  password: string;
  role: UserRole;
  is_disabled: boolean;
};

export type ResetPasswordDraft = {
  user_id: string;
  username: string;
  new_password: string;
};

export type UserPatch = {
  role?: UserRole;
  is_disabled?: boolean;
};

export type UsersStats = {
  visible: number;
  adminCount: number;
  disabledCount: number;
};

