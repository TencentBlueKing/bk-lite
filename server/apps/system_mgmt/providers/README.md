# BK-Lite Provider 集成插件开发指南

本文档说明 `server/apps/system_mgmt/providers/` 下 Provider 的实现约定、Manifest schema、能力 adapter 契约和验证方式。

Provider 是随服务代码发布、在 Django 进程内运行的 Python 包。当前实现以 `builtin/` 为唯一自动扫描目录；新增 Provider 应放入 `builtin/<provider_key>/`，不应依赖其他目录被自动发现。

## 1. 架构概览

Provider 由三部分组成：

1. **Manifest**：声明 Provider 身份、表单字段、业务配置和能力。
2. **Adapter**：实现登录、用户同步、通知等外部平台行为。
3. **Client**：集中处理第三方 API、认证、分页、超时和错误转换。

运行链路：

```text
ProviderRegistry
  -> loader 加载 builtin 包
  -> ProviderManifest
  -> CapabilityAdapterRegistry
  -> RuntimeApplicationService
  -> capability adapter
  -> 第三方 API / LDAP / IM 平台
```

核心文件：

```text
server/apps/system_mgmt/providers/loader.py
server/apps/system_mgmt/providers/registry.py
server/apps/system_mgmt/providers/runtime.py
server/apps/system_mgmt/providers/schemas.py
server/apps/system_mgmt/providers/base.py
server/apps/system_mgmt/providers/pack_i18n.py
```

加载规则：

- Provider 注册表首次读取时，在锁内加载内置 Provider。
- 加载器扫描 `server/apps/system_mgmt/providers/builtin/` 下的目录。
- 单个包导入、Manifest 校验或 adapter 注册失败时，跳过该包，不影响其他包。
- adapter 注册成功后由 `RuntimeApplicationService` 按 `provider_key + capability_key + operation` 调用。
- 服务启动阶段不会主动扫描 Provider；注册表首次被访问时才触发加载。

当前内置 Provider：

| Provider key | 能力 |
|---|---|
| `ad` | `login_auth`、`user_sync` |
| `feishu` | `login_auth`、`user_sync`、`im_notification` |
| `wechat` | `login_auth` |
| `wecom` | `login_auth`、`user_sync`、`im_notification` |
系统管理标准业务能力最多包括三种：`login_auth`（登录认证）、`user_sync`（用户同步）和 `im_notification`（IM 通知）。其他模块可以按需为对应 Provider 增加额外 capability；额外 capability 的业务契约由消费模块维护，不纳入本文。

## 2. Provider 目录结构

推荐结构：

```text
server/apps/system_mgmt/providers/builtin/acme/
├── __init__.py
├── manifest.py
├── language/
│   ├── en.yaml
│   └── zh-Hans.yaml
└── adapters/
    ├── __init__.py
    ├── client.py
    ├── base_connection.py
    ├── login_auth.py
    ├── user_sync.py
    └── im_notification.py
```

加载器强制检查以下文件：

```text
__init__.py
adapters/client.py
adapters/base_connection.py
```

Provider 还必须包含：

```text
language/en.yaml
language/zh-Hans.yaml
```

### `__init__.py`

入口文件应只导出 Manifest：

```python
from .manifest import PROVIDER_MANIFEST

__all__ = ["PROVIDER_MANIFEST"]
```

不要在包入口执行网络请求、数据库查询、启动线程或其他有副作用的逻辑。

### `manifest.py`

标准做法是创建 `ProviderManifest` 实例：

```python
from apps.system_mgmt.providers.schemas import ProviderManifest


PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "acme",
        "name": "Acme",
        "description": "Acme identity integration provider.",
        "base_connection_adapter_key": "acme.base_connection",
        "base_connection_adapter_path": (
            "adapters.base_connection.AcmeBaseConnectionAdapter"
        ),
        "instance_templates": {
            "base_connection": {
                "title": "Base Connection",
                "groups": [
                    {
                        "key": "credentials",
                        "title": "Credentials",
                        "fields": [
                            {
                                "key": "endpoint",
                                "label": "Endpoint",
                                "field_type": "string",
                                "required": True,
                            },
                            {
                                "key": "client_secret",
                                "label": "Client Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                                "reset_capabilities": ["login_auth"],
                            },
                        ],
                    }
                ],
            }
        },
        "business_templates": {
            "login_auth_form": {
                "title": "Login authentication",
                "groups": [
                    {
                        "key": "mapping",
                        "title": "Field mapping",
                        "fields": [
                            {
                                "key": "external_field",
                                "label": "External field",
                                "field_type": "string",
                                "required": True,
                            },
                            {
                                "key": "platform_field",
                                "label": "Platform field",
                                "field_type": "select",
                                "required": True,
                            },
                        ],
                    }
                ],
                "available_external_fields": ["user_id", "name", "email"],
                "default_external_match_field": "user_id",
            }
        },
        "capabilities": [
            {
                "key": "login_auth",
                "name": "Login Auth",
                "description": "Acme login authentication capability.",
                "adapter_key": "acme.login_auth",
                "adapter_path": "adapters.login_auth.AcmeLoginAuthAdapter",
                "connection_template": [],
                "business_template": "login_auth_form",
            }
        ],
    }
)
```

