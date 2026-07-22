# 2026 05 11 Fix Llm Exception Swallowing

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-11-fix-llm-exception-swallowing/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

### 当前状态

`ChatService.invoke_chat()` 是 opspilot 中 LLM 调用的核心入口，被以下组件调用：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           当前调用链                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   views.py (OpenAI API)  ──┐                                               │
│   AgentNode.execute()    ──┼──▶ ChatService.invoke_chat()                  │
│   IntentClassifier       ──┘           │                                   │
│   ChatService.chat()     ──────────────┘                                   │
│                                                                             │
│   返回结构: {"message": str, "total_tokens": int, ...}                      │
│   异常时:   {"message": "Agent execution failed: ..."} ← 无错误标记        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 约束

1. **向后兼容**：新增字段不应破坏现有消费者（字段可选读取）
2. **最小改动**：只修改必要的代码路径
3. **一致性**：与流式处理路径（已正确使用 `success=False`）保持一致

## Goals / Non-Goals

**Goals:**
- 让 `invoke_chat` 失败时返回显式错误结构
- 所有消费者能区分成功/失败
- 失败时中止流程而非静默继续
- 审计数据准确反映执行状态

**Non-Goals:**
- 不修改流式处理路径（已正确实现）
- 不引入新的异常类型（使用返回值标记）
- 不修改 `Engine._check_chain_result()` 逻辑（已正确检查 `success=False`）

## Decisions

### Decision 1: 使用返回值标记而非抛出异常

**选择**：在返回字典中添加 `success`、`error`、`error_type` 字段

**备选方案**：
- A. 抛出自定义异常 `ChatExecutionError`
- B. 返回 `Result` 对象（类似 Rust 的 Result 类型）

**理由**：
- 与现有流式处理路径一致（engine.py 已使用 `success=False`）
- 最小改动，不需要重构所有调用点的 try/except
- 向后兼容，现有代码仍可访问 `message` 字段

### Decision 2: 失败时返回完整结构

**选择**：失败时返回所有字段（包括 token 计数为 0）

```python
return {
    "message": error_message,
    "success": False,
    "error": str(e),
    "error_type": type(e).__name__,
    "total_tokens": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "browser_steps": [],
}, doc_map, title_map
```

**理由**：
- 避免下游访问缺失字段时报 KeyError
- 保持返回结构一致性

### Decision 3: IntentClassifier 失败时使用 "error" 意图

**选择**：失败时返回 `intent_result: "error"` 而非回退到第一个意图

**备选方案**：
- A. 返回 `success=False` 中止流程
- B. 保留回退但记录为失败

**理由**：
- 允许工作流配置专门的错误处理分支
- 比直接中止更灵活
- 如果没有 "error" 意图分支，引擎会自然中止

### Decision 4: OpenAI 兼容接口返回 HTTP 500

**选择**：失败时返回 HTTP 500 + JSON 错误体

```python
return JsonResponse({
    "error": {
        "message": data.get("error"),
        "type": data.get("error_type"),
        "code": "execution_failed"
    }
}, status=500)
```

**备选方案**：
- A. 返回 HTTP 200 + error 字段（某些客户端可能期望）
- B. 返回 HTTP 503 Service Unavailable

**理由**：
- 符合 OpenAI API 错误响应规范
- 客户端可通过状态码快速判断失败
- 500 表示服务端执行错误，语义准确

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 外部系统依赖当前返回结构 | 新增字段为可选，不删除现有字段 |
| IntentClassifier 没有 "error" 意图分支 | 引擎会自然中止，不会静默继续 |
| OpenAI 客户端不处理 500 错误 | 这是客户端问题，应该处理错误 |
| 测试覆盖不足 | 为每个修改点添加单元测试 |

## Migration Plan

1. **Phase 1**：修改 `chat_service.py`，添加错误字段（向后兼容）
2. **Phase 2**：修改消费者添加错误检查
3. **Phase 3**：修改 OpenAI 接口返回错误响应
4. **Phase 4**：添加测试验证错误传播

**回滚策略**：每个 Phase 可独立回滚，Phase 1 完全向后兼容

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-09
```

## Capability Deltas

### llm-error-propagation

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

## Work Checklist

## 1. 修改 ChatService.invoke_chat 返回结构

- [x] 1.1 修改 `server/apps/opspilot/services/chat_service.py` 的 `invoke_chat` 方法，在 `except Exception` 分支返回完整错误结构：`{"message": ..., "success": False, "error": str(e), "error_type": type(e).__name__, "total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "browser_steps": []}`
- [x] 1.2 在成功路径的返回结构中添加 `"success": True` 字段（可选，用于显式标记）

## 2. 修改 AgentNode 添加错误检查

- [x] 2.1 修改 `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` 的 `execute` 方法，检查 `data.get("success")` 是否为 `False`
- [x] 2.2 失败时返回 `{"success": False, "error": data.get("error"), output_key: data["message"]}`

## 3. 修改 IntentClassifierNode 移除静默回退

- [x] 3.1 修改 `server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py` 的 `execute` 方法，检查 `result.get("success")` 是否为 `False`
- [x] 3.2 当 `invoke_chat` 失败时，返回 `{"success": False, "intent_result": "error", "error": result.get("error")}`
- [x] 3.3 当意图不在配置列表中时，返回 `{"success": False, "intent_result": "error", "error": f"意图 '{intent_text}' 不在配置列表中: {intent_names}"}` 而非静默回退到第一个意图
- [x] 3.4 移除 `except Exception` 分支中的静默回退逻辑，改为返回显式错误

## 4. 修改 OpenAI 兼容接口返回错误响应

- [x] 4.1 修改 `server/apps/opspilot/views.py` 的 `get_chat_msg` 函数，检查 `data.get("success")` 是否为 `False`
- [x] 4.2 失败时返回 `JsonResponse({"error": {"message": ..., "type": ..., "code": "execution_failed"}}, status=500)`
- [x] 4.3 检查 `openai_completions` 和其他调用 `invoke_chat` 的视图函数，确保错误处理一致

## 5. 添加单元测试

- [x] 5.1 为 `ChatService.invoke_chat` 添加测试：验证异常时返回 `success=False` 结构
- [x] 5.2 为 `AgentNode.execute` 添加测试：验证 `invoke_chat` 失败时返回错误结构
- [x] 5.3 为 `IntentClassifierNode.execute` 添加测试：验证意图不匹配时返回错误而非回退
- [x] 5.4 为 OpenAI 兼容接口添加测试：验证失败时返回 HTTP 500

## 6. 验证与清理

- [x] 6.1 运行 `cd server && make test` 确保所有测试通过
- [x] 6.2 运行 `cd server && make lint` 确保代码风格符合规范
- [x] 6.3 手动测试：触发 LLM 调用失败场景，验证错误正确传播
