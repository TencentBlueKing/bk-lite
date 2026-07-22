# 2026 05 11 React Loop Enhancements

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-11-react-loop-enhancements/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

OpsPilot 原有 ReAct Agent 架构存在以下限制：
- 工具集和模型在 `setup()` 阶段锁死，运行时无法调整
- 无上下文管理，长任务撞 token 上限直接失败
- 子 Agent 共享全部 history，上下文膨胀
- 无执行安全机制，危险操作直接执行

本次增强基于 LangGraph StateGraph，在不改变整体架构的前提下，通过扩展节点逻辑和配置类实现能力增强。

**约束条件**：
- 必须兼容两个入口：skill test (`execute_agui`) 和 workflow execution (`engine.sse_execute`)
- 不引入新的外部依赖（除 LangGraph 已有能力）
- 保持向后兼容，现有 Skill 配置无需修改即可运行

## Goals / Non-Goals

**Goals:**
- 实现 20/25 项能力增强（引擎层完整实现）
- 181 个测试用例覆盖
- 17 个场景文件文档化

**Non-Goals:**
- #4 动态模型切换（LLMModel 缺少 tier/capability 元数据）
- #10 跨会话 Memory（设计完成，实现延期）
- #17/#18 任务状态持久化/断点续跑（需要 Redis/DB 后端接入）
- #5 toolChoice 数据层接入（引擎层已完成，Skill 模型待扩展）

## Decisions

### D1: prepareStep 钩子位置
**决策**: 在 compaction 之后、LLM 调用之前执行
**理由**: compaction 可能改变消息内容，prepareStep 需要看到压缩后的状态才能做出正确决策
**替代方案**: 在 compaction 之前执行 — 被否决，因为无法感知压缩后的 token 使用情况

### D2: 动态工具选择模式
**决策**: Tool pool activation 模式 + 阈值自适应
**理由**:
- 不需要 LLM 显式调用 meta-tool 请求工具
- 根据任务上下文自动激活相关工具池
- 阈值可配置，平衡工具数量和相关性
**替代方案**: request_tools meta-tool — 被否决，增加 LLM 调用开销

### D3: Done tool 拦截时机
**决策**: 在 `agent_node` LLM 响应后立即检测
**理由**: 避免进入 tools_node 执行，直接终止循环
**实现**: 检测 tool_calls 中是否包含 done tool，若有则提取结果并设置 `final_answer`

### D4: 子 Agent 上下文隔离
**决策**: `context_isolation=True` 时创建独立消息列表
**理由**: 防止主 Agent 上下文膨胀，子 Agent 只需要任务相关信息
**实现**:
- 隔离模式：仅传递 system prompt + 委派任务
- 共享模式：继承完整 history（向后兼容）

### D5: 并行子 Agent 执行
**决策**: Supervisor 返回逗号分隔 agent 名称 → `next_action="PARALLEL"` → `asyncio.gather`
**理由**: 复用现有 Supervisor 路由逻辑，最小改动
**实现**: `parallel_executor` 节点并行调用，结果合并后返回主 Agent

### D6: 人工审批机制
**决策**: LLM 自主判断风险 + `request_human_approval` 工具
**理由**:
- 不需要预定义危险操作列表
- LLM 根据上下文判断是否需要审批
- 通过工具调用触发审批流程
**实现**:
- 后端: Redis 轮询等待审批结果
- 前端: ApprovalCard 内联卡片 + 倒计时

### D7: 配置类设计
**决策**: 独立配置类 + 组合到 BasicLLMRequest
**理由**:
- 单一职责，每个配置类管理一个能力
- 可选配置，不影响现有 Skill
**配置类**:
- `ToolChoiceConfig`: auto/none/any/specific + apply_on_steps
- `ReflectionConfig`: 反思触发条件和策略
- `TimeoutConfig`: 单步超时 + 总时间限制
- `DoneToolConfig`: done tool 名称和 schema
- `CompactionConfig`: 压缩阈值和策略
- `MessageTrimConfig`: 裁剪规则

## Risks / Trade-offs

### R1: 上下文压缩信息丢失
**风险**: compaction 可能丢失关键信息
**缓解**:
- 保留 system prompt 和最近 N 条消息
- 关键 tool 结果标记为 "must keep"
- 压缩前后 token 统计日志

### R2: 并行子 Agent 资源竞争
**风险**: 多个子 Agent 同时执行可能竞争资源（如数据库连接）
**缓解**:
- 子 Agent 使用独立 trace_id
- 工具层已有连接池管理

