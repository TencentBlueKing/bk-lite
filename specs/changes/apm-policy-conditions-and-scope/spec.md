# APM 策略第三批：多条件、目标范围、下游依赖、SLO 燃烧率

Status: implemented

需求来源：2026-10-28 产品复核 APM 告警策略与主流竞品（Datadog APM Monitor、New Relic APM Conditions、Dynatrace Services
anomaly detection、SkyWalking Alarm、阿里云 ARMS 应用监控）的能力对照，结论是「看哪个数 / 相对谁 / 怎么比线」三个核心槽位
已不输竞品，剩余差距集中在条件组合、目标范围和新目标身份。产品明确本批**不再设后置**，六个差距一次补齐，并拍板多服务
采用轻量 scope 形态而不是监控同款策略组。

前两批规格：`specs/changes/apm-alert-calc-enrichment/spec.md`、`specs/changes/apm-alert-calc-catalog/spec.md`（均 implemented）。
决策记忆：`docs/design/product-decisions/apm-policy-calc-methods.md`。长期契约：`specs/capabilities/apm-alerting.md`。
监控同题决策：`docs/design/product-decisions/monitor-policy-multi-metric.md`（条件语义直接复用）、
`docs/design/product-decisions/monitor-policy-group.md`（本批明确不照搬）。

## Problem Statement

按竞品逐项对照（见 `~/.cursor/.../canvases/apm-policy-calc-competitor-gap.canvas.tsx` 的 28 项矩阵），今天 APM 策略配不出来的：

| 场景 | 竞品 | 现状 |
|---|---|---|
| 「吞吐 ≤ 1000 且 相对上一窗跌 50%」「错误率 > 5% 且 请求数 ≥ 200」 | ARMS 多条件、Dynatrace 绝对 + 相对双阈值、SkyWalking composite、Datadog composite | 一条策略一个条件；10-28 撤回的 D3 前置条件也只是门槛 |
| 新上线的接口自动进策略、逐端点判定 | ARMS 接口维度「遍历」、Datadog group by resource | 不选端点 = 服务整体聚合；选端点 = 手选静态清单 |
| 一条「错误率 > 5%」覆盖 30 个服务，新服务自动纳入 | ARMS 多应用 + 自动追加、Datadog tag scope | `ApmPolicy.service` 单外键 |
| 按实例判定（某台 Pod 时延高） | New Relic condition_scope=instance、SkyWalking instance | 无 |
| 「DB 调用耗时 > 500ms」「下游 HTTP 错误率 > 10%」 | ARMS 应用依赖服务 × 4 指标、New Relic external service、SkyWalking service_relation | 只看入口 Span |
| SLO 错误预算快燃 / 慢燃 | Datadog / Grafana 长短双窗燃烧率 | `ApmSlo` 只展示剩余预算，不告警 |
| 近 N 天均值 ± k·σ 动态区间 | 蓝鲸同比区间、Dynatrace 自适应 | 只有均值 |
| 保存前看最近 24h 会响几次 | ARMS 告警数预测 | 试算只算本窗 |

## Solution

四个结构性改动 + 两个小项，依赖顺序固定：先把条件从策略级单值变成条件列表，再把目标从 (端点, 版本) 扩成
(服务, 端点, 版本, 实例 | 依赖)，最后叠 SLO 燃烧率这个新策略类型。策略仍是叠加的几句话，不做表达式和 ML。

| 用户要说的 | 字段 | 本批变化 |
|---|---|---|
| 看哪个数 / 相对谁 / 怎么比线 | `conditions[]` | 1～3 个常规条件 + 0～2 个前置条件，全部满足；条件级比较基准 |
| 看谁 | `scope_mode` / `service_ids` / `application` / `endpoint_mode` / `instance_mode` / `target_kind` / `dependencies` | 多服务、全部端点、实例维度、下游依赖 |
| SLO 还能烧多久 | `metric_type=slo_burn_rate` + `slo` + 长短窗 | 新策略类型 |
| 对照更稳 / 先看会响几次 | `compare_value_kind=sigma`；试算 `replay_hours` | 小项 |

### 竞品覆盖对照（能力覆盖与术语输入，不照搬架构）

