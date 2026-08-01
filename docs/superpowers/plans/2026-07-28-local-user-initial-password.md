# 本地用户初始密码 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在安全策略中配置是否为管理员手动创建的本地用户初始化统一临时密码，并在首次登录时强制改密。

**Architecture:** 初始密码只以 Django 不可逆哈希存入 `SystemSettings`；读取 API 只返回启用与已配置状态。更新接口在一个事务中校验候选密码与将保存的策略；创建用户复制该哈希并设置 `temporary_pwd=True`，复用既有首次登录改密流程。

**Tech Stack:** Django/DRF、Django password hashers、React/TypeScript、Ant Design、pytest、pnpm。

## Global Constraints

- 仅影响 `create_user` 创建的本地用户；不改用户同步或既有密码弹窗。
- 默认关闭；关闭时清除哈希；API、响应和操作日志均不含明文。
- 开启时初始密码必须符合当前长度和复杂度；创建的用户必须 `temporary_pwd=True`。
- 已开启时变更长度或复杂度，必须同一请求重新设置合规初始密码，否则所有设置保持不变。
- 使用 Django ORM；不使用 raw SQL；保留无关工作区改动。

---

### Task 1: 后端安全策略接口与密码哈希存储

**Files:**

- Modify: `server/apps/system_mgmt/viewset/system_settings_viewset.py:14-78`
- Modify: `server/apps/system_mgmt/utils/password_validator.py:36-115`
- Create: `server/apps/system_mgmt/tests/test_local_user_initial_password_settings.py`

**Interfaces:**

- Consumes: `POST /system_mgmt/system_settings/update_sys_set/` 的现有密码策略字段。
- Produces: 持久化 `user_create_initial_password_enabled`（`"0" | "1"`）和仅服务端可读的 `user_create_initial_password_hash`；GET 返回 `user_create_initial_password_configured`，不返回哈希。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.django_db
def test_enable_initial_password_stores_only_hash_and_get_masks_it(api_factory, security_admin):
    response = _update(api_factory, security_admin, {
        "user_create_initial_password_enabled": "1",
        "user_create_initial_password": "InitialPwd1!",
        "pwd_set_min_length": "8", "pwd_set_max_length": "20",
        "pwd_set_required_char_types": "uppercase,lowercase,digit,special",
    })
    assert response.status_code == 200
    hashed = SystemSettings.objects.get(key="user_create_initial_password_hash").value
    assert hashed != "InitialPwd1!" and check_password("InitialPwd1!", hashed)
    payload = _get(api_factory, security_admin)
    assert payload["user_create_initial_password_configured"] == "1"
    assert "user_create_initial_password_hash" not in payload
    assert "InitialPwd1!" not in json.dumps(payload)

@pytest.mark.django_db
def test_disabling_initial_password_clears_the_hash(api_factory, security_admin):
    _enable_initial_password(api_factory, security_admin)
    assert _update(api_factory, security_admin, {"user_create_initial_password_enabled": "0"}).status_code == 200
    assert SystemSettings.objects.get(key="user_create_initial_password_hash").value == ""

@pytest.mark.django_db
def test_policy_change_requires_replacing_enabled_initial_password(api_factory, security_admin):
    _enable_initial_password(api_factory, security_admin)
    response = _update(api_factory, security_admin, {"pwd_set_min_length": "12"})
    assert response.status_code == 400
    assert SystemSettings.objects.get(key="pwd_set_min_length").value == "8"
```

- [ ] **Step 2: 运行 RED 测试**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_local_user_initial_password_settings.py -v`

Expected: FAIL；当前 API 不识别初始密码字段，也不会在策略变更时拒绝。

- [ ] **Step 3: 最小化实现**

```python
INITIAL_PASSWORD_ENABLED_KEY = "user_create_initial_password_enabled"
INITIAL_PASSWORD_HASH_KEY = "user_create_initial_password_hash"
# copy request.data; pop write-only user_create_initial_password before any
# SystemSettings update or audit logging. Derive effective policy from DB + request,
# validate candidate with PasswordValidator.validate_password_with_config,
# then transaction.atomic(): update policy, save make_password(candidate), or
# save an empty hash when disabled. GET removes hash and returns configured flag.
```

新增纯函数 `PasswordValidator.validate_password_with_config(password, config)`；既有 `validate_password()` 仍从数据库取策略后调用它。启用、或启用状态下修改长度/复杂度时必须提供候选密码；失败返回 400 且没有任何设置写入。密码策略缓存仍在 `pwd_set_*` 更新时失效，操作日志只列设置键。

