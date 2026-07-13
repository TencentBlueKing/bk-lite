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
