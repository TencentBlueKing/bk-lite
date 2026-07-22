# Historical Superpowers change: 2026-07-13-ad-login-base-dn-restore

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-13-ad-login-base-dn-restore-plan.md

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

## specs: 2026-07-13-ad-login-base-dn-restore-design.md

**作者**：Agent (Claude Code)
**日期**：2026-07-13
**项目**：bk-lite 集成中心 / AD Provider / login_auth
**前置 Spec**：[2026-07-02-integration-center-ad-base-dn-relocation-spec](../2026-07-02-integration-center-ad-base-dn-relocation-spec.md)
**修复 Issue**：AD 用户经用户同步成功落库后，通过 AD 登录认证时报 "AD user not found"

---

## 0. 范围与读者

- **范围**：本 spec 仅恢复 AD provider 在 `login_auth.connection_template` 下被一并误删的 `base_dn` 字段 + 后端 `build_connection_config` 的 `ValueError` 防御。
- **读者**：后端（manifest / adapter / serializer）、测试、前端（动态表单自动消费 manifest）、运维（升级后行为变化）。
- **不**在本 spec 范围：
  - 不恢复 `IntegrationInstance.config.base_dn`（连接级，2026-07-02 已正确移除，本 spec 不动）
  - 不恢复 `UserSyncSource.business_config.base_dn`（业务护栏冗余字段，2026-07-02 已正确移除）
  - 不引入代码层 fallback（root_dn ⊂ base_dn 方向下不安全）
  - 不重做 2026-07-02 的「connection 与 sync 解耦」决策
  - 不做数据迁移（base_dn 是 JSONField key，DB 无 schema 变更）

---

## 1. 背景与回归根因

### 1.1 当前 bug 症状

集成实例配置 AD provider 后：

1. 走「用户同步」能力：`ADUserSyncAdapter.sync_users` 用 `business_config.root_dn` 拉用户成功，落到 `User` 表。
2. 走「AD 登录认证」能力：`ADLoginAuthAdapter.authenticate` 调用 `build_connection_config(config)` 拿到 `base_dn=""`，传给 `search_single_user` → ldap3 用空 `search_base` 搜索 → 返回 0 条 → 返回 `"AD user not found"`。

### 1.2 回归来源：2026-07-02 spec 的论证边界遗漏

[2026-07-02 spec](../2026-07-02-integration-center-ad-base-dn-relocation-spec.md) §1.2 中论证：

> "LDAP/AD 协议层（RFC 4511）：建立连接只需要 URL + bind 信息，**不需要** `base_dn`。"
> "`base_dn` 在协议层不需要，被当作应用层越界校验字段，是冗余的。"
> "**整个 AD provider 配置里不再出现 `base_dn` 字段**。"

这个论证**对连接建立过程**是对的（`bind` 不需要 base_dn），但**对 `search_single_user` 用的 search_base 是错的**：

- `ADLoginAuthAdapter.authenticate` 路径 `ad.py:75-77`：
  ```python
  connection_config = build_connection_config(config)
  user = search_single_user(connection_config, identity_field, username, AD_LOGIN_ATTRIBUTES)
  ```
- `search_single_user` 在 `adapters/common/ldap.py:147-159` 用 `connection_config.base_dn` 作 `search_base` 传给 ldap3。

**LDAP 协议层 RFC 4511 §4.5.1.2 `SearchRequest.searchBase`**：search 操作必须有 `searchBase`，不能为空（DSE 不是用户对象容器）。`base_dn` 在 login_auth 路径上是**协议层必需字段**，不是应用层冗余校验。

2026-07-02 spec 删除 `base_dn` 时只看到"bind 不需要"，没有 grep 出 `search_single_user` 的 `search_base` 实际取值路径。这是边界遗漏。

### 1.3 双重范围区分

| 范围 | 字段 | 2026-07-02 决策 | 现状 | 本 spec 决策 |
|---|---|---|---|---|
| 连接建立（bind） | `IntegrationInstance.config.base_dn` | 移除 | 已移除 | **保持移除**（bind 不需要）|
| 同步搜索（`search_entries`） | `UserSyncSource.business_config.root_dn` | 保留单值 | 保留 | **不动** |
| **登录搜索（`search_single_user`）** | `IntegrationInstance.config.base_dn`（login_auth） | **被一并误删** | **缺失** | **本 spec 恢复，仅在 `login_auth.connection_template` 下** |

