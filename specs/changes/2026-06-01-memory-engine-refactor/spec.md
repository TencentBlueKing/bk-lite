# 2026 06 01 Memory Engine Refactor

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-01-memory-engine-refactor/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前记忆功能仅支持本地 PostgreSQL 存储，无法对接 Mem0、Zep 等第三方记忆系统。企业用户需要灵活选择记忆存储后端，利用第三方系统的高级能力（如语义搜索、知识图谱、自动事实提取）。本次改造引入引擎注册机制，支持多种记忆系统的即插即用。

## What Changes

- **新增记忆引擎注册中心**：`MemoryEngineRegistry` 管理所有已注册的记忆引擎
- **新增引擎基类**：`BaseMemoryEngine` 定义统一的 `read/write/delete` 接口
- **内置 4 种引擎**：Local（现有逻辑迁移）、Mem0、Zep、Custom API
- **新增引擎 API**：
  - `GET /memory_engines/` 列出所有引擎
  - `GET /memory_engines/{type}/schema/` 获取引擎参数定义
  - `POST /memory_engines/{type}/test/` 测试引擎连接
- **MemorySpace 模型新增字段**：`storage_type`（引擎类型）、`storage_config`（引擎配置 JSON）
- **前端动态配置表单**：根据引擎 schema 动态渲染配置界面
- **工作流节点改造**：`memory_read/write` 节点通过 Registry 获取引擎实例

## Capabilities

### New Capabilities
- `memory-engine-registry`: 记忆引擎注册中心，管理引擎注册、获取、列表、schema 查询
- `memory-engine-local`: 本地存储引擎，迁移现有 PostgreSQL 存储逻辑
- `memory-engine-mem0`: Mem0 云端记忆引擎，支持语义搜索和自动事实提取
- `memory-engine-zep`: Zep 记忆引擎，支持知识图谱和会话记忆
- `memory-engine-custom`: 自定义 API 引擎，支持对接任意 HTTP 接口
- `memory-engine-api`: 引擎管理 REST API，提供引擎列表、schema、测试连接接口
- `memory-config-ui`: 前端动态配置组件，根据 schema 渲染引擎配置表单

### Modified Capabilities
- `memory-space`: 新增 `storage_type` 和 `storage_config` 字段，支持选择和配置记忆引擎
- `memory-workflow-nodes`: 改造 `memory_read/write` 节点，通过 Registry 获取引擎实例执行操作

## Impact

### 后端
- `server/apps/opspilot/models/memory_mgmt.py` - 新增字段
- `server/apps/opspilot/memory/` - 新增目录，包含引擎基类、注册中心、各引擎实现
- `server/apps/opspilot/viewsets/memory_engine_view.py` - 新增引擎 API
- `server/apps/opspilot/urls.py` - 新增路由
- `server/apps/opspilot/tasks.py` - 改造 `process_memory_write` 使用引擎
- `server/apps/opspilot/utils/chat_flow_utils/nodes/memory/` - 改造节点

### 前端
- `web/src/app/opspilot/api/memoryEngine.ts` - 新增引擎 API hooks
- `web/src/app/opspilot/api/memory.ts` - 更新类型定义
- `web/src/app/opspilot/components/memory/EngineConfigForm.tsx` - 新增动态配置组件
- `web/src/app/opspilot/(pages)/memory/page.tsx` - 新增时选择引擎类型
- `web/src/app/opspilot/(pages)/memory/detail/config/page.tsx` - 动态渲染引擎配置

### 数据库
- 新增迁移：`MemorySpace` 表添加 `storage_type`、`storage_config` 字段

### 依赖
- 可选：`mem0` Python SDK（Mem0 引擎）
- 可选：`zep-python` SDK（Zep 引擎）
- `httpx`（Custom API 引擎 HTTP 请求）

## Implementation Decisions

## Context

### 背景
OpsPilot 记忆功能当前仅支持本地 PostgreSQL 存储。随着 AI Agent 记忆领域的发展，Mem0、Zep 等专业记忆系统提供了更强大的能力（语义搜索、知识图谱、自动事实提取）。企业用户需要灵活选择记忆后端。

### 现状
- `MemorySpace` 模型存储记忆空间配置
- `Memory` 模型存储记忆条目
- `memory_read.py` / `memory_write.py` 工作流节点直接操作 Django ORM
- `process_memory_write` Celery 任务处理异步写入和 LLM 合并

### 约束
- 必须向后兼容，现有记忆空间默认使用本地存储
- API Key 等敏感信息需加密存储
- 前端不硬编码引擎参数，从后端动态获取
- 第三方 SDK 为可选依赖，未安装时对应引擎不可用

### 相关方
- 后端：Django 模型、ViewSet、Celery 任务、工作流节点
- 前端：记忆空间管理页面、配置表单组件
- 运维：数据库迁移、可选依赖安装

## Goals / Non-Goals

**Goals:**
- 引入引擎注册机制，支持多种记忆系统即插即用
- 提供统一的 `read/write/delete` 接口，屏蔽底层差异
- 前端根据引擎 schema 动态渲染配置表单
- 内置 Local、Mem0、Zep、Custom API 四种引擎
- 敏感配置加密存储，前端脱敏显示