| 能力 | Datadog | New Relic | Dynatrace | SkyWalking | ARMS | 本方案 |
|---|---|---|---|---|---|---|
| 多条件「且」 | Composite | — | 双阈值同时越线 | composite && | 同时满足 / 任一 | 进：条件列表 + 全部满足（监控同款） |
| 条件级环比 | — | — | 相对阈值 | — | 条件可选环比 / 同比 | 进：条件级比较基准 |
| 全部端点逐个判定 | by resource | FACET | — | 按端点 | 遍历 | 进：`endpoint_mode=all` |
| 多服务 / 自动纳入 | tag scope | 多 entity | 全局 | include regex | 多应用 + 自动追加 | 进：多选服务 / 按应用 |
| 实例维度 | by host | instance scope | PGI | instance | — | 进：`instance_mode=grouped` |
| 下游依赖 | client resources | external service | 有 | service_relation | 应用依赖服务 | 进：`target_kind=dependency` |
| SLO 燃烧率 | 长短双窗 | SLO alert | SLO alert | — | — | 进：长短双窗 |
| σ 区间 | anomaly（ML） | baseline（ML） | 自适应 | — | — | 进：均值 ± k·σ，不做 ML |
| 历史回放 | — | — | — | — | 告警数预测 | 进：试算 24h 回放 |

## User Stories

1. 作为现场运维，我想配「吞吐 ≤ 1000 req/min 且 相对上一等长窗跌 50%」，半夜低谷不响、断崖才响；也想配「错误率 > 5% 且 请求数 ≥ 200」。
2. 作为现场运维，我想一条策略覆盖网关下所有接口，新接口上线自动进来，下线自动退出，不用维护清单。
3. 作为平台负责人，我想一条「P95 > 800ms」覆盖同一应用的全部服务，新接入的服务自动纳入。
4. 作为 SRE，我想按实例判定「某台 Pod P99 > 2s」，并在告警里看到实例 ID。
5. 作为研发负责人，我想对「下游 MySQL 调用平均耗时 > 300ms」「调用支付网关错误率 > 10%」告警。
6. 作为 SRE，我想对 SLO 配快燃 / 慢燃告警，1h+5m 燃 14.4× 立刻叫人，6h+30m 燃 6× 建单。
7. 作为现场运维，我想选「近 7 天同窗均值 ± 2σ」，比单纯均值少误报。
8. 作为现场运维，我想在保存前看最近 24 小时这条策略会命中几次、分别在几点。
9. 作为既有客户，我不改旧策略就保存，扫描、事件、快照与升级前逐字段一致。

## Implementation Decisions

### D1. 条件模型：`conditions[]` + 全部满足，策略级字段从锚点镜像

```json
"conditions": [
  {"ref": "a", "role": "regular", "metric_type": "throughput", "aggregation": "avg",
   "compare_mode": "absolute", "compare_offset_amount": null, "compare_value_kind": "",
   "min_request_count": null, "slow_threshold_ms": null, "apdex_threshold_ms": null,
   "thresholds": [{"severity": "warning", "comparator": "lte", "value": "16.67"}]},
  {"ref": "b", "role": "regular", "metric_type": "throughput", "aggregation": "avg",
   "compare_mode": "previous_window", "compare_value_kind": "percent",
   "thresholds": [{"severity": "warning", "comparator": "lte", "value": "-50"}]},
  {"ref": "g1", "role": "guard", "metric_type": "error_count", "comparator": "gte", "value": "1"}
]
```

