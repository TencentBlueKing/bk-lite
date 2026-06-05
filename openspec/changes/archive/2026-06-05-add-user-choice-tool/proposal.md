## Why

OpsPilot 的 ReAct Loop 目前只有审批功能（`request_human_approval`），用于高危操作的人工确认。但当 LLM 需要用户从多个选项中选择时（如用户请求查询多个表但一次只能查一个），只能通过普通对话让用户打字回复，体验不佳。

需要一个点击式的用户选择功能，让用户可以直接点击选项而不是打字，提升交互效率和用户体验。

## What Changes

- 新增 `request_user_choice` 工具，供 LLM 在需要用户选择时调用
- 新增 `user_choice_request` SSE 事件，前端渲染选择卡片
- 新增 `/submit_choice/` API 端点，接收用户选择
- 新增 `UserChoiceCard` 前端组件，支持按钮/下拉/复选框三种交互模式
- 支持单选和多选
- 支持超时后使用默认值

## Capabilities

### New Capabilities

- `user-choice-tool`: 后端用户选择工具实现，包括工具构建、缓存存储、等待轮询逻辑
- `user-choice-frontend`: 前端用户选择组件和 SSE 事件处理

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **后端代码**:
  - `server/apps/opspilot/utils/user_choice.py` (新增)
  - `server/apps/opspilot/metis/llm/chain/node.py` (添加 `_build_choice_tool`)
  - `server/apps/opspilot/views.py` (添加 `submit_choice` 端点)
  - `server/apps/opspilot/urls.py` (添加路由)

- **前端代码**:
  - `web/src/app/opspilot/components/custom-chat-sse/UserChoiceCard.tsx` (新增)
  - `web/src/app/opspilot/components/custom-chat-sse/aguiMessageHandler.ts` (处理新事件)
  - `web/src/app/opspilot/types/global.ts` (添加类型定义)
  - `web/src/app/opspilot/types/chat.ts` (添加事件类型)

- **API**: 新增 `POST /api/opspilot/bot_mgmt/submit_choice/`

- **依赖**: 无新增依赖，复用现有 Redis 缓存机制
