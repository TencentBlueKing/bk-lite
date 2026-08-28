# APM 服务拓扑调查闭环

Status: implemented

## Completion Evidence

- 拓扑服务在构图后并行叠服务级 RED；健康度按错误率分档；单个 RED 失败不让整张图失败；7 天窗口 RED 回退 24 小时。
- 节点 API 增加 `request_rate` / `error_rate` / `p95_ms`；边仍只返回观测调用量。
- 服务拓扑页点选节点/边打开右侧调查栏，加载最多 5 条样本 Trace，可深链服务详情与调用链；支持一跳隔离、服务名过滤、滚轮/拖拽/按钮缩放。
- 测试：`apps/apm/tests/test_topology_service.py` 中 RED 叠加用例；`topology-canvas.test.tsx`、`topology-layout.test.ts`、`metric-format.test.ts`；`apm-service-workflow-test.ts`、`apm-i18n-coverage-test.ts` 通过。
- sqlite 下原有 `test_topology_api_*` 仍因无关迁移 `NewSessionEventRelation.event` 无法建库，与本切片无关。

## Problem Statement

服务拓扑目前只能回答「谁调用了谁」，不能回答「慢在哪、错在哪」，点节点还会离开图去服务详情。边标签展示平均耗时和错误数，但后端始终返回 0；「只看异常」因此无效。排查必须在拓扑、服务详情和调用链之间跳转，无法停在图上看到样本 Trace。

## Solution

把服务拓扑做成可在图上排查的调查面：节点叠真实 RED（吞吐、错误率、P95），健康度按错误率着色；点选节点或边打开右侧栏，展示上下游和最多 5 条样本 Trace；支持一跳隔离、悬停高亮、服务名过滤、滚轮缩放与拖拽平移。边仍只表达观测调用量，不伪造边级时延或错误。

## User Stories

1. As an APM 使用者, I want 在拓扑节点上看到 P95、错误率健康色和相对调用量, so that 我能直接找出慢服务和出错服务。
2. As an APM 使用者, I want 点选节点或边后停在图上查看上下游与样本 Trace, so that 我不必离开拓扑就能决定下一步下钻。
3. As an APM 使用者, I want 隔离一个服务的一跳邻居并悬停高亮相连边, so that 复杂图里能看清局部依赖。
4. As an APM 使用者, I want 按服务名过滤图，并用鼠标缩放平移, so that 我能在真实规模的调用图上导航。
5. As an APM 使用者, I want 从侧栏打开服务详情或调用链探索, so that 需要完整证据时仍能带着当前服务和环境继续查。

## Implementation Decisions

- 依赖图继续由 VictoriaTraces 的 Jaeger `dependencies` 接口按时间窗聚合；不在本切片替换该数据面，也不计算边级 P95/错误。
- 拓扑服务在构图后按节点身份并行查询现有服务级 RED（不含时序/端点分解）。时间窗超过 24 小时时，RED 只取最近 24 小时，与首页看板一致。单个 RED 失败只让该节点健康度为未知，不让整张图失败。
- 节点健康度只表示错误率，不等同于告警状态：`>= 5%` 严重、`>= 1%` 警告、有样本且低于 1% 为正常、无样本或查询失败为未知。
- 拓扑 API 为节点增加可空的 `request_rate`、`error_rate`、`p95_ms`；边继续返回调用次数，界面不再展示始终为 0 的平均耗时和错误数。
- 点选节点或边打开右侧调查栏，不直接跳走。节点栏展示 RED、入/出邻居及边调用量、最多 5 条该服务的样本 Trace。边栏展示两端服务与被调用方样本 Trace。样本 Trace 复用现有调用链搜索，limit=5。
- Isolate 只保留目标服务及其直接入/出邻居和相应边。服务名过滤隐藏不匹配节点及其边，不再只改透明度。
- 画布自管平移与缩放（滚轮、拖拽、按钮、复位），缩放范围约 0.4–2.5。应用详情拓扑复用同一画布能力，但不强行加入调查栏。

## Testing Decisions

测试外部行为，不锁内部布局坐标或实现类名。

- 拓扑服务：有 RED 时节点带 P95/错误率和对应健康度；RED 失败或无样本时节点为未知且图仍可用；7 天窗口的 RED 查询回退到 24 小时；边调用量不变且不伪造时延/错误。
- 拓扑 API：组织可见性与歧义依赖省略保持现有契约；成功响应包含新的节点 RED 字段。
- 布局辅助：Isolate 只留一跳；关键字过滤隐藏不匹配节点。
- 页面与画布：节点/边可点选并打开调查栏；调查栏展示样本 Trace 与服务/调用链深链；边标签只有调用量；缩放按钮改变视图而不是离开页面。

先验：`test_topology_service.py`、`topology-canvas.test.tsx`、`topology-layout.test.ts`、`apm-service-workflow-test.ts`。

## Out of Scope

- 按任意 Trace 属性过滤后重画拓扑（Filter Traces）。
- 边级 P95/错误、Gateway/Sidecar 折叠、Entry Service 标记。
- 自定义时间范围、超过 7 天的拓扑窗口、提高 30 个目标上限。
- 替换 Jaeger dependencies 聚合，或开放用户粘贴 TraceQL/LogsQL。

## Further Notes

本切片是 Honeycomb Service Map 对照后的第一条调查闭环。按请求切片和边级时延需要新的 span 聚合，单独变更。
