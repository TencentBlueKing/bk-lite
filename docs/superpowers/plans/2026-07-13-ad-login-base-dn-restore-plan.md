# AD Provider · login_auth base_dn 字段恢复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 恢复 AD provider `login_auth` capability 的 `base_dn` 配置项 + 后端 `build_connection_config` 在 `base_dn` 缺失时显式 `ValueError` 防御。修复「AD 用户经用户同步成功落库后，通过 AD 登录认证报 'AD user not found'」的回归 bug。

**Architecture:** 在 `manifests/ad.py` 的 `capabilities[login_auth].connection_template` 内恢复一个 `base_dn` 必填字段（位置与 2026-07-02 spec 删除前一致），不改 `IntegrationInstance.config.base_dn`（连接级，2026-07-02 spec 已正确删除）。后端 `build_connection_config` 在 `base_dn` 为空（缺省/`None`/`""`）时抛 `ValueError`，由 `ad.py:94` 现有 `except ValueError` 分支接住并返回 `provider.invalid_config` 错误，消息含原始 error 内容。不引入新异常类、不做 Django data migration、不改前端组件（动态表单按 manifest 自动渲染）。

**Tech Stack:** Python 3.12, Django 4.2, pydantic v2, ldap3, Manifest-driven form renderer (Next.js / Ant Design frontend downstream), pytest, pytest-mock, monkeypatch.

## Global Constraints

- 仅恢复 AD provider 在 `login_auth.connection_template` 下的 `base_dn`；**不**动 `IntegrationInstance.config.base_dn`（连接级）、**不**动 `UserSyncSource.business_config.base_dn`、**不**复活 `is_sub_dn(root_dn, base_dn)` 业务护栏。详见 [spec §1.3](2026-07-13-ad-login-base-dn-restore-design.md)。
- **不**引入新异常类型。复用 `ValueError` + `ad.py:94` 现有 `except ValueError` 分支 + 改消息模板为 `f"AD login_auth configuration error: {error}"`。详见 [spec §3.2](2026-07-13-ad-login-base-dn-restore-design.md)。
- **不**写 Django data migration。`base_dn` 是 JSONField key，非 DB 列。详见 [spec §5.2](2026-07-13-ad-login-base-dn-restore-design.md)。
- **`base_dn` 铁律：禁止静默降级为空字符串。** 之前的实现 `str(raw.get("base_dn") or "")` 在缺省时返回空串，传到 ldap3 `search_base=""` 搜不到任何 user，触发迷惑的「AD user not found」错误。本次实现必须**显式拒绝**：缺省、`None`、`""`、纯空白都抛 `ValueError`，不让任何「空 base_dn」路径继续走到 LDAP。详见 [spec §3.2](2026-07-13-ad-login-base-dn-restore-design.md) + T2 step 1 的 `test_build_connection_config_does_not_silently_default_missing_base_dn_to_empty` 回归锁。
- **不**写 `reset_capabilities`，依赖 `schemas.py:23` 字段定义 + `integration_instance_serializer.py:137` 的 `field.reset_capabilities or [capability.key]` fallback 自动得到 `["login_auth"]`。
- **不**做代码层 fallback（不引入 `config.base_dn` 缺失时回退到 `business_config.root_dn` 的逻辑）。
- **不**改前端组件（动态表单按 manifest 字段渲染）。
- 字段属性：`required=True`、无 `default`、`placeholder="DC=example,DC=com"`、不带 `secret`、`field_type="string"`。
- UI 落点：集成中心详情页「登录认证」Tab（`web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`，tab key=`login_auth`）。`root_dn` 不在该页，是另一处菜单（系统管理 → 用户同步 → UserSyncSource 配置）。
- 任何 git commit 必须先经用户批准；不在执行期间自作主张提交。
- 必须为每个代码改动步骤执行 `test-driven-development`：先写失败测试，再实现，再验证通过。
- 提交「完成」前必须运行 `verification-before-completion`：`cd server && make test` 目标测试全绿，并记录输出。

---

## File Structure

### 修改文件

