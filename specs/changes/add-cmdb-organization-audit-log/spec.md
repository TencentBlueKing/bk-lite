# Add Cmdb Organization Audit Log

Status: ready

## Migration Context

- Legacy source: `openspec/changes/add-cmdb-organization-audit-log/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

CMDB 采集任务、模型、资产实例都存在组织归属变化，但平台操作日志当前缺少稳定的组织变化审计口径。审计人员无法直接从统一操作日志判断对象在创建、删除或迁移时进入或离开了哪些组织，需要补齐这一跨对象的组织上下文。

## What Changes

- CMDB 变更记录镜像到平台 `OperationLog.detail` 时，增加统一的 `organization_change` 结构。
- `organization_change` 仅保存组织 ID，不在写日志时解析组织名称或路径。
- `organization_change.field` 统一为 `"organization"`，不对外暴露采集任务 `team`、模型 `group`、资产 `organization` 的源字段差异。
- 采集任务、模型、资产实例在创建、删除、修改时 SHALL 记录组织上下文；没有组织上下文且未发生组织变化时不写 `organization_change`。
- 资产实例普通属性变更默认不镜像到平台操作日志；仅当 `organization` 发生变化时额外镜像。
- 操作日志写入失败仍不得影响原 CMDB 变更记录或主业务流程。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `operation-log-conventions`: 增加 CMDB 组织变化审计 detail 结构与镜像口径。

## Impact

- **代码范围**:
  - `server/apps/cmdb/utils/change_record.py`: 统一组织差异提取、`organization_change` detail 注入、资产组织变化条件镜像。
  - `server/apps/cmdb/services/collect_service.py`: 复用采集任务快照中的 `team` 作为组织上下文来源。
  - `server/apps/cmdb/services/model.py`: 补齐模型更新/删除等管理变更的组织上下文记录口径。
  - `server/apps/cmdb/services/instance.py`: 单实例和批量实例的组织字段变化触发平台操作日志镜像。
  - `server/apps/system_mgmt/nats/audit.py`: 保持 `detail` JSON 透传，不新增数据库字段。
- **API/数据结构**: `OperationLog.detail` 可能新增 `organization_change`，现有字段保持兼容。
- **测试范围**:
  - CMDB change record mirror 单元测试。
  - system_mgmt 操作日志镜像端到端测试。
  - 资产普通属性变更不镜像、组织变更才镜像的回归测试。
- **依赖**: 无新增第三方依赖，无数据库迁移。

## Implementation Decisions

## Context

CMDB 已有 `ChangeRecord` 作为业务变更记录，部分管理类场景会通过 `server/apps/cmdb/utils/change_record.py` 镜像到 `system_mgmt.OperationLog`。当前镜像 detail 透传 `before_data` 和 `after_data`，但没有稳定的组织变化结构，调用方需要自行理解采集任务 `team`、模型 `group`、资产实例 `organization` 等不同字段。

本次变更面向统一操作日志审计，不新增数据库字段，不改变 CMDB 源变更记录模型。组织变化作为 `OperationLog.detail.organization_change` 的 JSON 子结构保存。

## Goals / Non-Goals

**Goals:**

- 在平台操作日志中为 CMDB 组织归属变化提供稳定、可测试的审计结构。
- 覆盖采集任务、模型、资产实例的创建、修改、删除组织上下文。
- 资产实例普通属性变更不扩大镜像范围，只有组织变化时才进入平台操作日志。
- 保持操作日志写入失败不影响主业务流程。

**Non-Goals:**

- 不新增数据库字段或迁移。
- 不在写日志时解析组织名称或路径。
- 不改变 CMDB `ChangeRecord` 的已有保存语义。
- 不把所有资产普通属性变更镜像到平台操作日志。

## Decisions

### Decision 1: 组织变化写入 `OperationLog.detail.organization_change`

`organization_change` 固定结构如下：

```json
{
  "field": "organization",
  "before_ids": [1],
  "after_ids": [2],
  "added_ids": [2],
  "removed_ids": [1],
  "changed": true
}
```

理由：`OperationLog.detail` 已经是 JSONField，当前 CMDB 镜像也在 detail 中传递 `before_data`/`after_data`。复用 detail 可以避免 schema migration，并保持已有消费者兼容。

替代方案：新增 `OperationLog` 列。这个方案便于查询，但会引入 migration、跨数据库兼容和历史数据填充问题，不符合当前“补齐审计 detail”的范围。

### Decision 2: 只持久化组织 ID

组织变化只保存 ID。组织名称和路径由展示层或查询层按需解析。

理由：ID 是审计事实，不受组织重命名或路径调整影响；写日志时不跨模块查询组织树，降低失败面和性能开销。

替代方案：写入名称或路径快照。这个方案阅读更直观，但组织改名后历史名称语义复杂，也会让日志写入依赖组织树查询。

### Decision 3: 对外字段统一为 `organization`

采集任务源字段为 `team`，模型源字段为 `group`，资产实例源字段为 `organization`。镜像到操作日志时统一输出 `field: "organization"`。

理由：平台操作日志消费者关心“组织变化”，不应理解 CMDB 内部不同对象的字段名差异。

替代方案：输出源字段名或增加 `source_field`。这个方案利于排查实现细节，但会把内部模型差异泄露到审计合同中。

### Decision 4: 创建、删除、修改都记录组织上下文

创建时 `before_ids=[]`、`after_ids=<创建后组织>`；删除时反向记录；修改时记录迁移差异。没有组织上下文且未发生变化时不写 `organization_change`。

理由：审计场景不仅要知道“从 A 迁到 B”，也要知道对象何时进入或离开某个组织。

替代方案：只记录 update 迁移。这个方案日志更少，但无法回答“某组织新增或移除了哪些 CMDB 对象”的审计问题。

### Decision 5: 资产组织变化条件镜像

资产实例普通属性变更仍只保存 CMDB `ChangeRecord`；当 `organization` 变化时，才额外镜像到平台 `OperationLog`。

理由：资产属性更新频率高，全量镜像会显著放大平台操作日志噪音。组织变化是权限和审计相关字段，值得进入统一日志。

替代方案：把所有资产普通属性变更都镜像到平台操作日志。这个方案最完整，但会带来明显噪音和存储压力。

## Risks / Trade-offs

- [Risk] 组织 ID 在历史日志中不可直接阅读。
  Mitigation: 这是第一版有意取舍；展示层需要名称时按 ID 解析。

- [Risk] 不同对象的组织字段类型可能不一致，例如字符串、数字、列表、空值。
  Mitigation: 实现统一 normalize helper，将输入规范为去重后的 ID 列表，并覆盖测试。

- [Risk] 批量资产更新可能产生多条平台操作日志。
  Mitigation: 仅在每个实例组织确实变化时镜像，普通属性批量更新不镜像。

- [Risk] CMDB 镜像调用 system_mgmt 失败。
  Mitigation: 延续当前策略，捕获异常并记录 warning，不影响源 `ChangeRecord` 与主业务。

## Migration Plan

- 无数据库迁移。
- 部署后新产生的操作日志会带 `organization_change`；历史日志不回填。
- 回滚时移除 detail 增强逻辑即可，已有 JSON detail 字段可被旧版本忽略。

## Open Questions

无。当前已确认：创建/删除/修改均记录组织上下文；只存组织 ID；字段名统一为 `organization`。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-07
```