## 3. Manifest 约定

`ProviderManifest` 定义在 `schemas.py`。

### 顶层字段

| 字段 | 说明 |
|---|---|
| `key` | 稳定 Provider 标识；实例创建后不能更换 |
| `name` | 默认展示名称 |
| `description` | 默认描述 |
| `instance_templates` | 集成实例配置模板，通常包含基础连接 |
| `business_templates` | 登录映射、用户同步、通知映射等业务配置 |
| `capabilities` | Provider 支持的能力列表 |
| `base_connection_adapter_key` | 基础连接 adapter 的注册 key |
| `base_connection_adapter_path` | 基础连接 adapter 的包内相对路径 |

### 能力字段

每个 `capabilities` 条目至少包含：

```text
key
name
description
adapter_key
adapter_path
```

可选字段：

```text
connection_template
business_template
```

约束：

- Provider key 必须稳定，不能随代码版本变化。
- 同一 Manifest 内的 capability key 不能重复。
- `adapter_key` 必须以 `{provider_key}.` 开头，例如 `acme.login_auth`。
- `adapter_path` 必须是包内相对路径，例如 `adapters.login_auth.AcmeLoginAuthAdapter`。
- 不要写 `apps.system_mgmt.providers...` 或其他绝对模块路径。
- 所有 connection field 的 `key` 在实例模板和 capability 模板之间不能重复。
- `business_template` 必须引用已存在的 `business_templates` key。

### 模板关系

- `instance_templates` 描述集成实例级配置。
- `business_templates` 描述用户同步源、登录绑定或通知渠道使用的业务配置。
- capability 的 `connection_template` 描述该能力专属的实例级配置。
- `capability.business_template` 将能力绑定到对应的业务模板。

系统会将 `instance_templates` 的分组字段展平为兼容字段 `instance_template`，供现有详情页使用。

## 4. 表单字段设计

字段类型由 `TemplateFieldManifest` 定义，支持：

```text
string
password
number
boolean
select
textarea
```

### 敏感字段

```python
{
    "key": "app_secret",
    "label": "App Secret",
    "field_type": "password",
    "required": True,
    "secret": True,
    "mask_strategy": "full",
}
```

设置 `secret=True` 后，系统会自动设置为 `write_only=True`：

- 保存到实例前加密。
- API 回显时脱敏。
- adapter 通过 `instance.get_runtime_config()` 接收解密后的配置。
- 日志中不得出现该字段值。

`mask_strategy` 支持：

```text
full
last4
```

### `reset_capabilities`

字段变化后需要重新验证的能力由该字段声明：

```python
"reset_capabilities": ["login_auth", "user_sync"]
```

建议：

- 基础凭据、基础地址变化时，列出所有受影响能力。
- 能力专属 URL 变化时，只列出对应能力。
- 不要让配置变化后继续保留过期的 ready 状态。

实例配置和状态回退逻辑见：

```text
server/apps/system_mgmt/serializers/integration_instance_serializer.py
```

### `select` 字段

```python
{
    "key": "user_id_type",
    "label": "User ID Type",
    "field_type": "select",
    "required": True,
    "default": "user_id",
    "options": [
        {"value": "user_id", "label": "user_id"},
        {"value": "open_id", "label": "open_id"},
    ],
}
```

### 用户同步范围字段

组织树选择模式：

```python
{
    "key": "root_department_id",
    "label": "Root department",
    "field_type": "string",
    "required": True,
    "input_mode": "department_select",
}
```

手工输入模式：

```python
{
    "key": "root_dns",
    "label": "Root DNs",
    "field_type": "textarea",
    "required": True,
    "input_mode": "manual_input",
}
```

用户同步服务会优先查找 key 以 `root_` 开头的字段作为同步范围字段。

## 5. 语言文件

语言文件由 `pack_i18n.py` 加载。两个文件都必须存在，且根级 `description` 不能为空：