- `server/apps/system_mgmt/providers/manifests/ad.py`
  在 `capabilities[login_auth].connection_template` 内、`login_auth_identity_field` 之前插入 `base_dn` 字段定义（`required=True`, `placeholder="DC=example,DC=com"`, 简短 `help_text`）。
- `server/apps/system_mgmt/providers/adapters/common/ldap.py`
  在 `build_connection_config` 函数体最前加空值校验：`base_dn` 为空时抛 `ValueError("AD login_auth.base_dn is required but missing; configure it on the IntegrationInstance (登录认证 connection template).")`。
- `server/apps/system_mgmt/providers/adapters/ad.py`
  `authenticate` 方法第 94 行 `except ValueError:` 改为 `except ValueError as error:`，返回消息模板改为 `f"AD login_auth configuration error: {error}"`，`code` 改为 `"provider.invalid_config"`。

### 测试文件

- `server/apps/system_mgmt/tests/test_provider_manifest.py`
  新增 `test_ad_login_auth_connection_template_includes_base_dn_required`：加载 AD manifest 后断言 `login_auth.connection_template` 含 `key="base_dn"`、`required=True`、无 `default`。
- `server/apps/system_mgmt/tests/test_ad_provider.py`
  新增 `test_build_connection_config_raises_when_base_dn_missing`：覆盖 `{}` / `{"base_dn": ""}` / `{"base_dn": None}` 三种空形态，每种都抛 `ValueError`，消息含 "base_dn"。
- 新增 `test_ad_authenticate_returns_invalid_config_when_base_dn_missing`：调用 `ADLoginAuthAdapter.authenticate(config={}, username="x", password="y")` 断言 `success=False`、`code="provider.invalid_config"`、消息含 "base_dn"。
- `server/apps/system_mgmt/tests/test_integration_instance_serializer.py`
  新增 `test_update_base_dn_resets_login_auth_to_pending_verification`：mock AD provider manifest（`base_dn` 在 `login_auth.connection_template`），创建 instance，`base_dn` 由 "DC=old,DC=com" 改为 "DC=new,DC=com"，断言 `capability_status["login_auth"] == PENDING_VERIFICATION`、`capability_status["user_sync"]` 不变。

### 不动的文件

- `server/apps/system_mgmt/providers/adapters/ad.py` 中的 `ADUserSyncAdapter`（sync 不读 `base_dn`）
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`（sync 业务护栏相关，2026-07-02 已清）
- `server/apps/system_mgmt/services/capability_contract_service.py`（contract 校验，2026-07-02 已清）
- `server/apps/system_mgmt/migrations/`（无新 migration）
- 任何前端文件（动态表单按 manifest 字段自动渲染）

---

## Tasks

### T1. Manifest 恢复 `base_dn` 字段

**Goal:** `manifests/ad.py` 的 `capabilities[login_auth].connection_template` 中恢复 `base_dn` 必填字段。保证前端「登录认证」Tab 下出现「登录搜索 Base DN」必填输入。

**Files:**
- Modify: `server/apps/system_mgmt/providers/manifests/ad.py:162-181`
- Test: `server/apps/system_mgmt/tests/test_provider_manifest.py`

**Interfaces:**
- Consumes: `PROVIDER_MANIFEST` 当前 dict 结构（`ad.py:4-195`）
- Produces: AD manifest `login_auth.connection_template` 含 `{"key": "base_dn", "label": "登录搜索 Base DN", "field_type": "string", "required": True, "placeholder": "DC=example,DC=com", "help_text": "..."}`

- [ ] **Step 1: 写失败测试**

在 `server/apps/system_mgmt/tests/test_provider_manifest.py` 末尾追加：

```python
def test_ad_login_auth_connection_template_includes_base_dn_required():
    from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST

    login_auth_capability = next(
        capability for capability in PROVIDER_MANIFEST.capabilities if capability.key == "login_auth"
    )
    base_dn_field = next(
        (field for field in login_auth_capability.connection_template if field.key == "base_dn"),
        None,
    )

    assert base_dn_field is not None, "login_auth.connection_template must contain base_dn field"
    assert base_dn_field.required is True
    assert base_dn_field.default is None
    assert base_dn_field.placeholder == "DC=example,DC=com"
    assert base_dn_field.field_type == "string"
    # login_auth_identity_field must come AFTER base_dn in connection_template
    field_keys = [field.key for field in login_auth_capability.connection_template]
    assert field_keys.index("base_dn") < field_keys.index("login_auth_identity_field"), (
        "base_dn must precede login_auth_identity_field in connection_template"
    )
