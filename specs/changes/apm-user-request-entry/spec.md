# APM 应用拓扑用户请求入口

Status: implemented

## Completion Evidence

- 判定别名集中在 Adapter 契约常量（`HTTP_ENTRY_KEYS` + `RPC_SYSTEM_KEYS`，同时认 `span_attr:` 前缀）；`is_user_request_entry` 只认 `server` 类 Span。
- `DjangoApmTopologyService` 在现有有界 Trace 样本构图链路上合成 `kind=user_request` 节点（id `user_request:<environment>`，每环境折叠一个）与「用户请求 → 入口服务」边；边指标来自命中的根 SERVER Span，节点无 RED、健康度未知。拓扑接口新增 `include_user_request`，默认关闭。
- 仅应用详情页（应用服务拓扑）打开 `include_user_request` 与 `include_inferred`；全局服务拓扑页只传推断。`focusApplicationTopology` 保留连入焦点服务的用户请求节点，以及本应用已插桩服务的直接推断下游。
- 画布对 `user_request` 节点渲染内联用户图形（`data-service-icon="user-request"`）、本地化标签「用户请求」、「观测请求 N 次」副行与虚线入口边；卡片保持实线，与「推断」的虚线卡片区分。节点不接入调查栏与服务详情。
- 测试：`test_topology_service.py` 新增 9 个用户请求用例（默认关闭、consumer 不产节点、无 HTTP/RPC 属性不产节点、父 Span 在样本外仍计入、环境折叠、被插桩上游调用不算入口、入口服务不可见不出现）；`topology-layout.test.ts` 聚焦保留用例；`topology-canvas.test.tsx` 渲染用例。`test:apm-service-workflow` 55 通过；`pnpm type-check`、改动文件 eslint 通过；APM 后端非 django_db 全套 127 通过。
- 基线失败（与本切片无关，已核实 master 同样失败）：sqlite 下 `django_db` 拓扑 API 用例因无关迁移 `NewSessionEventRelation.event` 无法建库；`test:apm-i18n` 因 `topology-object-icon.ts` 既有图标资源名 `cc-default_默认` 被扫描器命中。

## Problem Statement

应用详情的「应用服务拓扑」只画应用内服务之间的调用边。用户请求从哪里打进这个应用没有任何表达：`demo-storefront` 这类第一个接到请求的服务和其它内部服务看起来一样，运维无法在图上一眼看出「流量从这里进来」。竞品在图顶用一个入口节点表达这层触发源，我们没有对应物。

现有「推断」节点解决的是反方向问题（已插桩服务打出去、下游未插桩），不能复用来表达上游触发源。

## Solution

在应用详情的应用服务拓扑上，查询时合成一类新的虚拟节点「用户请求」（`kind=user_request`）：当一条 Trace 的根 Span 是 `server` 类型、父 Span 不在本条 Trace 里、且带 HTTP/RPC 语义属性时，认定这是一次用户请求触发，画一条「用户请求 → 该服务」的边。每个环境折叠为一个用户请求节点。

不改探针、不改 Collector、不进服务目录。全局服务拓扑（`/apm/services` 拓扑页）不展示该节点，维持现状。

## User Stories

1. As an APM 使用者, I want 在应用详情拓扑上看到「用户请求」节点连向真正接到外部请求的服务, so that 我能一眼看出这个应用的流量入口在哪，而不用逐个猜哪个服务是第一跳。
2. As an APM 使用者, I want 只有真正由外部 HTTP/RPC 请求触发的服务才连到用户请求节点, so that 被其它已插桩服务调用的内部服务（如 `storefront → payment` 里的 payment）不会被误标成入口。
3. As an APM 使用者, I want 应用列表、服务目录、接入实例和全局服务拓扑保持现状, so that 用户请求不会被当成可配策略 / SLO 的目录对象，也不会在全局图上把多个应用的流量拧成一个假根。

## Implementation Decisions