**Non-Goals:**
- 不实现记忆数据在不同引擎间的迁移工具
- 不实现引擎的热切换（切换引擎后旧数据不自动迁移）
- 不实现引擎的负载均衡或故障转移
- 不实现自定义引擎的插件化加载（仅支持代码内注册）

## Decisions

### Decision 1: 引擎注册模式

**选择**: 类注册表模式（Class Registry Pattern）

**方案对比**:
| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 类注册表 | 简单直接，与现有 AlertSourceAdapterFactory 一致 | 新引擎需改代码 |
| B. 插件目录扫描 | 支持外部插件 | 复杂，安全风险 |
| C. 数据库配置 | 运行时可配 | 过度设计，引擎逻辑无法存DB |

**理由**: 方案 A 与项目现有模式一致（`AlertSourceAdapterFactory`），简单可靠。引擎数量有限（4-6种），无需插件化。

**实现**:
```python
class MemoryEngineRegistry:
    _engines: Dict[str, Type[BaseMemoryEngine]] = {}

    @classmethod
    def register(cls, engine_type: str, engine_class: Type[BaseMemoryEngine]):
        cls._engines[engine_type] = engine_class

    @classmethod
    def get_engine(cls, memory_space_id: int) -> BaseMemoryEngine:
        # 查询 MemorySpace，根据 storage_type 获取引擎类，实例化
        ...
```

### Decision 2: 引擎初始化参数

**选择**: 仅传入 `memory_space_id`，引擎内部查询配置

**方案对比**:
| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 传入 memory_space_id | 引擎自主查询，解耦 | 多一次 DB 查询 |
| B. 传入 config dict | 调用方控制配置 | 调用方需知道配置结构 |
| C. 传入 MemorySpace 对象 | 避免重复查询 | 耦合 Django 模型 |

**理由**: 方案 A 让引擎完全自主，调用方只需知道 `memory_space_id`。DB 查询开销可忽略（单条主键查询）。

### Decision 3: 参数 Schema 定义位置

**选择**: 引擎类的类方法 `get_config_schema()`

**方案对比**:
| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 引擎类方法 | Schema 与实现在一起，易维护 | 需重启生效 |
| B. 独立 JSON 文件 | 可热更新 | 分散，易不同步 |
| C. 数据库存储 | 运行时可改 | 过度设计 |

**理由**: 方案 A 保证 schema 与实现代码一致，避免不同步。引擎参数变化频率极低，无需热更新。

### Decision 4: 敏感字段加密

**选择**: 复用现有 `EncryptMixin`，在 `storage_config` JSON 内加密特定字段

**实现**:
```python
class MemorySpace(MaintainerInfo, TimeInfo, EncryptMixin):
    ENCRYPTED_CONFIG_FIELDS = ["api_key"]  # 需加密的字段名

    def save(self, *args, **kwargs):
        if self.storage_config:
            config = self.storage_config.copy()
            for field in self.ENCRYPTED_CONFIG_FIELDS:
                if field in config and config[field]:
                    self.encrypt_field(field, config)
            self.storage_config = config
        super().save(*args, **kwargs)
```

### Decision 5: 前端动态表单渲染

**选择**: 根据 schema 的 `type` 字段选择组件

**字段类型映射**:
| Schema Type | 前端组件 |
|-------------|----------|
| `text` | `<Input />` |
| `password` | `<Input.Password />` |
| `number` | `<InputNumber />` |
| `select` | `<Select />` |
| `json` | `<Input.TextArea />` + JSON 校验 |

### Decision 6: 工作流节点改造

**选择**: 节点内通过 Registry 获取引擎，调用统一接口

**改造前**:
```python
memories = Memory.objects.filter(memory_space_id=...).order_by("-updated_at")[:top_k]
```

**改造后**:
```python
# memory_read.py
engine = MemoryEngineRegistry.get_engine(memory_space_id)
result = engine.read(entity, query=message, top_k=top_k)
```

## Risks / Trade-offs

### Risk 1: 第三方服务不可用
**风险**: Mem0/Zep 服务宕机导致记忆功能失败
**缓解**:
- 引擎 `read/write` 方法内部 try-catch，失败时记录日志并返回空/失败结果
- 写入节点本身是异步支线，不影响主流程
- 读取节点失败时返回空 context，Agent 仍可正常对话

### Risk 2: API Key 泄露
**风险**: 配置中的 API Key 被泄露
**缓解**:
- 使用 `EncryptMixin` 加密存储
- API 返回时脱敏显示（`m0-***`）
- 前端使用 `password` 类型输入框

### Risk 3: 第三方 SDK 依赖冲突
**风险**: `mem0` 或 `zep-python` SDK 与现有依赖冲突
**缓解**:
- 设为可选依赖（`extras_require`）
- 引擎初始化时检查 SDK 是否安装，未安装则抛出明确错误
- 引擎列表 API 可标记哪些引擎可用

### Risk 4: 数据格式不兼容
**风险**: 不同引擎返回的记忆格式不一致
**缓解**:
- 统一 `MemoryReadResult.context` 为纯文本字符串
- 各引擎负责将自身格式转换为统一格式

### Trade-off 1: 性能 vs 简洁
**取舍**: 每次调用 `get_engine()` 都会查询 DB 获取配置
**接受理由**: 单条主键查询开销极小（<1ms），换取代码简洁和解耦