- [ ] **Step 4: 运行 GREEN 与回归**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_local_user_initial_password_settings.py apps/system_mgmt/tests/test_password_validator.py apps/system_mgmt/tests/test_pwd_policy_cache_3459.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add server/apps/system_mgmt/viewset/system_settings_viewset.py server/apps/system_mgmt/utils/password_validator.py server/apps/system_mgmt/tests/test_local_user_initial_password_settings.py
git commit -m "feat: 配置本地用户初始密码"
```

### Task 2: 创建本地用户时应用初始化密码

**Files:**

- Modify: `server/apps/system_mgmt/viewset/user_viewset.py:336-387`
- Modify: `server/apps/system_mgmt/tests/test_create_user_password_3466.py:32-84`

**Interfaces:**

- Consumes: Task 1 的 enabled 和 hash 设置。
- Produces: 已配置时创建的 `User.password` 可用且 `temporary_pwd=True`；关闭时保持不可用密码、`temporary_pwd=False`。

- [ ] **Step 1: 写失败测试**

```python
@pytest.mark.django_db
def test_create_local_user_uses_enabled_initial_password_and_forces_change():
    SystemSettings.objects.update_or_create(key="user_create_initial_password_enabled", defaults={"value": "1"})
    SystemSettings.objects.update_or_create(key="user_create_initial_password_hash", defaults={"value": make_password("InitialPwd1!")})
    response = _create_user_request("initial-password-user")
    assert response.status_code == 200
    user = User.objects.get(username="initial-password-user")
    assert check_password("InitialPwd1!", user.password)
    assert user.temporary_pwd is True

@pytest.mark.django_db
def test_create_local_user_without_enabled_initial_password_keeps_unusable_password():
    SystemSettings.objects.update_or_create(key="user_create_initial_password_enabled", defaults={"value": "0"})
    _create_user_request("no-initial-password-user")
    user = User.objects.get(username="no-initial-password-user")
    assert not is_password_usable(user.password)
    assert user.temporary_pwd is False
```

- [ ] **Step 2: 运行 RED 测试**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_create_user_password_3466.py -v`

Expected: FAIL；当前创建接口无条件 `make_password(None)`。

- [ ] **Step 3: 最小化实现**

```python
enabled = SystemSettings.objects.filter(key="user_create_initial_password_enabled", value="1").exists()
initial_hash = SystemSettings.objects.filter(key="user_create_initial_password_hash").values_list("value", flat=True).first() or ""
if enabled and not initial_hash:
    return JsonResponse({"result": False, "message": "本地用户初始密码未配置"}, status=400)
# User.objects.create(..., password=initial_hash if enabled else make_password(None), temporary_pwd=enabled)
```

设置查找在 `transaction.atomic()` 前，保留原组织、角色、权限校验；不接收创建请求的密码字段；不动用户同步和重置密码。

