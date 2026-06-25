# 告警中心-运营分析「网络状态拓扑」仪表盘组件设计

## 背景

运营分析仪表盘现有组件以指标展示为主，适合回答“指标是多少、趋势如何”，但不能直接回答“问题发生在网络拓扑的哪个位置、沿哪条链路扩散”。CMDB 已有网络拓扑结构视图，告警中心已有资产告警状态，但两者分散在不同入口，排障时需要人工在结构和状态之间拼接上下文。

本设计新增运营分析仪表盘内置场景组件「网络状态拓扑」，在 CMDB 网络拓扑结构上叠加告警状态，用于看板态故障定位。

## 当前依据

- CMDB 网络拓扑已存在：`web/src/app/cmdb/(pages)/assetData/detail/relationships/networkTopo.tsx`
- CMDB 网络拓扑接口已存在：`/cmdb/api/instance/network_topo/{model_id}/{inst_id}/?depth=`
- CMDB 网络拓扑服务已按中心实例 BFS 展开，并返回 `center / nodes / links / truncated`：`server/apps/cmdb/services/instance.py`
- CMDB 网络拓扑权限逻辑已存在于 `InstanceViewSet.network_topo`：`server/apps/cmdb/views/instance.py`
- 告警模型已有标准资产字段：`Alert.resource_type / resource_id / level / status`
- 告警中心已有内置 CMDB enrichment 规则，但 MVP 状态聚合只依赖标准字段：`server/apps/alerts/constants/init_data.py`
- 运营分析仪表盘已有 GridStack 布局、统一 widget renderer、导入导出配置结构：`web/src/app/ops-analysis/(pages)/view/dashBoard/`

## 目标

1. 在运营分析仪表盘中新增可拖拽、可调整大小的「网络状态拓扑」组件。
2. 组件以 CMDB 网络拓扑为结构来源，以告警中心活跃告警为状态来源。
3. 组件运行态只读，支持查看、缩放、平移、布局切换、导出图片、刷新和增量展开。
4. 点击告警节点时，高亮从该节点沿 `hop` 递减方向回到起点实例的故障链路。
5. 复用 CMDB 与 Alerts 既有权限逻辑，不在运营分析中重写权限规则。

## 非目标

1. 不支持任意外部 nodes/links 数据源。
2. 不进入普通数据源管理，不伪装成 `DataSourceAPIModel`。
3. 不在组件内编辑 CMDB 拓扑结构。
4. 不支持状态时间回放。
5. 不做节点侧滑告警抽屉。
6. MVP 不做模型范围过滤，不做通用筛选字段配置，不做组件内定时轮询。

## 方案选择

采用「内置场景组件 + 运营分析聚合接口」。

「网络状态拓扑」是 `sceneWidget`，不是普通数据源组件。它复用运营分析仪表盘的布局、保存、导入导出和刷新外壳，但不复用普通数据源的 `rest_api / params / field_schema / chart_type` 模型。

不选择普通数据源路径的原因：

1. 网络拓扑需要结构查询、告警聚合、权限裁剪、增量展开和链路高亮，不是普通字段映射问题。
2. 普通数据源路径会导致字段映射、单位、阈值、TopN、表格列等配置被大量特殊隐藏。
3. 用户会误以为该组件支持任意拓扑 API，与本期非目标冲突。

不增强 CMDB 原接口的原因：

1. CMDB 应保持结构事实边界。
2. 告警状态与看板交互属于运营分析场景。
3. 状态口径、看板刷新、故障链路高亮后续变化不应反向污染 CMDB 网络拓扑页。

## 添加入口

现有「添加组件」入口增加组件分类：

- 数据组件：保持现有流程，先选数据源，再选图表类型。
- 场景组件：展示平台内置业务组件，本期新增「网络状态拓扑」。

选择「网络状态拓扑」后，打开专用配置面板，不要求选择数据源。

## 配置面板

MVP 配置面板只包含「拓扑范围」：

| 字段 | 文案 | 说明 |
| --- | --- | --- |
| 模型 | 选择模型 | 仅展示支持网络拓扑的模型 |
| 实例 | 选择实例 | 以所选实例为中心展开网络拓扑 |
| 展开层级 | 默认 2 跳，最多 4 跳 | 最小 1，最大 4 |

保存结构：

```json
{
  "widgetKind": "scene",
  "chartType": "networkStatusTopology",
  "topology": {
    "model_id": "switch",
    "inst_id": "123",
    "inst_name": "核心交换机",
    "depth": 2
  }
}
```

MVP 不在配置面板暴露：

- 模型范围过滤
- 状态口径
- 默认布局
- 跳转行为
- 刷新间隔
- 普通数据源字段映射、单位、阈值、TopN、表格列

## 运行态交互

运行态为只读看板：

- 不显示编辑入口。
- 不支持添加设备。
- 不支持新增或删除连线。
- 不修改 CMDB 结构。

保留操作：

- 缩放、平移
- minimap
- 布局切换：分层、力导向、环形
- 适配视图
- 导出图片
- 手动刷新
- 点击节点增量展开下一跳

节点主体点击：

1. 点击节点主体选中节点。
2. 若节点有活跃告警，则高亮从该节点沿 `hop` 递减方向回到起点实例的故障链路。
3. 与该链路无关的节点和连线减淡。
4. 再次点击同一节点或点击画布空白，取消高亮。

节点 hover 浮层：

