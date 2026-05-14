## 1. 后端核心模块

- [x] 1.1 创建 `server/apps/opspilot/utils/user_choice.py`，实现缓存存储和轮询逻辑
- [x] 1.2 在 `server/apps/opspilot/metis/llm/chain/node.py` 中添加 `_build_choice_tool()` 方法
- [x] 1.3 在 `build_react_nodes()` 中注入 choice_tool（与 approval_tool 并列）

## 2. 后端 API 端点

- [x] 2.1 在 `server/apps/opspilot/views.py` 中添加 `submit_choice` 视图函数
- [x] 2.2 在 `server/apps/opspilot/urls.py` 中添加 `/submit_choice/` 路由

## 3. 前端类型定义

- [x] 3.1 在 `web/src/app/opspilot/types/global.ts` 中添加 `UserChoiceOption` 和 `UserChoiceRequest` 接口
- [x] 3.2 在 `web/src/app/opspilot/types/chat.ts` 中添加 `UserChoiceRequestValue` 类型
- [x] 3.3 更新 `AGUIMessage.value` 联合类型，包含 `UserChoiceRequestValue`
- [x] 3.4 在 `CustomChatMessage` 接口中添加 `userChoiceRequests?: UserChoiceRequest[]` 字段

## 4. 前端 SSE 事件处理

- [x] 4.1 在 `aguiMessageHandler.ts` 中添加 `userChoiceRequests` 数组和处理逻辑
- [x] 4.2 添加 `handleUserChoiceRequest()` 方法处理 `user_choice_request` 事件
- [x] 4.3 在 `updateMessageContent()` 中同步 `userChoiceRequests` 状态

## 5. 前端选择卡片组件

- [x] 5.1 创建 `web/src/app/opspilot/components/custom-chat-sse/UserChoiceCard.tsx` 组件
- [x] 5.2 实现按钮模式（单选，≤5 选项）
- [x] 5.3 实现下拉菜单模式（单选，>5 选项）
- [x] 5.4 实现复选框模式（多选）
- [x] 5.5 实现倒计时显示
- [x] 5.6 实现推荐选项高亮
- [x] 5.7 添加组件样式（复用 ApprovalCard 样式基础）

## 6. 前端组件集成

- [x] 6.1 在 `custom-chat-sse/index.tsx` 中导入并渲染 UserChoiceCard
- [x] 6.2 实现 `onSubmit` 回调，更新消息状态

## 7. 国际化

- [x] 7.1 添加中文翻译 key（chat.choiceMinSelect, chat.choiceSubmitFailed, chat.choicePlaceholder, chat.choiceConfirm, chat.choiceTimeout, chat.choiceSelected）
- [x] 7.2 添加英文翻译

## 8. 测试

- [x] 8.1 创建 `server/apps/opspilot/tests/react_agent/cases/test_user_choice.py` 单元测试
- [x] 8.2 测试工具注入、选择提交、超时处理、无人值守场景
