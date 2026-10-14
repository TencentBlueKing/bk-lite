# 运营分析应用拓扑场景组件

Status: implemented

## Problem Statement

运营分析大屏和仪表盘能放网络状态拓扑，但不能放 CMDB 应用拓扑。运维看一个应用系统时，需要同一张五带资源图，并按监控活跃告警染色；点开节点要能看 CMDB 信息、监控信息和告警信息，而不是离开画布。

## Solution

新增场景组件 `applicationTopology`。结构只来自 CMDB 应用拓扑（应用系统为圆心，深度 1–5，默认 3）。运营分析经 CMDB NATS 取五带结构，再按已有监控实例映射叠当前活跃告警。未接入监控为「未接入」，已接入且无告警为「正常」。点击节点在组件内打开详情：CMDB 基础信息、监控视图、告警列表都复用已声明的公开组件。

## Implementation Decisions

- 画布范围是仪表盘和大屏，支持分享，不进报表。组件配置只保存展开层级 `depth`（1–5，默认 3）。应用系统不写在组件里，由画布统一筛选提供：画布上有应用拓扑时自动补「应用系统」筛选项，选项来自 `cmdb/list_application_systems`。查看时在头部切换，同一张画布上的应用拓扑一起变。圆心必须是应用系统。
- CMDB 新增 NATS `application_resource_topology_by_uuid`，不经 OpenAPI 网关。它复用 `ApplicationResourceOverviewService.build_application_topology`，带 `user_info` 做实例读权限。圆心不是应用系统时失败，不返回结构。
- 运营分析 `ApplicationTopologyService` 不直连 CMDB 内部服务。告警口径与网络状态拓扑一致：`get_monitor_ids_by_inst_uuids` 再 `query_latest_active_alerts`（`status=new`）。无 `monitor_id`，或有 `monitor_id` 但汇总里没有该实例，`alert_count` 为 null，不得画成正常。有汇总且 `count=0` 才是正常。角标只在 `count>0` 时出现，超过 99 显示 99+。
- 五带归属继续用 CMDB `resolveLayer`，不在运营分析重写分类。`none` 不进带。
- 点击详情不跳转。登录态按需加载 `cmdb.baseInfo`、`monitor.monitorView`、`monitor.alertList`。未接入监控时监控和告警页说明未接入。分享态只保留图和染色，不在分享会话里打开这三个组件。
- 分享查询的取数身份是分享者。画布声明了应用拓扑组件后，可查询分享者有权的应用系统；筛选选项源随画布放行。未声明组件时 403。

## Testing Decisions

- CMDB NATS：非法 UUID、非应用模型、无权、深度传入构建函数。
- 运营分析拼图：未接入与 count=0 可区分；汇总缺失保持 null；响应不含上游哨兵。
- 分享：已声明实例委托分享者；未声明实例 403。
- 前端：分带、染色、角标、未分类节点不进图；保存配置拒绝非应用系统。

## Out of Scope

- 替换 CMDB 应用拓扑编辑页
- 服务树
- 报表
- 把公开详情组件改成分享可用
