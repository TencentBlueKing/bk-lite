# Monitor Effective Plugin View Design

## Context

监控视图的指标 tab 目前按监控对象展示全部插件。列表页 `ViewList` 通过 `getMonitorPlugin({ monitor_object_id })` 获取对象下所有插件，再传给详情弹窗；详情页 `/monitor/view/detail` 的 `MetricViews` 也按对象重新获取全部插件。

这会让同一个监控实例看到未实际接入的模板。例如主机实例只上报 `hostremote`，视图仍可能展示主机对象下其他模板。

仓库里已有两个事实来源：

- 主动采集事实：`CollectConfig.monitor_plugin` 记录某实例配置过的插件。
- 被动/API 上报事实：自定义 API/Pull/SNMP 模板对外使用 `plugin_id=<template_id>`，`MonitorPlugin.status_query` 可按最近数据判断某实例是否实际有上报。

`InstanceSearch.search_by_primary_object()` 已经实现了近似的插件状态合并逻辑，但通用视图列表和实例指标页没有复用它来过滤插件 tab。

## Goals

- 监控实例的视图只展示该实例有效的插件模板。
- 主动采集插件只要实例存在配置就展示，即使暂时离线。
- 被动/API 插件没有配置记录时，只有最近有数据才展示。
- 详情弹窗和独立详情页使用同一套后端判定结果。
- 保持前端 `monitor_plugin_id` 参数语义不变：仍使用数据库插件 id 查询指标和分组。

## Non-Goals

- 不迁移历史时序数据。
- 不改变 `plugin_id=<template_id>` 的外部上报契约。
- 不改变插件、指标、指标分组的既有筛选接口语义。
- 不新增用户手动选择“实例使用模板”的配置入口。
- 不为从未配置且从未上报的插件展示空视图。

## Recommended Approach

新增一个后端实例级有效插件接口，由后端合并配置事实和最近上报事实。前端两个指标入口都改为调用该接口，再用返回结果渲染插件 tab。

建议接口：

```text
GET /monitor/api/monitor_instance/{monitor_object_id}/effective_plugins/?instance_id=<monitor_instance_id>
```

返回结构复用插件列表字段，并补充状态字段：

```json
[
  {
    "id": 12,
    "name": "HostRemote",
    "display_name": "Host Remote",
    "template_id": "hostremote",
    "template_type": "pull",
    "is_pre": false,
    "is_custom": true,
    "status": "normal",
    "collect_mode": "auto"
  }
]
```

## Effective Plugin Rules

对目标实例构造两组插件集合：

- `configured_plugins`: 来自 `CollectConfig.objects.filter(monitor_instance_id=instance_id, monitor_plugin_id__isnull=False)`。
- `reported_plugins`: 来自该对象下插件的 `status_query` 查询结果，按对象 `instance_id_keys` 组装 VM 返回维度，命中当前 `instance_id` 时加入集合。

然后按集合关系生成结果：

- `configured_plugins ∩ reported_plugins`: 展示，`collect_mode=auto`，`status=normal`。
- `configured_plugins - reported_plugins`: 展示，`collect_mode=auto`，`status=offline`。
- `reported_plugins - configured_plugins`: 展示，`collect_mode=manual`，`status=normal`。
- 其他插件：不展示。

这与已确认口径一致：主动采集看配置事实，被动/API 看最近上报事实。

## Data Flow

```text
View row/detail route
  -> instance_id + monitor_object_id
  -> effective_plugins API
  -> CollectConfig configured plugins
  -> MonitorPlugin.status_query recent VM hits
  -> merged effective plugin list
  -> plugin tabs
  -> metrics_group/metrics queried by monitor_plugin_id
```

## Backend Design

把有效插件判定抽到服务层，避免视图和 `InstanceSearch` 重复实现。服务建议负责：

- 校验 `monitor_object_id` 和 `instance_id` 对应实例存在且未删除。
- 复用监控实例权限检查，确保用户不能查询无权实例的插件。
- 加载对象下插件，并保持与现有 `monitor_plugin` 列表相同的展示字段和翻译逻辑。
- 查询 `CollectConfig` 获取主动配置集合。
- 对有 `status_query` 的插件查询 VM，生成最近上报集合。
- 合并状态并返回排序后的列表。

`status_query` 查询窗口沿用现有 `get_plugin_normal_status_map()` 的 `step="20m"` 行为，保持与实例插件状态的一致性。

## Frontend Design

新增 API 方法，例如：

```ts
getEffectivePlugins(monitorObjectId, { instance_id })
```

使用位置：

- `web/src/app/monitor/(pages)/view/viewList.tsx`
  - `openViewModal(row)` 时按行实例拉有效插件。
  - `ViewModal`/`MonitorView` 只接收有效插件。
- `web/src/app/monitor/components/metric-views/index.tsx`
  - `initPage()` 使用 `monitorObjectId + instanceId` 拉有效插件。
  - 如果返回空列表，显示空指标内容，不再回退到对象下所有插件。

现有指标查询仍按选中 tab 的插件数据库 id 调用：

```text
/monitor/api/metrics_group/?monitor_object_id=...&monitor_plugin_id=...
/monitor/api/metrics/?monitor_object_id=...&monitor_plugin_id=...
```

## Error Handling

- 实例不存在或已删除：返回业务错误。
- 用户无权限访问实例：返回权限错误。
- 单个插件 `status_query` 查询失败：记录日志并跳过该插件的上报事实，已配置插件仍可按 `offline` 展示。
- 插件无 `status_query`：只参与配置事实判断，不作为被动上报插件展示。

## Testing

后端按 TDD 编写服务层测试：

- 主动配置且最近无数据时仍返回插件，状态为 `offline`。
- 主动配置且最近有数据时返回插件，状态为 `normal`。
- 无配置但最近有 `status_query` 命中时返回插件，状态为 `normal`，采集模式为 `manual`。
- 无配置且无最近数据时不返回插件。
- 同一插件同时命中配置和上报时只返回一次。
- 无权限实例不可查询。

前端验证聚焦 API 接入：

- 详情弹窗打开时使用行实例 id 请求有效插件。
- 独立详情页初始化时使用 URL 中的 `instance_id` 请求有效插件。
- 返回空插件列表时不展示对象下全量插件 tab。

## Rollout Notes

该变更只收窄视图可见插件，不影响数据采集、插件配置下发、上报契约或指标查询 API。若某个被动插件缺少 `status_query`，它不会作为“仅上报事实”展示，需要补齐插件元数据后才能被识别。