注意 `1.2 节` 提到的 `is_sub_dn(root_dn, base_dn)` 业务护栏随 2026-07-02 已废弃，本 spec 不复活。

---

## 2. Goals / Non-Goals

### 2.1 Goals

| # | 描述 | 验收点 |
|---|---|---|
| G1 | AD IntegrationInstance 在 `login_auth.connection_template` 下重新出现 `base_dn` 字段，必填 | `manifests/ad.py` `login_auth.capabilities[0].connection_template` 含 `key="base_dn"`、`required=True` |
| G2 | `build_connection_config` 在 `base_dn` 为空（含缺省、`None`、`""`）时抛 `ValueError`，错误信息含 "base_dn" | 单测覆盖三种空形态；ad.py:94 现有 `except ValueError` 分支接住后返回 `provider.invalid_config` |
| G3 | 修当前 bug：合法 `base_dn` 配置下 AD 登录可以找到用户 | 手动：集成中心填 base_dn → 测试连接 → AD 用户登录返回 token |
| G4 | 修改 `base_dn` 后 `capability_status["login_auth"]` 自动变 PENDING_VERIFICATION（要求重测），`user_sync` 不动 | 单测覆盖 |
| G5 | 防御下次回归：manifest 误删 `base_dn` 会在前端表单校验 + 后端 adapter 入口两处失败，不再静默 | 前端保存时拦截；后端 `LDAPConfigurationError` / `ValueError` 抛出 |

### 2.2 Non-Goals

- 不为 base_dn 引入多值字段（仍是单值 string）
- 不改 `ADUserSyncAdapter`（它不读 base_dn）
- 不引入代码层 fallback 到 `root_dn`（DN 方向是 root_dn ⊂ base_dn，fallback 会扩大/缩小语义不一致）
- 不恢复连接级 `IntegrationInstance.config.base_dn`（2026-07-02 已正确移除）
- 不恢复 `UserSyncSource.business_config.base_dn`（2026-07-02 已正确移除）
- 不做历史 IntegrationInstance 数据回填（用户确认不需要考虑本地数据兼容性）
- 不改前端组件（动态表单按 manifest 自动渲染）
- 不修改 `reset_capabilities` 显式声明（依赖 schema `or [capability.key]` fallback）

---

## 3. 设计变更

### 3.1 Manifest 增字段（核心）

**文件**：`server/apps/system_mgmt/providers/manifests/ad.py`

**位置**：`capabilities[login_auth].connection_template`，在 `login_auth_identity_field` **之前**插入：

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

**UI 落点（集成中心详情页 Tab 布局）**：

集成中心详情页（`web/src/app/system-manager/(pages)/integration-center/detail/page.tsx`）按 `INTEGRATION_DETAIL_TAB_ORDER = ['base', 'user_sync', 'login_auth', 'im_notification']`（`utils/integrationCenter.ts:17`）渲染 Tab。每个 Tab 字段来源：

- **「基础连接」tab**：`provider.instance_template`（即 `base_connection` group）—— 不含 `base_dn`
- **「用户同步」tab**：`user_sync.capability.connection_template` —— 不含 `base_dn`（同步字段 `root_dn` 在另一处配置，见下文）
- **「登录认证」tab**：`login_auth.capability.connection_template` —— **新增 `base_dn` 字段就在这里**

Tab 字段源逻辑（`detail/page.tsx:60-63`）：

```ts
const activeFields = useMemo(
  () => (activeTab === 'base'
    ? provider?.instance_template || []
    : activeCapability?.connection_template || []),
  ...
);
```

**运维动线**：系统管理 → 集成中心 → 选中 AD IntegrationInstance → 顶部「登录认证」Tab → 出现「登录搜索 Base DN」必填字段。

**注意区分**：同步范围字段 `root_dn` **不在这个详情页**，它在「系统管理 → 用户同步 → 新建/编辑同步源」表单（独立的 `UserSyncConfigModal`）里。`base_dn` 和 `root_dn` 两个 DN 字段分属不同页面、各管各的 scope，不要混淆。

**字段属性决策**：

