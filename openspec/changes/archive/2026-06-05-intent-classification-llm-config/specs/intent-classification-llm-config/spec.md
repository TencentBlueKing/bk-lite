## ADDED Requirements

### Requirement: 意图分类节点直接选择 LLM 模型

意图分类节点 SHALL 允许用户直接选择一个启用中的 LLM 模型作为分类执行模型，而不是选择智能体。

#### Scenario: 打开意图分类节点配置抽屉

- **WHEN** 用户在工作台打开意图分类节点配置抽屉
- **THEN** 系统 SHALL 显示“LLM模型”选择项
- **AND** 系统 SHALL 不再显示“选择智能体”字段

#### Scenario: 保存意图分类节点配置

- **WHEN** 用户选择一个 LLM 模型并保存节点
- **THEN** 节点配置 SHALL 持久化所选模型标识
- **AND** 后端执行 SHALL 使用该模型完成意图分类

### Requirement: 分类规则作为补充 prompt

意图分类节点 SHALL 提供一个非必填的“分类规则”字段，其内容作为内置分类 prompt 的补充，而不是替代。

#### Scenario: 用户未填写分类规则

- **WHEN** 用户保存节点时未填写分类规则
- **THEN** 系统 SHALL 允许保存
- **AND** 后端 SHALL 仅使用内置分类 prompt 执行分类

#### Scenario: 用户填写分类规则

- **WHEN** 用户填写分类规则并执行工作流
- **THEN** 后端 SHALL 将该内容追加到内置分类 prompt 之后
- **AND** 该补充内容 SHALL 参与本次分类判断

### Requirement: 意图分类节点不再依赖智能体配置

意图分类节点 SHALL 不再要求 `agent` 配置，也不再通过 `LLMSkill` 间接获取模型和 prompt。

#### Scenario: 执行新配置节点

- **WHEN** 意图分类节点包含 `llmModel`、`intents` 和可选的 `classificationRules`
- **THEN** 节点 SHALL 在没有 `agent` 的情况下成功执行分类
- **AND** 节点 SHALL 继续输出用于匹配分支的意图结果

### Requirement: 非兼容旧 agent 型意图分类配置

本次变更后的意图分类节点 SHALL 仅支持新配置协议，不保证兼容旧的 `agent` 型配置。

#### Scenario: 工作流仍使用旧配置

- **WHEN** 工作流中的意图分类节点仅包含旧 `agent` 配置而未按新协议重新保存
- **THEN** 系统 MAY 拒绝按新逻辑执行该节点
- **AND** 产品与实现 SHALL 以新配置协议为唯一支持目标
