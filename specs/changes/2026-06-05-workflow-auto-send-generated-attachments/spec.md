# 2026 06 05 Workflow Auto Send Generated Attachments

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-workflow-auto-send-generated-attachments/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

OpsPilot workflow 已经具备附件生成工具、附件资产表和下载链路，但现有编排设计要求用户在 Agent 节点和通知节点之间手工声明附件开关、附件 ID、附件名称和发送引用。这与当前产品方向不一致：附件能力应由智能体能力和运行时结果决定，而不是由编排人进行额外配置。

本次变更同时影响后端 workflow 节点执行器、附件资产服务和前端 chatflow 节点配置界面，属于跨模块改动。约束条件是必须复用现有 `WorkflowAttachmentAsset` + MinIO 存储链路，并保持邮件发送仍通过现有 `attachment_id` 读取文件内容的逻辑，以降低迁移风险。

## Goals / Non-Goals

**Goals:**
- 根据 Agent 选择的 skill 是否包含 `attachment_file` 工具，自动判断节点是否具备附件生成能力。
- 在不新增人工配置的前提下，让模型在运行时自主决定是否生成附件。
- 让邮件通知节点自动附带当前 execution 下全部已生成附件。
- 复用现有附件资产表、下载链接、MinIO 文件存储和基于 `attachment_id` 的文件解析逻辑。

**Non-Goals:**
- 不为非邮件通知类型补充附件能力。
- 不在本次变更中引入附件筛选、附件白名单或按节点精细选择发送的配置。
- 不修改附件文件内容的生成方式，也不新增新的文件格式支持。

## Decisions

### 1. 以 skill 工具列表而不是节点配置判断附件能力
Agent 节点不再保留 `attachmentId`、附件开关或附件名称配置。系统在执行前读取所选 `LLMSkill.tools`，只要存在内置 `attachment_file` 工具，就允许该节点在运行时生成附件。这样可以让配置与真实工具能力保持一致，避免“节点配置允许生成，但 skill 实际没有工具”的不一致状态。

备选方案是继续保留显式开关或附件字段，但这会让编排层承担额外认知成本，并且与“零配置自动生成”的产品方向相悖，因此不采用。

### 2. 保留 attachment_id 机制，但改为系统生成
底层仍使用 `WorkflowAttachmentAsset` 的 `attachment_id` 作为文件索引键，以兼容现有资产落库、下载和邮件发送逻辑。区别在于 `attachment_id` 不再由用户输入，而是由系统根据 `source_node_id` 自动生成。为避免同一节点多次生成附件时发生覆盖，系统应使用基于 `node_id` 的稳定前缀，并为同节点多文件生成唯一后缀。

备选方案是完全移除 `attachment_id`，只按资产主键或 `source_node_id` 查文件，但这会扩大后端改动面，且会破坏已有查询和下载逻辑，因此不采用。

### 3. 通知节点按 execution 全量收集附件
通知节点不再暴露 `attachmentIds` 配置。发送邮件时，节点直接查询当前 `execution_id` 下全部已生成的 `WorkflowAttachmentAsset` 记录，并逐个复用现有文件读取逻辑构造附件列表。这样可以消除引用配置错误，也与“只要有文件产生就全部发送”的产品要求一致。

备选方案是保留下拉选择或节点过滤，但这仍然需要用户介入，不符合当前需求，故不采用。

### 4. 前端移除附件编排字段，展示自动语义
前端 Agent 配置面板删除附件相关输入项，通知节点配置面板删除附件选择项，仅保留“邮件会自动发送本次运行生成的全部附件”的语义说明。NodeConfigDrawer、默认配置、类型定义和多语言文案同步清理，避免残留无效字段继续写入 workflow 配置。

## Risks / Trade-offs

- **[风险] 同一 Agent 节点生成多个附件时，单纯使用 node_id 会覆盖旧资产** → **缓解**：系统生成 attachment_id 时使用 `node_id` 前缀 + 唯一后缀，仍保留节点级归属。
- **[风险] 自动发送 execution 内全部附件会降低发送粒度** → **缓解**：明确本次只支持“全量发送”语义，后续如果出现筛选需求，再基于现有资产表扩展二期能力。
- **[风险] skill 工具配置变更会影响节点是否具备附件能力** → **缓解**：以运行时读取的实际工具列表为准，避免前后端缓存配置产生错误承诺。
- **[风险] 无附件时用户可能误以为邮件发送失败** → **缓解**：通知节点保持“无附件则发送普通邮件”的行为，并在界面文案中说明附件为自动附带。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-03
```

## Capability Deltas

### workflow-attachment-automation

## ADDED Requirements

### Requirement: Agent 节点自动识别附件生成能力
工作流系统 SHALL 根据 Agent 节点所选智能体的工具列表自动识别该节点是否具备附件生成能力，而不是依赖额外的附件配置字段。

#### Scenario: 智能体包含附件工具
- **WHEN** Agent 节点所选 `LLMSkill` 的工具列表中包含内置 `attachment_file` 工具
- **THEN** 系统将该节点视为可在运行时生成附件的节点

#### Scenario: 智能体不包含附件工具
- **WHEN** Agent 节点所选 `LLMSkill` 的工具列表中不包含内置 `attachment_file` 工具
- **THEN** 系统 SHALL 按普通 Agent 节点执行，且不会为该节点启用附件生成语义

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

### Requirement: 自动附件发送复用现有文件解析链路
自动附件发送 SHALL 复用现有基于 `attachment_id` 的文件解析和 MinIO 文件读取链路，以保证与已落地附件资产兼容。

#### Scenario: 发送节点组装附件内容
- **WHEN** 邮件通知节点为 execution 内附件构造发送请求
- **THEN** 系统 SHALL 继续通过附件资产记录中的 `attachment_id` 和文件对象读取真实文件内容，而不是改用新的文件下载协议

#### Scenario: 附件提供下载链接
- **WHEN** Agent 节点成功生成附件
- **THEN** 系统 SHALL 继续为附件资产保留可下载外链，并将该外链与来源节点关联以支持节点级追踪

## Work Checklist

## 1. Backend attachment automation

- [x] 1.1 Update Agent 节点执行逻辑，根据所选 skill 是否包含 `attachment_file` 工具自动启用附件生成能力，并移除对手工 `attachmentId` 配置的依赖。
- [x] 1.2 调整附件资产登记逻辑，为同一节点在一次 execution 内生成的多个附件分配系统化且唯一的 `attachment_id`，同时保留 `source_node_id` 和下载链接绑定。
- [x] 1.3 更新通知节点附件构造逻辑，邮件发送时自动收集当前 `execution_id` 下全部附件资产并复用现有 MinIO 文件读取链路发送。

## 2. Frontend workflow configuration cleanup

- [x] 2.1 移除 Agent 节点配置面板中的附件开关、附件 ID、附件名称等手工字段，并保持其余智能体配置正常保存。
- [x] 2.2 移除通知节点中的附件选择配置，改为仅展示“邮件会自动附带本次运行生成的全部附件”的语义。
- [x] 2.3 清理 chatflow 默认配置、类型定义、节点摘要和中英文文案中的旧附件字段，避免继续写入无效配置。

## 3. Validation

- [x] 3.1 更新并补齐现有 workflow 附件相关测试，覆盖 skill 工具能力识别、自动附件收集和多附件 asset 生成。
- [x] 3.2 运行 server 侧相关 pytest 用例以及 web 的 type-check，确认自动附件发送链路可用且无类型错误。