- `required=True`：前端表单必填。前端校验拦住静态误删。
- 无 `default`：DN 是环境相关，无默认值；空字符串触发后端 `ValueError`。
- `placeholder="DC=example,DC=com"`：仅示例，提示 DN 语法格式。
- `help_text`：明确区分 `base_dn` 与 `root_dn`，降低再次混淆风险。
- **不写** `reset_capabilities`：靠 `schemas.py:23` 字段定义 + `integration_instance_serializer.py:137` 的 `field.reset_capabilities or [capability.key]` fallback，自动得到 `["login_auth"]`——base_dn 变 → login 被打回 PENDING_VERIFICATION 重测；user_sync 不动。

### 3.2 `build_connection_config` 防御性校验

**文件**：`server/apps/system_mgmt/providers/adapters/common/ldap.py`

**改动**：在 `build_connection_config` 函数体最前加空值校验。

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

**异常传播路径**：

`build_connection_config` 抛 `ValueError` → 流入 `ad.py:75-120` 的 `try` 块 → **被现有 `ad.py:94` `except ValueError` 接住** → 返回 `failed_result(...)`。

**`ad.py:94` 现有 except 的语义改动**：

当前实现：

```python
except ValueError:
    return CapabilityExecutionResult.failed_result(
        "AD user search returned multiple matches",
        code="provider.auth_failed",
        field=identity_field,
    )
```

**改为**：

```python
except ValueError as error:
    return CapabilityExecutionResult.failed_result(
        f"AD login_auth configuration error: {error}",
        code="provider.invalid_config",
        field=identity_field,
    )
```

**改动影响**：
- `search_single_user` 多匹配抛 `ValueError("Expected a single LDAP user for 'sAMAccountName', got 3")` → 消息变为 `"AD login_auth configuration error: Expected a single LDAP user for 'sAMAccountName', got 3"`，code `provider.invalid_config`（从 `auth_failed` 变 `invalid_config`，语义更准——多匹配本就是配置/data 问题）
- `build_connection_config` 空 base_dn 抛 `ValueError("AD login_auth.base_dn is required but missing; ...")` → 消息直接包含，code `provider.invalid_config`

**简化决策**（避免引入自定义异常类）：
- B1 备选方案：自定义 `LDAPConfigurationError` 异常 + ad.py 增加 catch 分支（语义更精确）
- **采纳 B2**：复用现有 `ValueError` + 现有 `except ValueError` 分支 + 改消息模板。理由：单点改动、不引入新类、不动 catch 顺序。错误日志在 `except Exception` 上游 `logger.exception` 已保留，运维追溯路径完整。

### 3.3 数据流（修复后）

```
新建/编辑 AD IntegrationInstance
  ↓ 前端动态表单（manifest 驱动）
  ↓
填 base_dn（必填） + login_auth_identity_field + 其他字段
  ↓
POST/PUT config JSON to IntegrationInstance.config
  ↓
保存成功（manifest.required 校验已拦截）
  ↓
AD 用户登录
  ↓
login_with_binding() → runtime_service.execute()
  ↓ config = instance.get_runtime_config()  ← 含 base_dn
ADLoginAuthAdapter.authenticate(config)
  ↓
build_connection_config(config)              ← base_dn 非空，正常构造 LDAPConnectionConfig
search_single_user(connection_config, identity_field, username, ...)
  ↓ connection_config.base_dn 作 search_base
ldap3 connection.search(search_base=..., search_filter=...)
  ↓
找到用户 → bind_user_dn 验证密码 → success
```

**base_dn 缺失时的失败路径**（防御）：

```
build_connection_config({})
  ↓ base_dn="" → 抛 ValueError("AD login_auth.base_dn is required but missing; ...")
except ValueError as error
  ↓ 返回 failed_result("AD login_auth configuration error: AD login_auth.base_dn is required but missing",
                       code="provider.invalid_config")
前端 toast 提示明确：base_dn 配置缺失，而不是迷向的 "AD user not found"
```

---

## 4. 测试计划

### 4.1 新增用例

| ID | 文件 | 用例名 | 覆盖 |
|---|---|---|---|
| T1 | `server/apps/system_mgmt/tests/test_provider_manifest.py` | `test_ad_login_auth_connection_template_includes_base_dn_required` | manifest 加载后 `login_auth.connection_template` 含 `key="base_dn"`、`required=True`、无 `default`、`placeholder` 非空 |
| T2 | `server/apps/system_mgmt/tests/test_ad_provider.py` | `test_build_connection_config_raises_when_base_dn_missing` | `build_connection_config({})` / `{"base_dn": ""}` / `{"base_dn": None}` 三种空形态都抛 `ValueError`，错误信息含 "base_dn" |
| T3 | `server/apps/system_mgmt/tests/test_ad_provider.py` | `test_ad_authenticate_returns_invalid_config_when_base_dn_missing` | `ADLoginAuthAdapter.authenticate(config={}, username="x", password="y")` 返回 `failed_result`，`code="provider.invalid_config"`，`message` 含 "base_dn" |
| T4 | `server/apps/system_mgmt/tests/test_integration_instance_serializer.py` | `test_update_base_dn_resets_login_auth_to_pending_verification` | 更新 AD instance 且 `config.base_dn` 变化时，`capability_status["login_auth"]` 变 `PENDING_VERIFICATION`，`capability_status["user_sync"]` 不变 |