```yaml
name: Acme
description: Acme identity integration for login authentication.

templates:
  base_connection:
    title: Base Connection
    groups:
      credentials:
        title: Credentials
        fields:
          endpoint:
            label: Endpoint
          client_secret:
            label: Client Secret

  login_auth_form:
    title: Login authentication
    groups:
      mapping:
        title: Field mapping
        fields:
          external_field:
            label: External field

capabilities:
  login_auth:
    fields:
      login_auth_authorize_url:
        label: Authorization URL
```

文案覆盖顺序：

```text
请求语言 -> en.yaml -> Manifest 中的原始文案
```

规则：

- 中文文件名固定为 `zh-Hans.yaml`。
- `templates` 用于覆盖模板标题、分组标题和字段文案。
- `capabilities.<capability_key>.fields` 用于覆盖能力 connection field 文案。
- 语言文件只负责展示文案，不负责声明字段类型、required 或默认值。
- help text 中出现 ASCII 冒号时建议加引号，避免 YAML 解析失败。

## 6. Adapter 开发

基础接口定义在：

```text
server/apps/system_mgmt/providers/base.py
```

Adapter 方法使用类方法，参数至少包含：

```python
config: dict
provider_key: str
capability_key: str
**kwargs
```

推荐继承对应基类：

| 能力 | 基类 |
|---|---|
| `login_auth` | `BaseLoginAuthAdapter` |
| `user_sync` | `BaseUserSyncAdapter` |
| `im_notification` | `BaseIMNotificationAdapter` |

基础连接 adapter 没有专用基类，但必须实现相同形式的 `test_connection()`。

### 统一返回值

成功：

```python
from apps.system_mgmt.providers.runtime import CapabilityExecutionResult

return CapabilityExecutionResult.success_result(
    "Acme connection is ready",
    payload={"external_request_id": request_id},
)
```

失败：

```python
return CapabilityExecutionResult.failed_result(
    "Acme credentials are invalid",
    code="provider.auth_failed",
    field="client_secret",
    external_code="401",
    external_request_id=request_id,
)
```

虽然 Runtime 兼容普通字典，但 Provider 应直接返回 `CapabilityExecutionResult`，避免返回结构不一致。

常用错误码：

| 错误码 | 用途 |
|---|---|
| `provider.invalid_config` | 本地配置缺失或不合法 |
| `provider.invalid_response` | 外部响应格式不符合预期 |
| `provider.auth_failed` | 凭据或授权失败 |
| `provider.permission_denied` | 外部 API 权限不足 |
| `provider.permission_unverified` | 权限尚未确认 |
| `provider.bot_not_enabled` | IM 机器人未启用 |
| `provider.request_failed` | 外部请求失败 |
| `provider.timeout` | 外部请求超时 |
| `provider.unavailable` | Provider 不可用 |
| `provider.operation_not_implemented` | 能力未实现对应操作 |

通常网络错误、429 和 5xx 应设置 `retryable=True`；配置错误、权限错误和无效响应通常不可直接重试。

### 6.1 基础连接

Manifest：

```text
base_connection_adapter_key
base_connection_adapter_path
```

方法：

```text
test_connection(config, provider_key, capability_key="base", **kwargs)
```

职责：

- 检查公共凭据。
- 检查基础地址格式。
- 验证网络连接或获取基础 token。
- 不执行用户同步、登录或消息发送。

基础连接成功后，实例可以进入 ready；各 capability 仍可能需要单独验证。

### 6.2 `login_auth`

通常实现：

```text
test_connection()
build_login_url()
authenticate()
```

`build_login_url()` 常见参数：

```text
binding
redirect_uri
state
```

成功 payload 应包含：

```python
{"authorize_url": "https://..."}
```

`authenticate()` 常见参数：

```text
binding
auth_code
username
password
```

推荐返回：

```python
{
    "external_user": {
        "user_id": "...",
        "name": "...",
        "email": "...",
        "mobile": "...",
    }
}
```

登录服务依据绑定配置的 `external_field` 和 `platform_field` 匹配本地用户。因此必须返回稳定身份字段，不能只返回显示名称。

相关编排代码：

```text
server/apps/system_mgmt/services/login_auth_binding_service.py
```

### 6.3 `user_sync`

通常实现：

```text
test_connection()
list_departments()
sync_users()
```

#### `list_departments()`

常见参数：

```text
source
business_config
```

成功 payload：

```python
{
    "items": [
        {
            "id": "department-1",
            "name": "Engineering",
            "parent_id": None,
            "children": [],
            "selectable": True,
        }
    ],
    "external_request_id": "...",
}
```

该方法用于 `department_select` 模式的范围选择和后端校验。

#### `sync_users()`

常见参数：

```text
source
```