- 常规条件 1～3 条、前置条件 0～2 条，组合只有「全部满足」。不做「任意满足」、不做表达式、不做基于其它策略状态的复合策略（与监控同一立场）。
- **级别合成沿用监控**：策略级别 = 各常规条件命中级别的最低者；任一常规条件未命中任何级别则本轮不命中。前置条件只做门槛、不参与级别；任一前置不满足 → 本轮按未越线处理、走恢复计数（与 10-27 D3「前置不满足走恢复」一致）。
- **非锚点条件缺数据保持**：第一个常规条件是锚点，无数据 / 无流量只看锚点；其它条件 `missing_baseline` / `insufficient_samples` / 无样本时活动告警保持（不触发、不恢复、不计恢复），试算记 `missing_condition_data`。与监控「缺数据不等于不满足」同义。
- **条件级比较基准**（比监控多走一步）：每个常规条件独立选 `compare_mode` / `compare_offset_amount` / `compare_value_kind` / `min_request_count`。策略内不同对照窗 ≤ 2 个，每个目标每轮查询 ≤ 1 + 2 次 `service_red`；同一对照窗的多个条件共用一次查询（`service_red` 一次返回全部指标）。前置条件只允许 `absolute`。
- **不需要维度对齐**：全部条件都在同一目标上，监控的锚点广播省掉。
- **恢复阈值**只挂在锚点条件上（保留现有能力），方向与锚点阶梯相反；`trigger_after` / `trigger_window` / `recover_after` 仍是策略级。
- **镜像**：`metric_type`、`aggregation`、`compare_*`、`min_request_count`、`slow_threshold_ms`、`apdex_threshold_ms`、`thresholds` 这些既有策略级列从锚点条件镜像写入，快照 `policy_snapshot`、告警中心副本 `item` / `labels.metric_type`、SLO 引用不改读方。`conditions` 为空或只有一个常规条件且无前置时，读写行为与升级前逐字段一致。
- 告警 `value` / `current_value` 取锚点；`description` 在多条件时逐条写「a: 当前 X（阈值 Y）；b: …」；告警变量新增 `${<ref>_value}`（监控同名）。
- D6 禁则逐条件生效（慢阈值 / Apdex T 归属、Apdex 比较符、计数类不带最低请求数、`no_traffic` 只能单条件且 `absolute`）。新增：前置条件不含 `no_traffic`、不带级别、不带比较基准；`slo_burn_rate` 只能单条件。

### D2. 作用范围：多服务（轻量 scope）、端点模式、实例维度

```text
scope_mode     service | services | application        默认 service（现状）
service        现有外键，scope_mode=service 时必填；其它模式下为「首个服务」镜像，仅为兼容读方
service_ids    scope_mode=services 时 2..20 个
application    scope_mode=application 时必填，评估时取该应用下当前全部服务，新服务自动纳入
endpoint_mode  service | selected | all                默认 service；selected 对应现有 endpoints[]
instance_mode  all | grouped                           默认 all（现状，不按实例拆）
```

- **多服务不照搬监控策略组**。监控需要策略组是因为「实例入组」是接入路径；APM 没有这个接入动作，策略组的成员管理、默认组、整组停用都没有承载场景。轻量 scope 不动授权模型：策略组织已与服务组织解耦（10 月），告警组织从策略组织快照，只加一条「目标服务必须在策略组织可见，否则本轮跳过并在试算 `items[]` 标 `service_not_visible`」，fail-closed。
- **评估按服务拆单元**：每个服务独立展开目标并各自封顶 `MAX_POLICY_TARGETS = 100`，Celery 任务按 (policy, service) 派发；一条策略一轮扫描的查询数上限 = 服务数 × 100 × (1 + 对照窗数)。`ApmPolicyTargetState` 加 `service` 外键并进 `target_key`；`ApmAlert.service` 已是外键，告警身份不变。
- **全部端点不能靠 `top_endpoints`**（`MAX_TOP_ENDPOINTS = 10`）。新增适配器方法 `service_endpoints(query, limit)`：按入口 Span `stats by (endpoint) count()`，上限 100，按请求数降序。`endpoint_mode=all` 每轮从当前评估窗取活跃端点展开目标；新端点自然进入，`ApmPolicyTargetState` 按端点键保留。
- **消失端点的收口**：`all` 模式下某端点连续 `recover_after` 轮未出现在清单中，视为恢复，结束其活动告警并清状态行；不按端点出无数据告警，只保留服务级 `no_traffic`。`selected` 模式行为不变（手选端点无数据走现有路径）。
- **实例维度**：`grouped` 从当前评估窗的 `instance_activity`（适配器已有 `_INSTANCE_FIELD`）取活跃实例 ID 展开；`ServiceMetricQuery` 加 `instance_id`，过滤复用现有 `_INSTANCE_FIELD:=`。目标元组变为 (service, endpoint, version, instance)。告警变量加 `${instance}`；`ApmAlert` / `ApmPolicyTargetState` 加 `instance_id` 列。表单文案提示「按实例判定会一台一条告警，建议只对核心服务开」。
- **目标乘积封顶**：`endpoint_mode=all × instance_mode=grouped × version_mode=grouped` 允许，但每服务 100 封顶，超出按请求数取前 100 并在试算与策略详情标 `truncated`。

