# 集成中心 · AD Provider 解耦改造 Spec

**作者：** Agent (Claude Code)
**日期：** 2026-07-02
**项目：** bk-lite 集成中心 / AD Provider
**涉及产品：** `系统管理 / 集成中心 / 用户同步`
**对应 PRD：** 见下方

---

## 0. 范围与读者

- **范围**：本 spec 仅覆盖**集成中心 AD provider** 移除冗余 `base_dn` 字段、不影响飞书/钉钉/企业微信等其他 provider。
- **读者**：后端（Django, LDAP adapter, capability contract）、前端（Next.js 表单、动态表单组件）、测试（`make test` 通过率）、运维（升级期 schema 升级 / 旧实例兼容）。
- **不**在本 spec 范围：
  - 服务账号在 AD 上的 ACL 治理建议（运维文档另开）；
  - `connection_url` / `bind_dn` 等其他连接字段的语义变更；
  - 非 AD provider 的改造（如 LDAP / OpenLDAP）；
  - `WechatWork` / `Feishu` 等同步策略的字段变更。

---

## 1. 背景与现状

### 1.1 现状（**改造前**的 schema）

```
IntegrationInstance (ad) ← 集成实例
  config:        connection_url, ssl_encryption, timeout, bind_dn, bind_password, base_dn   ← 一份「一份连接」配置
UserSyncSource (ad)    ← 同步源（可建多个）
  business_config: root_dn, base_dn, user_object_class, user_filter, organization_object_class
```

### 1.2 痛点

1. **多 OU 重复配置**：
   - 同一 AD 域下若需要同步 `OU=Users,DC=bktest,DC=com,DC=cn` **与** `OU=Users,DC=main,DC=com,DC=cn` 两棵子树，必须**新建两个 IntegrationInstance**，重复填写 host / bind_dn / bind_password / ssl / timeout 等 5 个完全相同的连接字段。
   - 运维成本：N 个 OU → N 份 95% 重复配置。
   - 安全维护成本：服务账号密码轮转需逐个实例更新。

2. **`base_dn` 字段冗余**：
   - 现有 schema 中 `base_dn` 在 `instance_templates.base_connection`，`required=True`。
   - LDAP/AD 协议层（RFC 4511）：建立连接只需要 URL + bind 信息，**不需要** `base_dn`。
   - 即使在 sync source 层，`base_dn` 也只是 **「应用层越界校验」** 的字段，不发到 LDAP。`root_dn` 字符串本身就完整携带了"同步起点 + 范围声明"两层语义。**再造一个 `base_dn` 字段是冗余的**——它不发网络包、不进 LDAP，只在应用层被 `is_sub_dn(root_dn, base_dn)` 复述一次用户已经表达过的意图。
   - 当前 adapter 又把它当「连接是否完整」的硬校验项（`adapters/ad.py:148-159`），导致协议上根本不依赖的东西变成了「不能工作」的强约束。

3. **业内参考（bk-user `weops-4.x`）**：
   - bk-user 的 schema 同样有这个问题：`base_dn`（死字段）和 `basic_pull_node`（运行时的 search_base 来源）共存。
   - bk-user 选择保留 `basic_pull_node`、**没有**完全清理 `base_dn` 历史残留，这是它当前的不彻底状态。
   - 本 spec 选择比 bk-user 更彻底：**整个 AD provider 配置里不再出现 `base_dn` 字段**。

### 1.3 改造目标

| 目标 | 描述 | 验收点 |
|------|------|--------|
| **G1：连接与同步范围解耦** | 「连接实例」只承担连接职责；「同步源」承担同步范围职责 | 同一 IntegrationInstance 配 N 个 UserSyncSource，每个 source 自定义 `root_dn` |
| **G2：移除 base_dn 字段** | 集成中心 AD provider 的 manifest、adapter、serializer 一律不再有 `base_dn` 字段 | `manifests/ad.py` 不出现 `base_dn` 字面提及；adapter 与 serializer 不读 `base_dn` |
| **G3：root_dn 保持单值** | `root_dn` 不引入多值；多 OU 走「同 instance 多 source」 | `root_dn` 仍是单一字符串；不改 field_type |
| **G4：零侵入清理旧数据** | 旧 `integration.config.base_dn` 数据从 DB 中安全清理；旧 sync source 的 root_dn 仍按单值跑 | 启动期一次性 `config.pop("base_dn", None)`；新字段维护期短（一次性 Django data migration） |
| **G5：辅助字段收口** | `user_object_class` / `user_filter` / `organization_object_class` 保持可空走默认 | manifest 已是当前态：`required: False` + 用途描述 help_text |