- `source.business_config` 是 Provider 业务配置。
- `source.field_mapping` 是平台字段映射。

成功 payload 约定：

```python
{
    "group_list": [
        {
            "id": "department-1",
            "parent_id": "root-department",
            "name": "Engineering",
        }
    ],
    "user_list": [
        {
            "user_id": "alice",
            "name": "Alice",
            "email": "alice@example.com",
            "mobile": "13800000000",
            "department_ids": ["department-1"],
        }
    ],
    "external_request_id": "...",
}
```

要求：

- `group_list` 使用外部组织 ID。
- `parent_id` 应能在同一批组织数据中建立父子关系。
- 不要返回重复的本地根组织；本地根由同步服务管理。
- `user_list` 应提供稳定身份字段。
- 用户组织使用 `department_ids` 或兼容的 `departments` 列表。
- 用户没有可映射组织时，平台会回退到同步源根组织。
- Provider 只返回外部目录数据，不自行写入本地用户、组织或同步运行记录。

默认用户字段映射：

```text
username     <- user_id
display_name <- name
email        <- email
phone        <- mobile
```

外部字段不一致时，应通过 `field_mapping` 和 `available_external_fields` 支持，不要把字段名硬编码到平台服务中。

如需兼容历史配置，可以覆盖：

```python
normalize_business_config()
```

相关编排代码：

```text
server/apps/system_mgmt/services/user_sync_service.py
server/apps/system_mgmt/serializers/user_sync_source_serializer.py
```

### 6.4 `im_notification`

通常实现：

```text
test_connection()
list_external_users()
send_message()
```

对应业务模板应声明：

```text
available_external_fields
matchable_fields
receivable_fields
identity_fields
default_external_match_field
default_external_receive_field
```

#### `list_external_users()`

常见参数：

```text
channel
run
```

成功 payload：

```python
{
    "external_users": [
        {
            "user_id": "alice",
            "name": "Alice",
            "email": "alice@example.com",
            "mobile": "13800000000",
        }
    ]
}
```

平台会依据 Manifest 中的字段元数据进行外部用户匹配、稳定身份判断和接收 ID 快照保存。

#### `send_message()`

常见参数：

```text
title
content
receive_id_type
receive_ids
```

成功 payload 可以包含：

```python
{"sent_count": 3}
```

部分成功应明确设置 `partial_success=True`，并返回有界的失败摘要：

```python
CapabilityExecutionResult(
    success=True,
    partial_success=True,
    summary="3 sent, 1 failed",
    payload={
        "sent_count": 3,
        "failures": [{"receive_id": "...", "reason": "..."}],
    },
)
```

## 7. Client 和外部请求

推荐将第三方请求层集中放在：

```text
adapters/client.py
```

建议职责划分：

```text
client.py             -> token、请求、分页、公共错误处理
base_connection.py   -> 基础连接探测
login_auth.py        -> 登录流程
user_sync.py         -> 组织和用户转换
im_notification.py   -> 外部用户和消息
```

要求：

- 使用目标运行环境已有的依赖；Provider 加载过程不会安装依赖。
- 所有外部请求设置明确 timeout。
- 统一处理超时、HTTP 错误、无效 JSON 和分页游标异常。
- 尽可能提取第三方 request ID，写入结果的 `external_request_id`。
- 不将第三方完整响应写入 payload。
- 不在模块导入阶段发起网络请求或访问数据库。

## 8. 安全和日志

Provider 代码在服务进程内执行，能够接触实例运行配置和宿主应用模块。必须把 Provider 当作受信任的服务代码审查：

- 包入口和模块导入阶段不得产生副作用。
- 不读取、输出或持久化不必要的凭据。
- 不在日志中记录密码、token、OAuth code、完整敏感 URL 或原始响应正文。
- Provider 包内统一使用：

```python
from apps.system_mgmt.providers.log import logger
```

- 不使用 `print`、`loguru` 或 `apps.core.logger`。
- 网络错误和第三方错误应转换成安全摘要、错误码和必要的外部 request ID。
- 不直接修改本地用户、组织、实例状态；由系统管理服务负责持久化和状态编排。
- 数据库访问只能使用 Django ORM，禁止 raw SQL、`.raw()`、`RawSQL` 和 `cursor.execute`。

## 9. 前端和 API 接线

Provider 表单由 Manifest 驱动，通常不需要新增前端 Provider 分支。

核心接口：

```text
GET  /api/v1/system_mgmt/integration_instance/providers/
POST /api/v1/system_mgmt/integration_instance/
POST /api/v1/system_mgmt/integration_instance/{id}/test_connection/
```

前端消费的 Manifest 内容包括：