### Trade-off 2: 灵活性 vs 复杂度
**取舍**: 不支持插件化加载外部引擎
**接受理由**: 当前需求仅 4 种引擎，插件化增加复杂度和安全风险

## Migration Plan

### 数据库迁移
1. 新增迁移文件，添加 `storage_type`（默认 `"local"`）和 `storage_config`（默认 `{}`）字段
2. 现有数据自动获得默认值，无需数据迁移脚本

### 部署步骤
1. 合并代码
2. 执行 `python manage.py migrate`
3. 重启服务（引擎在 `apps.py` 的 `ready()` 中注册）
4. 前端自动获取新字段和引擎列表

### 回滚策略
1. 回滚代码到上一版本
2. 新字段保留在数据库中不影响旧代码（旧代码不读取这些字段）
3. 如需彻底回滚，执行反向迁移删除字段

## Open Questions

1. **Mem0/Zep SDK 版本**: 是否锁定特定版本？建议锁定主版本（如 `mem0>=0.1,<1.0`）
2. **引擎可用性检测**: 是否在引擎列表 API 中标记哪些引擎的 SDK 已安装？
3. **配置校验时机**: 保存时校验还是使用时校验？建议保存时基础校验（必填项），使用时完整校验（连接测试）

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-29
```

## Capability Deltas

### memory-config-ui

## ADDED Requirements

### Requirement: 动态引擎配置表单
前端 SHALL 提供 `EngineConfigForm` 组件，根据后端返回的 schema 动态渲染配置表单。

#### Scenario: 渲染 text 字段
- **WHEN** schema 包含 `{"name": "base_url", "type": "text", "label": "API 地址"}`
- **THEN** 渲染 `<Input />` 组件，label 为 "API 地址"

#### Scenario: 渲染 password 字段
- **WHEN** schema 包含 `{"name": "api_key", "type": "password", "label": "API Key"}`
- **THEN** 渲染 `<Input.Password />` 组件

#### Scenario: 渲染 number 字段
- **WHEN** schema 包含 `{"name": "timeout", "type": "number", "label": "超时时间"}`
- **THEN** 渲染 `<InputNumber />` 组件

#### Scenario: 渲染 select 字段
- **WHEN** schema 包含 `{"name": "version", "type": "select", "options": [{"value": "v1", "label": "V1"}, {"value": "v2", "label": "V2"}]}`
- **THEN** 渲染 `<Select />` 组件，包含指定选项

#### Scenario: 渲染 json 字段
- **WHEN** schema 包含 `{"name": "headers", "type": "json", "label": "自定义请求头"}`
- **THEN** 渲染 `<Input.TextArea />` 组件，提交时校验 JSON 格式

### Requirement: 必填字段校验
动态表单 SHALL 根据 schema 的 `required` 属性进行校验。

#### Scenario: 必填字段为空
- **WHEN** 用户未填写 `required: true` 的字段并提交
- **THEN** 显示校验错误，阻止提交

#### Scenario: 可选字段为空
- **WHEN** 用户未填写 `required: false` 的字段并提交
- **THEN** 允许提交

### Requirement: 默认值填充
动态表单 SHALL 使用 schema 的 `default` 属性填充初始值。

#### Scenario: 新建时填充默认值
- **WHEN** 创建新记忆空间，选择 Mem0 引擎
- **THEN** `base_url` 字段自动填充 `https://api.mem0.ai`

#### Scenario: 编辑时显示已保存值
- **WHEN** 编辑已有记忆空间
- **THEN** 表单显示已保存的配置值，而非默认值

### Requirement: 敏感字段脱敏显示
动态表单 SHALL 对已保存的敏感字段进行脱敏显示。

#### Scenario: 编辑时显示脱敏 API Key
- **WHEN** 编辑已有记忆空间，`api_key` 已保存为 `m0-abc123xyz`
- **THEN** 显示为 `m0-***` 或占位符

#### Scenario: 修改敏感字段
- **WHEN** 用户在脱敏字段中输入新值
- **THEN** 提交时使用新值覆盖

### Requirement: 连接测试按钮
动态表单 SHALL 提供连接测试功能。

#### Scenario: 测试连接成功
- **WHEN** 用户点击"测试连接"按钮，配置有效
- **THEN** 显示成功提示 "连接成功"

#### Scenario: 测试连接失败
- **WHEN** 用户点击"测试连接"按钮，配置无效
- **THEN** 显示错误提示，包含失败原因

### Requirement: 引擎选择器
记忆空间创建/编辑页面 SHALL 提供引擎类型选择器。

#### Scenario: 创建时选择引擎
- **WHEN** 用户创建新记忆空间
- **THEN** 显示引擎类型下拉框，选项从 `/memory_engines/` API 获取

#### Scenario: 切换引擎类型
- **WHEN** 用户切换引擎类型
- **THEN** 动态加载对应引擎的配置表单

#### Scenario: 编辑时禁用引擎切换
- **WHEN** 用户编辑已有记忆空间
- **THEN** 引擎类型下拉框禁用，不允许切换

### memory-engine-api

## ADDED Requirements

