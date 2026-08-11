# APM 数据面产品决策记忆

- 最近更新：2026-08-11
- 当前规格：`specs/changes/apm-nats-vt-pipeline/spec.md`

## 产品定位

APM 数据面是与 Django 控制面解耦的 traces-only 运行期链路。产品交付硬契约与自有组件；
生产底层依赖服务的流水线与编排由运维负责。

## 已确认范围

- 正式链路：区域 Collector → JetStream `apm.traces.<region>` → 系统 Collector → VictoriaTraces。
- 4318 仅受信区域内网；无应用级 Token（ADR 0008）。
- `deploy/apm` 定位为契约夹具与本地/CI 验证，不是生产 Compose/流水线真相源。
- 运维须满足 `ACCEPTANCE.md` / `CAPACITY.md` 中的验收与容量约束，编排工具自选。

## 已确认设计决策

- 采用方案「契约硬、编排软」：研发锁死拓扑、协议、ACK、清洗、安全与查询契约；运维落生产
  Stream/VT/系统 Collector/容量告警。
- 产品自有组件仍由研发维护：BK-Lite Collector 发行版、受管代理内嵌区域 Collector、Server
  接入与 VT 查询闭环。
- 根 Makefile 不承载 APM 数据面目标；命令入口在 `deploy/apm/Makefile`。
- 上线文档以验收清单命名（`ACCEPTANCE.md`），避免被理解成替运维设计发布流水线。

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

## 决策来源

- 2026-08-11 用户确认：只需提出 APM 链路需求与硬约束，底层依赖服务由运维流水线落地。
- ADR 0006 / 0008；`deploy/apm/README.md`、`ACCEPTANCE.md`、`CAPACITY.md`。
