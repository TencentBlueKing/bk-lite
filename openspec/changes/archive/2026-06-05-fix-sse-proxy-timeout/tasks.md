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
