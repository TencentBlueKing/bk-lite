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
# memory_read.py
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
