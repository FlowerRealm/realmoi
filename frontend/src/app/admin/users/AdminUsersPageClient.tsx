"use client";

// AUTO_COMMENT_HEADER_V1: AdminUsersPageClient.tsx
// 说明：管理员用户管理页（/admin/users）的 Client 入口（UI 组合层）。
//
// 拆分目标：降低单文件体积，将控制器逻辑与大块 UI 拆到 hooks/components。

import React from "react";
import { AppHeader } from "@/components/AppHeader";
import { RequireAdmin } from "@/components/RequireAdmin";
import { RequireAuth } from "@/components/RequireAuth";

import { CreateUserModal } from "./components/CreateUserModal";
import { ManageUserModal } from "./components/ManageUserModal";
import { ResetPasswordModal } from "./components/ResetPasswordModal";
import { UsersFiltersPanel } from "./components/UsersFiltersPanel";
import { UsersHeader } from "./components/UsersHeader";
import { UsersTable } from "./components/UsersTable";
import { useAdminUsersPageController } from "./hooks/useAdminUsersPageController";

export function AdminUsersPageClient() {
  const vm = useAdminUsersPageController();

  return (
    <RequireAuth>
      <RequireAdmin>
        <div className="relative w-full min-h-[100dvh] box-border pt-14 overflow-x-hidden">
          <AppHeader mode="overlay" />
          <main className="newapi-scope mx-auto max-w-6xl px-6 md:px-7 pt-10 pb-10 space-y-3 relative z-10">
            <UsersHeader
              total={vm.total}
              stats={vm.stats}
              loading={vm.loading}
              onCreateUser={vm.openCreateModal}
              onRefresh={() => void vm.load()}
            />

            {vm.showCreateModal ? (
              <CreateUserModal
                errorText={vm.errorText}
                alertText={vm.alertText}
                alertKind={vm.alertKind}
                creatingUser={vm.creatingUser}
                draft={vm.createDraft}
                setDraft={vm.setCreateDraft}
                onClose={() => vm.setShowCreateModal(false)}
                onSubmit={() => void vm.createUser()}
              />
            ) : null}

            {vm.showResetModal ? (
              <ResetPasswordModal
                errorText={vm.errorText}
                setErrorText={vm.setErrorText}
                alertText={vm.alertText}
                setAlertText={vm.setAlertText}
                alertKind={vm.alertKind}
                setAlertKind={vm.setAlertKind}
                resetting={Boolean(vm.resettingUserId)}
                draft={vm.resetDraft}
                setDraft={vm.setResetDraft}
                onClose={() => vm.setShowResetModal(false)}
                onResetPassword={() => void vm.resetPassword()}
              />
            ) : null}

            {vm.selectedUserId ? (
              <ManageUserModal
                errorText={vm.errorText}
                alertText={vm.alertText}
                alertKind={vm.alertKind}
                me={vm.me}
                selectedUser={vm.selectedUser}
                mutating={vm.mutatingUserId === vm.selectedUserId}
                resetting={vm.resettingUserId === vm.selectedUserId}
                onClose={() => vm.setSelectedUserId(null)}
                onPatchUser={(userId, patch) => void vm.patchUser(userId, patch)}
                onOpenResetPassword={(u) => {
                  vm.openResetPassword(u);
                  vm.setSelectedUserId(null);
                }}
              />
            ) : null}

            {vm.errorText ? <div className="glass-alert glass-alert-error">{vm.errorText}</div> : null}
            {vm.alertText ? (
              <div
                className={["glass-alert", vm.alertKind === "success" ? "glass-alert-success" : "glass-alert-error"].join(
                  " "
                )}
              >
                {vm.alertText}
              </div>
            ) : null}

            <UsersFiltersPanel
              filtersDraft={vm.filtersDraft}
              setFiltersDraft={vm.setFiltersDraft}
              filters={vm.filters}
              total={vm.total}
              loading={vm.loading}
              onApply={vm.applyFilters}
              onReset={vm.resetFilters}
            />

            <UsersTable
              items={vm.items}
              loading={vm.loading}
              selectedUserId={vm.selectedUserId}
              onSelectUser={(userId) => {
                vm.setErrorText(null);
                vm.setAlertText(null);
                vm.setSelectedUserId(userId);
              }}
              activePage={vm.activePage}
              totalPages={vm.totalPages}
              total={vm.total}
              pageSize={vm.pageSize}
              onChangePageSize={(pageSize) => {
                vm.setPageSize(pageSize);
                vm.setActivePage(1);
              }}
              onPrevPage={vm.handlePrevPage}
              onNextPage={vm.handleNextPage}
            />
          </main>
        </div>
      </RequireAdmin>
    </RequireAuth>
  );
}

