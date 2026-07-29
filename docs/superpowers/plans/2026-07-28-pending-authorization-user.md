# 新增用户角色可选 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许系统管理手工新增本地用户不选择个人角色，同时保持组织为必选项。

**Architecture:** 保持后端 `create_user` 的组织合法性、普通组织和权限范围校验，不改变 `update_user` 或用户同步。前端新增态只移除角色提交拦截和必填标记；新增、编辑的组织校验继续生效。

**Tech Stack:** Next.js/React/Ant Design；Django REST Framework；pytest。

## Global Constraints

- 仅改手工新增本地用户的角色必选限制。
- `create_user`、`update_user` 和同步流程均继续要求至少一个普通组织。
- 不新增数据库迁移；空 `User.role_list` 是待授权的个人角色状态。
- 保留非空角色的 ID 校验，以及现有组织范围校验。

---

### Task 1: 覆盖后端创建约束

**Files:**

- Modify: `server/apps/system_mgmt/tests/test_org_scope_permissions.py`
- Verify: `server/apps/system_mgmt/viewset/user_viewset.py`

- [x] **Step 1: 新增创建用户时角色为空、组织有效的回归测试**

测试发送 `groups: [group.id]`、`roles: []`，断言创建成功并持久化空 `role_list`。

- [x] **Step 2: 新增创建用户时组织为空的保护测试**

测试发送 `groups: []`，断言接口返回失败且不会创建用户。

- [x] **Step 3: 运行定向 pytest 验证创建与编辑的组织约束**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_org_scope_permissions.py::test_create_user_allows_empty_personal_roles apps/system_mgmt/tests/test_org_scope_permissions.py::test_create_user_still_rejects_empty_groups apps/system_mgmt/tests/test_org_scope_permissions.py::test_update_user_still_rejects_empty_groups -q`

Expected: PASS。

### Task 2: 仅移除新增态角色校验

**Files:**

- Modify: `web/src/app/system-manager/(pages)/user/structure/userModal.tsx`
- Modify: `web/src/app/system-manager/hooks/useUserModalData.ts`
- Create: `web/scripts/system-manager-pending-authorization-user-test.ts`

- [x] **Step 1: 保持组织必填 UI 与提交校验**

普通用户的组织字段继续使用 `required={!isSuperuser}`；空组织和仅虚拟组织继续在提交前被拦截。

- [x] **Step 2: 将角色必填限制限定为编辑态**

角色字段与空角色阻断仅在 `type === 'edit' && !isSuperuser` 时启用，因此新增普通用户可以提交空个人角色。

- [x] **Step 3: 运行前端源级回归检查**

Run: `cd web && pnpm exec tsx scripts/system-manager-pending-authorization-user-test.ts`

Expected: PASS。

### Task 3: 范围验证

- [x] **Step 1: 检查空白与同步链路差异**

Run: `git diff --check && git diff -- server/apps/system_mgmt/services/user_sync_service.py`

Expected: 无空白错误，用户同步服务无差异。
