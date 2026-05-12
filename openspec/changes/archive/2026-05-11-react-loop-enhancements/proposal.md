## Why

OpsPilot 的 ReAct Agent 在 Loop 控制、长任务支撑、子 Agent 协作、执行安全等方面存在明显差距。对标 Vercel AI SDK v6 和 Claude Agent 长任务模式，需要系统性增强 Agent 能力，使其能够处理复杂的智能运维场景。

## What Changes

### Phase 1 — Agent Loop 基础能力
- **#1 prepareStep 钩子**: 每步前可动态调整 tools/model/messages
- **#2 stopWhen 灵活停止**: 支持步数、token 预算、自定义条件组合
- **#3 动态工具选择**: Tool pool activation 模式，阈值自适应
- **#5 toolChoice 控制**: 引擎层实现 auto/none/any/specific + apply_on_steps
- **#6 循环内反思**: 检测连续失败/循环，触发 replan
- **#7 done tool 显式终止**: 强制结构化输出结束
- **#25 自适应重试**: 工具失败后换参数/换工具重试

### Phase 2 — 长任务支撑
- **#8 上下文 compaction**: 自动摘要压缩历史消息
- **#9 消息裁剪/摘要**: 保留 system + 最近 N 条 + 关键 tool 结果
- **#12 Token 预算控制**: 超预算时优雅终止并输出中间结果
- **#19 步骤级进度汇报**: agent_step_progress 事件 + 前端组件
- **#20 取消与优雅终止**: abort signal 机制
- **#21 超时熔断**: 单步超时 + 总时间限制

### Phase 3 — 子 Agent 体系
- **#13 子 Agent 独立上下文**: context_isolation 模式
- **#14 toModelOutput 结果摘要**: with_structured_output 提取 JSON
- **#15 并行子 Agent 执行**: asyncio.gather 并行委派
- **#16 子 Agent 流式进度**: sub_agent_progress 生命周期事件

### Phase 4 — 运维安全
- **#22 人工审批**: LLM 自主判断风险 + request_human_approval 工具
- **#23 执行后验证**: verification_started/completed 事件
- **#24 回滚能力**: rollback_started/completed 事件

### 延期/跳过
- **#4 动态模型切换**: LLMModel 缺少 tier/capability 元数据
- **#10 跨会话 Memory**: 设计完成，实现延期
- **#11 Session 持久化恢复**: 依赖 #17/#18
- **#17/#18 任务状态持久化/断点续跑**: 延期

## Capabilities

### New Capabilities
- `react-loop-control`: prepareStep/stopWhen/toolChoice/done-tool/reflection 循环控制
- `context-management`: compaction/message-trim/token-budget 上下文管理
- `sub-agent-orchestration`: context-isolation/toModelOutput/parallel-execution/streaming-progress 子 Agent 协作
- `ops-safety`: human-approval/verification/rollback 运维安全

### Modified Capabilities
（无，这是新增能力）

## Impact

### 后端
- `server/apps/opspilot/metis/llm/chain/node.py`: 核心 ReAct 节点重构
- `server/apps/opspilot/metis/llm/chain/entity.py`: 新增 ToolChoiceConfig, ReflectionConfig, TimeoutConfig, DoneToolConfig 等配置类
- `server/apps/opspilot/metis/llm/chain/compaction.py`: 上下文压缩实现
- `server/apps/opspilot/metis/llm/chain/message_trim.py`: 消息裁剪实现
- `server/apps/opspilot/metis/llm/agent/supervisor_multi_agent.py`: 并行子 Agent + 流式进度

### 前端
- `web/src/app/opspilot/components/custom-chat-sse/AgentStepProgress.tsx`: 步骤进度组件
- `web/src/app/opspilot/components/custom-chat-sse/ApprovalCard.tsx`: 审批卡片组件

### 测试
- 181 个测试用例通过
- 17 个场景文件，13 个 GREEN 状态

### 自定义事件
- `agent_step_progress`: 步骤进度（含 agent_name）
- `sub_agent_progress`: 子 Agent 生命周期
- `approval_request`: 审批请求
- `verification_started/completed`: 验证事件
- `rollback_started/completed`: 回滚事件