```

- [ ] **Step 2: 验证测试失败**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py::test_ad_login_auth_connection_template_includes_base_dn_required -x -q --no-cov`

Expected: FAIL with `assert base_dn_field is not None`（当前 manifest 无 `base_dn`）。

- [ ] **Step 3: 改 manifest 加 `base_dn` 字段**

在 `server/apps/system_mgmt/providers/manifests/ad.py` 第 169 行 `connection_template=[` 之后、第 171 行 `{"key": "login_auth_identity_field", ...}` 之前，插入：

```python
                {
                    "key": "base_dn",
                    "label": "登录搜索 Base DN",
                    "field_type": "string",
                    "required": True,
                    "placeholder": "DC=example,DC=com",
                    "help_text": (
                        "登录认证时 LDAP 搜索的根目录，决定可在哪个 OU/子树范围内查找登录用户。"
                        "与「同步起始目录 (root_dn)」是不同字段：root_dn 限制同步范围，base_dn 限制登录搜索范围。"
                    ),
                },
```

**不要**写 `reset_capabilities`。依赖 schema 自动 fallback。

- [ ] **Step 4: 验证测试通过**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -x -q --no-cov`

Expected: ALL PASS（包括 step 1 新增的 case + 既有的 AD/sync manifest case）。

- [ ] **Step 5: 手动 sanity**

Run: `cd server && uv run python -c "from apps.system_mgmt.providers.manifests.ad import PROVIDER_MANIFEST; import json; print(json.dumps([f.key for cap in PROVIDER_MANIFEST.capabilities if cap.key=='login_auth' for f in cap.connection_template], ensure_ascii=False))"`

Expected: `["base_dn", "login_auth_identity_field"]`

- [ ] **Step 6: Commit（需用户批准）**

```bash
git add server/apps/system_mgmt/providers/manifests/ad.py \
        server/apps/system_mgmt/tests/test_provider_manifest.py
git commit -m "fix(ad-login): restore base_dn in login_auth.connection_template"
```

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_provider_manifest.py -x -q --no-cov` 全绿。
- [ ] `grep -nE 'base_dn' server/apps/system_mgmt/providers/manifests/ad.py` 返回至少 1 行命中（仅在 `login_auth.connection_template` 内）。

---

### T2. `build_connection_config` 加 `ValueError` 防御

**Goal:** `build_connection_config(config)` 在 `config.base_dn` 为空（缺省/`None`/`""`/纯空白）时抛 `ValueError`，错误信息含 "base_dn"。

**Files:**
- Modify: `server/apps/system_mgmt/providers/adapters/common/ldap.py:16-25`
- Test: `server/apps/system_mgmt/tests/test_ad_provider.py`

**Interfaces:**
- Consumes: `config: dict[str, Any] | None`
- Produces: 构造好的 `LDAPConnectionConfig`（行为不变）；或抛 `ValueError` 含 "base_dn"

- [ ] **Step 1: 写失败测试**

在 `server/apps/system_mgmt/tests/test_ad_provider.py` 末尾追加：

```python
@pytest.mark.parametrize(
    "config",
    [
        {},                                       # 完全缺省
        {"base_dn": ""},                          # 空字符串
        {"base_dn": None},                        # None
        {"base_dn": "   "},                       # 仅空白
        {"connection_url": "x"},                  # 缺 base_dn 但有其它字段
    ],
)
def test_build_connection_config_raises_when_base_dn_missing(config):
    with pytest.raises(ValueError, match=r"base_dn"):
        build_connection_config(config)


def test_build_connection_config_does_not_silently_default_missing_base_dn_to_empty():
    """回归锁：之前实现 `str(raw.get('base_dn') or '')` 在缺省时静默返回 base_dn='',
    空串传到 ldap3 search_base='' 会搜不到任何 user，触发迷惑的 'AD user not found'。
    新实现必须在缺省 / None / 空串 / 空白时立即抛 ValueError，不允许静默降级。
    """
    from dataclasses import asdict

    # 验证：缺省 / None / 空串 三种「曾经的静默路径」现在都抛 ValueError
    for silent_config in [{}, {"base_dn": None}, {"base_dn": ""}]:
        with pytest.raises(ValueError):
            build_connection_config(silent_config)

    # 验证：非空 base_dn 不抛，且 LDAPConnectionConfig.base_dn 等于传入值（不被改写）
    config = build_connection_config({"base_dn": "DC=corp,DC=com", "connection_url": "x"})
    assert asdict(config)["base_dn"] == "DC=corp,DC=com"
    # 验证：纯空白也被识别为空（strip 后等于空）
    with pytest.raises(ValueError):
        build_connection_config({"base_dn": "   "})
```

