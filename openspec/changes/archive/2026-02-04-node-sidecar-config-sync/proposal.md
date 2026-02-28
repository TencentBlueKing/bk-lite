## Why

用户在 UI 编辑节点名称或组织时，这些变更需要同步到节点的 sidecar.yaml 配置文件，以保持数据库和节点配置的一致性。当前编辑节点只更新数据库，节点上的 sidecar.yaml 仍是旧值。

## What Changes

- 修改现有 `update_node` API：编辑成功后异步触发配置同步
- 新增 Celery 任务：`sync_node_properties_to_sidecar` 负责异步同步
- 新增 Service 方法：`SidecarConfigService.sync_node_properties()` 处理具体同步逻辑
- 通过 NATS Executor 远程读写节点 sidecar.yaml 并重启服务

## Capabilities

### New Capabilities
- `node-sidecar-config-sync`: 节点属性（name/organizations）自动同步到 sidecar.yaml

### Modified Capabilities
- `update_node` API: 新增异步同步触发（不影响 API 响应时间）

## Impact

- **代码影响**: `server/apps/node_mgmt/` 新增 service 方法、celery task，修改 views
- **API 影响**: 无新 API，复用现有 `PATCH /nodes/{id}/update/`
- **依赖**: 复用现有 `apps.rpc.executor.Executor` 和 Celery
- **运维影响**: 需确保 nats-executor 有权限读写 sidecar.yaml 和重启 sidecar.service

## Evolution Note

本变更是对初始方案的调整：
- **初始方案**: 独立 API `PATCH /nodes/{id}/sidecar-config/` 允许任意配置编辑
- **最终方案**: 集成到 `update_node` 流程，只同步 name 和 organizations

原因：产品需求明确后，确认核心需求是保持 DB 和节点配置的同步，而非通用配置编辑器。