### D3. 下游依赖：`target_kind = entry | dependency`

```text
target_kind    entry | dependency                默认 entry
dependencies   target_kind=dependency 时：[] = 全部依赖；或 [{"channel": "db", "system": "mysql", "statement": "..."}] 手选 ≤ 20
```

- 依赖目标来自现有 `client_db_rollups` 的分类结果（channel / system / statement，已区分 DB、缓存、HTTP 出站），每轮从当前评估窗取；`[]` 为全部，上限沿用 40（`MAX_CLIENT_ROLLUPS`）。
- 适配器加 `service_red` 同形的 `dependency_red(query)`：`kind:="3"` + 按 channel / system / statement 过滤，`stats` 函数集与入口完全一致（`avg / max / quantile / count() if`）。
- 指标面裁剪：时延族、错误率、错误数、慢请求数 / 占比、`throughput`（调用数）可用；`apdex`、`no_traffic` 对依赖不适用，serializer 拒绝。错误定义仍是 Span `status_code`。
- `target_kind=dependency` 与 `endpoint_mode` / `instance_mode` 互斥（依赖目标不再按端点、实例拆）；与多服务可叠加。
- 告警变量加 `${dependency}`（格式「system statement」）；告警中心副本 `labels` 加 `target_kind`；快照 `policy_snapshot` 加 `target_kind` / `dependencies`。
- 消失依赖的收口与 D2 全部端点同规则。

### D4. SLO 错误预算燃烧率：新策略类型

```text
metric_type              slo_burn_rate
slo                      ApmSlo 外键，必填；策略 scope 固定为该 SLO 的服务 / 环境 / 端点，不接受 D2 / D3 字段
burn_long_window_minutes 60..1440
burn_short_window_minutes 默认 long / 12，允许 5..long/2
thresholds[].value       燃烧率倍数，比较符只允许 gt / gte
```

- 燃烧率 = (1 − 窗内合规率) / (1 − objective)。合规率复用 `SloMetricQuery`（已支持任意起止）；每轮两次查询（长窗、短窗），**两窗同时 ≥ 阈值才命中**，级别取两窗各自命中级别的最低者（与 D1 同构）。
- 表单给两个预设：「快燃」1h + 5m、阈值 14.4×（严重）；「慢燃」6h + 30m、阈值 6×（警告）。要两种就建两条策略，不把两套窗塞进一条策略。
- 比较基准、最低请求数、恢复阈值、`conditions` 多条件、评估延迟补偿对这个类型全部禁用（它自身是相对量，长窗远大于导出延迟）。长窗样本为 0 记 `no_data`，短窗为 0 记 `insufficient_samples`。
- 告警变量加 `${slo_name}`、`${burn_rate}`、`${budget_remaining}`；告警中心副本 `item=slo_burn_rate`。
- SLO 删除时策略一并停用并结束活动告警（SLO 是目标身份）。

### D5. 小项

- **σ 区间**：`compare_value_kind = sigma`，只对 `baseline_days` 且 N ≥ 3 开放；阈值填 k（0.5..5），比较值 = (当前 − 均值) / σ；σ 为样本标准差，可用天数 < 3 记 `missing_baseline`。表单单位标签「σ」。
- **24h 回放**：试算请求加 `replay_hours`（0 | 24），非 0 时对每个目标追加一条 `stats by (_time:W)` 查询拿 24h / W 个窗的值，逐窗按条件判定（不含连续 N、不含前轮状态），返回 `replay: {windows, hits, hit_at: [...]}`。只读，不写任何状态；目标上限仍 20；`slo_burn_rate` 与 `baseline_days` 的回放按对照窗同形平移，查询数 ≤ 20 × (1 + 对照窗数) × 2。

