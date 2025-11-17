# AG-UI 协议端点说明

## 概述

Metis 现在支持 AG-UI 协议的流式响应，除了原有的 OpenAI 格式 SSE 端点外，所有 Agent 都新增了对应的 AG-UI 协议端点。

## AG-UI 协议优势

- **结构化事件流**: 提供更丰富的事件类型（RUN_STARTED, TEXT_MESSAGE_START, TOOL_CALL_START 等）
- **更好的可视化支持**: 前端可以根据事件类型展示不同的 UI 组件
- **工具调用跟踪**: 更清晰地展示 Agent 的工具调用过程

## 可用端点

### 1. ReAct Agent
- **AG-UI 端点**: `POST /agent/invoke_react_agent_agui`
- **OpenAI SSE 端点**: `POST /agent/invoke_react_agent_sse`
- **同步端点**: `POST /agent/invoke_react_agent`

### 2. Plan and Execute Agent
- **AG-UI 端点**: `POST /agent/invoke_plan_and_execute_agent_agui`
- **OpenAI SSE 端点**: `POST /agent/invoke_plan_and_execute_agent_sse`
- **同步端点**: `POST /agent/invoke_plan_and_execute_agent`

### 3. LATS Agent
- **AG-UI 端点**: `POST /agent/invoke_lats_agent_agui`
- **OpenAI SSE 端点**: `POST /agent/invoke_lats_agent_sse`
- **同步端点**: `POST /agent/invoke_lats_agent`

### 4. ChatBot Workflow
- **AG-UI 端点**: `POST /agent/invoke_chatbot_workflow_agui`
- **OpenAI SSE 端点**: `POST /agent/invoke_chatbot_workflow_sse`
- **同步端点**: `POST /agent/invoke_chatbot_workflow`

## 请求格式

所有端点使用相同的请求格式（以 ReActAgentRequest 为例）：

```json
{
  "user_message": "用户问题",
  "model": "gpt-4",
  "thread_id": "optional-thread-id"
}
```

## 响应格式

### AG-UI 协议响应示例

```
data: {"type":"RUN_STARTED","thread_id":"xxx","run_id":"xxx","timestamp":1700000000000}

data: {"type":"TEXT_MESSAGE_START","message_id":"msg_xxx","role":"assistant","timestamp":1700000000000}

data: {"type":"TEXT_MESSAGE_CONTENT","message_id":"msg_xxx","delta":"这是回答内容","timestamp":1700000000000}

data: {"type":"TEXT_MESSAGE_END","message_id":"msg_xxx","timestamp":1700000000000}

data: {"type":"RUN_FINISHED","thread_id":"xxx","run_id":"xxx","timestamp":1700000000000}
```

### OpenAI SSE 响应示例

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1700000000,"model":"gpt-4","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1700000000,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"这是回答内容"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1700000000,"model":"gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## 实现细节

### 核心实现

新增的 `BaseAgent.agui_stream_response_handler` 方法提供了 AG-UI 协议的通用处理逻辑：

```python
@staticmethod
async def agui_stream_response_handler(workflow, body, response: ResponseStream):
    """AG-UI 协议流式响应处理器"""
    try:
        result = workflow.agui_stream(body)
        async for sse_event in result:
            await response.write(sse_event.encode('utf-8'))
        logger.info(f"AG-UI 流式响应完成，问题: {body.user_message}")
    except Exception as e:
        logger.error(f"AG-UI 流式响应失败，问题: {body.user_message}, 错误: {e}")
        raise
```

### 设计原则

1. **最小化改动**: 在 `BaseAgent` 中仅新增一个方法，不影响现有逻辑
2. **保留现有功能**: 所有原有的 OpenAI SSE 端点保持不变
3. **复用 Neco 实现**: 直接调用 Neco 的 `agui_stream` 方法，确保协议一致性
4. **简洁高效**: 新方法仅负责数据转发，业务逻辑在 Neco 层处理

## 使用建议

- **前端可视化需求**: 使用 AG-UI 端点，可获得更丰富的事件类型用于 UI 展示
- **兼容现有系统**: 使用 OpenAI SSE 端点，与现有 OpenAI 客户端兼容
- **调试和测试**: 使用同步端点，获得完整的响应数据