- [ ] **Step 2: 验证测试失败**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_ad_provider.py::test_build_connection_config_raises_when_base_dn_missing -x -q --no-cov`

Expected: FAIL with `Failed: DID NOT RAISE` 或类似（当前 `build_connection_config` 把 `base_dn=""` 静默返回）。

- [ ] **Step 3: 加 `ValueError` 校验**

修改 `server/apps/system_mgmt/providers/adapters/common/ldap.py:16-25`，函数体改为：

```python
def build_connection_config(config: dict[str, Any] | None) -> LDAPConnectionConfig:
    raw = config or {}
    base_dn = str(raw.get("base_dn") or "").strip()
    if not base_dn:
        raise ValueError(
            "AD login_auth.base_dn is required but missing; "
            "configure it on the IntegrationInstance (登录认证 connection template)."
        )
    return LDAPConnectionConfig(
        connection_url=str(raw.get("connection_url") or ""),
        use_ssl=str(raw.get("ssl_encryption") or "").lower() in {"ssl", "ldaps", "true", "1"},
        timeout=int(raw.get("timeout") or 10),
        bind_dn=str(raw.get("bind_dn") or ""),
        bind_password=str(raw.get("bind_password") or ""),
        base_dn=base_dn,
    )
```

- [ ] **Step 4: 验证测试通过**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_ad_provider.py -x -q --no-cov`

Expected: ALL PASS（5 个 parametrize case + 既有用例）。

- [ ] **Step 5: Commit（需用户批准）**

```bash
git add server/apps/system_mgmt/providers/adapters/common/ldap.py \
        server/apps/system_mgmt/tests/test_ad_provider.py
git commit -m "feat(ad-login): raise ValueError when login_auth.base_dn is missing"
```

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_ad_provider.py -x -q --no-cov` 全绿（包含 step 1 新增的 5 个 parametrize + 1 个显式回归锁 `test_build_connection_config_does_not_silently_default_missing_base_dn_to_empty`）。
- [ ] 既有 AD provider 测试不退化。

---

### T3. `ad.py:94` `except ValueError` 消息模板变更

**Goal:** `ADLoginAuthAdapter.authenticate` 在 `build_connection_config` 抛 `ValueError` 时返回 `provider.invalid_config` 错误，消息含 "base_dn" 关键字。同时 `search_single_user` 多匹配错误也走同一分支（消息含 `Expected a single LDAP user...`）。

**Files:**
- Modify: `server/apps/system_mgmt/providers/adapters/ad.py:94-99`
- Test: `server/apps/system_mgmt/tests/test_ad_provider.py`

**Interfaces:**
- Consumes: `ADLoginAuthAdapter.authenticate(config, username, password)`
- Produces: `CapabilityExecutionResult.failed_result(message, code="provider.invalid_config", field=identity_field)`，`message` 含原始 `ValueError` 内容

- [ ] **Step 1: 写失败测试**

在 `server/apps/system_mgmt/tests/test_ad_provider.py` 末尾追加：

```python
def test_ad_authenticate_returns_invalid_config_when_base_dn_missing():
    """base_dn 缺失时 authenticate 不应返回迷惑的 'AD user not found'，
    而应明确返回 provider.invalid_config + 含 base_dn 的消息。"""
    result = ADLoginAuthAdapter.authenticate(
        config={},   # 完全没填 base_dn
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="secret",
    )

    assert result.success is False
    assert result.errors[0].code == "provider.invalid_config"
    assert "base_dn" in result.errors[0].message.lower()
