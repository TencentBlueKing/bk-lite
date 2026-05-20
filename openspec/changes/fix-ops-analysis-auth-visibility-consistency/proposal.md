## Why

`operation_analysis` 当前存在两类相互关联但职责不同的权限一致性问题：

1. `DirectoryModelViewSet` 的目录写接口直接使用 ORM 处理创建和更新，请求只经过模块级 `@HasPermission` 校验，绕过了 `AuthViewSet` 的组织范围写入校验、`current_team` 属主校验和实例级 `Operate` 校验。这会让目录写请求退化为“只校验模块角色”，存在跨组织写入和跨实例修改风险。
2. 仪表盘、拓扑图、架构图虽然允许修改 `groups`，但侧边栏入口完全依赖目录树接口。目录树先按目录及祖先目录链做过滤，再拼出子对象节点。如果对象的目标 `groups` 超过其所属目录链的可见范围，保存后切换到新组织时对象不会出现在侧边栏，形成“保存成功但不可发现”的配置漂移。

这两个问题都属于 `operation_analysis` 资源权限模型的不一致：

- 写入授权链不一致
- 容器可见性约束缺失

本次 change 先收敛并修复这两项。对“对象可出现但运行时因数据源无权而失败”的保存时前置校验暂不纳入范围，继续保留现有运行时数据源访问控制。

## What Changes

- 修复目录写接口，要求 `DirectoryModelViewSet` 的 create/update/partial_update 复用 `AuthViewSet` 的统一写时授权链。
- 为仪表盘、拓扑图、架构图新增目录链可见性一致性校验：对象目标 `groups` 不得超过所属目录及其祖先目录链的可见范围。
- 在保存失败时返回明确的冲突信息，指出是目录写授权失败，还是目录链可见性不满足。

## Capabilities

### New Capabilities

- `operation-analysis-resource-write-auth`: `operation_analysis` 目录写接口必须执行与 `AuthViewSet` 一致的组织范围与实例级授权校验。
- `operation-analysis-container-visibility-consistency`: 非目录对象的目标 `groups` 必须被所属目录链完整覆盖，避免对象保存后在目标组织中不可发现。

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **后端代码**:
  - `server/apps/operation_analysis/views/view.py`
  - `server/apps/core/utils/viewset_utils.py`（复用现有能力，不要求新增通用规则）
  - 新增或调整 `operation_analysis` 服务层/校验逻辑，用于目录链一致性检查
- **前端交互**:
  - `web/src/app/ops-analysis/components/sidebar.tsx` 当前直接提交 `groups`，后续需消费更明确的错误反馈
- **API 行为变更**:
  - 目录写接口对无权组织或无权实例的请求返回 403，而不是仅凭模块角色放行
  - 画布保存接口在目标 `groups` 超出目录链可见范围时拒绝保存，并返回冲突明细
- **不在本次范围**:
  - 不新增画布引用数据源的保存时前置校验，继续保留现有运行时“无权访问当前数据源”拦截
