# react-loop-control Specification

## Purpose
TBD - created by archiving change react-loop-enhancements. Update Purpose after archive.
## Requirements
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
