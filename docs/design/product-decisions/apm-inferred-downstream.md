# APM 推断下游产品决策记忆

- 最近更新：2026-08-28
- 当前规格：`specs/changes/apm-inferred-downstream/spec.md`

## 产品定位

给 Web 等已插桩服务装一个探针后，运维能在 **服务拓扑** 上看到它访问过的 **MySQL / Redis / Kafka 等未插桩下游**，并下钻到产生该判断的 Client Span。这不是把 mysql 登记成 **APM 服务**，也不是 CMDB 资产发现。

**推断下游**：由已插桩服务的 Client Span 属性推导出的未上报 OTLP 的依赖（库、缓存、消息、外部 RPC）。它出现在调用图上，不进入服务目录，没有 `service.instance.id`，不能配与插桩服务相同的策略 / SLO。

_Avoid_：把推断下游叫成 APM 服务、接入实例、监控实例。

## 产品判断

当前产品说法「装一个 Web 探针，应用列表里也会出现 mysql」**不正确**。目录只认 Resource 上的 `service.namespace + service.name`。Web 访问 MySQL 时，`service.name` 仍是 Web 自己；库类型写在 Span 属性里。

OTC + VictoriaTraces **够当证据源，不够当目录实现**。OTC 不发现服务；VT 存的是 Trace 不是指标。查询 Client Span 可以回答「这个服务打过谁」；不能自动生成 `ApmService(name=mysql)`。

MVP 做成 **服务拓扑页上的推断节点 + 调用链可解释**，不扩张服务目录，也不改应用详情子拓扑。这样能验证「一个探针看见下游」的闭环，又不会污染应用列表、权限和组织继承。

## 已确认范围

以下条目来自本会话已对齐事实，落地规格时默认继承。

- 不把推断下游写入 `ApmService` / `ApmServiceInstance`。
- 不在 Collector 里伪造 `service.name=mysql` 的 ResourceSpan。
- 不 fork OpenTelemetry Collector 去扫语言探针标签。Span 键在各语言 instrumentation，不在 OTC。
- 产品查询用语义约定 **属性别名**，不按语言各写一套查询。至少同时认：
  - 库：`db.system` 与 `db.system.name`
  - 库名：`db.name` 与 `db.namespace`
  - 消息：`messaging.system`
  - RPC：`rpc.system`（可选 `rpc.service`）
  - 兜底：`peer.service`，其次 host（`server.address` / `net.peer.name` / `network.peer.address` / `net.peer.ip`）
  - 端口（仅展示）：`server.port` / `net.peer.port` / `network.peer.port`
- 推断节点展示 Span 里实际有的 host、port、库名；缺字段不编造；折叠身份不按 IP。
- VictoriaTraces 字段前缀 `span_attr:` 由存储加上，探针源码里没有这个前缀。
- 语言探针对照表只服务文档、排障和验收夹具，不是发现能力的前置。
- 分析源码与归档离线包使用同一组钉死版本（2026-08-26 建议，发布时以流水线归档为准）：

| 语言 | 制品 | 版本 | 读源码 tag |
|---|---|---|---|
| Java | `opentelemetry-javaagent.jar` | 2.31.1 | `opentelemetry-java-instrumentation` `v2.31.1` |
| Python | `opentelemetry-distro[otlp]` | 0.65b0（配套 SDK 1.44.0） | `opentelemetry-python-contrib` `v0.65b0` |
| Node.js | `@opentelemetry/auto-instrumentations-node` | 0.79.0 | `opentelemetry-js-contrib` `auto-instrumentations-node-v0.79.0` |
| Go | `go.opentelemetry.io/otel` | v1.46.0 | `opentelemetry-go` `v1.46.0`；库插桩看同期 `opentelemetry-go-contrib` |

- 探针版本不与 Collector `0.153.0` 对齐。Git 仓库不钉探针号；`docs/operations/apm-probe-artifact-release.md` 只要求流水线固定版本并 `apm_probe_init`。构建必须带版本号，禁止 `pip download` 不钉版本。
- MVP 产品入口是 **服务拓扑** 与 **应用详情画布**。应用列表、服务目录、接入实例、下属服务表和关键信息 KPI 都不展示推断节点。

## 已确认设计决策