### 4.2 不动的既有测试

- `test_provider_manifest.py::test_ad_user_sync_manifest_exposes_directory_query_parameters`：2026-07-02 spec §7.1 已调整为不含 base_dn，本 spec 不动。
- `test_ad_provider.py::test_test_connection_passes_when_base_dn_absent`：2026-07-02 spec §7.2 验证 test_connection 不依赖 base_dn（本 spec 范围内 test_connection 也不依赖），保持通过。
- `test_ad_provider.py::test_sync_users_fails_when_root_dn_absent`：root_dn 必填保留。

### 4.3 验证命令

```bash
cd server && make test                                  # 全 server 测试
cd web && pnpm lint && pnpm type-check                  # 前端 lint（无改动但跑一遍）
# 手动：起服 → 集成中心 → AD provider → 必填 base_dn → 配 user_sync root_dn
# → 跑 user_sync → 用同步进来的用户走 AD 登录 → 期望拿到 token，不再 "AD user not found"
```

覆盖率门槛 ≥ 75%（沿用 `server/.pre-commit-config.yaml`）。

---

## 5. 运维 / 升级说明

### 5.1 升级后行为变化

| 行为 | 升级前 | 升级后 |
|---|---|---|
| 集成中心 AD provider 详情页「登录认证」Tab 下「登录搜索 Base DN」字段 | 不存在 | 出现，必填，placeholder `DC=example,DC=com` |
| AD 登录认证（base_dn 缺失） | 静默通过 → LDAP 返 0 条 → 迷惑的 "AD user not found" | 立即抛 `ValueError` → `provider.invalid_config`，消息含 "base_dn" |
| 修改 `base_dn` | 不存在 | login capability 自动 PENDING_VERIFICATION，user_sync 不动 |
| 历史 AD IntegrationInstance 无 `base_dn` | （已无法登录，bug 状态） | 配置页打开后强制要求填 base_dn 才能保存 |

### 5.2 历史数据

- 不做 Django data migration，不清理 DB JSONField 残留。
- 升级后首次打开历史 AD IntegrationInstance 配置页：表单要求填 base_dn，保存即生效。
- 用户已确认不需要考虑本地数据兼容性。

### 5.3 回滚

- 本 spec 是新增字段 + 加防御校验，回滚等价于「删除 manifest 字段 + revert `build_connection_config` 校验 + revert `ad.py:94` 消息变更」。revert 即可，无 DB schema 依赖。
- Pre-merge：单测失败即 revert。
- Post-merge：revert PR 即生效，无需 feature flag。

---

## 6. 决策记录

| 决策 | 选项 | 取舍 | 理由 |
|---|---|---|---|
| `base_dn` 放 manifest 哪里 | A. `base_connection`（连接级） / **B. `login_auth.connection_template`（login 专属）** / C. `login_auth_form`（业务模板） | ✅ **B** | `base_dn` 是 login 专属，A 被 `reset_capabilities:["user_sync"]` 误伤，C 与 LoginAuthBinding 业务字段错位 |
| 是否显式写 `reset_capabilities` | 显式 `["login_auth"]` vs **不写（fallback `[capability.key]`）** | ✅ **不写** | schemas.py:23 + serializer:137 fallback 自动得到 `["login_auth"]`，与现有 `login_auth_identity_field` 风格一致 |
| `default` 是否给 | 给默认值 vs **不给** | ✅ **不给** | DN 环境相关，无意义；空串触发 ValueError 早暴露 |
| `placeholder` 是否给 | 不给 vs **给示例** | ✅ **给** | 仅作格式提示，不参与运行时 |
| `required` 标 True | False vs **True** | ✅ **True** | 前端表单必填，缺则保存失败 |
| 后端防御异常类型 | `ValueError`（B2） vs 自定义 `LDAPConfigurationError`（B1） | ✅ **B2** | 单点改动；不改 catch 顺序；不改 `ad.py:94` 现有 except 块语义（仅消息模板）；新增异常类不必要 |
| 是否引入代码层 fallback 到 root_dn | fallback vs **不引入** | ✅ **不引入** | DN 方向 root_dn ⊂ base_dn，fallback 会缩小登录范围（其他部门用户登不上），违反 2026-07-02 决策精神（连接/sync 解耦） |
| 是否做历史数据回填 | 回填 vs **不回填** | ✅ **不回填** | 用户明确本地不需要数据兼容性；DB JSONField 无需迁移；强制前端填回即可 |

