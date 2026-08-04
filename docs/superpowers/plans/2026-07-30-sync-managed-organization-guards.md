# 同步组织与用户管理限制 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 保证同步源根组织改名不会在下次同步时重复创建根组织，并限制同步组织和同步用户的直接管理操作。

**Architecture:** 后端以 `Group.sync_source` 作为同步管理对象的权威标识，在组织 action 中执行删除和名称变更的强制校验。根组织改名在同一事务内回写 `UserSyncSource.root_group_name`；同步用户的更新接口只保留语言、时区、角色与规则，拒绝基本资料与组织归属的改动。前端根据 API 返回的 `sync_source` 禁用不允许的操作，后端校验始终作为边界。

**Tech Stack:** Django REST Framework、Django ORM、pytest、Next.js、React、TypeScript、Ant Design。

## Global Constraints

- 只改系统管理同步组织、同步用户相关代码，不处理历史重复根组织。
- 数据库访问只使用 Django ORM；不引入 raw SQL。
- 同步用户角色和访问规则仍属于平台管理范围，可继续编辑。
- 密码重置、启停、解锁不在本次范围。

---

### Task 1: 组织 API 的同步保护与根名称回写

**Files:**
- Modify: `server/apps/system_mgmt/viewset/group_viewset.py`
- Modify: `server/apps/system_mgmt/tests/test_group_viewset_api.py`

**Interfaces:**
- Consumes: `Group.sync_source`、`UserSyncSource.root_group_name`。
- Produces: `update_group` 对同步子组织拒绝名称修改；同步根组织改名后保存对应同步源名称；`delete_groups` 拒绝任何同步组织。

- [ ] **Step 1: Write the failing tests**

```python
def test_update_synced_root_group_updates_sync_source_name(super_client, user_sync_source):
    root = Group.objects.create(name="旧根", parent_id=0, sync_source=user_sync_source)
    response = super_client.post(f"{BASE}/update_group/", {"group_id": root.id, "group_name": "新根", "role_ids": []}, format="json")
    user_sync_source.refresh_from_db()
    assert response.json()["result"] is True
    assert user_sync_source.root_group_name == "新根"

def test_update_synced_child_group_rejects_name_change(super_client, user_sync_source):
    child = Group.objects.create(name="外部子组织", parent_id=1, sync_source=user_sync_source)
    response = super_client.post(f"{BASE}/update_group/", {"group_id": child.id, "group_name": "新名称", "role_ids": []}, format="json")
    assert response.json()["result"] is False

def test_delete_synced_group_is_rejected(super_client, user_sync_source):
    group = Group.objects.create(name="同步组织", parent_id=0, sync_source=user_sync_source)
    response = super_client.post(f"{BASE}/delete_groups/", {"id": group.id}, format="json")
    assert response.json()["result"] is False
    assert Group.objects.filter(id=group.id).exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_group_viewset_api.py -k 'synced' -v`

Expected: FAIL because current endpoints permit child rename and group deletion, and do not update the sync source root name.

- [ ] **Step 3: Implement the minimal guards**

```python
if obj.sync_source_id and obj.parent_id != 0 and requested_name != obj.name:
    return JsonResponse({"result": False, "message": "Synced child group name cannot be changed"})

with transaction.atomic():
    Group.objects.filter(id=obj.id).update(**update_fields)
    if obj.sync_source_id and obj.parent_id == 0 and requested_name != obj.name:
        UserSyncSource.objects.filter(id=obj.sync_source_id).update(root_group_name=requested_name)

if obj.sync_source_id:
    return JsonResponse({"result": False, "message": "Synced groups cannot be deleted directly"})
```

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_group_viewset_api.py -k 'synced' -v`

Expected: PASS.

### Task 2: 同步用户更新保护

**Files:**
- Modify: `server/apps/system_mgmt/viewset/user_viewset.py`
- Modify: `server/apps/system_mgmt/tests/test_user_viewset_api.py` (or the existing user-viewset API test module)

**Interfaces:**
- Consumes: `User.sync_source` and the existing `update_user` request schema.
- Produces: synced users preserve display name, email, phone, and group list; locale/timezone and platform role/rule updates are accepted.

- [ ] **Step 1: Write the failing tests**

```python
def test_update_synced_user_only_changes_locale_timezone_and_platform_permissions(super_client, synced_user):
    response = super_client.post(f"{BASE}/update_user/", synced_user_payload(synced_user, lastName="篡改", email="new@example.com", groups=[], locale="zh", timezone="Asia/Shanghai"), format="json")
    synced_user.refresh_from_db()
    assert response.json()["result"] is True
    assert synced_user.display_name != "篡改"
    assert synced_user.group_list != []
    assert synced_user.locale == "zh"
    assert synced_user.timezone == "Asia/Shanghai"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_user_viewset_api.py -k 'synced_user' -v`

Expected: FAIL because `update_user` currently writes display name, contact information and `group_list` for all users.

- [ ] **Step 3: Implement the minimal update-field selection**

```python
if target_user.sync_source_id:
    update_fields = {"locale": params.get("locale"), "timezone": params.get("timezone"), "role_list": params.get("roles")}