```

- [ ] **Step 2: 验证测试失败**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_ad_provider.py::test_ad_authenticate_returns_invalid_config_when_base_dn_missing -x -q --no-cov`

Expected: FAIL（当前 `except ValueError` 返回 `"AD user search returned multiple matches"` + `code="provider.auth_failed"`，与断言不符）。

- [ ] **Step 3: 改 `ad.py:94` except 分支**

修改 `server/apps/system_mgmt/providers/adapters/ad.py:94-99`，从：

```python
        except ValueError:
            return CapabilityExecutionResult.failed_result(
                "AD user search returned multiple matches",
                code="provider.auth_failed",
                field=identity_field,
            )
```

改为：

```python
        except ValueError as error:
            return CapabilityExecutionResult.failed_result(
                f"AD login_auth configuration error: {error}",
                code="provider.invalid_config",
                field=identity_field,
            )
```

**同时**确认 `test_ad_login_auth_fails_when_search_returns_multiple_users`（`test_ad_provider.py:80-92`）期望的 `code="provider.auth_failed"` 现在变成 `code="provider.invalid_config"`。需要在 step 1 之前更新该既有测试（见 step 3.5）。

- [ ] **Step 3.5: 同步更新既有测试 `test_ad_login_auth_fails_when_search_returns_multiple_users`**

修改 `server/apps/system_mgmt/tests/test_ad_provider.py:80-92`：

```python
@patch("apps.system_mgmt.providers.adapters.ad.search_single_user")
def test_ad_login_auth_fails_when_search_returns_multiple_users(mock_search_single_user):
    mock_search_single_user.side_effect = ValueError("multiple")

    result = ADLoginAuthAdapter.authenticate(
        config=_base_config(),
        provider_key="ad",
        capability_key="login_auth",
        username="alice",
        password="secret",
    )

    assert result.success is False
    # 多匹配也是配置/数据问题，走 provider.invalid_config + 消息含原始 error
    assert result.errors[0].code == "provider.invalid_config"
    assert "multiple" in result.errors[0].message
```

- [ ] **Step 4: 验证测试通过**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_ad_provider.py -x -q --no-cov`

Expected: ALL PASS（包括 step 1 新增的 case + step 3.5 更新后的多匹配 case + 既有用例）。

- [ ] **Step 5: Commit（需用户批准）**

```bash
git add server/apps/system_mgmt/providers/adapters/ad.py \
        server/apps/system_mgmt/tests/test_ad_provider.py
git commit -m "fix(ad-login): surface base_dn config error via provider.invalid_config"
```

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_ad_provider.py -x -q --no-cov` 全绿。
- [ ] 既有多匹配测试不退化（已 step 3.5 同步更新）。

---

### T4. Serializer 触发 PENDING_VERIFICATION 回归测试

**Goal:** 当 AD instance 的 `config.base_dn` 变化时，`capability_status["login_auth"]` 自动变 `PENDING_VERIFICATION`，`capability_status["user_sync"]` 不变。这条不变代码（依赖 manifest `reset_capabilities or [capability.key]` fallback），仅补回归测试锁定契约。

**Files:**
- Test only: `server/apps/system_mgmt/tests/test_integration_instance_serializer.py`

**Interfaces:**
- Consumes: 既有 `IntegrationInstanceSerializer.update` 流程（`integration_instance_serializer.py:110-146`）
- Produces: 不改生产代码；新增 case 锁定 `login_auth` 自动 PENDING、`user_sync` 不动

- [ ] **Step 1: 写测试**

在 `server/apps/system_mgmt/tests/test_integration_instance_serializer.py` 末尾追加（参考既有 `test_integration_instance_serializer_scoped_update_only_resets_target_capability` 模式，line 151-186）：