---

## 2. 数据模型变更

### 2.1 IntegrationInstance.config（删除 base_dn）

```diff
 {
   "connection_url": "...",
   "ssl_encryption": "...",
   "timeout": 10,
   "bind_dn": "...",
-  "bind_password": "...",
-  "base_dn": "DC=example,DC=com"
+  "bind_password": "..."
 }
```

> 整个实例级 `base_dn` 字段删除。详细迁移路径见 §6。

### 2.2 UserSyncSource.business_config（不引入 base_dn）

```diff
 {
-  "root_dn": "OU=Users,DC=example,DC=com",
-  "base_dn": "DC=example,DC=com",
+  "root_dn": "OU=Users,DC=example,DC=com",
   "user_object_class": "user",        // 默认
   "user_filter": "(&(objectCategory=Person)(sAMAccountName=*))",  // 默认
   "organization_object_class": "organizationalUnit"                 // 默认
 }
```

**最终字段语义**：

| 字段 | 必填 | 默认 | 类型 | 说明 |
|------|------|------|------|------|
| `root_dn` | ✅ | — | `str` | 同步起点；**单值字符串**；为空或空白则同步失败。**字符串本身即是「同步起点 + 范围声明」**，不再附加 `base_dn` 业务护栏字段 |
| `user_object_class` | ❌ | `user` | `str` | 上一阶段已改造为可空 |
| `user_filter` | ❌ | `(&(objectCategory=Person)(sAMAccountName=*))` | `str` | 同上 |
| `organization_object_class` | ❌ | `organizationalUnit` | `str` | 同上 |

> **设计决定：`root_dn` 永远保持单值字符串，不引入 list / `\|\|` 多值；`base_dn` 字段彻底不在 bk-lite AD provider 出现。**
> 多 OU 同步的解法是：**同一个 IntegrationInstance 下建多个 UserSyncSource，每个 source 填各自的 `root_dn`**——一份 AD 连接服务 N 份同步任务。这是「connection 与 sync 解耦」的核心收益。

---

## 3. 接口契约

### 3.1 Provider Manifest（`server/apps/system_mgmt/providers/manifests/ad.py`）

#### 改动 A：删除 `instance_templates.base_connection` 中的 `base_dn`

```python
{
    "key": "base_connection",
    "groups": [
        {
            "key": "connection",
            "fields": [
                {"key": "connection_url", ...},
                {"key": "ssl_encryption", ...},
                {"key": "timeout", ...},
                {"key": "bind_dn", ...},
                {"key": "bind_password", "secret": True, ...},
                # base_dn 整段删除
            ],
        }
    ],
},
```

#### 改动 B：`user_sync_form` 不引入 `base_dn`；`root_dn` 保持单值 `string`

```python
{
    "key": "scope",
    "title": "同步范围",
    "fields": [
        {
            "key": "root_dn",
            "label": "同步起始目录",
            "field_type": "string",
            "required": True,
            "placeholder": "OU=Users,DC=example,DC=com",
            "input_mode": "manual_input",
            # 现状单值；不引入多值、不引入 base_dn
        },
        {"key": "user_object_class",  ...},  # 现状
        {"key": "user_filter",        ...},  # 现状
        {"key": "organization_object_class", ...},  # 现状
    ],
},
```

> 同步范围字段**仅 `root_dn` 一项**。`base_dn` 字段从 AD provider 配置中彻底移除。

### 3.2 Capability Contract 校验（`server/apps/system_mgmt/services/capability_contract_service.py`）

`validate_user_sync_contract` 在遇到 AD 业务参数时仅校验：

1. `root_dn` 必填（单值字符串，非空）。

> 不再有 `is_sub_dn(root_dn, base_dn)` 校验规则；不存在 base_dn 字段。

### 3.3 API 行为变化（对客户端透明）

| API | 行为 |
|-----|------|
| `POST /api/system_mgmt/integration_instance/` | `config.base_dn` 不再被接受（后端静默忽略 / 不写回 DB）；manifest 上根本不再有该字段 |
| `PATCH /api/system_mgmt/integration_instance/<id>/` | 同上 |
| `POST /api/system_mgmt/user_sync_source/` | `business_config.root_dn` 必填；不存在 `business_config.base_dn` |
| `PATCH /api/system_mgmt/user_sync_source/<id>/` | 同上 |
| `GET /api/system_mgmt/user_sync_source/` | 返回 `business_config` 仅含 `root_dn` 三件套（不含 base_dn） |