### Requirement: 引擎列表 API
系统 SHALL 提供 API 端点返回所有可用的记忆引擎列表。

#### Scenario: 获取引擎列表
- **WHEN** 发送 `GET /api/opspilot/memory_engines/`
- **THEN** 返回 200，body 为引擎列表：
  ```json
  {
    "result": true,
    "data": [
      {"type": "local", "name": "本地存储", "description": "..."},
      {"type": "mem0", "name": "Mem0", "description": "..."},
      {"type": "zep", "name": "Zep", "description": "..."},
      {"type": "custom", "name": "自定义 API", "description": "..."}
    ]
  }
  ```

### Requirement: 引擎 Schema API
系统 SHALL 提供 API 端点返回指定引擎的配置参数定义。

#### Scenario: 获取引擎 Schema
- **WHEN** 发送 `GET /api/opspilot/memory_engines/mem0/schema/`
- **THEN** 返回 200，body 包含引擎信息和字段定义：
  ```json
  {
    "result": true,
    "data": {
      "type": "mem0",
      "name": "Mem0",
      "description": "...",
      "fields": [
        {"name": "api_key", "label": "API Key", "type": "password", "required": true, "encrypted": true},
        {"name": "base_url", "label": "API 地址", "type": "text", "required": false, "default": "https://api.mem0.ai"}
      ]
    }
  }
  ```

#### Scenario: 获取不存在的引擎 Schema
- **WHEN** 发送 `GET /api/opspilot/memory_engines/unknown/schema/`
- **THEN** 返回 400，body 包含错误信息

### Requirement: 引擎连接测试 API
系统 SHALL 提供 API 端点测试引擎配置是否有效。

#### Scenario: 测试连接成功
- **WHEN** 发送 `POST /api/opspilot/memory_engines/mem0/test/`，body 包含有效配置
- **THEN** 返回 200，body 为 `{"result": true, "data": {"success": true, "message": "连接成功"}}`

#### Scenario: 测试连接失败
- **WHEN** 发送 `POST /api/opspilot/memory_engines/mem0/test/`，body 包含无效配置
- **THEN** 返回 200，body 为 `{"result": true, "data": {"success": false, "message": "认证失败: Invalid API key"}}`

#### Scenario: 测试本地引擎
- **WHEN** 发送 `POST /api/opspilot/memory_engines/local/test/`
- **THEN** 返回 200，body 为 `{"result": true, "data": {"success": true, "message": "本地存储无需测试"}}`

### Requirement: API 权限控制
引擎 API SHALL 要求用户登录认证。

#### Scenario: 未认证访问
- **WHEN** 未携带认证 token 访问引擎 API
- **THEN** 返回 401 Unauthorized

#### Scenario: 认证用户访问
- **WHEN** 携带有效认证 token 访问引擎 API
- **THEN** 正常返回数据

### memory-engine-custom

## ADDED Requirements

### Requirement: Custom API 引擎读取记忆
Custom API 引擎 SHALL 通过用户配置的 HTTP 端点读取记忆。

#### Scenario: 调用自定义读取端点
- **WHEN** 调用 `read(entity, query, top_k)`
- **THEN** 发送 POST 请求到配置的 `read_endpoint`，body 包含 `{"entity": {...}, "query": "...", "top_k": 5}`

#### Scenario: 解析响应
- **WHEN** 自定义端点返回 `{"context": "...", "memories": [...]}`
- **THEN** 映射为 `MemoryReadResult(context=response["context"], raw_memories=response["memories"])`

#### Scenario: 端点返回错误
- **WHEN** 自定义端点返回非 2xx 状态码
- **THEN** 记录错误日志，返回空结果

### Requirement: Custom API 引擎写入记忆
Custom API 引擎 SHALL 通过用户配置的 HTTP 端点写入记忆。

#### Scenario: 调用自定义写入端点
- **WHEN** 调用 `write(entity, content, title, metadata)`
- **THEN** 发送 POST 请求到配置的 `write_endpoint`，body 包含 `{"entity": {...}, "content": "...", "title": "...", "metadata": {...}}`

#### Scenario: 解析写入响应
- **WHEN** 自定义端点返回 `{"success": true, "memory_id": "..."}`
- **THEN** 返回 `MemoryWriteResult(success=True, memory_id=response["memory_id"])`

### Requirement: Custom API 引擎删除记忆
Custom API 引擎 SHALL 通过用户配置的 HTTP 端点删除记忆。

#### Scenario: 调用自定义删除端点
- **WHEN** 调用 `delete(entity, memory_id)`
- **THEN** 发送 DELETE 请求到配置的 `delete_endpoint`，body 包含 `{"entity": {...}, "memory_id": "..."}`

### Requirement: Custom API 引擎配置 Schema
Custom API 引擎 SHALL 定义所需的配置参数。

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `CustomMemoryEngine.get_config_schema()`
- **THEN** 返回包含以下字段的列表：
  - `base_url`: text 类型，必填，API 基础地址
  - `read_endpoint`: text 类型，必填，读取端点路径（如 `/memory/read`）
  - `write_endpoint`: text 类型，必填，写入端点路径
  - `delete_endpoint`: text 类型，必填，删除端点路径
  - `api_key`: password 类型，可选，加密存储
  - `headers`: json 类型，可选，自定义请求头

