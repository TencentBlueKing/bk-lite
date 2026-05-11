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