---

## 4. AD Adapter 行为变更

文件：`server/apps/system_mgmt/providers/adapters/ad.py`

### 4.1 移除「连接级 base_dn 校验」+ 「单 root_dn」主流程

#### 改动 A：`test_connection`

```python
@classmethod
def test_connection(cls, config, provider_key, capability_key, **kwargs):
    try:
        connection_config = build_connection_config(config)
        # base_dn 完全不参与连接完整性校验
        if not all([
            connection_config.connection_url,
            connection_config.bind_dn,
            connection_config.bind_password,
        ]):
            return CapabilityExecutionResult.failed_result(
                "AD connection configuration is incomplete",
                code="provider.invalid_config",
            )
        probe_root_dse(connection_config)
    except Exception as error:
        ...
```

#### 改动 B：`sync_users` 主流程（单 root_dn，无 base_dn）

```python
def sync_users(cls, config, provider_key, capability_key, **kwargs):
    source = kwargs.get("source")
    business_config = getattr(source, "business_config", None) or {}

    user_object_class        = cls._get_business_config_value(business_config, "user_object_class", cls.DEFAULT_USER_OBJECT_CLASS)
    user_filter              = cls._get_business_config_value(business_config, "user_filter", cls.DEFAULT_USER_FILTER)
    organization_object_class = cls._get_business_config_value(business_config, "organization_object_class", cls.DEFAULT_ORGANIZATION_OBJECT_CLASS)

    root_dn = str(business_config.get("root_dn") or "").strip()
    if not root_dn:
        return CapabilityExecutionResult.failed_result(
            "AD user sync root_dn is required",
            code="provider.invalid_config",
            field="root_dn",
        )

    try:
        connection_config = build_connection_config(config)
        if not all([
            connection_config.connection_url,
            connection_config.bind_dn,
            connection_config.bind_password,
        ]):
            return CapabilityExecutionResult.failed_result(
                "AD connection configuration is incomplete",
                code="provider.invalid_config",
            )

        user_entries = search_entries(
            connection_config, root_dn,
            cls._build_object_search_filter(user_object_class, user_filter),
            AD_LOGIN_ATTRIBUTES, paged_size=100,
        )
        organization_entries = search_entries(
            connection_config, root_dn,
            cls._build_object_class_filter(organization_object_class),
            ["distinguishedName"], paged_size=100,
        )
    except Exception as error:
        ...

    group_map: dict[str, dict] = {}
    user_list = []
    for user_entry in user_entries:
        normalized_user = cls._normalize_sync_user(user_entry)
        distinguished_name = normalized_user["distinguishedName"]
        if not distinguished_name:
            continue
        department_ids = cls._collect_department_dns(distinguished_name, root_dn)
        normalized_user["department_ids"] = department_ids or [root_dn]
        user_list.append(normalized_user)

        for group_entry in cls._build_group_entries(normalized_user["department_ids"], root_dn):
            group_map[group_entry["id"]] = group_entry

    for group_entry in cls._build_organization_group_entries(organization_entries, root_dn):
        group_map[group_entry["id"]] = group_entry

    group_list = sorted(group_map.values(), key=lambda item: (item["parent_id"], item["id"]))
    return CapabilityExecutionResult.success_result(
        "AD user sync payload prepared",
        payload={"group_list": group_list, "user_list": user_list},
    )
```

> 与原始实现的差异：**`base_dn` 在所有路径上不再被读写**；`root_dn` 仍按单值字符串处理。多 OU 同步的解法不在此处扩展，靠「同 instance 多 source」承接。

### 4.2 schema 迁移期兼容

迁移期兼容由 **Serializer + 启动期 Django 迁移**（§6）协同完成；**Adapter 不做兼容读取**。这是故意的——

- 让 Adapter 单一职责（运行）；
- 让 Serializer 单一职责（写校验 + 兼容期读取）。

---

## 5. 前端

### 5.1 改造点

| 位置 | 改动 |
|------|------|
| 集成中心「基础连接」表单 | 删除「目录访问边界」输入项 |
| 集成中心「用户同步」表单 | **不**新增字段；保留 4 个原字段（同步起始目录 + 三件套） |
| i18n（zh.json / en.json） | 删除 `catalog/baseDn` 等 key（如存在）|
| `userSyncUtils.ts` | `getUserSyncBusinessConfigDefaults` 不含 `base_dn` |
| `UserSyncConfigFields.tsx` | 不动 |
| 多 OU 场景 | 在「用户同步」列表「同一 IntegrationInstance」行下提供「**新建同步源**」入口 |