- **查询时推断，不物化目录。** 推断节点只存在于当前时间窗（及拓扑切片）的查询结果。静默/归档语义只属于插桩服务与实例。原因：库节点没有稳定实例身份；写入目录会与「未知 namespace 不自动建应用」冲突，也会让组织继承、告警、SLO 误绑到 mysql。
- **构图走有界 Trace 样本，不依赖 Jaeger `dependencies` 的库边。** 当前拓扑切片已按父子 Span 聚跨服务边。推断边在同一批样本上识别：`span.kind=client`（或 producer），且带上表别名之一，且没有另一 `service.name` 的子 Span。原因：VT 库边只认 `db.system.name`，child 名是 `checkout:mysql`，和目录对不上；老探针默认发 `db.system`。样本路径与请求切片、边级 P95/错误一致。
- **身份折叠规则（MVP）。** 优先 `peer.service`；否则库用 `db.system.name` 或 `db.system`，消息用 `messaging.system`；再否则 `server.address` / `net.peer.name`。同一时间窗同一调用方下相同折叠键合成一个节点。不按调用方拆成 `checkout:mysql` 这种 VT 图专用名。两个真实库实例若属性只有 `db.system=mysql`，会合成一个节点；**不按 IP 拆节点**。Client Span 上实际有的 host / port / 库名挂在节点和样本上展示（`host:port`，缺端口不加默认端口）；库名不覆盖 host。不把 `db.connection_string` / `db.query.text` / 凭据写进拓扑身份。高基数按地址拆分后置。
- **节点分两类。** `instrumented`：已在当前组织可见的 `ApmService`。`inferred`：未插桩下游。推断节点展示类型（mysql / redis / kafka）和 Span 里实际有的地址 / 库名，角标「推断」。点推断节点打开调查栏：调用方、样本 Client Span（各样本可带自己的地址）、下钻调用链；**不提供服务详情、策略、SLO、组织调整**。
- **RED 口径。** 推断节点没有独立吞吐。边的调用量 / 错误率 / P95 来自调用方 Client Span。节点健康度沿用拓扑错误率分档。截断时 `truncated=true`，文案不得说成全量拓扑。
- **权限。** 推断节点只在调用方 `ApmService` 对当前组织可见时出现。不能靠推断节点枚举其他组织的库地址。
- **Collector 保持 traces-only。** 不启用 `servicegraphconnector`、不恢复 spanmetrics、不增加 APM VictoriaMetrics。推断不经过 OTC 改写。
- **`OTEL_SEMCONV_STABILITY_OPT_IN`。** 接入片段默认不打开 `database`。查询别名同时覆盖默认旧键与 opt-in 新键。若日后默认切到稳定约定，只改别名表和夹具，不改目录模型。
- **第一版先做服务拓扑，应用详情画布随后补直接下游。** 推断查询挂在现有拓扑构图（有界 Trace 样本）上。应用详情只展示本应用已插桩服务的直接推断下游，不进下属服务表 / KPI / 目录，避免 mysql 被理解成 APM 服务。一跳邻居自己的推断下游不进入本应用图。

## 用户闭环（MVP）

1. 用户给 Web 服务接入官方探针（系统内下载、钉死版本）。
2. Web 产生访问 MySQL / Redis 的 Client Span，经现有 OTC → NATS → VT。
3. 打开 **服务拓扑** 页（可带现有请求切片）。不经过应用列表或应用详情。
4. 图上除插桩服务外，出现带「推断」角标的 mysql / redis 节点。
5. 点该节点或边，调查栏列出样本 Trace；打开瀑布能看到带 `db.system*` 的 Client Span。
6. 应用列表、服务列表、接入实例、下属服务表仍只有插桩服务；mysql 不会多出一行。应用详情**画布**可以出现本应用的直接推断下游。

## 明确后置

- 应用列表 / 服务目录 / 下属服务表展示推断下游。
- 推断对象持久化、手工确认/忽略、与 CMDB / Monitor 实例关联。
- 未插桩 HTTP/SaaS 的完整 inferred service（VictoriaTraces issue #121 级）。
- 按 `server.address` 拆分多个 mysql 实例，或合并跨服务的同一库。
- OTC 侧虚拟节点 metrics、spanmetrics。
- 给推断节点配 APM 策略 / SLO / 告警。
- 在接入页按语言展示完整 Span 标签表（可作为内部对照，不进第一版 UI）。

## 仍待确认

无。

## 实现接缝（供后续 spec）

- 领域：拓扑构图在现有有界 Trace 样本上增加推断边/节点；节点带 `kind=instrumented|inferred` 与折叠键。
- Adapter：模板化 LogsQL/样本聚合，禁止用户透传 TraceQL；别名表集中在 Adapter 或单一契约常量，测试锁外部行为（有 `db.system` 或 `db.system.name` 都能出 mysql 节点）。
- Web：仅服务拓扑画布区分推断节点样式；调查栏对推断节点隐藏服务详情入口。应用详情拓扑本切片保持现状。
- 探针：发布手册把 `v<VERSION>` 换成上表版本；wheelhouse / npm / Go module 必须钉版本。对照表用 GitHub 公开 tag 阅读，不 fork。
- 先验测试：`test_topology_service.py`、`topology-canvas.test.tsx`、`apm-service-workflow-test.ts`；另加钉死探针版本的 demo/lab 夹具（Python 或 Java 打真实或模拟 mysql Client Span）。

## 已替代决策

- 「装一个 Web 探针就会在应用列表发现 mysql」：2026-08-26 明确为不正确的产品说法；正确说法是拓扑上出现推断下游。
- 「用 db.name 填推断节点地址」：2026-08-27 改为库名独立字段；地址只来自 host/port 别名。
- 「fork OTC 用 Cloud 扫各语言探针标签」：2026-08-26 改为读各语言 instrumentation 的钉死 tag，查询走语义约定别名。
- 「用 VT Jaeger dependencies 的 `service:mysql` 边当发现结果」：不作身份源；仅可作辅助对照。
- 「MVP 同时改服务拓扑和应用详情子拓扑」：2026-08-26 改为第一版只做服务拓扑。2026-08-28 用户确认应用详情**画布**补本应用的直接推断下游，仍不进目录 / KPI / 下属服务表。

## 决策来源

- 2026-08-28 用户确认：应用详情拓扑要讲完整请求路径，画布补本应用已插桩服务的直接推断下游；一跳邻居的推断下游不进入本应用图。
- 2026-08-27 用户确认：推断下游展示 Client Span 实际有的 host/port/库名；不按 IP 改折叠键；高基数拆分后置。
- 2026-08-26 会话：服务发现身份、OTC+VT 能力边界、Span 属性可查询、探针制品文档无版本号、建议钉 2.31.1 / 0.65b0 / 0.79.0 / v1.46.0。
- 仓库事实：`DjangoTelemetryCatalogService` 只认 Resource 身份；`docs/operations/apm-probe-artifact-release.md`；Collector `0.153.0` traces-only；拓扑切片改为有界 Trace 样本。
- 对照而非目标架构：Datadog inferred services、OTel `servicegraphconnector` 虚拟节点、VictoriaTraces PR #117 / issue #121。
