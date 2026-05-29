## MODIFIED Requirements

### Requirement: prepareStep 每步前钩子
系统 SHALL 在每个 ReAct 循环步骤的 LLM 调用前执行 prepareStep 钩子，允许动态调整工具集、消息和配置。

#### Scenario: prepareStep 修改可用工具
- **WHEN** prepareStep 钩子返回新的 active_tools 列表
- **THEN** 当前步骤的 LLM 调用 SHALL 使用新的工具集

#### Scenario: prepareStep 在 compaction 之后执行
- **WHEN** 消息历史触发 compaction
- **THEN** prepareStep SHALL 在 compaction 完成后执行，能够感知压缩后的消息状态

#### Scenario: 分析完成后 hint 禁止额外 YAML 获取
- **WHEN** `analyze_deployment_configurations` 执行完成返回 `_next_step_hint`
- **THEN** hint SHALL 包含明确指令"不要调用 get_kubernetes_resource_yaml，修复方案基于分析数据直接生成"
