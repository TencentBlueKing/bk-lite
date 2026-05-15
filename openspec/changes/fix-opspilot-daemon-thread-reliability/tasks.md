## 1. Issue #2959 - SSE 持久化可靠性

### 1.1 sse_chat.py 修复

- [x] 1.1.1 将 `create_stream_generator()` 中的 daemon 线程持久化改为同步执行
- [x] 1.1.2 在 `_log_and_update_tokens_sync()` 调用前后添加异常处理和日志
- [x] 1.1.3 添加落库失败时的补偿记录（写入错误日志表或文件）

### 1.2 engine.py 修复

- [x] 1.2.1 将 `_record_conversation_history()` 从 daemon 线程改为同步执行
- [x] 1.2.2 将 `_record_execution_result()` 从 daemon 线程改为同步执行
- [x] 1.2.3 评估 `_execute_subsequent_nodes_async()` 是否需要修改（后续节点执行）
  - 结论：保持异步，因为这是执行后续工作流节点，不是持久化
- [x] 1.2.4 添加异常处理，确保落库失败不影响已发送的流式响应

### 1.3 测试

- [ ] 1.3.1 编写单元测试验证持久化在流结束后同步完成
- [ ] 1.3.2 测试异常场景下的补偿机制

---

## 2. Issue #2960 - 中断信号持久化

### 2.1 execution_interrupt.py 修复

- [x] 2.1.1 修改 `is_interrupt_requested()` 增加数据库兜底查询
- [x] 2.1.2 添加缓存未命中时查询 `WorkFlowTaskResult.status == INTERRUPTED` 的逻辑
- [x] 2.1.3 优化查询性能（使用 `exists()` 而非 `filter().first()`）

### 2.2 views.py 确认

- [x] 2.2.1 确认 `interrupt_chat_flow_execution` 已正确更新数据库状态（当前已实现）
- [x] 2.2.2 确保缓存和数据库状态一致性

### 2.3 node.py / engine.py / agui_chat.py 验证

- [x] 2.3.1 验证所有 `is_interrupt_requested()` 调用点都能正确获取中断状态
- [x] 2.3.2 添加日志记录中断检查来源（缓存/数据库）

### 2.4 测试

- [ ] 2.4.1 编写单元测试验证缓存过期后仍能检测到中断
- [ ] 2.4.2 测试长时间运行任务的中断场景

---

## 3. Issue #2961 - 外部渠道消息可靠处理

### 3.1 base_chat_flow_utils.py 修复

- [x] 3.1.1 修改 `is_message_processed()` 实现两阶段去重（processing/completed）
- [x] 3.1.2 添加 `mark_message_completed()` 方法
- [x] 3.1.3 添加 `mark_message_failed()` 方法（清除去重标记）
- [x] 3.1.4 修改 `async_process_and_reply()` 在成功时调用 `mark_message_completed()`
- [x] 3.1.5 修改 `async_process_and_reply()` 在失败时调用 `mark_message_failed()`

### 3.2 wechat_chat_flow_utils.py 修复

- [x] 3.2.1 更新 `handle_wechat_message()` 使用 Celery 任务替代 daemon 线程
- [x] 3.2.2 确保异步处理完成后正确更新去重状态

### 3.3 dingtalk_chat_flow_utils.py 修复

- [x] 3.3.1 修改 `_is_message_processed()` 实现两阶段去重
- [x] 3.3.2 添加 `mark_message_completed()` 和 `mark_message_failed()` 方法
- [x] 3.3.3 删除 `_async_process_and_reply()` 方法（逻辑移到 Celery 任务）
- [x] 3.3.4 更新 `handle_dingtalk_message()` 使用 Celery 任务替代 daemon 线程

### 3.4 tasks.py 新增 Celery 任务

- [x] 3.4.1 添加 `process_wechat_message` Celery 任务
- [x] 3.4.2 添加 `process_dingtalk_message` Celery 任务
- [x] 3.4.3 配置 `max_retries=3, default_retry_delay=60`

### 3.5 测试

- [ ] 3.5.1 编写单元测试验证两阶段去重逻辑
- [ ] 3.5.2 测试处理失败后消息可重试
- [ ] 3.5.3 测试处理超时后消息可重试

---

## 4. 集成测试

- [ ] 4.1 端到端测试 SSE 流式对话的审计日志完整性
- [ ] 4.2 端到端测试长时间任务的中断功能
- [ ] 4.3 端到端测试外部渠道消息的可靠处理（需要模拟 WeChat/DingTalk 回调）

---

## 5. 文档更新

- [ ] 5.1 更新 AGENTS.md 中的 Runbook，添加相关故障排查指南
- [ ] 5.2 添加配置说明（如 `WORKFLOW_INTERRUPT_CACHE_TTL`、去重 TTL 等）
