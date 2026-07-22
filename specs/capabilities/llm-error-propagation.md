## ADDED Requirements

### Requirement: invoke_chat 返回显式错误结构

当 `ChatService.invoke_chat()` 执行失败时，系统 SHALL 返回包含错误标记的完整结构，而非仅返回错误消息文本。

返回结构 MUST 包含以下字段：
- `message`: 错误消息文本
- `success`: 布尔值，失败时为 `False`
- `error`: 原始异常信息字符串
- `error_type`: 异常类型名称
- `total_tokens`: 0
- `prompt_tokens`: 0
- `completion_tokens`: 0
- `browser_steps`: 空列表

#### Scenario: LLM 调用异常

- **WHEN** LLM 调用抛出异常（如网络超时、模型不可用）
- **THEN** `invoke_chat` 返回 `{"success": False, "error": "...", "error_type": "...", "message": "Agent execution failed: ..."}`

#### Scenario: RAG 检索异常

- **WHEN** RAG 检索过程抛出异常
- **THEN** `invoke_chat` 返回 `{"success": False, ...}` 结构

#### Scenario: Tool 执行异常

- **WHEN** 工具调用抛出异常
- **THEN** `invoke_chat` 返回 `{"success": False, ...}` 结构

#### Scenario: eventlet 环境检测

- **WHEN** 检测到 eventlet 环境不支持 asyncio.run
- **THEN** `invoke_chat` 返回 `{"success": False, "error_type": "RuntimeError", ...}` 结构

---

### Requirement: AgentNode 检查执行结果

`AgentNode.execute()` SHALL 检查 `invoke_chat` 返回的 `success` 字段，失败时返回带错误标记的结果。

#### Scenario: invoke_chat 成功

- **WHEN** `invoke_chat` 返回 `success=True` 或无 `success` 字段（向后兼容）
- **THEN** AgentNode 返回 `{output_key: message}` 正常结果

#### Scenario: invoke_chat 失败

- **WHEN** `invoke_chat` 返回 `success=False`
- **THEN** AgentNode 返回 `{"success": False, "error": "...", output_key: error_message}`

---

### Requirement: IntentClassifier 不静默回退

`IntentClassifierNode.execute()` SHALL 在意图分类失败时返回显式错误，而非静默回退到第一个意图。

#### Scenario: 意图匹配成功

- **WHEN** LLM 返回的意图文本在配置的意图列表中
- **THEN** 返回匹配的意图作为 `intent_result`

#### Scenario: 意图不在列表中

- **WHEN** LLM 返回的意图文本不在配置的意图列表中
- **THEN** 返回 `{"success": False, "intent_result": "error", "error": "意图 'xxx' 不在配置列表中"}`

#### Scenario: invoke_chat 调用失败

- **WHEN** `invoke_chat` 返回 `success=False`
- **THEN** 返回 `{"success": False, "intent_result": "error", "error": "..."}`

---

### Requirement: OpenAI 兼容接口返回错误响应

OpenAI 兼容接口 (`/v1/chat/completions`) SHALL 在执行失败时返回 HTTP 500 错误响应。

#### Scenario: 执行成功

- **WHEN** `invoke_chat` 返回 `success=True` 或无 `success` 字段
- **THEN** 返回 HTTP 200 + 正常 completion 响应

#### Scenario: 执行失败

- **WHEN** `invoke_chat` 返回 `success=False`
- **THEN** 返回 HTTP 500 + JSON 错误体 `{"error": {"message": "...", "type": "...", "code": "execution_failed"}}`

---

### Requirement: Engine 正确记录失败状态

当节点返回 `success=False` 时，Engine SHALL 将 `WorkFlowTaskResult` 记录为失败状态。

#### Scenario: 节点返回 success=False

- **WHEN** 任意节点（AgentNode、IntentClassifier 等）返回 `{"success": False, ...}`
- **THEN** `Engine._check_chain_result()` 返回 `(False, error_info)`
- **AND** `WorkFlowTaskResult` 记录为 FAIL 状态

#### Scenario: 节点返回无 success 字段（向后兼容）

- **WHEN** 节点返回不包含 `success` 字段的字典
- **THEN** `Engine._check_chain_result()` 返回 `(True, {})` 认为成功
