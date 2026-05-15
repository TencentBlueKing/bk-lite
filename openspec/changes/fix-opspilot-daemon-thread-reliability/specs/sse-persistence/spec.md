# SSE 持久化可靠性修复

## 问题描述

SSE 流式对话的 bot 回复、技能日志与 WorkFlowTaskResult 收尾统一延后到 daemon 线程做 best-effort 持久化，主流程不等待也不兜底。

**影响文件**:
- `server/apps/opspilot/utils/sse_chat.py`
- `server/apps/opspilot/utils/chat_flow_utils/engine/engine.py`

## 当前实现（问题代码）

### sse_chat.py (行 334-339)

```python
if final_stats["content"]:
    def log_in_background():
        _log_and_update_tokens_sync(...)
    # 问题：daemon 线程，进程退出时不等待
    threading.Thread(target=log_in_background, daemon=True).start()
```

### engine.py (行 551-561, 582-590, 616-624)

```python
# 对话历史
threading.Thread(
    target=lambda: self._record_conversation_history(...),
    daemon=True,
).start()

# 执行结果
threading.Thread(
    target=lambda: self._record_execution_result(...),
    daemon=True,
).start()
```

## 修复方案

### 方案：同步执行持久化

将 daemon 线程的持久化操作改为同步执行。流式输出已经完成，此时同步落库不影响用户体验。

### sse_chat.py 修复

```python
async def generate_stream():
    try:
        async for chunk in stream_gen:
            if isinstance(chunk, tuple) and chunk[0] == "STATS":
                _, final_stats["content"] = chunk
                # 修复：同步执行，不再使用 daemon 线程
                if final_stats["content"]:
                    try:
                        _log_and_update_tokens_sync(
                            final_stats, skill_name, skill_id, 
                            current_ip, kwargs, user_message, 
                            show_think, history_log
                        )
                    except Exception as e:
                        logger.error(f"SSE 持久化失败: {e}", exc_info=True)
                        # 可选：写入补偿队列
            else:
                yield chunk
    except Exception as e:
        logger.error(f"Stream chat error: {e}", exc_info=True)
        # ...
```

### engine.py 修复

```python
# 对话历史 - 同步执行
if accumulated_content:
    try:
        self._record_conversation_history(
            user_id, accumulated_content, "bot",
            entry_type, node_id, session_id,
        )
    except Exception as e:
        logger.error(f"对话历史持久化失败: {e}", exc_info=True)

# 执行结果 - 同步执行
if not next_nodes:
    try:
        self._record_execution_result(
            input_data, final_message, True, start_node_type
        )
    except Exception as e:
        logger.error(f"执行结果持久化失败: {e}", exc_info=True)
```

## 性能影响

- 落库操作通常 <100ms
- 流式输出已完成，用户已看到回复
- 同步落库不影响用户体验
- 可通过监控落库延迟评估影响

## 测试要点

1. 验证流结束后 bot 对话历史正确保存
2. 验证 token 审计日志正确记录
3. 验证 WorkFlowTaskResult 状态正确更新
4. 验证异常场景下的错误日志记录