### Requirement: Custom API 引擎请求认证
Custom API 引擎 SHALL 支持多种认证方式。

#### Scenario: Bearer Token 认证
- **WHEN** 配置了 `api_key`
- **THEN** 请求头包含 `Authorization: Bearer {api_key}`

#### Scenario: 自定义请求头
- **WHEN** 配置了 `headers` JSON
- **THEN** 将 headers 合并到请求头中

### memory-engine-local

## ADDED Requirements

### Requirement: 引擎基类接口
所有记忆引擎 SHALL 继承 `BaseMemoryEngine` 并实现以下抽象方法：
- `read(entity, query, top_k) -> MemoryReadResult`
- `write(entity, content, title, metadata) -> MemoryWriteResult`
- `delete(entity, memory_id) -> bool`
- `get_engine_info() -> dict` (类方法)
- `get_config_schema() -> list` (类方法)

#### Scenario: 引擎实现完整接口
- **WHEN** 创建继承 `BaseMemoryEngine` 的引擎类
- **THEN** 必须实现所有抽象方法，否则无法实例化

### Requirement: Local 引擎读取记忆
Local 引擎 SHALL 从 PostgreSQL 数据库读取记忆条目。

#### Scenario: 读取个人记忆
- **WHEN** 调用 `read(entity, query, top_k=5)`，entity 包含 `user_id="alice@example.com"`，记忆空间 scope 为 `personal`
- **THEN** 返回该用户在该记忆空间的最近 5 条记忆，按 `updated_at` 降序

#### Scenario: 读取组织记忆
- **WHEN** 调用 `read(entity, query, top_k=5)`，entity 包含 `organization_id=1`，记忆空间 scope 为 `team`
- **THEN** 返回该组织在该记忆空间的最近 5 条记忆

#### Scenario: 无匹配记忆
- **WHEN** 调用 `read()` 但无匹配记忆
- **THEN** 返回 `MemoryReadResult(context="", raw_memories=[], source="local")`

### Requirement: Local 引擎写入记忆
Local 引擎 SHALL 将记忆写入 PostgreSQL 数据库，支持智能合并。

#### Scenario: 写入新记忆（无现有记忆）
- **WHEN** 调用 `write(entity, content, title)`，该实体在该记忆空间无现有记忆
- **THEN** 创建新的 `Memory` 记录，返回 `MemoryWriteResult(success=True, memory_id=<new_id>)`

#### Scenario: 合并现有记忆
- **WHEN** 调用 `write(entity, content, title)`，该实体已有记忆
- **THEN** 使用 LLM 智能合并新旧内容，更新现有记忆记录

#### Scenario: 无 LLM 配置时简单追加
- **WHEN** 调用 `write()` 但记忆空间未配置 `default_model`
- **THEN** 将新内容追加到现有记忆末尾（用 `---` 分隔）

### Requirement: Local 引擎删除记忆
Local 引擎 SHALL 支持删除记忆条目。

#### Scenario: 删除指定记忆
- **WHEN** 调用 `delete(entity, memory_id="123")`
- **THEN** 删除 ID 为 123 的记忆记录，返回 `True`

#### Scenario: 删除实体所有记忆
- **WHEN** 调用 `delete(entity, memory_id=None)`
- **THEN** 删除该实体在该记忆空间的所有记忆，返回 `True`

#### Scenario: 删除不存在的记忆
- **WHEN** 调用 `delete()` 但目标记忆不存在
- **THEN** 返回 `False`

### Requirement: Local 引擎元信息
Local 引擎 SHALL 提供引擎元信息和空的配置 schema。

#### Scenario: 获取引擎信息
- **WHEN** 调用 `LocalMemoryEngine.get_engine_info()`
- **THEN** 返回 `{"type": "local", "name": "本地存储", "description": "使用 PostgreSQL 数据库存储记忆"}`

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `LocalMemoryEngine.get_config_schema()`
- **THEN** 返回空列表 `[]`（本地存储无需额外配置）

### memory-engine-mem0

## ADDED Requirements

### Requirement: Mem0 引擎读取记忆
Mem0 引擎 SHALL 通过 Mem0 API 搜索记忆。

#### Scenario: 语义搜索记忆
- **WHEN** 调用 `read(entity, query="用户的饮食偏好", top_k=5)`
- **THEN** 调用 Mem0 `/v3/memories/search/` API，返回语义相关的记忆

#### Scenario: 无 query 时获取最近记忆
- **WHEN** 调用 `read(entity, query=None, top_k=5)`
- **THEN** 使用默认 query "recent memories" 搜索

#### Scenario: API 调用失败
- **WHEN** Mem0 API 返回错误或超时
- **THEN** 记录错误日志，返回空结果 `MemoryReadResult(context="", raw_memories=[], source="mem0")`

### Requirement: Mem0 引擎写入记忆
Mem0 引擎 SHALL 通过 Mem0 API 添加记忆。

#### Scenario: 写入记忆
- **WHEN** 调用 `write(entity, content, title)`
- **THEN** 调用 Mem0 `/v3/memories/add/` API，传入 messages 格式的内容

#### Scenario: 异步处理
- **WHEN** Mem0 API 返回 `event_id`
- **THEN** 返回 `MemoryWriteResult(success=True, event_id=<event_id>)`

