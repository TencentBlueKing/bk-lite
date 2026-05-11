## 1. Phase 1 — Agent Loop 基础能力

- [x] 1.1 实现 prepareStep 钩子 (`node.py` build_react_nodes)
- [x] 1.2 实现 stopWhen 灵活停止条件 (`node.py` should_continue)
- [x] 1.3 实现动态工具选择 (Tool pool activation 模式)
- [x] 1.4 实现 toolChoice 控制 (`entity.py` ToolChoiceConfig + `node.py` bind_kwargs)
- [x] 1.5 实现循环内反思 (`entity.py` ReflectionConfig + `node.py` 反思逻辑)
- [x] 1.6 实现 done tool 显式终止 (`entity.py` DoneToolConfig + `node.py` 拦截逻辑)
- [x] 1.7 实现自适应重试 (工具失败后换参数/换工具)

## 2. Phase 2 — 长任务支撑

- [x] 2.1 实现上下文 compaction (`chain/compaction.py`)
- [x] 2.2 实现消息裁剪 (`chain/message_trim.py`)
- [x] 2.3 实现 Token 预算控制 (stopWhen 中 token 累计统计)
- [x] 2.4 实现步骤级进度汇报 (`_emit_step_progress` + agent_step_progress 事件)
- [x] 2.5 实现取消与优雅终止 (abort signal 机制)
- [x] 2.6 实现超时熔断 (`entity.py` TimeoutConfig)

## 3. Phase 3 — 子 Agent 体系

- [x] 3.1 实现子 Agent 独立上下文 (context_isolation 模式)
- [x] 3.2 实现 toModelOutput 结果摘要 (with_structured_output)
- [x] 3.3 实现并行子 Agent 执行 (`supervisor_multi_agent.py` parallel_executor)
- [x] 3.4 实现子 Agent 流式进度上报 (sub_agent_progress 事件)

## 4. Phase 4 — 运维安全

- [x] 4.1 实现人工审批机制 (request_human_approval 工具)
- [x] 4.2 实现审批 SSE 事件 (approval_request)
- [x] 4.3 实现 Redis 轮询等待审批
- [x] 4.4 实现前端 ApprovalCard 组件
- [x] 4.5 实现执行后验证事件 (verification_started/completed)
- [x] 4.6 实现回滚事件 (rollback_started/completed)

## 5. 配置类实现

- [x] 5.1 ToolChoiceConfig (auto/none/any/specific + apply_on_steps)
- [x] 5.2 ReflectionConfig (反思触发条件和策略)
- [x] 5.3 TimeoutConfig (单步超时 + 总时间限制)
- [x] 5.4 DoneToolConfig (done tool 名称和 schema)
- [x] 5.5 CompactionConfig (压缩阈值和策略)
- [x] 5.6 MessageTrimConfig (裁剪规则)

## 6. 前端组件

- [x] 6.1 AgentStepProgress 组件 (`web/src/app/opspilot/components/custom-chat-sse/AgentStepProgress.tsx`)
- [x] 6.2 ApprovalCard 组件 (内联审批卡片 + 倒计时)

## 7. 测试

- [x] 7.1 编写单元测试 (181 个测试用例)
- [x] 7.2 编写场景测试文件 (17 个场景，13 个 GREEN)
- [x] 7.3 测试 approval 流程 (`test_approval.py`)

## 8. 文档

- [x] 8.1 编写 opspilot_plan.md 能力演进计划
- [x] 8.2 更新场景文件状态 (RED/GREEN 标记)

## 9. 待完成（延期）

- [ ] 9.1 #5 toolChoice 数据层接入 (Skill DB model + migration + serializer + frontend form)
- [ ] 9.2 #4 动态模型切换 (需要 LLMModel tier/capability 元数据)
- [ ] 9.3 #10 跨会话 Memory (设计完成，实现延期)
- [ ] 9.4 #17/#18 任务状态持久化/断点续跑 (需要 Redis/DB 后端)
