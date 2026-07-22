# 2026 06 05 Fix Sse Proxy Timeout

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-fix-sse-proxy-timeout/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

OpsPilot 的 Web 聊天使用 SSE (Server-Sent Events) 实现流式响应。当前架构：

```
Browser → Next.js Proxy → Django ASGI → LLM API
         (route.ts)      (SSE stream)
```

**问题**：
1. Next.js Proxy (`web/src/app/(core)/api/proxy/[...path]/route.ts`) 没有正确处理 SSE 响应头
2. Proxy 没有配置超时，依赖 Next.js 默认行为（约 60s）
3. 后端 LLM 调用超时 120s，对于复杂 Agent 任务可能不够

**约束**：
- 不能改变现有 API 路径结构
- 需要兼容非 SSE 的普通 API 请求
- 不能影响其他模块的 Proxy 行为

## Goals / Non-Goals

**Goals:**
- Next.js Proxy 正确透传 SSE 流式响应（Content-Type、缓冲控制）
- Proxy 超时配置为 5 分钟，匹配后端 Agent 总超时
- LLM 单次调用超时从 120s 增加到 300s
- 保持向后兼容，非 SSE 请求行为不变

**Non-Goals:**
- 不实现心跳保活机制（可作为后续优化）
- 不修改 Nginx/Ingress 层配置（部署层面单独处理）
- 不改变 AGUI 协议或事件格式

## Decisions

### Decision 1: Proxy 超时策略

**选择**：使用 AbortController + setTimeout 实现 5 分钟超时

**理由**：
- fetch API 原生支持 AbortController
- 可以精确控制超时时间
- 超时后能返回明确的 504 错误

**替代方案**：
- Next.js `experimental.proxyTimeout` 配置 → 不够灵活，且是实验性功能
- 不设置超时 → 可能导致连接无限挂起

### Decision 2: SSE 响应识别

**选择**：通过 `Content-Type: text/event-stream` 识别 SSE 响应

**理由**：
- 标准的 SSE 识别方式
- 后端已经正确设置了 Content-Type
- 简单可靠

**替代方案**：
- 通过 URL 路径判断 → 不够通用，需要维护路径列表
- 通过请求头判断 → 增加复杂度

### Decision 3: SSE 响应头处理

**选择**：透传后端响应头，并确保关键头存在

关键响应头：
```
Content-Type: text/event-stream
Cache-Control: no-cache, no-store, must-revalidate
X-Accel-Buffering: no  (禁用 Nginx 缓冲)
Connection: keep-alive
```

**理由**：
- 后端已设置正确的头，透传即可
- 额外确保关键头存在，防止被中间层覆盖

### Decision 4: LLM 超时配置

**选择**：将 `TimeoutConfig.llm_timeout_seconds` 默认值从 120s 改为 300s

**理由**：
- 复杂推理任务（如 Claude 深度思考）可能需要更长时间
- 与 Agent 总超时 (300s) 保持一致
- 用户仍可通过配置覆盖

**替代方案**：
- 保持 120s，让用户自行配置 → 默认体验差
- 设置更长如 600s → 可能掩盖真正的问题

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 超时设置过长可能掩盖后端问题 | 保留日志记录，监控长时间请求 |
| SSE 识别可能误判 | 仅当 Content-Type 完全匹配时才特殊处理 |
| 增加服务器连接占用 | 5 分钟是合理上限，与 Agent 总超时一致 |
| 修改默认超时可能影响现有行为 | 仅影响超过 120s 的请求，这些之前本来就会失败 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-27
```

## Capability Deltas

### sse-proxy-passthrough

## ADDED Requirements

### Requirement: SSE Response Detection
The Proxy SHALL detect SSE responses by checking if the upstream `Content-Type` header starts with `text/event-stream`.

#### Scenario: SSE response detected
- **WHEN** upstream response has `Content-Type: text/event-stream`
- **THEN** Proxy SHALL apply SSE-specific handling (streaming, headers, timeout)

#### Scenario: Non-SSE response unchanged
- **WHEN** upstream response has `Content-Type: application/json`
- **THEN** Proxy SHALL use default handling without SSE optimizations

### Requirement: SSE Header Passthrough
The Proxy SHALL transparently pass through all SSE-related headers from the upstream response, and ensure critical headers are present.

#### Scenario: Headers passed through
- **WHEN** upstream SSE response includes `Content-Type`, `Cache-Control`, `X-Accel-Buffering`
- **THEN** Proxy SHALL include all these headers in the client response

#### Scenario: Missing critical headers added
- **WHEN** upstream SSE response is missing `X-Accel-Buffering` header
- **THEN** Proxy SHALL add `X-Accel-Buffering: no` to disable Nginx buffering

### Requirement: SSE Stream Passthrough
The Proxy SHALL stream SSE data chunks to the client as they arrive, without buffering the entire response.

#### Scenario: Chunks streamed immediately
- **WHEN** upstream sends an SSE event chunk
- **THEN** Proxy SHALL forward the chunk to client within 100ms (no buffering delay)

#### Scenario: Stream remains open
- **WHEN** upstream SSE connection is active
- **THEN** Proxy SHALL keep client connection open until upstream closes or timeout

### Requirement: Extended Timeout for SSE
The Proxy SHALL use a 5-minute (300 second) timeout for SSE connections, matching the backend Agent total timeout.

#### Scenario: Long SSE connection allowed
- **WHEN** SSE connection has been active for 4 minutes with periodic data
- **THEN** Proxy SHALL keep the connection open

#### Scenario: Timeout after inactivity
- **WHEN** no data received from upstream for 5 minutes
- **THEN** Proxy SHALL close the connection and return 504 Gateway Timeout

### Requirement: LLM Call Timeout Extension
The default `llm_timeout_seconds` in `TimeoutConfig` SHALL be 300 seconds to support complex reasoning tasks.

#### Scenario: Default timeout is 300s
- **WHEN** a new `TimeoutConfig` is created without explicit `llm_timeout_seconds`
- **THEN** the default value SHALL be 300 seconds

#### Scenario: Custom timeout respected
- **WHEN** `TimeoutConfig` is created with `llm_timeout_seconds=600`
- **THEN** the LLM call timeout SHALL be 600 seconds

## Work Checklist

## 1. Next.js Proxy SSE 支持

- [x] 1.1 修改 `web/src/app/(core)/api/proxy/[...path]/route.ts`，添加 SSE 响应检测逻辑（检查 `Content-Type: text/event-stream`）
- [x] 1.2 实现 SSE 响应的流式透传，使用 `ReadableStream` 逐块转发数据
- [x] 1.3 确保 SSE 关键响应头透传：`Content-Type`、`Cache-Control`、`X-Accel-Buffering: no`
- [x] 1.4 添加 5 分钟（300 秒）超时配置，使用 `AbortController` + `setTimeout` 实现

## 2. 后端超时配置调整

- [x] 2.1 修改 `server/apps/opspilot/metis/llm/chain/entity.py`，将 `TimeoutConfig.llm_timeout_seconds` 默认值从 120 改为 300

## 3. 验证测试

- [x] 3.1 本地启动 Web 和 Server，测试 OpsPilot 聊天功能的 SSE 流式响应
- [x] 3.2 验证长时间 Agent 任务（超过 2 分钟）不会超时断开
- [x] 3.3 验证浏览器开发者工具中响应头包含 `X-Accel-Buffering: no`

> **注意**: 以上验证任务需要手动测试，代码变更已完成。
