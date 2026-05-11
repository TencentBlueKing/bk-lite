## Why

`ChatService.invoke_chat()` 在 LLM/Agent 执行异常时，将异常降级为普通 `{"message": error_text}` 返回，不携带任何失败标记。下游节点（AgentNode、IntentClassifier）和 API 层（OpenAI 兼容接口）将错误文本当作成功输出处理，导致：

1. **路由错误**：意图分类失败时静默回退到第一个意图，消息被错误路由
2. **审计污染**：`WorkFlowTaskResult` 记录为 SUCCESS，对话历史记录错误文本为正常回复
3. **用户困惑**：用户收到错误文本但无法区分成功/失败
4. **排障困难**：真实失败被掩盖，难以定位问题

参考：[GitHub Issue #2853](https://github.com/TencentBlueKing/bk-lite/issues/2853)

## What Changes

- **BREAKING**: `ChatService.invoke_chat()` 返回结构新增 `success`、`error`、`error_type` 字段
- 所有 `invoke_chat` 消费者必须检查 `success` 字段
- `IntentClassifierNode` 移除静默回退逻辑，失败时返回显式错误
- `AgentNode` 失败时返回带 `success=False` 的结果
- OpenAI 兼容接口失败时返回错误响应而非伪装成功
- `Engine._check_chain_result()` 逻辑保持不变（已正确检查 `success=False`）

## Capabilities

### New Capabilities

- `llm-error-propagation`: 定义 LLM 执行失败时的错误传播机制，包括返回结构、错误类型、下游处理规范

### Modified Capabilities

<!-- 无现有 spec 需要修改 -->

## Impact

### 代码影响

| 文件 | 修改类型 |
|------|----------|
| `server/apps/opspilot/services/chat_service.py` | 修改返回结构 |
| `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` | 添加错误检查 |
| `server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py` | 移除静默回退，添加错误检查 |
| `server/apps/opspilot/views.py` | 添加错误检查，返回错误响应 |

### API 影响

- OpenAI 兼容接口 (`/v1/chat/completions`) 失败时将返回 HTTP 500 而非 200
- 内部 `invoke_chat` 返回结构变更（新增字段）

### 向后兼容性

- **内部调用**：需要更新所有 `invoke_chat` 消费者
- **外部 API**：OpenAI 兼容接口行为变更，失败时返回错误状态码