else:
    update_fields = {...existing local-user fields...}
```

Keep the existing `UserRule` write path for both user kinds, since rules are platform-owned.

- [ ] **Step 4: Run the focused tests to verify they pass**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_user_viewset_api.py -k 'synced_user' -v`

Expected: PASS.

### Task 3: 管理界面的操作收口

**Files:**
- Modify: `web/src/app/system-manager/components/user/...` (the existing user edit form and table action components)
- Modify: `web/src/app/system-manager/components/user/...test...` or `web/scripts/...`
- Modify: the organization tree/action component that invokes `updateGroup` / `deleteTeam`

**Interfaces:**
- Consumes: existing API `sync_source` values returned for users and organization data.
- Produces: synced-user form disables basic information and organization controls while leaving locale, timezone, roles and rules editable; synced organization action UI does not offer delete and does not allow child name editing.

- [ ] **Step 1: Locate the actual action components and write failing focused frontend tests**

```ts
assert.equal(canEditSyncedUserField('locale'), true);
assert.equal(canEditSyncedUserField('groups'), false);
assert.equal(canDeleteSyncedGroup({ sync_source: 1 }), false);
```

- [ ] **Step 2: Run the focused frontend test command and verify it fails**

Run: `cd web && pnpm exec tsx <focused-test-script>`

Expected: FAIL because no synced-organization guard exists and the user editor treats synced users as local users.

- [ ] **Step 3: Add minimal UI guards using the returned sync-source identifiers**

```tsx
const isSyncedUser = user.sync_source != null;
<Form.Item name="groups"><TreeSelect disabled={isSyncedUser} /></Form.Item>
<Input disabled={isSyncedUser} />
```

Do not hide or disable role/rule, locale, or timezone controls for synchronized users.

- [ ] **Step 4: Run the focused frontend test and static checks**

Run: `cd web && pnpm exec tsx <focused-test-script> && pnpm type-check`

Expected: PASS.

### Task 4: 回归验证

**Files:**
- Modify: only files from Tasks 1–3.

- [ ] **Step 1: Run server regressions**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_group_viewset_api.py apps/system_mgmt/tests/test_user_viewset_api.py apps/system_mgmt/tests/test_user_sync_service.py -v`

Expected: PASS.

- [ ] **Step 2: Run frontend type check and any touched focused scripts**

Run: `cd web && pnpm type-check`

Expected: PASS.

- [ ] **Step 3: Review the diff for scope**

Run: `git diff --check && git diff -- server/apps/system_mgmt web/src/app/system-manager web/scripts`

Expected: no whitespace errors and no unrelated changes.

## Self-Review

- Spec coverage: Task 1 covers root-name synchronization, no direct synchronized-organization deletion, and child-name locking. Task 2 covers synchronized-user basic-information and organization immutability while retaining platform roles/rules. Task 3 prevents routine UI attempts; Task 4 verifies regressions.
- Placeholder scan: no implementation decision is deferred; exact final frontend component paths will be determined from the existing component tree before the red test, because the plan intentionally does not invent a component that may not exist.
- Type consistency: backend guards use the existing `sync_source_id`, `root_group_name`, `locale`, `timezone`, `group_list`, and `role_list` model fields.