## Capability Deltas

### operation-log-conventions

## ADDED Requirements

### Requirement: CMDB 组织变化审计 detail
CMDB 变更镜像到平台操作日志时，系统 SHALL 在 `OperationLog.detail` 中使用统一的 `organization_change` 结构记录组织上下文变化。

`organization_change` SHALL 包含：
- `field`: 固定为 `"organization"`
- `before_ids`: 变更前组织 ID 列表
- `after_ids`: 变更后组织 ID 列表
- `added_ids`: 本次新增的组织 ID 列表
- `removed_ids`: 本次移除的组织 ID 列表
- `changed`: 是否发生组织上下文变化

#### Scenario: 采集任务创建时记录组织上下文
- **WHEN** 用户创建采集任务且任务保存后的组织 ID 为 `[1, 2]`
- **THEN** 平台操作日志 detail SHALL 包含 `organization_change`
- **AND** `organization_change.field` SHALL 为 `"organization"`
- **AND** `organization_change.before_ids` SHALL 为 `[]`
- **AND** `organization_change.after_ids` SHALL 为 `[1, 2]`
- **AND** `organization_change.added_ids` SHALL 为 `[1, 2]`
- **AND** `organization_change.removed_ids` SHALL 为 `[]`
- **AND** `organization_change.changed` SHALL 为 `true`