### 5.2 字段类型

**没有**新增 `field_type`，也没有删除字段（manifest 上本来要删的 base_dn 整段已经不存在）。零前端组件改动。

### 5.3 UX 行为

- 「集成中心详情」tab：基础连接里 **不再**显示「目录访问边界」。
- 「用户同步」配置：**只有 4 个字段**（同步起始目录 + 三件套），与改造前相比少一个。
- 「同步起始目录」**单值**输入框不变。
- 多 OU 同步：在「用户同步」列表「同一 IntegrationInstance」行下提供「**新建同步源**」按钮，点击即在当前 instance 下新增一份 UserSyncSource；可在两份 source 间共用同一份连接。

---

## 6. 兼容性与运维说明

### 6.1 数据迁移：**本 spec 不做**

`base_dn` 字段是 `IntegrationInstance.config` / `UserSyncSource.business_config` 这两个 **JSONField 里的一个 key**，**不是** DB 的列；本 spec 把所有"读 `base_dn`"的代码路径移除即可，**不**写 Django data migration，**不**批量清理存量 JSON 里的 `base_dn` 键。

升级后存量 JSON 里残留的 `base_dn` 字段是「无害的尸体」：
- 不会被任何运行时代码读
- 序列化器不再校验它
- 前端 UI 不再展示它
- 等同于「存在但完全无影响」

> 显式声明：本 spec 不提供 `0009_drop_ad_base_dn` 之类的 Django migration。如运维需要清理存量 JSON（出于节省存储 / 审计可读性等考虑），由运维另起一次性 `manage.py shell` 任务维护，**不**是本 spec 的契约范围。

### 6.2 兼容性（这是 breaking change，不是 silent-tolerance）

| 项 | 行为 |
|---|------|
| DB 中已有 `base_dn` 残留 | 不清理、不报错、不影响功能（运行时没有任何代码读它） |
| 旧 API 客户端携带 `config.base_dn` / `business_config.base_dn` POST 请求 | **400** `Unsupported user_sync business config fields: base_dn`；`validate_user_sync_contract` 的白名单校验拒绝任何 manifest 未声明的字段 |
| 升级窗口期（API 升级而 UI 还没升级） | 旧版 UI 仍会让用户填 `base_dn`；POST 时会被 400 拒绝；必须 UI 与 API **协调升级** |

> **设计决定：本 spec 不做 silent-tolerance。** 严格白名单是 contract 层既有的数据治理策略（"DB 里的 business_config 永远只含 manifest 声明的字段"），是值得保留的防线。silent-tolerance 看似友好，但会绕过这道防线、给未来 schema 演进留下隐患。
>
> 正常升级路径（前后端同时升级）下，新 UI 不会再渲染 `base_dn` 字段，POST 自然不会带 `base_dn`，strict 白名单不会触发。silent-tolerance 真正能防御的只是"老 API 脚本 / 老版 UI 在升级后还跑"这种 niche 场景，得不偿失。

### 6.3 backward incompatibilities（突破式变更）

| 项 | 影响范围 | 缓解 |
|---|---------|------|
| 集成中心 AD provider 配置不再有 `base_dn` 字段（UI 上） | 运维用户不再填这个字段 | 表单字段直接移除 |
| **API 中 `business_config.base_dn` / `config.base_dn`** | **会 400**（contract 严格白名单）；旧 API 客户端必须停止发送 `base_dn` | 升级文档（`docs/operations.md`）明确写「升级后带 base_dn 的请求会 400」；运维需协调 API 与 UI 同步升级 |
| 多 OU 场景 | 不再需要 `root_dn` 多值；改由「同 instance 下建立多个 UserSyncSource」承接 | UI「新建同步源」按钮 + 文档 |

> 显式声明：**不**在 `root_dn` 上引入多值字段；`base_dn` 字段在 bk-lite AD provider 配置里**整体废弃**。

---

## 7. 测试计划

### 7.1 现有测试断言

| 文件 | 断言 | 是否需要修改 |
|------|------|-------------|
| `test_provider_manifest.py::test_ad_user_sync_manifest_exposes_directory_query_parameters` | `field_map` 含 4 个字段（不再含 base_dn） + 3 个 default | **是**：调整为 `["root_dn", "user_object_class", "user_filter", "organization_object_class"]`；移除 `base_dn` 在 `base_connection` 处的检查（若存在） |
| `test_ad_provider.py` | 默认 filter 拼装 / `root_dn` 单值 | **新增**：见 §7.2 |
| `test_user_sync_source_viewset.py` | 序列化器校验路径 | **删除**：base_dn 相关断言；保留 root_dn 必填断言 |

