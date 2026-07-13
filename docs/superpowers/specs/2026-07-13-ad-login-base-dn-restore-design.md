# 集成中心 · AD login_auth base_dn 恢复 Spec

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