#### Scenario: 模型更新时记录组织迁移
- **WHEN** 用户将模型组织从 `[1]` 更新为 `[2, 3]`
- **THEN** 平台操作日志 detail SHALL 包含 `organization_change`
- **AND** `organization_change.field` SHALL 为 `"organization"`
- **AND** `organization_change.before_ids` SHALL 为 `[1]`
- **AND** `organization_change.after_ids` SHALL 为 `[2, 3]`
- **AND** `organization_change.added_ids` SHALL 为 `[2, 3]`
- **AND** `organization_change.removed_ids` SHALL 为 `[1]`
- **AND** `organization_change.changed` SHALL 为 `true`

#### Scenario: 资产删除时记录删除前组织上下文
- **WHEN** 用户删除资产实例且删除前组织 ID 为 `[4]`
- **THEN** 平台操作日志 detail SHALL 包含 `organization_change`
- **AND** `organization_change.field` SHALL 为 `"organization"`
- **AND** `organization_change.before_ids` SHALL 为 `[4]`
- **AND** `organization_change.after_ids` SHALL 为 `[]`
- **AND** `organization_change.added_ids` SHALL 为 `[]`
- **AND** `organization_change.removed_ids` SHALL 为 `[4]`
- **AND** `organization_change.changed` SHALL 为 `true`

#### Scenario: 无组织上下文时不写组织变化 detail
- **WHEN** CMDB 对象创建、更新或删除前后均没有组织 ID
- **THEN** 平台操作日志 detail SHALL NOT 包含 `organization_change`

### Requirement: CMDB 组织变化只持久化组织 ID
CMDB 组织变化审计 SHALL 只在 `organization_change` 中持久化组织 ID，系统 MUST NOT 在写操作日志时解析或持久化组织名称、组织路径。

#### Scenario: 操作日志 detail 不包含组织名称
- **WHEN** 平台操作日志记录 CMDB 组织变化
- **THEN** `organization_change` SHALL 只包含组织 ID 列表
- **AND** `organization_change` SHALL NOT 包含组织名称字段
- **AND** `organization_change` SHALL NOT 包含组织路径字段

### Requirement: 资产普通属性变更不扩大平台操作日志范围
资产实例普通属性变更 SHALL 保持现有 CMDB `ChangeRecord` 记录行为；只有资产实例 `organization` 发生变化时，系统 SHALL 将该资产变更镜像到平台操作日志。

#### Scenario: 资产普通属性变化但组织不变
- **WHEN** 用户修改资产实例名称且 `organization` 变更前后均为 `[1]`
- **THEN** 系统 SHALL 创建 CMDB `ChangeRecord`
- **AND** 系统 SHALL NOT 为该普通属性变更新增平台 `OperationLog`

#### Scenario: 资产组织变化时镜像平台操作日志
- **WHEN** 用户将资产实例组织从 `[1]` 更新为 `[2]`
- **THEN** 系统 SHALL 创建 CMDB `ChangeRecord`
- **AND** 系统 SHALL 新增平台 `OperationLog`
- **AND** 平台操作日志 detail SHALL 包含 `organization_change`
- **AND** `organization_change.before_ids` SHALL 为 `[1]`
- **AND** `organization_change.after_ids` SHALL 为 `[2]`