### Requirement: Mem0 引擎删除记忆
Mem0 引擎 SHALL 通过 Mem0 API 删除记忆。

#### Scenario: 删除指定记忆
- **WHEN** 调用 `delete(entity, memory_id="mem-123")`
- **THEN** 调用 Mem0 `DELETE /v1/memories/{memory_id}/` API

### Requirement: Mem0 引擎配置 Schema
Mem0 引擎 SHALL 定义所需的配置参数。

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `Mem0MemoryEngine.get_config_schema()`
- **THEN** 返回包含以下字段的列表：
  - `api_key`: password 类型，必填，加密存储
  - `base_url`: text 类型，可选，默认 `https://api.mem0.ai`
  - `org_id`: text 类型，可选
  - `project_id`: text 类型，可选

### Requirement: Mem0 引擎实体映射
Mem0 引擎 SHALL 将 `MemoryEntity` 映射为 Mem0 的 filter 格式。

#### Scenario: 个人记忆映射
- **WHEN** entity 包含 `user_id="alice@example.com"`
- **THEN** 映射为 `{"user_id": "alice@example.com"}`

#### Scenario: 组织记忆映射
- **WHEN** entity 包含 `organization_id=1`
- **THEN** 映射为 `{"agent_id": "org-1"}`

### memory-engine-registry

## ADDED Requirements

### Requirement: 引擎注册
系统 SHALL 提供 `MemoryEngineRegistry` 类，支持注册记忆引擎类。

#### Scenario: 注册引擎
- **WHEN** 调用 `MemoryEngineRegistry.register("mem0", Mem0MemoryEngine)`
- **THEN** 引擎类被存储在注册表中，可通过类型标识获取

#### Scenario: 重复注册覆盖
- **WHEN** 对同一 `engine_type` 多次调用 `register()`
- **THEN** 后注册的引擎类覆盖先前的

### Requirement: 获取引擎实例
系统 SHALL 提供 `get_engine(memory_space_id)` 方法，根据记忆空间 ID 返回对应的引擎实例。

#### Scenario: 获取已注册引擎
- **WHEN** 调用 `MemoryEngineRegistry.get_engine(memory_space_id)`，且该记忆空间的 `storage_type` 对应的引擎已注册
- **THEN** 返回该引擎类的实例，实例已使用记忆空间配置初始化

#### Scenario: 获取未注册引擎
- **WHEN** 调用 `get_engine(memory_space_id)`，且 `storage_type` 对应的引擎未注册
- **THEN** 抛出 `ValueError` 异常，消息包含未知的引擎类型

#### Scenario: 记忆空间不存在
- **WHEN** 调用 `get_engine(memory_space_id)`，且该 ID 不存在
- **THEN** 抛出 `MemorySpace.DoesNotExist` 异常

### Requirement: 列出所有引擎
系统 SHALL 提供 `list_engines()` 方法，返回所有已注册引擎的元信息列表。

#### Scenario: 列出引擎
- **WHEN** 调用 `MemoryEngineRegistry.list_engines()`
- **THEN** 返回列表，每项包含 `type`、`name`、`description` 字段

#### Scenario: 无引擎注册
- **WHEN** 调用 `list_engines()` 且无引擎注册
- **THEN** 返回空列表

### Requirement: 获取引擎 Schema
系统 SHALL 提供 `get_schema(engine_type)` 方法，返回指定引擎的参数定义。

#### Scenario: 获取已注册引擎 Schema
- **WHEN** 调用 `MemoryEngineRegistry.get_schema("mem0")`
- **THEN** 返回包含 `type`、`name`、`description`、`fields` 的字典

#### Scenario: 获取未注册引擎 Schema
- **WHEN** 调用 `get_schema("unknown")`
- **THEN** 抛出 `ValueError` 异常

### memory-engine-zep

## ADDED Requirements

### Requirement: Zep 引擎读取记忆
Zep 引擎 SHALL 通过 Zep API 获取会话记忆。

#### Scenario: 获取会话记忆
- **WHEN** 调用 `read(entity, query, top_k)`
- **THEN** 调用 Zep `GET /sessions/{sessionId}/memory` API，返回 context 字符串

#### Scenario: 返回结构化结果
- **WHEN** Zep API 返回 `context` 和 `relevant_facts`
- **THEN** 将 `context` 作为 `MemoryReadResult.context`，`relevant_facts` 放入 `raw_memories`

### Requirement: Zep 引擎写入记忆
Zep 引擎 SHALL 通过 Zep API 添加会话记忆。

#### Scenario: 写入记忆
- **WHEN** 调用 `write(entity, content, title)`
- **THEN** 调用 Zep `POST /sessions/{sessionId}/memory` API，传入 messages 格式

#### Scenario: 消息格式转换
- **WHEN** 传入纯文本 content
- **THEN** 转换为 `[{"role": "user", "role_type": "user", "content": content}]` 格式

### Requirement: Zep 引擎删除记忆
Zep 引擎 SHALL 通过 Zep API 删除会话记忆。

#### Scenario: 删除会话记忆
- **WHEN** 调用 `delete(entity)`
- **THEN** 调用 Zep `DELETE /sessions/{sessionId}/memory` API