### D6. 组合禁则（serializer 一次拒绝）

| 禁止 | 原因 |
|---|---|
| 常规条件 0 或 > 3；前置 > 2；`ref` 重复 | 形态上限 |
| 前置条件带级别、比较基准、`no_traffic` | 前置只做门槛 |
| 策略内不同对照窗 > 2 | 查询成本 |
| `no_traffic` 与任何其它条件并存，或非 `absolute` | 它的 0 就是信号 |
| 恢复阈值不在锚点，或方向与锚点阶梯同向 | 滞回只作用于告警整体 |
| `scope_mode=services` 且 `service_ids` ∉ 2..20；`application` 缺 `application` | 范围上限 |
| `target_kind=dependency` + `endpoint_mode≠service` 或 `instance_mode=grouped` 或 `apdex` / `no_traffic` | 依赖目标不按端点 / 实例拆 |
| `slo_burn_rate` + 任何 D1 多条件 / D2 / D3 / 比较基准 / 最低请求数 / 恢复阈值字段；比较符 `lt` / `lte` | 新策略类型自成一体 |
| `burn_short_window_minutes` > long / 2 或 < 5 | Google 建议短窗 = 长窗 / 12 |
| `sigma` + 非 `baseline_days` 或 N < 3；k ∉ 0.5..5 | σ 需要样本 |
| `replay_hours` ∉ {0, 24} | 本批只做 24h |

### D7. 表单（`policy-editor.tsx`）

- 第 1 步「作用范围」：范围模式（单服务 / 多服务 / 按应用）；端点模式（整体 / 手选 / 全部端点）；实例维度（不拆 / 按实例）；目标类型（入口 / 下游依赖，依赖列表从 `client_db_rollups` 取）。`slo_burn_rate` 类型下这一步只显示 SLO 选择。
- 第 2 步「指标定义」改为条件卡列表：每张卡含指标、慢阈值 / Apdex T、汇聚方法、比较基准、最低请求数；「添加条件」上限 3；「前置条件」单独一段，上限 2，默认折叠。
- 第 3 步「告警条件」阈值表按级别分行、一行 = 一个级别 × 全部常规条件（监控 10-21 结论）；恢复阈值只在锚点列。`slo_burn_rate` 下显示长短窗与「快燃 / 慢燃」预设按钮，阈值单位「×」。
- 比较基准 `baseline_days` 下 Δ / % / σ 三选；σ 时阈值单位「σ」。
- 试算面板加「回放最近 24h」开关，结果表加「24h 命中」列并可展开命中时刻。
- 布局沿用 152px 标签列与 560px 控件宽；Tailwind `className`，不新增 SCSS Module，不硬编码色值；统一尺寸常量不拆。
- 存量单条件策略打开时表单与升级前一致（一张条件卡、无前置、范围模式单服务）。

### D8. 试算、快照、事件、详情

- 试算 `items[]` 加 `service`、`instance`、`dependency`、`conditions: [{ref, current_value, baseline_value, compared_value, matched_severity}]`、`guards: [{ref, value, matched}]`、`replay`；verdict 加 `guard_not_met`、`missing_condition_data`、`service_not_visible`。
- 快照点加 `condition_values: {ref: value}`；`policy_snapshot` 加 `conditions`、`scope_mode`、`service_ids`、`endpoint_mode`、`instance_mode`、`target_kind`、`dependencies`、`slo`、长短窗。
- 告警详情主趋势仍只画锚点；其余条件在「条件」分区按 ref 列当前值 / 阈值 / 命中；`slo_burn_rate` 画燃烧率与阈值线，第二轴画剩余预算。
- 告警列表加「服务 / 实例 / 依赖」列（按 scope 显示）。

## Testing Decisions

只锁外部行为：serializer 接受 / 拒绝、目标展开结果、每轮查询次数上限、`_advance_target` 级别合成与保持态、试算响应与零副作用、快照字段。不测私有方法调用次数。

后端（`apps.apm.tests`，本地 Postgres `--reuse-db`；sqlite 可跑的部分用 sqlite）：