### Requirement: CMDB 组织变化日志失败不影响主流程
CMDB 组织变化镜像到平台操作日志失败时，系统 SHALL 保留源 CMDB 变更记录并继续完成主业务流程。

#### Scenario: 平台操作日志写入失败
- **WHEN** CMDB 已成功创建 `ChangeRecord` 且调用平台操作日志服务失败
- **THEN** 系统 SHALL 保留该 CMDB `ChangeRecord`
- **AND** 系统 SHALL NOT 回滚已成功的 CMDB 主业务变更
- **AND** 系统 SHALL 记录 warning 日志用于排查

## Work Checklist

## 1. 测试先行

- [ ] 1.1 在 `server/apps/cmdb/tests/test_change_record_mirror_service.py` 增加组织差异 helper 的单元测试，覆盖列表、数字、字符串、空值、重复值规范化。
- [ ] 1.2 在 `server/apps/cmdb/tests/test_change_record_mirror_service.py` 增加采集任务创建/更新/删除镜像 detail 的测试，断言 `organization_change.field` 固定为 `organization` 且只包含组织 ID。
- [ ] 1.3 在 `server/apps/cmdb/tests/test_change_record_mirror_service.py` 增加资产普通属性变更不镜像、资产组织变化才镜像的测试。
- [ ] 1.4 在 `server/apps/system_mgmt/tests/test_audit_mirror_e2e_service.py` 增加端到端测试，确认 `OperationLog.detail.organization_change` 按 JSON 结构持久化。

## 2. 组织变化提取与镜像口径

- [ ] 2.1 在 `server/apps/cmdb/utils/change_record.py` 增加组织 ID 规范化 helper，将 `None`、单值、列表统一为去重后的 ID 列表。
- [ ] 2.2 在 `server/apps/cmdb/utils/change_record.py` 增加 `organization_change` 构建 helper，按 `before_ids`、`after_ids` 计算 `added_ids`、`removed_ids`、`changed`。
- [ ] 2.3 扩展 `_mirror_change_record`，在 detail 中注入 `organization_change`，且无组织上下文时不写该字段。
- [ ] 2.4 保持 `_mirror_change_record` 的异常隔离策略，确保平台操作日志失败不影响 `ChangeRecord` 写入。

## 3. CMDB 对象接入

- [ ] 3.1 确认采集任务 `CollectModelService._snapshot_task` 的 `team` 字段进入 before/after 快照，并通过统一 helper 映射为 `organization_change`。
- [ ] 3.2 补齐模型管理更新路径的 `ChangeRecord`，确保模型 `group` 变化进入平台操作日志的 `organization_change`。
- [ ] 3.3 检查模型创建/删除路径，确保有组织上下文时按创建/删除口径记录 `organization_change`。
- [ ] 3.4 调整资产实例单个更新镜像策略，仅当 `organization` 变化时把普通属性场景额外镜像到平台操作日志。
- [ ] 3.5 调整资产实例批量更新镜像策略，仅对组织发生变化的实例镜像平台操作日志。

## 4. 验证与收口

- [ ] 4.1 运行 `cd server && MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_change_record_mirror_service.py apps/system_mgmt/tests/test_audit_mirror_e2e_service.py`。
- [ ] 4.2 如实现触及模型服务或实例服务既有测试，补跑相关最小回归：`apps/cmdb/tests/test_model_service_methods.py`、`apps/cmdb/tests/test_instance_service_crud.py`。
- [ ] 4.3 运行 `PATH=/Users/windyzhao/.nvm/versions/node/v24.15.0/bin:$PATH openspec status --change add-cmdb-organization-audit-log`，确认 proposal、design、specs、tasks 均完成。
