## Why

OpsPilot workflow 的附件发送方案目前依赖编排人显式声明附件开关、附件 ID 和通知节点附件选择，配置成本高且容易出错。新的产品方向要求把附件能力收敛成“智能体有能力就自动生成、通知节点自动发送”，把手工引用改成运行时自动感知和全量收集。

此外，现有后端已经具备附件资产落库、MinIO 文件存储和下载链路，适合在不推翻底层模型的前提下，将 workflow 编排层升级为零配置的自动附件发送体验。

## What Changes

- Agent 节点不再暴露附件开关、附件 ID、附件名等人工配置项。
- Agent 节点根据所选智能体是否包含内置 `attachment_file` 工具来判断是否具备附件生成能力。
- 具备附件能力的 Agent 节点在执行时，由模型根据 prompt 自主决定是否调用 `generate_attachment_file` 生成附件。
- 系统继续将生成出的附件落到 `WorkflowAttachmentAsset`，并保留 `attachment_id`、`source_node_id`、`execution_id`、下载链接和 MinIO 文件存储链路。
- 通知节点移除附件选择配置，邮件发送时自动收集当前 execution 下全部已生成附件并作为邮件附件发送。
- 保留现有基于 `attachment_id` 解析附件文件的后端逻辑，但附件 ID 改为系统自动生成，不再由用户录入。

## Capabilities

### New Capabilities
- `workflow-attachment-automation`: 工作流中基于智能体工具能力自动生成附件，并在通知节点自动发送 execution 内全部附件的能力。

### Modified Capabilities

None.

## Impact

### 后端 (server/apps/opspilot/)
- `utils/chat_flow_utils/nodes/agent/agent.py`: 根据 skill 工具能力自动处理附件生成和节点级外链绑定。
- `utils/chat_flow_utils/nodes/action/action.py`: 通知节点自动收集当前 execution 的全部附件并发送邮件。
- `services/workflow_attachment_service.py`: 复用附件生成与资产落库逻辑，补充系统化 attachment_id 生成规则。
- `models/bot_mgmt.py`、迁移文件：如需补充附件资产查询或元数据约束，沿用现有资产表演进。

### 前端 (web/src/app/opspilot/)
- `components/chatflow/components/nodeConfigs/AgentsNodeConfig.tsx`: 移除附件相关手工配置。
- `components/chatflow/components/nodeConfigs/NotificationNodeConfig.tsx`: 移除附件选择配置，保留自动发送语义。
- `components/chatflow/NodeConfigDrawer.tsx`、`constants/chatflow.ts`、`types.ts`、`locales/*.json`: 同步清理附件编排字段和文案。

### 系统行为
- 邮件通知将默认附带当前 execution 中全部已生成附件。
- 非邮件通知类型继续不支持附件。