### Requirement: Zep 引擎配置 Schema
Zep 引擎 SHALL 定义所需的配置参数。

#### Scenario: 获取配置 Schema
- **WHEN** 调用 `ZepMemoryEngine.get_config_schema()`
- **THEN** 返回包含以下字段的列表：
  - `api_key`: password 类型，必填，加密存储
  - `base_url`: text 类型，可选，默认 `https://api.getzep.com`

### Requirement: Zep 引擎会话 ID 映射
Zep 引擎 SHALL 将 `MemoryEntity` 映射为 Zep 的 session_id。

#### Scenario: 个人记忆映射
- **WHEN** entity 包含 `user_id="alice@example.com"`
- **THEN** session_id 为 `"alice@example.com"`

#### Scenario: 组织记忆映射
- **WHEN** entity 包含 `organization_id=1`
- **THEN** session_id 为 `"org-1"`

### memory-space

## ADDED Requirements

### Requirement: 存储类型字段
`MemorySpace` 模型 SHALL 包含 `storage_type` 字段标识使用的记忆引擎。

#### Scenario: 默认存储类型
- **WHEN** 创建新记忆空间未指定 `storage_type`
- **THEN** 默认值为 `"local"`

#### Scenario: 指定存储类型
- **WHEN** 创建记忆空间指定 `storage_type="mem0"`
- **THEN** 保存该值

### Requirement: 存储配置字段
`MemorySpace` 模型 SHALL 包含 `storage_config` JSON 字段存储引擎配置。

#### Scenario: 默认配置
- **WHEN** 创建新记忆空间未指定 `storage_config`
- **THEN** 默认值为空字典 `{}`

#### Scenario: 保存配置
- **WHEN** 创建记忆空间指定 `storage_config={"api_key": "xxx", "base_url": "..."}`
- **THEN** 保存该配置

### Requirement: 敏感配置加密
`MemorySpace` 模型 SHALL 对 `storage_config` 中的敏感字段进行加密存储。

#### Scenario: 保存时加密
- **WHEN** 保存 `storage_config` 包含 `api_key` 字段
- **THEN** `api_key` 值被加密后存储到数据库

#### Scenario: 读取时解密
- **WHEN** 读取 `storage_config`
- **THEN** `api_key` 值被解密后返回

### Requirement: API 返回脱敏配置
记忆空间 API SHALL 对敏感配置字段进行脱敏处理。

#### Scenario: 列表 API 脱敏
- **WHEN** 调用 `GET /api/opspilot/memory_space/`
- **THEN** 返回的 `storage_config` 中 `api_key` 显示为 `"***"`

#### Scenario: 详情 API 脱敏
- **WHEN** 调用 `GET /api/opspilot/memory_space/{id}/`
- **THEN** 返回的 `storage_config` 中 `api_key` 显示为前缀 + `"***"`（如 `"m0-***"`）

### Requirement: 创建时指定引擎
记忆空间创建 API SHALL 支持指定存储类型和配置。

#### Scenario: 创建本地存储记忆空间
- **WHEN** 调用 `POST /api/opspilot/memory_space/`，body 包含 `{"name": "test", "storage_type": "local"}`
- **THEN** 创建成功，`storage_type` 为 `"local"`，`storage_config` 为 `{}`

#### Scenario: 创建 Mem0 记忆空间
- **WHEN** 调用 `POST /api/opspilot/memory_space/`，body 包含 `{"name": "test", "storage_type": "mem0", "storage_config": {"api_key": "xxx"}}`
- **THEN** 创建成功，配置被加密存储

### Requirement: 编辑时禁止切换引擎
记忆空间更新 API SHALL 禁止修改 `storage_type`。

#### Scenario: 尝试切换引擎类型
- **WHEN** 调用 `PUT /api/opspilot/memory_space/{id}/`，body 包含不同的 `storage_type`
- **THEN** 返回 400 错误，提示不允许切换存储类型

#### Scenario: 更新配置
- **WHEN** 调用 `PUT /api/opspilot/memory_space/{id}/`，body 包含新的 `storage_config`
- **THEN** 更新成功，新配置被加密存储

### memory-workflow-nodes

## MODIFIED Requirements

### Requirement: 记忆读取节点执行
记忆读取节点 SHALL 通过引擎注册表获取引擎实例执行读取操作。

#### Scenario: 读取记忆
- **WHEN** 执行记忆读取节点，配置了 `memory_space_id`
- **THEN** 通过 `MemoryEngineRegistry.get_engine(memory_space_id)` 获取引擎，调用 `engine.read(entity, query, top_k)`

#### Scenario: 返回上下文
- **WHEN** 引擎返回 `MemoryReadResult`
- **THEN** 将 `result.context` 作为节点输出的 `memory_context`

#### Scenario: 引擎不可用
- **WHEN** 引擎初始化失败（如 SDK 未安装）
- **THEN** 记录错误日志，返回空 `memory_context`

### Requirement: 记忆写入节点执行
记忆写入节点 SHALL 通过 Celery 异步任务调用引擎写入。

#### Scenario: 触发异步写入
- **WHEN** 执行记忆写入节点
- **THEN** 调用 `process_memory_write.delay(memory_space_id, entity, content, title)`，节点立即返回不阻塞