- 序列化：D6 每条禁则一个拒绝 + 对应接受；存量 payload（无新字段）接受且 `conditions` 由镜像字段合成一条；`conditions` 单条无前置时镜像列与升级前逐字段一致。
- 条件：两常规条件级别合成取最低；任一常规未命中 → 不命中；前置不满足 → 走恢复；非锚点缺数据 → 保持且 `consecutive_*` 不变；条件级不同对照窗 ≤ 2 且共用窗只查一次（用 memory adapter 计数查询）。
- 范围：`services` / `application` 按服务拆单元各自封顶 100；不可见服务跳过并记 `service_not_visible`；`endpoint_mode=all` 从 `service_endpoints` 展开、新端点进入、消失端点连续 `recover_after` 轮后告警结束与状态行清理；`instance_mode=grouped` 目标含实例且查询带实例过滤；乘积超 100 截断。
- 依赖：`dependency_red` 的 LogsQL 字符串（`kind:="3"` + 过滤）；`[]` 全部依赖上限 40；`apdex` / `no_traffic` 拒绝；`${dependency}` 渲染。
- SLO：燃烧率公式；长窗无样本 `no_data`、短窗无样本 `insufficient_samples`；两窗同时越线才命中、级别取最低；SLO 删除停用策略并结束告警。
- 小项：σ 计算与 N < 3 的 `missing_baseline`；回放窗口数、命中数、零副作用、查询数上限。
- 日志回归：新失败路径各只记一条 `apm` WARNING，带 `policy_id` / `failed_stage` / `error_type`，不含查询正文与响应体。

前端（`policy-editor.test.tsx` 等）：

- 条件卡增删上限、前置段上限、按级别分行阈值表 payload、恢复阈值只在锚点；范围模式切换与互斥禁用；依赖列表取数；SLO 类型下预设按钮写入长短窗与阈值；σ 单位；回放开关与结果列；存量策略打开表单与升级前一致、保存 payload 不带新字段。
- `pnpm exec vitest run <相关文件>`、`pnpm exec eslint <改动文件>`、`pnpm type-check`。

验收记录必须附：本机 Docker 底座 VictoriaTraces 上，对 `demo-storefront` 同一时段核对 `service_endpoints` 清单与 Explore 端点页一致、
`dependency_red` 某条 DB 依赖的 avg / 调用数与依赖页一致、燃烧率手算一致；多条件策略「吞吐 ≤ X 且 环比 ≤ −50%」在三组构造数据下结论符合 D1。

## Out of Scope

- 组合方式「任意满足」、布尔表达式、基于其它策略状态的复合策略、「任意满足」下的级别合成。
- 监控同款策略组（成员管理、默认组、整组停用、通知在组上设置）。轻量 scope 之上若后续确需，另起 change。
- HTTP 5xx 状态码族计数（与 Span 错误定义两套口径）、按异常类型计数（span event 字段可查性未验证）、JVM / 运行时指标（监控域）、静默期 / 重复通知 / 维护窗（告警中心）。
- ML 异常检测、时序预测、查询语言框。
- 回放超过 24h、回放含连续 N 状态机。
- 服务级统一慢阈值 / Apdex T；策略级评估延迟。

## Further Notes

### 切片顺序（每片独立提交，先绿旧策略回归再进下一片）

1. **条件模型**（D1 + D6 对应禁则 + D7 第 2、3 步 + D8 条件字段）：迁移加 `conditions` 列并从镜像列回填；评估改为逐条件取值、级别合成、保持态；试算、快照、详情、变量。旧策略逐字段回归先绿。
2. **作用范围**（D2）：`scope_mode` / `service_ids` / `application` / `endpoint_mode` / `instance_mode`；`service_endpoints` 适配器方法；`ServiceMetricQuery.instance_id`；`ApmPolicyTargetState` 加 `service` / `instance_id`；按服务拆单元派发；消失端点收口；表单第 1 步。
3. **下游依赖**（D3）：`target_kind` / `dependencies`；`dependency_red`；指标面裁剪禁则；变量与副本标签；表单目标类型。
4. **SLO 燃烧率**（D4）：新类型、`slo` 外键、长短窗、预设、SLO 删除联动；详情图。
5. **小项**（D5）：σ 区间、24h 回放。
6. **文档**：本规格 Status 改 implemented；更新 `specs/capabilities/apm-alerting.md` 长期契约；更新 `docs/design/product-decisions/apm-policy-calc-methods.md`（「明确后置」清空、补本批决策与「已替代决策」）；`CONTEXT.md` 增补「端点模式 / 实例维度 / 依赖 / 快燃 / 慢燃 / 前置条件」词汇。