- [ ] **Step 4: 运行 GREEN 与登录回归**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_create_user_password_3466.py apps/system_mgmt/tests/test_otp_login_flow.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add server/apps/system_mgmt/viewset/user_viewset.py server/apps/system_mgmt/tests/test_create_user_password_3466.py
git commit -m "feat: 创建本地用户应用初始密码"
```

### Task 3: 安全策略页面与国际化

**Files:**

- Modify: `web/src/app/system-manager/types/security.ts:32-47`
- Modify: `web/src/app/system-manager/api/security/index.ts:11-65`
- Modify: `web/src/app/system-manager/(pages)/user/security-settings/page.tsx:11-225`
- Modify: `web/src/app/system-manager/components/security/authSettings.tsx:8-218`
- Modify: `web/src/app/system-manager/locales/zh.json:491-535`
- Modify: `web/src/app/system-manager/locales/en.json:491-535`

**Interfaces:**

- Consumes: enabled/configured 读取字段和 write-only `user_create_initial_password`。
- Produces: 开关、条件显示的初始密码与确认输入，及策略变更时的重新输入提示。

- [ ] **Step 1: 写失败的 UI 测试**

```tsx
it('requires confirmation when enabling initial password', async () => {
  render(<LoginSettings {...baseProps} initialPasswordEnabled={false} />);
  await user.click(screen.getByRole('switch', { name: /创建用户时初始化密码/i }));
  expect(screen.getByLabelText(/初始密码/i)).toBeVisible();
  expect(screen.getByLabelText(/确认初始密码/i)).toBeVisible();
});
it('does not render a configured password value after refetch', () => {
  render(<LoginSettings {...baseProps} initialPasswordEnabled initialPasswordConfigured />);
  expect(screen.queryByDisplayValue('InitialPwd1!')).not.toBeInTheDocument();
});
```

- [ ] **Step 2: 运行 RED 测试**

Run: `cd web && pnpm test -- authSettings.test.tsx`

Expected: FAIL；当前组件没有这些 props/控件。若仓库没有 `test` 脚本，记录事实并以 lint/type-check 建立基线。

- [ ] **Step 3: 最小化实现**

```tsx
const payload = {
  ...existingPasswordPolicy,
  userCreateInitialPasswordEnabled: pendingInitialPasswordEnabled ? '1' : '0',
  ...(pendingInitialPassword ? { userCreateInitialPassword: pendingInitialPassword } : {}),
};
```

增加 fetched/pending enabled、configured 与仅内存存在的 password/confirm 状态。开启、或 enabled 状态改变 min/max/字符类型时，前端要求非空且相同；后端仍为最终校验。成功、关闭或重新获取后清空密码字段。使用 `Input.Password`，关闭时隐藏；刷新后仅显示“已配置”，不回填值。添加中英文标签、必填/不一致、策略变更重新设置、线下告知提示；不展示或发送密码。

- [ ] **Step 4: 运行验证**

Run: `cd web && pnpm lint && pnpm type-check && pnpm build`

Expected: PASS。

- [ ] **Step 5: 手动验证**

Run: `cd web && pnpm dev`

Expected: 默认关闭；开启需输入确认；刷新后掩码；关闭清空；改长度/复杂度强制重新输入；创建本地用户后以初始密码登录进入改密页。

- [ ] **Step 6: 提交**

```bash
git add web/src/app/system-manager/types/security.ts web/src/app/system-manager/api/security/index.ts 'web/src/app/system-manager/(pages)/user/security-settings/page.tsx' web/src/app/system-manager/components/security/authSettings.tsx web/src/app/system-manager/locales/zh.json web/src/app/system-manager/locales/en.json
git commit -m "feat: 配置本地用户初始密码界面"
```

### Task 4: 全链路验收与发布记录

**Files:**

- Modify: `specs/capabilities/legacy-prd-系统管理-组织.md:15-52`
- Create: `web/src/app/system-manager/public/versions/system-manager/zh/2026-07-28.md`
- Create: `web/src/app/system-manager/public/versions/system-manager/en/2026-07-28.md`

- [ ] **Step 1: 添加端到端回归断言**

```python
@pytest.mark.django_db
def test_enabled_initial_password_user_requires_reset_after_login():
    user = _create_configured_local_user()
    result = get_user_login_token(user=user, username=user.username, password="InitialPwd1!")
    assert result["data"]["temporary_pwd"] is True
```

- [ ] **Step 2: 运行最终验证**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_local_user_initial_password_settings.py apps/system_mgmt/tests/test_create_user_password_3466.py apps/system_mgmt/tests/test_password_validator.py apps/system_mgmt/tests/test_pwd_policy_cache_3459.py apps/system_mgmt/tests/test_otp_login_flow.py -v`

Run: `cd web && pnpm lint && pnpm type-check && pnpm build`

Expected: PASS；若基线失败，保留完整原始输出并明确与本改动的关系。

- [ ] **Step 3: 更新长期规格和中英文版本记录**

记录默认关闭、仅手工本地用户、统一临时密码、首次登录改密、策略变更必须重新设置、密码不回显/不发送。不要写入示例真实密码或哈希。

- [ ] **Step 4: 提交**

```bash
git add specs/capabilities/legacy-prd-系统管理-组织.md web/src/app/system-manager/public/versions/system-manager/zh/2026-07-28.md web/src/app/system-manager/public/versions/system-manager/en/2026-07-28.md
git commit -m "docs: 记录本地用户初始密码策略"
```

## Self-Review

- 规格覆盖：Task 1 处理默认、掩码、清除和策略联动；Task 2 处理手工本地用户与首次改密；Task 3 处理界面、确认、不可回显和线下告知；Task 4 覆盖全链路与文档。
- 占位扫描：无 TBD/TODO；每项改动均有路径、接口和验证命令。
- 类型一致性：前端读 enabled/configured、写 write-only password；后端从请求中 `pop` 明文后仅保存 hash。
