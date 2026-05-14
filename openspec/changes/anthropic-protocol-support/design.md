## Context

OpsPilot 当前的 LLM 调用架构基于 LangChain，所有供应商统一使用 `ChatOpenAI` 客户端。虽然 `VENDOR_TYPE_CHOICES` 中已定义 `anthropic` 类型，但实际调用时：

1. `LLMClientFactory.create_client()` 只创建 `ChatOpenAI` 实例
2. `ModelVendorSyncService.OPENAI_COMPATIBLE_VENDOR_TYPES` 不包含 `anthropic`
3. 所有模型属性都命名为 `openai_api_key`、`openai_api_base`

这导致 Anthropic 供应商配置后无法正常工作。本次变更需要在保持现有架构稳定的前提下，扩展协议支持能力。

关键约束：
- 不重构现有 LangChain 架构，利用 `langchain-anthropic` 包的 `ChatAnthropic` 类
- 协议选择逻辑对大多数供应商透明，只有 `other` 类型需要用户显式选择
- 向后兼容现有数据，`protocol_type` 字段默认为 `openai`

## Goals / Non-Goals

**Goals:**
- 为 `anthropic` 类型供应商启用 Anthropic 协议调用
- 为 `other` 类型供应商提供协议选择能力（OpenAI / Anthropic）
- 支持 Anthropic 模型列表获取（优先 API，失败时手动添加）
- 前端在 `other` 类型时显示协议选择 UI

**Non-Goals:**
- 不重构 LangChain 架构或引入新的抽象层
- 不修改其他供应商类型的行为（openai、azure、aliyun 等）
- 不支持 Anthropic 特有功能（如 extended thinking），仅保证基础聊天能力
- 不在本次变更中支持更多协议类型

## Decisions

### 1. 使用 LangChain Anthropic 集成而非原生 SDK

选择 `langchain-anthropic` 包的 `ChatAnthropic` 类，而非直接使用 `anthropic` SDK。

**原因：**
- `ChatAnthropic` 与 `ChatOpenAI` 接口兼容，都继承自 `BaseChatModel`
- 现有代码（agent、chain、tool）无需修改，只需在工厂层切换客户端
- 流式输出、工具调用等能力已由 LangChain 封装
- 减少代码改动量和测试范围

**备选方案：** 直接使用 `anthropic` SDK 并自行处理消息格式转换、流式响应解析。但这会增加大量适配代码，且与现有 LangChain 架构不一致，因此不采用。

### 2. 协议类型由供应商类型隐式推导 + other 显式选择

协议选择逻辑：
```python
def get_protocol_type(vendor: ModelVendor) -> str:
    if vendor.vendor_type == "anthropic":
        return "anthropic"
    if vendor.vendor_type == "other":
        return vendor.protocol_type or "openai"
    return "openai"
```

**原因：**
- 大多数供应商协议固定，无需用户选择
- 只有 `other` 类型可能对接不同协议的第三方服务
- 减少 UI 复杂度，避免用户困惑

**备选方案：** 所有供应商都显示协议选择。但这会增加配置复杂度，且对于 OpenAI、Azure 等供应商没有实际意义，因此不采用。

### 3. protocol_type 字段仅在 ModelVendor 层存储

`protocol_type` 字段添加到 `ModelVendor` 模型，而非 `LLMModel`。

**原因：**
- 协议是供应商级别的属性，同一供应商下的所有模型使用相同协议
- 减少数据冗余和一致性维护成本
- `LLMModel` 通过 `vendor` 外键获取协议类型

**备选方案：** 在 `LLMModel` 层也存储 `protocol_type`。但这会导致数据冗余，且同一供应商下模型协议不一致的场景不存在，因此不采用。

### 4. Anthropic 模型同步采用"尝试 API + 手动兜底"策略

模型同步逻辑：
1. 首先尝试调用 `GET /v1/models` 获取模型列表
2. 如果 API 返回错误或不可用，提示用户手动添加模型
3. 不硬编码模型列表，避免维护负担

**原因：**
- Anthropic 的 `/v1/models` API 可能不稳定或需要特定权限
- 硬编码模型列表需要持续维护，且可能与用户实际可用模型不符
- 手动添加模型是现有功能，用户已熟悉

**备选方案：** 硬编码 Anthropic 官方模型列表。但这需要持续维护，且无法覆盖用户自定义模型，因此不采用。

### 5. 前端协议选择 UI 仅在 other 类型时显示

UI 设计：
- 选择 `other` 供应商类型时，显示"协议类型"单选框
- 选项：OpenAI 兼容（默认）、Anthropic 兼容
- 其他供应商类型不显示此选项

**原因：**
- 减少 UI 复杂度，避免用户对固定协议供应商产生困惑
- 与后端协议推导逻辑一致
- 保持现有供应商配置流程不变

## Architecture

### 调用链路

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LLM 调用链路                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  LLMModel                                                                   │
│     │                                                                       │
│     ▼                                                                       │
│  BasicLLMRequest (包含 protocol_type)                                       │
│     │                                                                       │
│     ▼                                                                       │
│  LLMClientFactory.create_client()                                           │
│     │                                                                       │
│     ├── protocol_type == "anthropic" ──▶ ChatAnthropic                     │
│     │                                                                       │
│     └── protocol_type == "openai" ────▶ ChatOpenAI                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 数据模型变更

```python
# ModelVendor 新增字段
PROTOCOL_TYPE_CHOICES = (
    ("openai", "OpenAI 兼容"),
    ("anthropic", "Anthropic 兼容"),
)

class ModelVendor(models.Model):
    # ... 现有字段 ...
    protocol_type = models.CharField(
        max_length=20,
        choices=PROTOCOL_TYPE_CHOICES,
        default="openai",
        verbose_name="协议类型",
    )
```

## Risks

### 1. LangChain Anthropic 版本兼容性
- **风险：** `langchain-anthropic` 与现有 `langchain` 版本可能存在兼容性问题
- **缓解：** 在 CI 中添加依赖兼容性测试，锁定兼容版本

### 2. Anthropic API 行为差异
- **风险：** Anthropic API 的错误码、限流策略与 OpenAI 不同，可能导致错误处理不一致
- **缓解：** 在 `normalize_llm_error_message()` 中添加 Anthropic 错误码映射

### 3. 流式响应格式差异
- **风险：** Anthropic SSE 格式与 OpenAI 不同，可能影响前端流式展示
- **缓解：** LangChain 已封装差异，但需要在集成测试中验证流式输出

## Open Questions

1. ~~协议选择的触发条件~~ → 已决定：仅 `other` 类型显示协议选择
2. ~~模型同步策略~~ → 已决定：尝试 API + 手动兜底
3. ~~默认 API 地址~~ → 已决定：`https://api.anthropic.com`