### R3: 审批超时处理
**风险**: 用户长时间不响应审批请求
**缓解**:
- 可配置超时时间（默认 5 分钟）
- 超时后自动拒绝并记录日志

### R4: toolChoice 数据层未接入
**风险**: 引擎层能力无法通过 UI 配置
**缓解**:
- 引擎层完整实现，API 可用
- 数据层接入作为后续任务（#5）

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-11
```

## Capability Deltas

### context-management

## ADDED Requirements

### Requirement: 上下文 compaction
系统 SHALL 在消息历史接近 token 上限时自动执行上下文压缩。

#### Scenario: 触发 compaction 阈值
- **WHEN** 消息历史 token 数超过 CompactionConfig.threshold
- **THEN** 系统 SHALL 自动执行压缩，将历史消息摘要化

#### Scenario: compaction 保留关键信息
- **WHEN** 执行 compaction
- **THEN** 系统 SHALL 保留 system prompt、最近 N 条消息、标记为 must_keep 的工具结果

#### Scenario: compaction 后继续执行
- **WHEN** compaction 完成
- **THEN** 系统 SHALL 使用压缩后的消息继续 ReAct 循环

### Requirement: 消息裁剪
系统 SHALL 支持在每步前对历史消息进行裁剪。

#### Scenario: 按消息数量裁剪
- **WHEN** MessageTrimConfig.max_messages 配置生效
- **THEN** 系统 SHALL 仅保留最近 max_messages 条消息

#### Scenario: 按 token 数量裁剪
- **WHEN** MessageTrimConfig.max_tokens 配置生效
- **THEN** 系统 SHALL 裁剪消息直到总 token 数低于阈值

#### Scenario: 保留 system prompt
- **WHEN** 执行消息裁剪
- **THEN** system prompt SHALL 始终保留，不被裁剪

### Requirement: Token 预算控制
系统 SHALL 支持为单次 Agent 执行设置 token 预算上限。

#### Scenario: token 预算统计
- **WHEN** Agent 执行过程中
- **THEN** 系统 SHALL 累计统计所有 LLM 调用的 token 使用量

#### Scenario: 超出预算优雅终止
- **WHEN** 累计 token 使用量超过 max_tokens_budget
- **THEN** 系统 SHALL 优雅终止并返回当前中间结果，而非直接报错

#### Scenario: 预算警告
- **WHEN** token 使用量达到预算的 80%
- **THEN** 系统 SHALL 在 agent_step_progress 事件中包含预算警告信息

### ops-safety

## ADDED Requirements

### Requirement: 人工审批机制
系统 SHALL 支持 LLM 自主判断高风险操作并请求人工审批。

#### Scenario: LLM 调用 request_human_approval 工具
- **WHEN** LLM 判断当前操作需要人工确认
- **THEN** LLM SHALL 调用 request_human_approval 工具，传入操作描述和风险说明

#### Scenario: 审批请求 SSE 事件
- **WHEN** request_human_approval 工具被调用
- **THEN** 系统 SHALL 发送 approval_request SSE 事件到前端

#### Scenario: Redis 轮询等待审批
- **WHEN** 审批请求发出后
- **THEN** 系统 SHALL 通过 Redis 轮询等待用户审批结果

#### Scenario: 审批通过继续执行
- **WHEN** 用户批准操作
- **THEN** 系统 SHALL 继续执行原计划的操作

#### Scenario: 审批拒绝终止操作
- **WHEN** 用户拒绝操作
- **THEN** 系统 SHALL 终止当前操作并通知 LLM 寻找替代方案

#### Scenario: 审批超时处理
- **WHEN** 审批请求超过配置的超时时间（默认 5 分钟）
- **THEN** 系统 SHALL 自动拒绝并记录日志

#### Scenario: 前端 ApprovalCard 展示
- **WHEN** 前端收到 approval_request 事件
- **THEN** ApprovalCard 组件 SHALL 内联展示审批卡片，包含倒计时

### Requirement: 执行后验证
系统 SHALL 支持变更类操作执行后自动触发验证。

#### Scenario: verification_started 事件
- **WHEN** 变更操作执行完成，开始验证
- **THEN** 系统 SHALL 发送 verification_started SSE 事件

#### Scenario: verification_completed 事件
- **WHEN** 验证完成
- **THEN** 系统 SHALL 发送 verification_completed SSE 事件，包含验证结果

#### Scenario: 验证失败触发回滚
- **WHEN** 验证结果显示操作未生效
- **THEN** 系统 SHALL 提示 LLM 考虑回滚或重试

### Requirement: 回滚能力
系统 SHALL 支持变更类操作的回滚。

#### Scenario: rollback_started 事件
- **WHEN** 开始执行回滚操作
- **THEN** 系统 SHALL 发送 rollback_started SSE 事件

#### Scenario: rollback_completed 事件
- **WHEN** 回滚完成
- **THEN** 系统 SHALL 发送 rollback_completed SSE 事件，包含回滚结果

### Requirement: 取消与优雅终止
系统 SHALL 支持用户中途取消正在执行的 Agent 任务。

#### Scenario: 用户发起取消
- **WHEN** 用户点击取消按钮
- **THEN** 系统 SHALL 设置 abort signal，Agent 在下一个检查点优雅退出

#### Scenario: 取消后返回中间结果
- **WHEN** Agent 收到取消信号
- **THEN** 系统 SHALL 返回当前已完成的中间结果，而非空结果

### Requirement: 超时熔断
系统 SHALL 支持单步超时和总时间限制。

#### Scenario: 单步超时
- **WHEN** 单个工具执行时间超过 TimeoutConfig.step_timeout
- **THEN** 系统 SHALL 终止该工具执行并返回超时错误

#### Scenario: 总时间限制
- **WHEN** Agent 总执行时间超过 TimeoutConfig.total_timeout
- **THEN** 系统 SHALL 优雅终止 Agent 并返回当前结果

### Requirement: 步骤级进度汇报
系统 SHALL 支持结构化的步骤级进度汇报。

#### Scenario: agent_step_progress 事件格式
- **WHEN** Agent 完成一个步骤
- **THEN** 系统 SHALL 发送 agent_step_progress 事件，包含 step_number、total_steps（如已知）、description

#### Scenario: 前端进度展示
- **WHEN** 前端收到 agent_step_progress 事件
- **THEN** 前端 SHALL 展示 "第 N 步：正在执行 XXX" 格式的进度信息

### react-loop-control

## ADDED Requirements

### Requirement: prepareStep 每步前钩子
系统 SHALL 在每个 ReAct 循环步骤的 LLM 调用前执行 prepareStep 钩子，允许动态调整工具集、消息和配置。

#### Scenario: prepareStep 修改可用工具
- **WHEN** prepareStep 钩子返回新的 active_tools 列表
- **THEN** 当前步骤的 LLM 调用 SHALL 使用新的工具集

#### Scenario: prepareStep 在 compaction 之后执行
- **WHEN** 消息历史触发 compaction
- **THEN** prepareStep SHALL 在 compaction 完成后执行，能够感知压缩后的消息状态

### Requirement: stopWhen 灵活停止条件
系统 SHALL 支持多种停止条件的组合，包括步数限制、token 预算、自定义条件。

#### Scenario: 达到最大步数停止
- **WHEN** 循环步数达到 max_steps 配置值
- **THEN** 系统 SHALL 优雅终止循环并返回当前结果

#### Scenario: 超出 token 预算停止
- **WHEN** 累计 token 使用量超过 max_tokens_budget
- **THEN** 系统 SHALL 优雅终止循环并返回中间结果

#### Scenario: 无 tool_calls 自然停止
- **WHEN** LLM 响应不包含 tool_calls
- **THEN** 系统 SHALL 终止循环并返回 LLM 的最终回答

### Requirement: 动态工具选择
系统 SHALL 支持 Tool pool activation 模式，根据任务上下文自动激活相关工具池。

#### Scenario: 工具池阈值激活
- **WHEN** 任务上下文与某工具池的相关性超过配置阈值
- **THEN** 该工具池中的工具 SHALL 被激活并可供 LLM 使用

#### Scenario: 工具池动态切换
- **WHEN** 任务进入新阶段，上下文发生变化
- **THEN** 系统 SHALL 重新评估工具池相关性并调整可用工具

### Requirement: toolChoice 控制
系统 SHALL 支持 toolChoice 配置，控制 LLM 的工具调用行为。

#### Scenario: toolChoice auto 模式
- **WHEN** toolChoice 配置为 "auto"
- **THEN** LLM SHALL 自主决定是否调用工具

#### Scenario: toolChoice none 模式
- **WHEN** toolChoice 配置为 "none"
- **THEN** LLM SHALL 不调用任何工具，仅生成文本回答

#### Scenario: toolChoice specific 模式
- **WHEN** toolChoice 配置为 specific 并指定工具名称
- **THEN** LLM SHALL 强制调用指定的工具

#### Scenario: toolChoice apply_on_steps 限制
- **WHEN** toolChoice 配置了 apply_on_steps 列表
- **THEN** toolChoice 规则 SHALL 仅在指定步骤生效

### Requirement: 循环内反思
系统 SHALL 在检测到循环卡住或连续失败时触发反思机制。

#### Scenario: 连续失败触发反思
- **WHEN** 连续 N 次工具调用失败（N 由 ReflectionConfig 配置）
- **THEN** 系统 SHALL 触发反思，让 LLM 重新审视当前方向

#### Scenario: 循环检测触发反思
- **WHEN** 检测到 LLM 在重复相同的工具调用模式
- **THEN** 系统 SHALL 触发反思，提示 LLM 尝试新方向

### Requirement: done tool 显式终止
系统 SHALL 支持 done tool 机制，允许 LLM 显式终止循环并返回结构化结果。

#### Scenario: done tool 调用终止循环
- **WHEN** LLM 调用 done tool
- **THEN** 系统 SHALL 立即终止循环，不执行 tools_node

#### Scenario: done tool 提取结构化结果
- **WHEN** LLM 调用 done tool 并传入参数
- **THEN** 系统 SHALL 从 done tool 参数中提取结构化结果作为 final_answer

### Requirement: 自适应重试
系统 SHALL 在工具执行失败时支持自适应重试策略。

#### Scenario: 工具失败后换参数重试
- **WHEN** 工具执行失败且错误可重试
- **THEN** 系统 SHALL 允许 LLM 调整参数后重试

#### Scenario: 工具失败后换工具重试
- **WHEN** 工具执行多次失败
- **THEN** 系统 SHALL 提示 LLM 考虑使用替代工具

### sub-agent-orchestration

## ADDED Requirements

### Requirement: 子 Agent 独立上下文
系统 SHALL 支持子 Agent 使用独立上下文，不继承主 Agent 全部历史。

#### Scenario: context_isolation 模式启用
- **WHEN** AgentConfig.context_isolation = True
- **THEN** 子 Agent SHALL 仅接收 system prompt 和委派任务，不继承主 Agent 历史

#### Scenario: context_isolation 模式禁用（向后兼容）
- **WHEN** AgentConfig.context_isolation = False 或未配置
- **THEN** 子 Agent SHALL 继承主 Agent 完整历史（保持向后兼容）

### Requirement: toModelOutput 结果摘要
系统 SHALL 支持子 Agent 返回结构化摘要而非全部消息。

#### Scenario: output_schema 配置生效
- **WHEN** AgentConfig.output_schema 配置了 JSON schema
- **THEN** 子 Agent 完成后 SHALL 使用 LLM with_structured_output 提取结构化结果

#### Scenario: toModelOutput 错误回退
- **WHEN** 结构化输出提取失败
- **THEN** 系统 SHALL 回退到返回子 Agent 的原始最终回答

### Requirement: 并行子 Agent 执行
系统 SHALL 支持 Supervisor 同时委派多个子 Agent 并行执行。

#### Scenario: 逗号分隔触发并行
- **WHEN** Supervisor LLM 返回逗号分隔的 agent 名称（如 "k8s_agent,db_agent"）
- **THEN** 系统 SHALL 设置 next_action="PARALLEL" 并进入并行执行节点

#### Scenario: asyncio.gather 并行执行
- **WHEN** 进入 parallel_executor 节点
- **THEN** 系统 SHALL 使用 asyncio.gather 并行调用所有指定的子 Agent

#### Scenario: 并行结果合并
- **WHEN** 所有并行子 Agent 完成
- **THEN** 系统 SHALL 合并所有结果并返回给主 Agent

### Requirement: 子 Agent 流式进度上报
系统 SHALL 支持子 Agent 执行过程中实时上报进度。

#### Scenario: agent_step_progress 包含 agent_name
- **WHEN** 子 Agent 执行步骤
- **THEN** agent_step_progress 事件 SHALL 包含 agent_name 字段标识来源

#### Scenario: sub_agent_progress 生命周期事件
- **WHEN** 子 Agent 开始/完成执行
- **THEN** 系统 SHALL 发送 sub_agent_progress 事件，包含 status (started/completed/failed)

#### Scenario: 前端 AgentStepProgress 组件展示
- **WHEN** 前端收到 agent_step_progress 或 sub_agent_progress 事件
- **THEN** AgentStepProgress 组件 SHALL 展示子 Agent 执行进度

## Work Checklist

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