### 7.2 新增用例（最小集合）

| 文件 | 用例 | 覆盖 |
|------|------|------|
| `test_ad_provider.py` | `test_test_connection_passes_when_base_dn_absent` | 移除 base_dn 连接级校验后，`integration.config.base_dn` 缺失时 `test_connection` 仍 `success` |
| `test_ad_provider.py` | `test_sync_users_fails_when_root_dn_absent` | `root_dn` 为空时同步失败（保留既有行为） |

> 不再有 `is_sub_dn` / base_dn 业务护栏相关用例——schema 上 base_dn 字段整体废弃。

### 7.3 验证命令

```bash
cd server && make test
cd web && pnpm lint && pnpm type-check
# 手动：起服 → 集成中心 → 配 AD（基础连接无 base_dn） → 配同步源（仅 root_dn） → 跑同步 → 验结果
# 多 OU 场景：同 instance 下新建两份 source，每份各自 root_dn，验分别拉
```

覆盖率 ≥ 75%（`server/.pre-commit-config.yaml` 已校验），最低门槛用例集见 §7.2。

---

## 8. 回滚计划

| 阶段 | 触发条件 | 回滚动作 |
|------|---------|----------|
| **Pre-merge**：还未发布 master | adapter 单测失败 / 序列化器迁移路径出错 | revert commit；不发布 |
| **Post-merge · 上线后才发现问题** | 生产出现 schema 报错或同步空 | release 校验开关 `AD_BASE_DN_RELAXED=true`（FeatureFlag 兜底）；或直接 revert PR；DB 里残留 `base_dn` 值因为代码不读它、不会自动恢复成「被读取状态」 |

---

## 9. 安全考量

### 9.1 服务账号 ACL 与应用层职责边界

- **应用层不做"访问边界护栏"**：`base_dn` 字段在 bk-lite AD provider 配置中整体废弃，应用层不再做"额外护栏"。
- **`root_dn` 字符串本身就是运维意图**：作为 LDAP `search_base=` 的同时，也是审计 / 日志可观测的运维意图陈述。
- **真正的边界由 AD ACL 决定**：服务账号在 AD 上的 OU ACE 是唯一可靠的访问护栏。应用层不感知也不验证；这部分归 AD 运维治理。
- 上一阶段的 `is_sub_dn` 业务护栏随 `base_dn` 字段一并废弃——它带来的是「应用层复述用户已经表达过的意图」，没有新增任何主动防御。

### 9.2 越界行为模式

- **正常**：管理员设 `root_dn = OU=A,DC=bktest,DC=com,DC=cn`；服务账号在 `DC=bktest` 上有 `GenericRead`：搜索返回 A 子树 → 正常。
- **静默空**：管理员错填 `root_dn = DC=com,DC=cn` 而服务账号仅在 `DC=bktest` 有权限：LDAP 返回空 → 同步结果静默空（**这是预期行为而非 bug**）；下次迭代可加诊断提示。
- **服务账号 ACL 治理文档**：`docs/superpowers/specs/.../related-security-doc.md`（运维用），不在本 spec 内。

---

## 10. 实施步骤（Tasks）

1. **T1：Schema 删除**
   - 改 `manifests/ad.py`：删 instance 级 `base_dn`；**不**在 `user_sync_form` 里新增 `base_dn`；`root_dn` 保持 `field_type: "string"` 单值。
   - 改 `serializers/user_sync_source_serializer.py`：移除 `is_sub_dn(root_dn, base_dn)` 校验分支（约 115-127 行）；保留 root_dn 必填断言。
   - 改 `serializers/integration_instance_serializer.py`（如有）：去掉 `base_dn` 必填校验 / 接受为 tolerated legacy。
2. **T2：Adapter 清理**
   - `adapters/ad.py`：`test_connection` 与 `sync_users` 完全删除 `base_dn` 的所有读写代码路径；`root_dn` 仍是**单值字符串**。
3. **T3：Contract 同步**
   - `services/capability_contract_service.py`：`validate_user_sync_contract` 删除 `base_dn` 相关校验分支；`root_dn` 不做多值归一化。
