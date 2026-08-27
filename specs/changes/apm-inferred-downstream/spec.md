# APM 推断下游（服务拓扑）

Status: implemented

## Completion Evidence

- 别名集中在 `server/apps/apm/adapters/span_aliases.py`：`db.system` 或 `db.system.name` 单独出现都能折叠成 mysql 推断节点；`span_attr:` 前缀同样生效。host 认 `server.address` / `net.peer.name` / `network.peer.address` / `net.peer.ip`，port 认 `server.port` / `net.peer.port` / `network.peer.port`；库名独立，不覆盖 host。
- 推断节点和样本 Client Span 展示 Span 里实际有的 `host:port` 与库名；缺端口不加默认值。两个不同 IP 且 `db.system=mysql` 仍折叠为一个 mysql 节点，节点上保留小集合地址。
- `DjangoApmTopologyService` 在有界 Trace 样本上识别 client/producer、无另一 `service.name` 子 Span 的调用；不 import / 不写入 `ApmService`。无组织可见调用方时不出现推断节点。
- 仅服务拓扑页传 `include_inferred=true`。画布展示「推断」角标与虚线描边；调查栏列出调用方和样本 Client Span，隐藏服务详情。应用详情 `focusApplicationTopology` 丢弃推断邻居。
- demo catalog `/products` 发出模拟 mysql Client Span；探针手册钉死 Java 2.31.1、Python 0.65b0（SDK 1.44.0）、Node 0.79.0、Go v1.46.0。
- 测试：`apps/apm/tests/test_topology_service.py` 中别名 / host:port / 双 IP 折叠 / 可见性 / 不写目录用例；`topology-canvas.test.tsx`、`topology-layout.test.ts`；`apm-service-workflow-test.ts`、`apm-i18n-coverage-test.ts` 通过。sqlite 下 `@pytest.mark.django_db` 拓扑 API 仍因无关迁移 `NewSessionEventRelation.event` 无法建库。

## Problem Statement

给 Web 等已插桩服务装探针后，运维在服务拓扑上仍只能看到目录里的 `ApmService`。MySQL / Redis / Kafka 等未插桩下游写在 Client Span 属性里，不会变成 `service.name`，因此不会进入应用列表或服务目录。当前拓扑若继续走 VictoriaTraces Jaeger `dependencies`，库边还可能叫 `checkout:mysql`，且只认 `db.system.name`，和目录对不上。

## Solution

查询时推断，不物化目录。服务拓扑用与请求切片相同的有界 Trace 样本构图；在样本上识别 `span.kind=client|producer`、带语义约定别名、且没有另一 `service.name` 子 Span 的调用，折叠成 `kind=inferred` 节点。只在 `/apm/services` 拓扑页展示；应用列表、服务目录、接入实例、应用详情子拓扑和服务详情依赖标签都不出现推断节点。Collector 保持 traces-only。

## User Stories

1. As an APM 使用者, I want 在服务拓扑上看到已插桩服务访问过的 mysql / redis 等未插桩下游, so that 装一个 Web 探针就能解释「它打过谁」，而不要把库登记成 APM 服务。
2. As an APM 使用者, I want 点推断节点看到调用方和样本 Client Span，并能打开瀑布图, so that 我能核验这条推断从哪条 Span 来。
3. As an APM 使用者, I want 应用列表和服务目录里仍然只有插桩服务, so that mysql 不会被当成可配策略 / SLO 的目录对象。

## Implementation Decisions

- 不写入 `ApmService` / `ApmServiceInstance`；不伪造 `service.name=mysql` 的 ResourceSpan；不 fork OTC；不启用 servicegraphconnector / spanmetrics / 额外 VictoriaMetrics。
- 别名表集中在 Adapter 契约常量，查询同时认：`db.system` 与 `db.system.name`；`db.name` 与 `db.namespace`；`messaging.system`；`rpc.system`（可选 `rpc.service`）；host `server.address` / `net.peer.name` / `network.peer.address` / `net.peer.ip`；port `server.port` / `net.peer.port` / `network.peer.port`。折叠键优先 `peer.service`，否则库/消息 system，再否则 host。库名不覆盖 host，也不进入折叠键。
- 推断节点只存在于当前查询结果。`include_inferred=true` 仅服务拓扑页打开；默认关闭，避免应用详情子拓扑和服务详情依赖列表出现推断节点。
- 推断节点只在调用方 `ApmService` 对当前组织可见时出现。边 RED 来自调用方 Client Span。节点健康度沿用错误率分档（`>=5%` 严重、`>=1%` 警告）。
- 构图与请求切片共用有界 Trace 样本，不把推断边挂在 Jaeger `dependencies` 上。Adapter 保留 `service_dependencies` 仅作对照，拓扑服务不再用它构图。
- 探针发布手册钉死 Java 2.31.1、Python 0.65b0（SDK 1.44.0）、Node 0.79.0、Go v1.46.0；构建禁止不钉版本的 `pip download`。demo 夹具发出模拟 mysql Client Span。

## Testing Decisions

- `db.system` 或 `db.system.name` 单独出现都能得到 `kind=inferred` 的 mysql 节点。
- 仅有 `net.peer.name`+`net.peer.port` 或仅有 `server.address`+`server.port` 时节点展示 `host:port`；缺端口只展示 host，不编造默认端口。
- 两个不同 IP 且 `db.system=mysql` 仍折叠为一个 mysql 节点；样本 Client Span 各自保留自己的地址。
- `db.name` 是独立字段，不写进 `peer_address`。不把 `db.connection_string` / `db.query.text` 写进身份。
- 拓扑构图不创建 `ApmService(name=mysql)`；服务目录 / 应用列表 API 仍无 mysql 行。
- 无组织可见调用方时不出现推断节点。
- 服务拓扑画布展示「推断」角标；调查栏对推断节点隐藏服务详情；应用详情聚焦辅助函数丢弃推断邻居。

先验：`test_topology_service.py`、`topology-canvas.test.tsx`、`apm-service-workflow-test.ts`。

## Out of Scope

- 应用详情子拓扑、应用列表、服务目录展示推断下游。
- 推断对象持久化、CMDB / Monitor 关联、按 `server.address` 拆分多个 mysql 实例。
- 给推断节点配策略 / SLO / 告警。
- OTC 虚拟节点 metrics。

## Further Notes

产品决策：`docs/design/product-decisions/apm-inferred-downstream.md`。本切片接在 `apm-topology-request-slice` 的有界样本构图之上。
