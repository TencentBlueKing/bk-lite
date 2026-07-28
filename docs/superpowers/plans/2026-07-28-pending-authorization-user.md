+# 待授权本地用户创建 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许系统管理中手工新增本地用户时不选择组织和角色，形成待授权账户；编辑用户和用户同步流程继续维持现有规则。

**Architecture:** 前端新增弹窗不再将组织和角色标记或校验为必填，仍将空数组传给现有创建接口。后端仅在 `create_user` 请求包含组织时校验组织有效性和操作范围；`update_user` 和同步服务完全不改。回归测试直接驱动 `create_user` action，断言空数组被持久化。

**Tech Stack:** Next.js/React/Ant Design；Django REST Framework；pytest。

## Global Constraints

- 仅改“手工新增本地用户”，不得改变 `update_user` 或用户同步流程。
- 不新增数据库迁移；`User.group_list`、`User.role_list` 保持 JSON 空数组语义。
- 若请求包含组织或角色，继续执行 ID 合法性校验；非超级管理员针对非空组织继续校验组织范围。
- 保留无关工作区改动，不做全仓格式化。

---

### Task 1: 创建接口接受待授权账户

**Files:**
- Modify: `server/apps/system_mgmt/tests/test_org_scope_permissions.py`
- Modify: `server/apps/system_mgmt/viewset/user_viewset.py:336-387`

**Interfaces:**
- Consumes: `UserViewSet.create_user(request)`，请求 `groups: []`、`roles: []`。
- Produces: 成功响应 `{\"result\": true}`，新建 `User.group_list == []` 且 `User.role_list == []`。

- [ ] **Step 1: 写入失败测试**

```python
@pytest.mark.django_db
def test_create_user_allows_pending_authorization_account():
    request = APIRequestFactory().post(
        "/system_mgmt/api/user/create_user/",
        {
            "username": "pending_authorization_user",
            "lastName": "Pending Authorization User",
            "email": "pending@example.com",
            "phone": None,
            "locale": "zh-Hans",
            "timezone": "Asia/Shanghai",
            "groups": [],
            "roles": [],
            "rules": [],
        },
        format="json",
    )
    force_authenticate(request, user=_request_user([], {"user_group-Add User"}, is_superuser=True))
    response = UserViewSet.as_view({"post": "create_user"})(request)
    assert _json_payload(response) == {"result": True}
    user = User.objects.get(username="pending_authorization_user")
    assert user.group_list == []
    assert user.role_list == []
```

- [ ] **Step 2: 运行测试，确认当前实现因组织必填而失败**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_org_scope_permissions.py::test_create_user_allows_pending_authorization_account -q`

Expected: FAIL，响应 `result` 为 `False`，原因是 `_validate_selected_groups([])` 拒绝空组织。

- [ ] **Step 3: 最小化修改创建接口**

将 `create_user` 的组织验证改为仅在 `groups` 非空时调用 `_validate_selected_groups`、标准化组织 ID 和执行组织范围校验；空数组直接写入 `User.group_list`。不修改 `update_user`。

- [ ] **Step 4: 重跑该测试，确认通过**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_org_scope_permissions.py::test_create_user_allows_pending_authorization_account -q`

Expected: PASS。

### Task 2: 新增弹窗允许空组织与角色

**Files:**
- Modify: `web/src/app/system-manager/(pages)/user/structure/userModal.tsx:194-242`
- Modify: `web/src/app/system-manager/hooks/useUserModalData.ts:250-327`

**Interfaces:**
- Consumes: `selectedGroups: React.Key[]` 与 `selectedRoles: number[]`。
- Produces: 新增和普通用户状态下允许空数组提交；编辑流程的提交校验不变。

- [ ] **Step 1: 写入前端源级行为检查**

在现有 Web 脚本约定下新增 `web/scripts/system-manager-pending-authorization-user-test.ts`，读取两个文件并断言：组织与角色的 `required` 属性只在 `type === 'edit'` 时启用；提交校验中的组织/角色阻断也只在 `type === 'edit'` 时启用；不触及同步 API。

- [ ] **Step 2: 运行检查，确认当前代码失败**

Run: `cd web && pnpm exec tsx scripts/system-manager-pending-authorization-user-test.ts`

Expected: FAIL，因为当前条件是 `!isSuperuser`，新增普通用户仍被阻断。

- [ ] **Step 3: 最小化修改弹窗和 hook**

将两个 `Form.Item.required` 改为 `type === 'edit' && !isSuperuser`；将三项组织/角色提交阻断改为 `type === 'edit' && !isSuperuser && ...`。不改变 payload 构造、编辑逻辑或用户同步代码。

- [ ] **Step 4: 重跑前端检查**

Run: `cd web && pnpm exec tsx scripts/system-manager-pending-authorization-user-test.ts`

Expected: PASS。

### Task 3: 影响范围验证

**Files:**
- Verify: `server/apps/system_mgmt/tests/test_org_scope_permissions.py`
- Verify: `web/scripts/system-manager-pending-authorization-user-test.ts`
- Verify: `web/src/app/system-manager/(pages)/user/structure/userModal.tsx`
- Verify: `web/src/app/system-manager/hooks/useUserModalData.ts`

**Interfaces:**
- Consumes: Task 1、Task 2 的完成状态。
- Produces: 已验证的本地用户创建行为，且编辑和同步未被改变。

- [ ] **Step 1: 运行后端组织范围测试模块**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_org_scope_permissions.py -q`

Expected: PASS，尤其是已有 `test_update_user_rejects_unauthorized_groups` 仍通过。

- [ ] **Step 2: 运行前端源级行为检查**

Run: `cd web && pnpm exec tsx scripts/system-manager-pending-authorization-user-test.ts`

Expected: PASS。

- [ ] **Step 3: 检查变更范围**

Run: `git diff --check && git diff -- server/apps/system_mgmt/services/user_sync_service.py server/apps/system_mgmt/viewset/user_viewset.py web/src/app/system-manager/hooks/useUserModalData.ts web/src/app/system-manager/(pages)/user/structure/userModal.tsx`

Expected: 无空白错误；同步服务无差异；`update_user` 无功能性改动。

- [ ] **Step 4: 提交**

```bash
git add server/apps/system_mgmt/tests/test_org_scope_permissions.py \
  server/apps/system_mgmt/viewset/user_viewset.py \
  web/src/app/system-manager/(pages)/user/structure/userModal.tsx \
  web/src/app/system-manager/hooks/useUserModalData.ts \
  web/scripts/system-manager-pending-authorization-user-test.ts \
  docs/superpowers/plans/2026-07-28-pending-authorization-user.md
git commit -m "feat: 支持新增待授权本地用户"
```