4. **T4：前端兼容 & 文案**
   - `userSyncUtils.ts`：**不**增加 `base_dn` 默认值；表单中**不**新增字段；i18n 中删除 `catalog/baseDn` 相关 key（如存在）。
   - 「用户同步」列表提供「**新建同步源**」按钮，让同 instance 下能快速建多 source（多 OU 场景）。
5. **T5：测试**
   - 新增 §7.2 最小用例集；改 `test_provider_manifest.py` 涉及字段顺序的断言（去掉 base_dn）。
6. **T6：文档**
   - `docs/superpowers/specs/` 本 spec 已建；`docs/operations.md` 加一条「AD 集成升级说明」；
   - `docs/superpowers/plans/` 创建配套 plan 文件。
7. **T7：PR + 合 master**
   - 跑 `make test`（server）+ `pnpm lint && pnpm type-check`（web）；CI 通过后合入。

> **不做 Django data migration**。`base_dn` 是 JSONField 里的 key，不是 DB 列；代码不再读它，JSON 里的残留是「无害尸体」，见 §6.1。本 spec 不提供 `0009_drop_ad_base_dn` 之类的迁移文件。

---

## 11. 度量与监控

| 指标 | 期望 |
|------|------|
| 创建集成实例时同时配置同步源的转化率 | 不下降 |
| 「新建 OU 同步任务」的运维操作步骤数 | **从 6 步 → 2 步**（复制现有 user_sync_source + 改 root_dn） |
| 升级后生产 1 周内同步失败率 | 不上升 |
| 用户提交：AD 集成中心配置错误工单 | -30%（同步范围问题不再需要拆实例） |

---

## 12. 决策记录

| 决策 | 选项 | 取舍 | 理由 |
|------|------|------|------|
| 是否保留 `base_dn` 字段 | 保留（下放 / 平铺 / 高级选项）vs **彻底删除** | ✅ **彻底删除** | `base_dn` 不发 LDAP 包；`root_dn` 字符串已携带「同步起点 + 范围声明」双重语义；再造一个字段是冗余 |
| `root_dn` 字段类型 | 单 string vs list/`\|\|` 多值 vs 新 `string_with_multi` | ✅ **单 string** | 多 OU 走「同 instance 多 source」；不引入新 field_type；最小改动面 |
| 多 OU 同步的解法 | `root_dn` 多值 vs 同 instance 多 source | ✅ **同 instance 多 source** | schema 层解耦最自然；不改 root_dn 字段语义 |
| 旧实例 base_dn 数据处理 | 数据迁移脚本 vs 仅 lazy read vs **就地清理** | ✅ **就地清理** | 没有"新字段"承接；cleanup 一次到位 |
| 越界保护 | Application `is_sub_dn` vs AD ACL | ✅ **信任 AD ACL** | Application 不能真正阻止搜索；ACL 是唯一可靠防线；删字段 = 撤回伪护栏 |
| `user_object_class` / `user_filter` / `organization_object_class` | 必填 vs 可空 | ✅ **可空走默认** | 现状已完成（本次会话）|

---

## 13. 风险与副作用

| 风险 | 影响 | 缓解 |
|------|------|------|
| 旧集成实例升级后 JSON 里残留 `base_dn` 键 | **低**：残留值不会被任何代码读取，等同于死数据 | 见 §6.1；本 spec 不清理，由运维另起任务 |
| 跨 OU 同步时 Profile/Department 的 `parent_id` 关系错误 | 低 | `_collect_department_dns` 取自当前 root_dn，不混 |
| 通用 LDAP provider 未来也要 `basic_pull_node` 风格 | 中 | 本 spec 末尾预留「扩展到非 AD LDAP provider」备注 |

---

## 14. 参考

- bk-user `weops-4.x` 调研：
  - `client.py:50,94-127`
  - `syncer.py:48-70,72-82`
  - `settings.yaml:79-82,98-101`
- bk-lite 既有改动：本会话已落盘的 `manifests/ad.py`（`user_object_class`/`user_filter`/`organization_object_class` help_text + required=False）。
- 现有 Serializer：`apps/system_mgmt/serializers/user_sync_source_serializer.py:115-127`（base_dn 业务护栏分支随后会被 T1 删除）。

---

**版本**：v0.2 · 收口 base_dn 字段彻底删除
**决策变更**：v0.1 → v0.2 —— 由"`base_dn` 下放到 sync source"改为"`base_dn` 字段在 AD provider 配置中整体废弃"
**待 review**：运维（迁移 SOP）、测试（用例最小集）、安全（应用层不冒充 AD ACL 语义需明确）

