# workflow-attachment-automation Specification

## Purpose
TBD - created by syncing change workflow-auto-send-generated-attachments. Update Purpose after archive.

## Requirements
### Requirement: Agent 节点自动识别附件生成能力
工作流系统 SHALL 根据 Agent 节点所选智能体的工具列表自动识别该节点是否具备附件生成能力，而不是依赖额外的附件配置字段。

#### Scenario: 智能体包含附件工具
- **WHEN** Agent 节点所选 `LLMSkill` 的工具列表中包含内置 `attachment_file` 工具
- **THEN** 系统将该节点视为可在运行时生成附件的节点

#### Scenario: 智能体不包含附件工具
- **WHEN** Agent 节点所选 `LLMSkill` 的工具列表中不包含内置 `attachment_file` 工具
- **THEN** 系统 SHALL 按普通 Agent 节点执行，且不会为该节点启用附件生成语义

---

### Requirement: Agent 节点按运行结果自动登记附件资产
具备附件能力的 Agent 节点 SHALL 在模型实际调用附件生成工具时自动登记附件资产，并为附件生成系统管理的标识。

#### Scenario: 模型调用附件生成工具
- **WHEN** 具备附件能力的 Agent 节点执行过程中调用 `generate_attachment_file`
- **THEN** 系统 SHALL 创建 `WorkflowAttachmentAsset` 记录，保存文件内容、`execution_id`、`source_node_id` 和系统生成的 `attachment_id`

#### Scenario: 同一节点多次生成附件
- **WHEN** 同一 Agent 节点在一次 execution 内生成多个附件
- **THEN** 系统 SHALL 为每个附件生成唯一的 `attachment_id`，且不得覆盖该节点先前生成的附件资产

#### Scenario: 模型未生成附件
- **WHEN** 具备附件能力的 Agent 节点执行完成但模型未调用附件生成工具
- **THEN** 系统 SHALL 不创建任何附件资产，且后续通知节点不得伪造空附件

---

### Requirement: 通知节点自动发送 execution 内全部附件
邮件通知节点 SHALL 自动收集当前 execution 下全部已生成附件，并将这些附件全部作为邮件附件发送。

#### Scenario: execution 存在已生成附件
- **WHEN** 邮件通知节点执行时当前 `execution_id` 下存在一个或多个 `WorkflowAttachmentAsset`
- **THEN** 系统 SHALL 收集全部附件资产并将其作为附件列表发送到邮件渠道

#### Scenario: execution 没有附件
- **WHEN** 邮件通知节点执行时当前 `execution_id` 下不存在任何附件资产
- **THEN** 系统 SHALL 继续发送不带附件的邮件通知

#### Scenario: 非邮件通知类型
- **WHEN** 通知节点的通知类型不是邮件
- **THEN** 系统 SHALL 保持现有行为且不得尝试附带 workflow 附件

---

### Requirement: 自动附件发送复用现有文件解析链路
自动附件发送 SHALL 复用现有基于 `attachment_id` 的文件解析和 MinIO 文件读取链路，以保证与已落地附件资产兼容。

#### Scenario: 发送节点组装附件内容
- **WHEN** 邮件通知节点为 execution 内附件构造发送请求
- **THEN** 系统 SHALL 继续通过附件资产记录中的 `attachment_id` 和文件对象读取真实文件内容，而不是改用新的文件下载协议

#### Scenario: 附件提供下载链接
- **WHEN** Agent 节点成功生成附件
- **THEN** 系统 SHALL 继续为附件资产保留可下载外链，并将该外链与来源节点关联以支持节点级追踪
