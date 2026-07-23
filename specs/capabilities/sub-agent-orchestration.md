# sub-agent-orchestration Specification

## Purpose
TBD - created by archiving change react-loop-enhancements. Update Purpose after archive.
## Requirements
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
