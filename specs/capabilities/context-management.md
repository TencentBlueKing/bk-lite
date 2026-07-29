# context-management Specification

## Purpose
TBD - created by archiving change react-loop-enhancements. Update Purpose after archive.
## Requirements
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
