# APM 数据面产品决策记忆

- 最近更新：2026-11-10
- 当前规格：[APM NATS / VictoriaTraces 数据面](../../../specs/changes/apm-nats-vt-pipeline/spec.md)、[聚合层变更](../../../specs/changes/observability-aggregate-metrics/spec.md)

## 产品定位

APM 数据面是与 Django 控制面解耦的运行期链路。调用链明细写入 VictoriaTraces。入口 RED
与可用性 SLO 允许读独立聚合库，明细、策略、慢请求、Apdex、延迟 SLO、下钻与拓扑仍以
VictoriaTraces 为准。目标契约见 [ADR 0011](../../adr/0011-apm-rum-aggregate-metrics-store.md)，
落地见[聚合层变更](../../../specs/changes/observability-aggregate-metrics/spec.md)，当前尚未部署。
产品交付硬契约与自有组件；生产底层依赖服务的流水线与编排由运维负责。

## 已确认范围

- 正式链路：区域 Collector → JetStream `apm.traces.<region>` → 系统 Collector → VictoriaTraces。
- 4318 仅受信区域内网；无应用级 Token（ADR 0008）。
- `deploy/apm` 定位为契约夹具与本地/CI 验证，不是生产 Compose/流水线真相源。
- 运维须满足 `ACCEPTANCE.md` / `CAPACITY.md` 中的验收与容量约束，编排工具自选。
- 入口 RED 与可用性 SLO 的目标读路径是独立聚合库。Monitor 的 VictoriaMetrics 仍只服务监控。聚合库不复用它的地址。这条读路径当前尚未部署。

## 已确认设计决策

- 采用方案「契约硬、编排软」：研发锁死拓扑、协议、ACK、清洗、安全与查询契约；运维落生产
  Stream/VT/系统 Collector/容量告警。
- 产品自有组件仍由研发维护：BK-Lite Collector 发行版、受管代理内嵌区域 Collector、Server
  接入与 VT 查询闭环。
- 根 Makefile 不承载 APM 数据面目标；命令入口在 `deploy/apm/Makefile`。
- 上线文档以验收清单命名（`ACCEPTANCE.md`），避免被理解成替运维设计发布流水线。
- 聚合库的部署与写入规则见[聚合库运维规则](../../operations/aggregate-metrics-store.md)。研发不提供生产编排。`deploy/apm` 在聚合流水线落地前仍是调用链契约夹具。

## 明确后置

- 不受信网络 / 公网接入的身份、Token、Gateway 模型。
- 把契约夹具自动对接到某一家运维平台的具体流水线模板。

## 仍待确认

无。

## 已替代决策

- 「研发交付完整参考生产部署/上线手册，运维按手册逐步执行」：2026-08-11 调整为契约夹具 +
  验收约束，生产编排交运维。
- 「根 Makefile 提供 `apm-*` 包装目标」：2026-08-11 移除，与 `server/`、`agents/stargazer`
  等模块内 Makefile 风格对齐。
- 「APM 数据面保持 traces-only，不使用 VictoriaMetrics，不生成 Span Metrics」：2026-11-10
  改为入口 RED 与可用性 SLO 允许读独立聚合库。明细、策略、慢请求、Apdex、延迟 SLO、下钻与拓扑
  仍以 VictoriaTraces 为准。Monitor 的 VictoriaMetrics、尾采样和 Edge 仍不进入 APM 数据面。
  见 [ADR 0011](../../adr/0011-apm-rum-aggregate-metrics-store.md)。ADR 0006 的其余决定不变。

## 决策来源

- 2026-08-11 用户确认：只需提出 APM 链路需求与硬约束，底层依赖服务由运维流水线落地。
- ADR 0006 / 0008；`deploy/apm/README.md`、`ACCEPTANCE.md`、`CAPACITY.md`。
- 2026-11-10：[ADR 0011](../../adr/0011-apm-rum-aggregate-metrics-store.md) 部分替代 ADR 0006 里关于 Span Metrics 和 APM VictoriaMetrics 的决定。2026-11-09 的概念验证支持累计写入、固定分片、不去重和容量估算。