```python
@pytest.mark.django_db
def test_update_base_dn_resets_login_auth_to_pending_verification(monkeypatch):
    """AD login_auth.connection_template 含 base_dn 时，更新 base_dn 应重置 login_auth，
    不动 user_sync。回归 2026-07-13 spec。"""
    manifest = FakeManifest(
        instance_template=[
            FakeField("connection_url", required=True),
            FakeField("bind_dn", required=True),
            FakeField("bind_password", required=True),
        ],
        capabilities=[
            FakeCapability(
                "login_auth",
                connection_template=[
                    FakeField("base_dn", required=True),
                    FakeField("login_auth_identity_field", required=True),
                ],
            ),
            FakeCapability("user_sync", connection_template=[]),
        ],
    )
    patch_provider_registry(monkeypatch, manifest)

    instance = IntegrationInstance.objects.create(
        name="corp-ad",
        provider_key="ad",
        description="AD 集成",
        config={
            "connection_url": "ad.example.com",
            "bind_dn": "CN=svc,DC=corp,DC=example,DC=com",
            "bind_password": "secret",
            "base_dn": "DC=old,DC=example,DC=com",
            "login_auth_identity_field": "sAMAccountName",
        },
        status=IntegrationInstanceStatusChoices.READY,
        capability_status={
            "login_auth": IntegrationInstanceStatusChoices.READY,
            "user_sync": IntegrationInstanceStatusChoices.READY,
        },
    )

    serializer = IntegrationInstanceSerializer(
        instance=instance,
        data={
            "config_scope": "login_auth",
            "config": {"base_dn": "DC=new,DC=example,DC=com"},
        },
        partial=True,
    )

    assert serializer.is_valid(), serializer.errors
    updated = serializer.save()
    assert updated.capability_status["login_auth"] == IntegrationInstanceStatusChoices.PENDING_VERIFICATION
    assert updated.capability_status["user_sync"] == IntegrationInstanceStatusChoices.READY
```

- [ ] **Step 2: 验证测试通过（无生产代码改动）**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_integration_instance_serializer.py::test_update_base_dn_resets_login_auth_to_pending_verification -x -q --no-cov`

Expected: PASS（既有 serializer 已经基于 `field.reset_capabilities or [capability.key]` fallback 实现，无需改动代码）。

**如果测试失败**：说明 `FakeField` 默认 `reset_capabilities=None` 被 serializer 误读（line 137 的 `or [capability.key]` 应已兜底，但需 case-by-case 排查）。**不要**直接改 serializer 代码，先 `git diff` 既有 serializer 与新测试期望是否一致；如果有真实 bug，回到对应 spec/task 增量修复，不要在本任务扩散。

- [ ] **Step 3: Commit（需用户批准）**

```bash
git add server/apps/system_mgmt/tests/test_integration_instance_serializer.py
git commit -m "test(ad-login): lock PENDING reset on base_dn change"
```

**Verification:**
- [ ] `cd server && uv run pytest apps/system_mgmt/tests/test_integration_instance_serializer.py -x -q --no-cov` 全绿。
- [ ] 既有 `test_integration_instance_serializer_scoped_update_only_resets_target_capability` 等不退化。

---

### T5. 最终验证 + 手动集成检查

**Goal:** 跑全 server 测试，确认没有回归；在 dev 环境跑一次端到端：配 AD instance → 走 AD 登录认证链路，确认 `AD user not found` 错误消失。

**Files:**
- 不改文件

- [ ] **Step 1: 全 server 测试**

Run: `cd server && make test`

Expected: ALL PASS。注意收集 step 1-4 新增的 4 个 case 全部在列：
- `test_provider_manifest.py::test_ad_login_auth_connection_template_includes_base_dn_required`
- `test_ad_provider.py::test_build_connection_config_raises_when_base_dn_missing`（5 个 parametrize）
- `test_ad_provider.py::test_ad_authenticate_returns_invalid_config_when_base_dn_missing`
- `test_integration_instance_serializer.py::test_update_base_dn_resets_login_auth_to_pending_verification`

- [ ] **Step 2: 前端 lint + type-check（无改动但跑一遍）**

Run: `cd web && pnpm lint && pnpm type-check`

Expected: ALL PASS（前端零改动，但跑一遍排除意外回归）。

- [ ] **Step 3: 手动集成验证（dev 环境）**

按 [spec §4.3 验证命令](2026-07-13-ad-login-base-dn-restore-design.md)：

```bash
# 起 server + web（dev）
cd server && make dev       # :8011
cd web && pnpm dev          # :3000