#### Scenario: 异步任务执行
- **WHEN** Celery 任务执行
- **THEN** 通过 `MemoryEngineRegistry.get_engine(memory_space_id)` 获取引擎，调用 `engine.write(entity, content, title)`

#### Scenario: 写入失败不影响主流程
- **WHEN** 引擎写入失败
- **THEN** 记录错误日志，主对话流程不受影响

### Requirement: 实体构建
工作流节点 SHALL 根据记忆空间 scope 构建 `MemoryEntity`。

#### Scenario: 个人记忆实体
- **WHEN** 记忆空间 `scope="personal"`
- **THEN** 构建 `MemoryEntity(user_id=current_user.username)`

#### Scenario: 组织记忆实体
- **WHEN** 记忆空间 `scope="team"`
- **THEN** 构建 `MemoryEntity(organization_id=current_organization_id)`

## Work Checklist

## 1. 数据模型与迁移

- [x] 1.1 在 `MemorySpace` 模型添加 `storage_type` 字段（CharField，默认 `"local"`）
- [x] 1.2 在 `MemorySpace` 模型添加 `storage_config` 字段（JSONField，默认 `{}`）
- [x] 1.3 实现 `MemorySpace` 的 `EncryptMixin` 集成，加密 `storage_config` 中的敏感字段
- [x] 1.4 生成并执行数据库迁移

## 2. 引擎基础架构

- [x] 2.1 创建 `server/apps/opspilot/memory/` 目录结构
- [x] 2.2 实现 `BaseMemoryEngine` 抽象基类（`read/write/delete/get_engine_info/get_config_schema`）
- [x] 2.3 实现 `MemoryEntity` 数据类（`user_id`, `organization_id`）
- [x] 2.4 实现 `MemoryReadResult` 和 `MemoryWriteResult` 数据类
- [x] 2.5 实现 `MemoryEngineRegistry` 类（`register/get_engine/list_engines/get_schema`）

## 3. 引擎实现

- [x] 3.1 实现 `LocalMemoryEngine`（读取/写入/删除，复用现有 Django ORM 逻辑）
- [x] 3.2 实现 `Mem0MemoryEngine`（API 调用，实体映射，配置 schema）
- [x] 3.3 实现 `ZepMemoryEngine`（API 调用，会话 ID 映射，配置 schema）
- [x] 3.4 实现 `CustomMemoryEngine`（HTTP 请求，认证，配置 schema）

## 4. 引擎注册与初始化

- [x] 4.1 在 `apps.py` 的 `ready()` 方法中注册所有引擎
- [x] 4.2 实现引擎 SDK 可用性检测（`mem0`/`zep-python` 是否安装）
- [x] 4.3 添加可选依赖到 `pyproject.toml`（`mem0`, `zep-python`, `httpx`）

## 5. 引擎 API 端点

- [x] 5.1 创建 `MemoryEngineViewSet`（`list_engines`, `get_schema`, `test_connection`）
- [x] 5.2 注册 URL 路由（`/api/opspilot/memory_engines/`）
- [x] 5.3 实现连接测试逻辑（各引擎的 `test_connection` 方法）

## 6. 记忆空间 API 修改

- [x] 6.1 修改 `MemorySpaceSerializer` 添加 `storage_type` 和 `storage_config` 字段
- [x] 6.2 实现 `storage_config` 脱敏逻辑（列表/详情 API 返回时）
- [x] 6.3 实现更新时禁止切换 `storage_type` 的校验

## 7. 工作流节点改造

- [x] 7.1 修改 `memory_read.py` 使用 `MemoryEngineRegistry.get_engine()` 获取引擎
- [x] 7.2 修改 `memory_write.py` 使用引擎注册表
- [x] 7.3 修改 `process_memory_write` Celery 任务使用引擎注册表
- [x] 7.4 实现 `MemoryEntity` 构建逻辑（根据 scope 构建 user_id 或 organization_id）

## 8. 前端类型与 API

- [x] 8.1 更新 `MemorySpace` TypeScript 类型（添加 `storage_type`, `storage_config`）
- [x] 8.2 添加引擎 API hooks（`useMemoryEngines`, `useEngineSchema`, `useTestConnection`）
- [x] 8.3 添加引擎相关国际化文案

## 9. 前端动态配置表单

- [x] 9.1 实现 `EngineConfigForm` 组件（根据 schema 动态渲染）
- [x] 9.2 实现字段类型映射（text/password/number/select/json）
- [x] 9.3 实现必填校验和默认值填充
- [x] 9.4 实现敏感字段脱敏显示
- [x] 9.5 实现连接测试按钮

## 10. 前端页面集成

- [x] 10.1 修改记忆空间创建弹窗，添加引擎类型选择器
- [x] 10.2 修改记忆空间配置页面，集成 `EngineConfigForm`
- [x] 10.3 实现编辑时禁用引擎类型切换

## 11. 验证与清理

- [x] 11.1 验证本地引擎向后兼容（现有记忆空间正常工作）
- [x] 11.2 验证 Mem0 引擎端到端流程
- [x] 11.3 验证 Zep 引擎端到端流程
- [x] 11.4 验证 Custom API 引擎端到端流程
- [x] 11.5 验证前端动态表单渲染和提交