- **判定规则（只认用户 HTTP/RPC 请求）**：Span `kind=server`，父 Span 不在本条 Trace 里（`parent_span_id` 为空，或指向样本外），且带 HTTP 或 RPC 语义属性。HTTP 认 `http.request.method` / `http.method` / `http.route` / `url.path`，RPC 认 `rpc.system`；与推断下游一致，同时认探针原始键与 `span_attr:` 存储前缀，别名集中在 Adapter 契约常量。`consumer`（消息消费）与无 HTTP/RPC 属性的根 Span（定时任务等）不认，后置。
- **节点身份与折叠**：每个环境一个用户请求节点（id 形如 `user_request:<environment>`），`kind=user_request`，显示名「用户请求」。不按入口服务、路由或客户端拆分。
- **构图链路**：复用现有有界 Trace 样本构图（`DjangoApmTopologyService._ingest_trace` 所在链路），不新增查询面。拓扑接口新增开关 `include_user_request`，默认关闭；仅应用详情页打开。全局服务拓扑页不传该参数。
- **边与指标口径**：边为「用户请求 → 入口服务」，指标来自命中判定的根 SERVER Span（调用量、P95、错误率），与现有边聚合同一口径；样本 Trace 上限沿用每边 5 条。用户请求节点自身不带 RED，健康度为未知（中性样式），不参与「只看异常」过滤。入口服务节点的指标已统计 SERVER Span，本判定不重复计数。
- **权限**：用户请求节点只在入口服务对当前组织可见时出现，不能借它枚举不可见服务。
- **前端表达**：`ApmTopologyNodeKind` 增加 `user_request`。画布用独立图标（用户/入口图形）加虚线边，与「推断」的虚线卡片区分开；第一版只做识别，节点不可点选进服务详情，应用详情拓扑维持无调查栏的现状。应用聚焦逻辑（`focusApplicationTopology` 语义）保留连进本应用焦点服务的用户请求节点，不因它无 `service_namespace` 而丢弃。
- **与推断下游的边界**：推断下游（`kind=inferred`）在全局服务拓扑做依赖发现；应用详情画布额外展示本应用已插桩服务的直接推断下游，与用户请求入口一起讲完整请求路径。两类虚拟节点判定规则独立，不共用 `kind`。推断不进下属服务表 / KPI / 目录。

## Testing Decisions

测试外部行为，不锁内部布局坐标或查询语句。先验：`test_topology_service.py`、`topology-layout.test.ts`、`topology-canvas.test.tsx`、`apm-service-workflow-test.ts`。

- 拓扑服务：根 `server` Span 带 HTTP 属性且开 `include_user_request` 时，图中出现该环境的用户请求节点与指向入口服务的边（含调用量 / P95 / 错误率）；默认关闭时图与现状完全一致；`consumer` 根 Span、无 HTTP/RPC 属性的根 Span 不产生节点；同环境多条 Trace 折叠为一个节点；被其它已插桩服务调用的服务不连用户请求边；入口服务不可见时节点不出现；不写入 `ApmService`。
- 前端布局：应用聚焦保留连入焦点服务的 `user_request` 节点及其边；全局拓扑页请求不带 `include_user_request`。
- 画布：`kind=user_request` 节点渲染独立图标与「用户请求」标签，虚线边，无健康分档着色；节点不触发服务详情跳转。

## Out of Scope

- 全局服务拓扑（`/apm/services` 拓扑页）展示用户请求节点。
- 消息消费（`consumer`）、定时任务等非用户触发源的入口表达。
- 应用详情拓扑的调查栏、用户请求节点的点选下钻。
- 区分真人用户与未插桩上游调用方（curl、探活、未插桩网关）；需要 RUM，不在服务端探针范围。
- 按路由 / 端点 / 客户端拆分多个入口节点；Gateway/Sidecar 折叠。
- 探针或 Collector 侧任何改动；把用户请求写入服务目录或配策略 / SLO。

## Further Notes

产品决策见 `docs/design/product-decisions/apm-topology.md`（2026-08-28 条目）。本切片接在 `apm-inferred-downstream` 之后，与它共用「查询时合成虚拟节点、不物化目录」的模式，但方向相反：推断是下游依赖发现，本切片是上游触发源标识。原先后置的「Entry Service」指全局拓扑上的入口服务标记，本切片是更窄的应用级触发源表达，全局入口标记继续后置。