约束：切片 1 是切片 2～5 的前提（目标与条件的笛卡尔积、试算 `items[]` 结构都建立在条件列表上）；切片 2 的「按服务拆单元」是切片 3、4 多服务叠加的前提。切片 3～5 彼此独立，可并行。

### 主验收

- 旧策略不改保存，扫描、事件、快照与升级前逐字段一致；表单打开与升级前一致。
- 「吞吐 ≤ 16.67 req/s 且 相对上一等长窗 ≤ −50%」：半夜 10 req/s 平稳 → b 不命中 → `ok`；2000 → 800 → a 不命中 → `ok`；30 → 10 → 触发警告。
- 「错误率 > 5%（严重 10%）且 请求数 ≥ 200（前置）」：请求 150、错误率 12% → `guard_not_met`；请求 300、错误率 12% → 严重。
- `endpoint_mode=all`：新端点下一轮进试算；端点下线连续 `recover_after` 轮后活动告警结束。
- `scope_mode=application`：新服务接入后下一轮进试算；不可见服务 `service_not_visible`。
- `instance_mode=grouped`：告警 `${instance}` 有值，试算每实例一行。
- `target_kind=dependency`：「mysql 调用 avg > 300ms」能建告警，试算值与依赖页一致。
- `slo_burn_rate` 快燃预设：长窗 1h 错误率 2%、短窗 5m 错误率 3%、objective 99.9% → 燃烧率 20 / 30 → 严重；短窗 0.05% → 不命中。
- `sigma`：7 天均值 100、σ 10、当前 125、k=2 → 2.5σ 命中；只有 2 天有数据 → `missing_baseline`。
- 回放 24h：返回 24h / W 个窗的命中数与时刻，试算后无任何新记录。

### 已确认成立的现网事实（2026-10-28）

- `MAX_TOP_ENDPOINTS = 10`，`top_endpoints` 不能作为「全部端点」来源。
- `SloMetricQuery` 带任意 `started_at / ended_at`，燃烧率双窗不需要改 SLI 查询。
- `_INSTANCE_FIELD` / `_PEER_SERVICE_FIELD` / `_DB_SYSTEM_FIELD` 已在适配器；`client_db_rollups` 已按 channel / system / statement 分类，上限 40。
- `ApmPolicyTargetState` 唯一键 (policy, target_key)，`target_key` 可容纳服务与实例。
- `ApmAlert.service` 已是可空外键；告警组织从策略组织快照；策略组织与服务组织已解耦。
- `policies.py` 内 `policy.service` 引用 23 处，是切片 2 的主要改动面。

### 决策记录

- **多条件走监控同款「条件列表 + 全部满足」而不是 10-27 D3 的「0～2 条绝对值前置」**：产品本批要求对齐竞品的「吞吐下限 且 环比下跌」，前置条件无法表达环比；监控的级别合成、保持态语义已和产品对过，直接复用。
- **条件级比较基准、对照窗 ≤ 2**：ARMS / Dynatrace 的经典场景要求第二条带相对量；上限 2 让每目标查询数与现有近 N 天均值路径持平。
- **多服务用轻量 scope 不用策略组**（2026-10-28 产品拍板）：APM 没有「实例接入」场景支撑策略组；授权模型已解耦，scope 只加一条可见性校验。
- **全部端点 / 全部依赖每轮动态取清单，不存静态列表**：新对象自然进入、消失对象按 `recover_after` 收口，避免清单与现网脱节。
- **SLO 燃烧率一条策略一组长短窗**：快燃 / 慢燃预设各建一条，比把两组窗塞进三级阈值清楚。
- **σ 只对 `baseline_days` N ≥ 3 开放**：少于 3 个样本的标准差没有解释力。
