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
