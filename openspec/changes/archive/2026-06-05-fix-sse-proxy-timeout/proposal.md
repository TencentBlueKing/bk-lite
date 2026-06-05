## Why

OpsPilot 的 Web 聊天功能在长时间对话（特别是 Agent 执行工具）时会出现超时断开问题。根本原因是：

1. **Next.js Proxy 层**没有正确处理 SSE 流式响应，也没有配置足够的超时时间
2. **LLM 调用超时**默认 120 秒，对于复杂推理任务可能不够

这导致用户在使用 Agent 功能时，经常遇到连接中断，体验很差。

## What Changes

- **修复 Next.js API Proxy**：正确透传 SSE 流式响应，增加超时配置到 5 分钟
- **增加 LLM 调用超时**：将默认 `llm_timeout_seconds` 从 120 秒增加到 300 秒
- **优化 SSE 响应头**：确保禁用缓冲、设置正确的 Content-Type

## Capabilities

### New Capabilities

- `sse-proxy-passthrough`: Next.js Proxy 正确识别并透传 SSE 流式响应，包括正确的响应头和超时配置

### Modified Capabilities

（无现有 spec 需要修改）

## Impact

- **前端**：`web/src/app/(core)/api/proxy/[...path]/route.ts` - Proxy 路由处理
- **后端**：`server/apps/opspilot/metis/llm/chain/entity.py` - TimeoutConfig 默认值
- **用户体验**：长时间 Agent 任务不再意外断开
- **兼容性**：无破坏性变更，仅增加超时容忍度
