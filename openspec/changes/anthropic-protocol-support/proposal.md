## Why

OpsPilot 当前所有 LLM 供应商调用都使用 OpenAI 协议格式，虽然 `vendor_type` 中已定义 `anthropic` 类型，但实际调用时仍走 `ChatOpenAI` 客户端。这导致：

1. 无法直接对接 Anthropic 官方 API（使用不同的认证头和消息格式）
2. 用户配置 Anthropic 供应商后，测试连接和模型调用会失败
3. 对于使用 Anthropic 协议的第三方代理服务，"其他"类型供应商无法正确调用

## What Changes

- 新增 Anthropic 协议支持，使 `anthropic` 类型供应商使用 `ChatAnthropic` 客户端调用 API
- 为 `other`（其他）类型供应商新增 `protocol_type` 字段，允许用户选择 OpenAI 或 Anthropic 协议
- 前端在选择"其他"供应商时显示协议选择 UI，其他供应商类型自动使用对应协议
- 模型同步优先尝试 Anthropic API，不可用时支持手动添加模型

## Capabilities

### New Capabilities

- `anthropic-protocol-support`: 支持 Anthropic 协议格式的 LLM 调用，包括认证、消息格式转换和流式响应处理

### Modified Capabilities

- `model-vendor-management`: ModelVendor 模型新增 `protocol_type` 字段，用于"其他"类型供应商的协议选择
- `llm-client-factory`: LLMClientFactory 根据协议类型创建对应的 LangChain 客户端（ChatOpenAI 或 ChatAnthropic）
- `model-sync-service`: 模型同步服务支持 Anthropic API 格式的模型列表获取

## Impact

### Backend (server/)

- `server/pyproject.toml`: 新增 `langchain-anthropic` 依赖
- `server/apps/opspilot/models/model_provider_mgmt.py`: ModelVendor 新增 `protocol_type` 字段
- `server/apps/opspilot/migrations/`: 新增数据库迁移文件
- `server/apps/opspilot/metis/llm/common/llm_client_factory.py`: 支持创建 ChatAnthropic 客户端
- `server/apps/opspilot/metis/llm/chain/entity.py`: BasicLLMRequest 新增 `protocol_type` 属性
- `server/apps/opspilot/services/model_vendor_sync_service.py`: 支持 Anthropic 模型列表获取
- `server/apps/opspilot/serializers/model_vendor_serializer.py`: 序列化器支持 `protocol_type` 字段

### Frontend (web/)

- `web/src/app/opspilot/types/provider.ts`: 类型定义新增 `protocol_type`
- `web/src/app/opspilot/constants/provider.ts`: 新增协议类型常量
- `web/src/app/opspilot/components/provider/vendorModal.tsx`: "其他"类型供应商显示协议选择 UI

## Protocol Selection Rules

| 供应商类型 | 支持的协议 | 显示协议选择 | 默认协议 |
|-----------|-----------|-------------|---------|
| openai | OpenAI | ❌ | openai |
| azure | OpenAI | ❌ | openai |
| aliyun | OpenAI | ❌ | openai |
| zhipu | OpenAI | ❌ | openai |
| baidu | OpenAI | ❌ | openai |
| anthropic | Anthropic | ❌ | anthropic |
| deepseek | OpenAI | ❌ | openai |
| other | OpenAI / Anthropic | ✅ | openai |

## Default API Endpoints

- Anthropic 官方: `https://api.anthropic.com`
