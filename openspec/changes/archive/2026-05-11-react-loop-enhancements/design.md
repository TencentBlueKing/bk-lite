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
