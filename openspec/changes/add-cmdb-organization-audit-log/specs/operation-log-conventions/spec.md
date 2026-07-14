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