```text
核心交换机-01
交换机 · Critical
活跃告警：3

[实例详情] [查看告警]
```

- 实例详情：打开 CMDB 实例详情。
- 查看告警：打开告警中心列表，携带 `resource_type / resource_id / active status` 过滤。
- 无活跃告警时，隐藏或置灰「查看告警」。

## 状态口径

MVP 只按当前用户可见的活跃告警计算节点状态。

活跃告警：

```text
Alert.status in AlertStatus.ACTIVATE_STATUS
```

告警匹配：

```text
Alert.resource_type == node.model_id
Alert.resource_id == node.id
```

等级映射：

| 告警等级 | 节点状态 | 颜色 | 脉冲 |
| --- | --- | --- | --- |
| `0 Critical` | critical | 红 | 开启 |
| `1 Error` | error | 红 | 不开启 |
| `2 Warning` | warning | 黄 | 不开启 |
| 无活跃告警 | normal | 绿 | 不开启 |

只对最高优先级 `Critical` 节点启用红色呼吸脉冲。脉冲是节点外圈柔和扩散的红色光晕，用于吸引注意，不改变节点位置，不弹窗，不发声。

MVP 不使用仪表盘时间范围改变节点颜色，避免历史已恢复告警把节点染红。后续如需历史分析，应作为独立能力设计。

## 后端接口

新增运营分析聚合接口：

```http
POST /operation_analysis/api/scene_widgets/network_status_topology/
```

请求：

```json
{
  "model_id": "switch",
  "inst_id": "123",
  "depth": 2
}
```

响应：

```json
{
  "center": {
    "id": "123",
    "name": "核心交换机",
    "model_id": "switch",
    "hop": 0,
    "expanded": true,
    "status": "critical",
    "max_level": "0",
    "alert_count": 3
  },
  "nodes": [],
  "links": [],
  "truncated": false
}
```

接口流程：

1. 校验 `model_id / inst_id / depth`。
2. 将 `depth` 钳制到 1 到 4。
3. 复用 CMDB 网络拓扑服务获取结构。
4. 收集结构节点的 `model_id + id`。
5. 复用 Alerts 权限过滤后的查询集，聚合当前用户可见的活跃告警。
6. 合并每个节点的 `status / max_level / alert_count`。
7. 返回增强后的拓扑结构。

## 权限边界

权限过滤必须复用既有逻辑。

Operation Analysis：

- 校验接口入口权限和参数格式。
- 传递 `request.user` 和必要上下文。
- 聚合下游已授权数据。
- 不复制 CMDB 或 Alerts 的领域权限规则。

CMDB：

- 参考并复用 `InstanceViewSet.network_topo`。
- 中心实例必须通过 `require_instance_permission`。
- BFS 展开时复用 `CmdbRulesFormatUtil.format_user_groups_permissions` 和 `InstanceManage.network_topology(... permission_map, user)`。
- 无权限对端不进入节点和连线，也不继续下探。

Alerts：

- 参考 `AlertModelViewSet` 的 `_get_permission_filtered_queryset` 和 `get_queryset_by_permission`。
- 状态聚合只基于当前用户可见告警。
- 如果用户无权查看某节点告警，该节点不会因不可见告警变色。

## 错误处理

前端状态：

| 场景 | 表现 |
| --- | --- |
| 加载中 | 组件内 Spin |
| 空结构 | 暂无网络拓扑关系 |
| 结构失败 | 网络拓扑结构加载失败 |
| 状态失败 | 告警状态加载失败 |
| 节点截断 | 拓扑节点较多，已达展示上限（100），不再继续展开 |

状态查询失败时不静默染绿，避免误导用户。

## 前端实现边界

新增 `networkStatusTopology` 场景组件注册，但不加入普通数据源图表类型。

组件可从 CMDB `NetworkTopo` 中抽取或复用以下能力：

- X6/XFlow 渲染
- 三种布局
- minimap
- 导出图片
- 增量展开
- 节点上限提示

需要移除或隐藏：

- 编辑模式
- 添加设备
- 新增连线
- 删除连线
- 端口编辑弹窗

## 后续扩展

1. 模型范围过滤：在配置面板中增加可选模型约束，展开时只展示指定模型。
2. 语义化 scope 参数：为机房、业务、环境等范围筛选预留结构，但不接普通数据源参数体系。
3. 状态局部刷新：结构不变时只刷新告警状态。
4. 告警详情浮层：在不引入复杂抽屉的前提下展示最近告警摘要。
5. 历史状态分析：如需按时间范围看历史，应另行设计，不改变当前健康态口径。

## 测试计划

后端：

1. 参数校验和 depth 钳制。
2. CMDB 网络拓扑结构合并。
3. CMDB 权限裁剪透传。
4. Alerts 权限过滤复用。
5. 活跃告警聚合。
6. `Critical / Error / Warning / Normal` 状态映射。
7. 结构失败和状态失败。
8. `truncated` 透传。

前端：

1. 场景组件出现在添加组件入口。
2. 配置面板只展示模型、实例、展开层级。
3. 保存后的 layout item 能重新渲染。
4. 加载、空、失败、截断状态正确。
5. 节点状态色、角标、Critical 脉冲正确。
6. 点击告警节点高亮到起点实例的链路。
7. hover 浮层展示实例详情和查看告警入口。
8. 编辑、添加设备、新增连线、删除连线入口不出现。

验证命令：

```bash
cd server && make test
cd web && pnpm lint && pnpm type-check
```