---

## 7. 与 2026-07-02 spec 的关系

| 范围 | 2026-07-02 决策 | 本 spec 决策 | 关系 |
|---|---|---|---|
| `IntegrationInstance.config.base_dn`（连接级） | 移除 | **保持移除** | 一致：bind 不需要 |
| `UserSyncSource.business_config.base_dn` | 移除 | **保持移除** | 一致：`root_dn` 单值已足够 |
| `UserSyncSource.business_config.root_dn` | 保留单值 string | **不动** | 一致 |
| `IntegrationInstance.config.base_dn`（login_auth capability 级） | **被一并误删（边界遗漏）** | **本 spec 恢复** | 修复回归 |
| `is_sub_dn(root_dn, base_dn)` 业务护栏 | 移除 | **保持移除** | 一致 |
| 「同 instance 多 source」承接多 OU | 引入 | **不动** | 一致 |

**对 2026-07-02 spec 的修正声明**：

2026-07-02 spec §1.2 关于「RFC 4511 不需要 base_dn」的论证**只对 bind 路径成立**，对 search 路径（`search_single_user` 用的 `search_base`）不成立。RFC 4511 §4.5.1.2 `SearchRequest.searchBase` 是协议层必需字段，不是应用层冗余校验。本 spec 是这一论证遗漏的边界修复，不挑战 2026-07-02 主体决策（连接/sync 解耦、`base_dn` 整体废弃的方向）。

---

## 8. 风险与副作用

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 漏改 `ADUserSyncAdapter` 引入回归 | 低 | sync 路径不受影响 | 单测覆盖；ADUserSyncAdapter 不读 base_dn |
| 升级后历史 instance 登不上（缺 base_dn） | 高（已知 bug 状态） | 已无法登录，升级后强制填回即可 | 前端表单必填；保存即生效 |
| `ad.py:94 except ValueError` 消息变 → 多匹配错误文案变化 | 低 | 多匹配场景很少见；新文案仍准确 | 既有 UI 处理 `failed_result` 不变 |
| `reset_capabilities` fallback 行为不被理解 | 低 | 字段变 → login 自动 PENDING_VERIFICATION；user_sync 不动 | 帮助运维理解 manifest 设计意图的注释（可选，不在本 spec 强制） |

---

## 9. 实施步骤（Tasks）

1. **T1：Manifest 增字段**
   - `server/apps/system_mgmt/providers/manifests/ad.py` `capabilities[login_auth].connection_template` 内 `login_auth_identity_field` 之前插入 `base_dn` 字段。
2. **T2：`build_connection_config` 防御**
   - `server/apps/system_mgmt/providers/adapters/common/ldap.py` 加 base_dn 空值校验，抛 `ValueError`。
3. **T3：`ad.py:94` 消息模板调整**
   - `server/apps/system_mgmt/providers/adapters/ad.py` line 94 `except ValueError` 改为 `except ValueError as error`，返回消息模板改为 `f"AD login_auth configuration error: {error}"`，code 改为 `provider.invalid_config`。
4. **T4：测试**
   - T1/T2/T3/T4 四个 case（见 §4.1）。
5. **T5：手动验证**
   - 起服 → 集成中心 AD provider 验证表单出现 base_dn 字段 → 跑测试登录。
6. **T6：PR 合 master**
   - 跑 `make test`（server）+ `pnpm lint && pnpm type-check`（web，无改动但跑一遍）；CI 通过后合入。

---

**版本**：v1.0 · 恢复 login_auth base_dn 字段 + 后端防御
**对应 issue**：本次会话诊断（"AD user not found"，回归自 2026-07-02 spec）
**下一步**：spec 通过审阅后进入 writing-plans 流程生成实施计划