```text
instance_templates
business_templates
capabilities
connection_template
field_type
options
required
input_mode
```

相关前端代码：

```text
web/src/app/system-manager/api/integration-center/index.ts
web/src/app/system-manager/(pages)/integration-center/CreateIntegrationInstanceModal.tsx
web/src/app/system-manager/components/user/user-sync/UserSyncConfigFields.tsx
```

Provider 新增后，重点验证 Manifest 能否驱动现有页面，而不是为每个平台复制一套表单。

## 10. 推荐开发流程

1. 确定稳定的 `provider_key` 和需要支持的 capability。
2. 在 `builtin/<provider_key>/` 创建包目录。
3. 编写 `__init__.py` 和 `manifest.py`。
4. 先定义基础连接字段、敏感字段和状态回退关系。
5. 为每个 capability 定义 connection template 和 business template。
6. 编写 `language/en.yaml` 与 `language/zh-Hans.yaml`。
7. 在 `client.py` 集中实现认证、请求、分页和错误转换。
8. 实现 adapter，并统一返回 `CapabilityExecutionResult`。
9. 增加 Manifest、loader、adapter 和端到端服务测试。
10. 发布服务代码后，访问 Provider 列表、创建实例、测试基础连接，再逐项测试 capability。

## 11. 验证命令

### Python 语法

```bash
python -m compileall server/apps/system_mgmt/providers/builtin/acme
```

### Provider 相关测试

项目 Django 测试使用约定的 PostgreSQL 测试数据库：

```bash
cd server

uv run pytest \
  apps/system_mgmt/tests/test_provider_manifest.py \
  apps/system_mgmt/tests/test_provider_loader.py \
  apps/system_mgmt/tests/test_provider_loader_base_connection.py \
  --no-cov
```

如果实现了具体能力，还应运行对应测试，例如：

```bash
uv run pytest \
  apps/system_mgmt/tests/test_login_auth_manifest.py \
  apps/system_mgmt/tests/test_im_notification_manifest.py \
  apps/system_mgmt/tests/test_runtime_service.py \
  --no-cov
```

### 必测行为

- Provider 能被注册表发现并成功加载。
- Manifest 的 capability、adapter key 和相对 adapter path 正确。
- 缺失文件、重复 key、错误引用会使当前 Provider 失败，而不会破坏其他 Provider。
- 基础连接缺少必填配置时返回 `provider.invalid_config`。
- 外部超时和网络失败返回正确错误码及 retryable 状态。
- secret 字段保存后加密、回显脱敏，adapter 收到解密配置。
- 配置字段变化会使受影响 capability 回到待验证状态。
- 登录结果包含可匹配的稳定外部身份。
- 用户同步返回 `group_list`、`user_list` 和正确的外部组织关系。
- 通知同步返回 `external_users`，发送消息支持成功和部分成功结果。
- Provider 列表接口返回本地化后的 name、description 和表单结构。

## 12. 常见错误

- 把 Provider 放在 `builtin` 之外并期待加载器自动发现。
- `adapter_path` 写成绝对模块路径。
- `adapter_key` 没有使用 `{provider_key}.` 前缀。
- Manifest 中重复使用 connection field key。
- `business_template` 引用不存在的模板。
- 忘记提供 `language/en.yaml` 或 `language/zh-Hans.yaml`。
- 语言 YAML 中的冒号没有正确引用，导致整个 Provider 注册失败。
- `__init__.py` 在导入时访问网络或数据库。
- adapter 直接返回第三方原始响应，而不是 `CapabilityExecutionResult`。
- 用户同步返回 `users` / `groups`，而平台服务实际消费的是 `user_list` / `group_list`。
- 用户同步组织 ID 与用户的 `department_ids` 不一致。
- `im_notification` 没有声明匹配字段和接收字段。
- 配置变化没有正确声明 `reset_capabilities`。
- 在日志中输出凭据、完整 URL、响应正文或无界对象。

## 13. 代码依据

本文档对应当前实现：

```text
server/apps/system_mgmt/providers/schemas.py
server/apps/system_mgmt/providers/loader.py
server/apps/system_mgmt/providers/registry.py
server/apps/system_mgmt/providers/runtime.py
server/apps/system_mgmt/providers/base.py
server/apps/system_mgmt/providers/pack_i18n.py
server/apps/system_mgmt/models/integration_instance.py
server/apps/system_mgmt/serializers/integration_instance_serializer.py
server/apps/system_mgmt/services/login_auth_binding_service.py
server/apps/system_mgmt/services/user_sync_service.py
server/apps/system_mgmt/services/im_notification_service.py
server/apps/system_mgmt/providers/builtin/
```