# 浏览器操作：
# 1. 系统管理 → 集成中心 → 找到 AD provider → 详情页
# 2. 顶部「登录认证」Tab → 期望出现「登录搜索 Base DN」必填字段
# 3. 填入 DN（如 DC=bktest,DC=com,DC=cn）→ 保存
# 4. 顶部「测试连接」（针对 login_auth）→ 期望通过
# 5. 系统管理 → 用户同步 → 确认 sync source 已有 root_dn 且能拉人
# 6. 退出 admin → 用同步进来的 AD 用户走 AD 登录入口登录 → 期望成功拿 token
```

预期：
- 步骤 2：表单字段出现
- 步骤 4：测试连接返回成功（前提：service account 有读权限）
- 步骤 6：拿到 token 不再 "AD user not found"

**如果步骤 6 仍失败**：可能是 service account 在 base_dn 上读不到、identity_field 与输入不匹配、密码错。回到 [前面对话](2026-07-13-ad-login-base-dn-restore-design.md) 的排查清单。

- [ ] **Step 4: 最终汇总**

确认完成：
- 4 个新测试用例存在并 PASS
- `make test` 全绿
- `pnpm lint && pnpm type-check` 全绿
- 手动集成验证步骤 2/4/6 全部通过

- [ ] **Step 5: 不在本任务内提交（按用户要求保留手动提交）**

任务到此结束。等待用户对 PR 的 commit 节奏指示。

**Verification:**
- [ ] `cd server && make test` 0 failure
- [ ] `cd web && pnpm lint && pnpm type-check` 0 error
- [ ] 手动集成验证 3 个步骤全通过

---

## Self-Review

按 writing-plans skill 的 self-review 检查表对照 spec 复核一遍。

### 1. Spec coverage

| Spec 段落 | 覆盖任务 |
|---|---|
| §1 背景与回归根因 | （说明性，无需任务） |
| §2 Goals G1：manifest 加字段 | T1 |
| §2 Goals G2：`build_connection_config` 抛 `ValueError` | T2 |
| §2 Goals G3：合法 base_dn 下 AD 登录找到用户 | T5 step 3 |
| §2 Goals G4：base_dn 变化触发 login PENDING、user_sync 不动 | T4 |
| §2 Goals G5：防御下次回归（manifest + 后端双层） | T1 + T2 |
| §3.1 manifest 字段定义 | T1 step 3 |
| §3.2 `build_connection_config` 防御 | T2 step 3 |
| §3.2 `ad.py:94` 消息模板 | T3 step 3 |
| §3.3 数据流验证 | T5 step 3 |
| §4.1 T1 测试 | T1 step 1 |
| §4.1 T2 测试 | T2 step 1 |
| §4.1 T3 测试 | T3 step 1 |
| §4.1 T4 测试 | T4 step 1 |
| §5 运维 / 升级说明 | （文档性，无代码任务） |
| §6 决策记录 | （决策性，无代码任务） |
| §7 与 2026-07-02 spec 关系 | （背景性） |

无遗漏。所有 spec 要求映射到具体任务。

### 2. Placeholder scan

扫描全文无 TBD/TODO/「待补」「稍后」「类似 Task N」等占位。每个代码步骤的代码块完整给出。Parametrize 测试用例 5 个全部列出。

### 3. Type consistency

- `build_connection_config(config: dict[str, Any] | None)` → `LDAPConnectionConfig` 或抛 `ValueError` —— 在 T2 step 3 和 T3 step 1 中保持一致。
- `CapabilityExecutionResult.failed_result(message, code="provider.invalid_config", field=identity_field)` —— 在 T3 step 3 中保持，error code 与既有 spec 一致。
- `IntegrationInstanceStatusChoices.PENDING_VERIFICATION` / `READY` —— 在 T4 中沿用既有 import。
- `FakeManifest` / `FakeField` / `FakeCapability` / `patch_provider_registry` —— T4 step 1 中按既有模式使用，与 `test_integration_instance_serializer_scoped_update_only_resets_target_capability`（line 151-186）保持一致。

### 4. 一致性结论

无内部矛盾。Plan 与 spec 完全对齐。