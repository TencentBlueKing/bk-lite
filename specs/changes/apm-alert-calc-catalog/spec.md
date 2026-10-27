# APM 告警计算方式目录：指标面 × 比较基准 × 判定规则

Status: implemented

需求来源：CTeam `p398_716` 第二批。第一批（相对上一等长窗、N 小时 / N 天前同窗、最低请求数、试算）已按
`specs/changes/apm-alert-calc-enrichment/spec.md` 落地（提交 `b2d1c03967`、`98abb914a9`）。产品在 2026-10-27
复核后要求按客户实际场景对照竞品补齐 APM 告警的计算能力，并以本仓库技术栈（VictoriaTraces LogsQL 流式聚合、
Django、Ant Design 表单）为准选落法，而不是照搬竞品的查询语言框或机器学习引擎。
本 spec 不改写第一批规格的 D1～D7，只在其上叠加。监控、日志两域的同题规格见
`specs/changes/monitor-alert-calc-enrichment/spec.md`、`specs/changes/log-policy-calc-catalog/spec.md`；
三域共用同一套用户词汇（当前值 / 相对上一等长窗 / 同窗 / 变化量 / 变化率 / 前置条件 / 恢复阈值），不共用引擎。

## Problem Statement

第一批把「相对谁」这一槽位补齐了，但「看哪个数」「怎么比线」两个槽位仍是最初的最小集。
按客户会配的 APM 告警逐项对照 Datadog APM Monitor、New Relic APM Conditions、Elastic APM Rules、
SkyWalking Alarm、阿里云 ARMS 应用监控、蓝鲸监控，下面这些场景今天配不出来：

| 场景 | 竞品 | 现状 |
|---|---|---|
| 「平均时延 > 300ms」「P90 > 500ms」「最大时延 > 5s」 | Datadog avg/p50/p75/p90/p99；SkyWalking P50～P99；Elastic avg/p95/p99；ARMS 平均耗时 | 只有 P95 / P99 |
| 「错误数 ≥ 100 次」（小流量服务错误率失真，直接看次数） | Elastic Error count；ARMS 调用错误次数；New Relic error_count；ARMS 最佳实践「错误数上限 + 环比上升」 | 只有错误率 |
| 「慢请求（> 1s）数 ≥ 50 / 占比 > 10%」 | ARMS 慢调用次数；Datadog Analytics「slow requests spike」 | 不支持 |
| 「Apdex < 0.8」 | Datadog、New Relic、SkyWalking apdex | 不支持 |
| 「流量 ≤ 1000 且 比上一窗跌 50%」（半夜低谷只设下限会误报，断崖才是故障） | ARMS 最佳实践多条件；SkyWalking composite；Datadog Composite；监控多指标条件 | 一条策略一个条件 |
| 「10 个周期里 3 次超线才告」（抖动大的接口不要连续 N） | SkyWalking `count` within `period`；ARMS「持续：x 分钟内 x 次」；蓝鲸 `trigger_config.count/check_window`；New Relic `AT_LEAST_ONCE` | 只有连续 N 次 |
| 「触发 > 80%，恢复 < 70%」（79～81 来回振铃） | Datadog recovery thresholds；Zabbix recovery expression；监控已有恢复阈值 | 只有连续 N 次不满足 |
| 「比近 7 天同一时段均值高 50%」（单日对照会被昨天的事故带偏） | 蓝鲸高级同比 / 同比区间；New Relic baseline；Datadog anomaly；监控「近 N 天均值」 | 只能对照某一天 |
| 「下游依赖（DB / 第三方）耗时或错误率升高」 | ARMS 应用依赖服务调用 × 4 指标；New Relic external service；Datadog client resources | 只看入口 Span |

另有两个判定准确性问题在第一批复核时暴露：Span 由 SDK 批量导出，落库比发生晚数秒到一分钟，评估窗 `[T−W, T]`
的尾部必然少算；对绝对阈值只是轻微偏低，对「相对上一等长窗」则系统性地把当前窗算小、把下跌放大。竞品普遍有
evaluation delay（Datadog）/ aggregation delay（New Relic）。本仓库没有。

## Solution

四条技术栈事实决定了落法：

1. 策略评估已经是「对每个目标跑一次 `service_red`，整窗一条 `stats` 聚合 + 一条按时间分桶的 `stats`」。LogsQL `stats`
   管道可以在同一条查询里并列任意多个函数：`avg(duration)`、`max(duration)`、`quantile(0.5|0.75|0.9, duration)`、
   `count() if (duration:>T)`、`count() if (duration:<=T)`。指标面从 5 个扩到 12 个不增加查询次数。
2. 对照窗已经是「同一条查询平移起止」；多天同窗均值可以用 `_time:[a,b) or _time:[c,d) …` 加 `stats by (_time:1d)`
   在一条查询里拿到 N 天的值（2026-10-27 已在本机 VT 实跑确认，见「已确认成立的现网事实」）。
3. 前置条件只读同一次 `service_red` 返回的其它字段（请求数、错误数、吞吐），零额外查询。
4. 判定状态在 `ApmPolicyTargetState` 一行里，加一个最近 N 窗命中位串就能做「N 个周期内 M 次」，不需要新表。

因此策略仍是叠加的几句话，不做互斥下拉，也不做表达式：

| 用户要说的 | 表单位置 | 字段 | 本批变化 |
|---|---|---|---|
| 看哪个数 | 定义指标 · 指标 | `metric_type` + 参数 | 时延统计量族、错误数、慢请求、Apdex |
| 相对谁 | 告警条件 · 比较基准 | `compare_mode` + `compare_offset_amount` + `compare_value_kind` | 加「近 N 天同窗均值」 |
| 够不够数 / 先满足什么 | 告警条件 · 前置条件 | `min_request_count`（保留）+ `guard_conditions[]` | 加 0～2 条绝对值前置条件 |
| 怎么比线 | 多级阈值 / 触发 / 恢复 | `thresholds` + `trigger_after` + `trigger_window` + `recovery_threshold` + `recover_after` | 加 N 中 M、恢复阈值 |
| 什么时候算 | 全局 | `APM_POLICY_EVALUATION_DELAY` | 评估窗整体后移 |

明确不做：Datadog / New Relic / Elastic 的机器学习异常检测与 Watchdog；查询语言框（Trace Analytics、NRQL、KQL）；
距容量线剩余时间（APM 没有水位类指标）；静默期 / 通知间隔 / 维护窗（归告警中心）；复合策略（基于其它策略的告警状态）；
任意 AND / OR 表达式；直方图分位。

### 竞品覆盖对照（只做能力覆盖与术语输入，不照搬架构；来源为各家当前官方文档）

| 能力 | Datadog APM | New Relic APM | Elastic APM | SkyWalking | ARMS | 蓝鲸监控 | 现状 | 本方案 |
|---|---|---|---|---|---|---|---|---|
| 时延 avg / p50 / p75 / p90 / p95 / p99 / max | avg p50 p75 p90 p99 | response_time（可选分位） | avg p95 p99 | P50～P99 | 平均耗时、Pxx | 看指标 | p95 p99 | 进：全部七个 |
| 错误率 | 有 | error_percentage | failed transaction rate | service_sla | 调用错误率 | — | 有 | 保持 |
| 错误数 | errors/s | error_count | error count | — | 调用错误次数 | — | 无 | 进 |
| 慢请求数 / 占比 | Analytics 查询 | — | — | — | 慢调用次数 | — | 无 | 进（策略级慢阈值） |
| Apdex | 有 | apdex | — | apdex | — | — | 无 | 进（策略级 T） |
| 吞吐 / 无流量 | hits；no data | throughput；loss of signal | low transaction count（ML） | cpm | 调用次数 | 无数据 | 有 | 保持 |
| 相对上一窗 Δ / % | Change Alert | NRQL compare | — | — | 环比 | 环比策略 | 有 | 保持 |
| N 小时 / N 天前同窗 | Change Alert N ago | — | — | — | 同比（上小时 / 昨日） | 同比策略 | 有 | 保持 |
| 近 N 天同窗均值 | anomaly（ML） | baseline（ML） | anomaly（ML） | — | — | 高级同比 / 同比区间 | 无 | 进：统计均值，不做 ML |
| 最低样本门 | min N hits | — | — | — | — | — | 有 | 保持 |
| 多条件「且」 | Composite | — | — | composite-rules | 多条件触发 | 同级别算法连接符 | 无 | 进：0～2 条绝对值前置条件 |
| N 个周期内 M 次 | — | AT_LEAST_ONCE | — | count / period | 持续 x 分钟内 x 次 | count / check_window | 无 | 进 |
| 恢复阈值（滞回） | recovery thresholds | — | — | — | — | — | 无 | 进 |
| 评估延迟 | evaluation delay | aggregation delay | lookback | — | — | — | 无 | 进：全局 |
| 下游依赖调用 | client resources | external service | — | relation metrics | 应用依赖服务调用 | — | 无 | 后置（切片 3 评估） |
| 实例维度 | by host | condition_scope=instance | — | instance metrics | — | — | 无 | 后置 |
| 保存前试算 | 预览 | 预览 | — | — | — | — | 有 | 随契约扩展 |
| ML 异常 / 离群 / 预测 | 有 | 有 | 有 | — | — | 智能检测 | 无 | 不做 |

## User Stories

1. 作为现场运维，我想在指标里直接选「平均时延 / P50 / P75 / P90 / P95 / P99 / 最大时延」，表达「P90 > 500ms」「最大时延 > 5s」。
2. 作为现场运维，我想对小流量服务配「错误数 ≥ 100 次」，不被 2 个请求 1 个失败的 50% 吵醒，也不被最低请求数挡掉真正的错误。
3. 作为现场运维，我想配「慢请求（> 1s）占比 > 10%」或「慢请求数 ≥ 50」，不必用 P95 硬套。
4. 作为研发负责人，我想对核心服务配「Apdex < 0.8」，用一个数表达体验达标。
5. 作为现场运维，我想配「吞吐 ≤ 1000 req/min 且比上一等长窗跌 50%」，半夜低谷不响、断崖式下跌才响。
6. 作为现场运维，我想配「10 个周期内 3 次超线才告警」，抖动大的接口不再漏报也不再狂响。
7. 作为现场运维，我想配「触发 P95 > 800ms，恢复 P95 < 600ms」，600～800 之间保持告警不来回振铃。
8. 作为现场运维，我想选「近 7 天同窗均值」并用变化率比线，不被昨天的一次事故带偏对照。
9. 作为值班人员，我想试算和告警详情把慢阈值、Apdex T、前置条件是否满足、N 中 M 的命中数、恢复带状态都摆出来。
10. 作为既有客户，我不改旧策略就保存，扫描结果与升级前完全一致（评估延迟除外，见 D7）。

## Implementation Decisions

### D1. 指标面：`metric_type` 扩为 12 个，参数两个

```text
metric_type   error_rate | error_count | p50 | p75 | p90 | p95 | p99 | latency_avg | latency_max
              | slow_request_count | slow_request_rate | apdex | throughput | no_traffic
slow_threshold_ms   1..600000   仅 slow_request_count / slow_request_rate 必填
apdex_threshold_ms  1..600000   仅 apdex 必填，默认 500
```

- 存储仍是扁平枚举（`AlterField choices`），表单按族分组显示：时延（七个统计量）/ 错误（错误率、错误数）/ 慢请求（数、占比）/
  Apdex / 吞吐 / 无流量。不改成「`metric_type=latency` + 统计量」两个字段：`p95` / `p99` 已被策略、快照、告警中心副本、
  SLO 引用，拆字段要动所有读方。
- `ServiceRed` / `ServiceRedPoint` 扩字段：`avg_ms`、`max_ms`、`p50_ms`、`p75_ms`、`p90_ms`、`slow_count`、`satisfied_count`、
  `tolerating_count`。`ServiceMetricQuery` 加 `slow_threshold_ms: int | None`、`apdex_threshold_ms: int | None`，为空时不生成对应
  `count() if`。`final_stats` 一条查询并列全部函数；按时间分桶的 `stats_range` 同形。
- 单位与量纲：`error_rate` / `slow_request_rate` / `apdex` 库内 0～1；`error_count` / `slow_request_count` 单位「次 / 窗」；
  时延族 ms；吞吐 req/s 不变。`apdex = (satisfied + tolerating / 2) / requests`，比较符只允许 `lt` / `lte`。
- 汇聚方式（`aggregation`）只对「率 / 分位 / 均值」族有意义；`error_count` / `slow_request_count` 是整窗总数，表单隐藏汇聚方式，
  后端忽略并存 `avg`（与 `no_traffic` 同处理）。
- 比较基准对新指标的适用：时延族、`error_rate`、`slow_request_rate`、`apdex`、`throughput`、`error_count`、`slow_request_count`
  都允许 `previous_window` / 同窗 / 近 N 天均值；`apdex` 的 `percent` 分母是 0～1 的分数，允许。`no_traffic` 仍只允许 `absolute`。
- 最低请求数适用于：`error_rate`、`slow_request_rate`、`apdex`、时延族。`error_count` / `slow_request_count` / `throughput` /
  `no_traffic` 必须为 null（计数本身就是信号）。

### D2. 比较基准：加「近 N 天同窗均值」

```text
compare_mode           absolute | previous_window | offset_hours | offset_days | baseline_days
compare_offset_amount  baseline_days 时为 N，2..7（受 35 天留存与查询成本双重约束）
compare_value_kind     baseline_days 允许 delta | percent（与监控 baseline_days 一致；同窗仍只允许 percent）
```

- 对照 = 过去 N 天中每天同一时段 `[T−W−k·1d, T−k·1d]`（k=1..N）各自按策略汇聚得一个数，再取算术均值。
  某天请求数 < `min_request_count`（或为 0）则该天不计入；可用天数 < ⌈N/2⌉ 记 `missing_baseline`（reason `baseline_days_insufficient`）。
- 查询：一条 LogsQL，`(_time:[s1,e1) or … or _time:[sN,eN)) <entry filters> | stats by (_time:1d) <final_stats>`，
  按桶回填到 k。本机 VT 已实跑确认可行（见「已确认成立的现网事实」）；区间必须写成半开 `[s, e)`，闭区间会比
  `stats_query` 的 `start/end` 多算边界上的 Span。精确去重路径（`_bounded_spans`）对多区间同样适用，总窗长 N×W ≤ 1d 时走去重。
  若某环境该写法失败，退回 N 次 `service_red`，并把使用 `baseline_days` 的策略目标上限压到 20（`MAX_BASELINE_POLICY_TARGETS`）。
- 试算、快照、告警详情：`baseline_value` 为均值；`baseline_series` 画均值线，不画 N 条。试算 `items[]` 加 `baseline_days_used`。
- 不做「均值 ± k·σ 的动态区间」（蓝鲸同比区间 / 振幅）：本批先用均值；若现场反馈均值对照仍误报再评估 `compare_value_kind=sigma`。

### D3. 前置条件：0～2 条绝对值门槛

```json
"guard_conditions": [
  {"metric_type": "throughput", "comparator": "lte", "value": "16.67"},
  {"metric_type": "error_count", "comparator": "gte", "value": "100"}
]
```

- 语义：全部前置条件满足，主条件才评估阈值；任一不满足 → 本轮按「未越线」处理，走恢复计数（与 ARMS 多条件「且」一致，
  与 `min_request_count` 的「保持态」不同：样本不足是「判不了」，前置不满足是「判了，正常」）。
- 只允许绝对值、单阈值、无级别；`metric_type` 不允许 `no_traffic`，可与主指标相同（ARMS「吞吐 ≤ 1000 且 环比跌 50%」就是同指标）。
  值来自同一次 `service_red`，零额外查询；前置条件的指标若需要慢阈值 / Apdex T，沿用策略级参数。
- 不做「任意满足」、不做条件级比较基准、不做条件级级别合成。监控多指标条件的「锚点维度对齐」在 APM 不需要：所有条件都在同一个
  (service, environment, endpoint, version) 目标上。
- 试算 `verdict` 加 `guard_not_met`，`items[]` 加 `guards: [{metric_type, value, matched}]`；告警 `description` 在有前置条件时写明。

### D4. 触发：N 个周期内 M 次

```text
trigger_after    M，含义不变（1..20）
trigger_window   null | N，M ≤ N ≤ 20；null = 连续 M 次（现状）
```

- `ApmPolicyTargetState` 加 `hit_history`（最长 20 位的 0/1 字符串，最新在末尾）。每次「可判定」的评估推一位；
  `missing_baseline` / `insufficient_samples` / `no_data` 不推（保持态不改历史）。
- 触发：`trigger_window` 为空时沿用 `consecutive_hits ≥ trigger_after`；不为空时 `hit_history[-N:]` 中 1 的个数 ≥ M。
  级别取本轮命中级别（与现状一致，不取历史最高）。
- 恢复仍是「连续 `recover_after` 次不满足（或越过恢复阈值）」；触发后 `hit_history` 清空，避免同一批命中反复触发。
- 试算文案：`trigger_window` 不为空时写「近 N 轮命中 k / M」；草稿没有历史，写「本轮命中 1 / M（N 轮内）」。

### D5. 恢复阈值（滞回）

```text
recovery_threshold   {} | {"comparator": "lt", "value": "600"}
```

- 一条线，作用于告警整体恢复；方向必须与阈值阶梯相反（阶梯已强制同一比较符）。空 = 现状。
- 判定三态：越线 → 命中；越过恢复线 → 计恢复；两线之间 → `hold`：不触发、不计恢复、`consecutive_hits` 不清、活动告警保持，
  快照追加 `info` 点并写 `data_state=hold`。与监控 D5 的 `hold_events` 同义。
- 恢复阈值按结果单位填写：`percent` 比较基准下填变化率，`absolute` 下填指标单位；前端随比较基准切换单位标签，不重算数字。
- 试算 `verdict` 加 `hold`（仅已保存且活动时），草稿带内记 `ok`。

### D6. 组合禁则（serializer 一次拒绝）

| 禁止 | 原因 |
|---|---|
| `slow_*` 缺 `slow_threshold_ms`；`apdex` 缺 `apdex_threshold_ms`；其它指标带这两个参数 | 参数只属于对应指标 |
| `apdex` + 比较符 `gt` / `gte`（absolute 下） | Apdex 只会「低于」告警 |
| `error_count` / `slow_request_count` / `throughput` / `no_traffic` + `min_request_count` | 计数本身是信号 |
| `baseline_days` + `compare_offset_amount` ∉ 2..7 | 留存与成本 |
| `baseline_days` + `compare_value_kind` ∉ {delta, percent} | 与监控一致 |
| `guard_conditions` 超过 2 条、含 `no_traffic`、带比较基准或级别 | 前置只做门槛 |
| `trigger_window` < `trigger_after` 或 > 20 | N 中 M 的 M ≤ N |
| `recovery_threshold` 比较符与阶梯同向；`no_traffic` 带恢复阈值 | 滞回必须反向；无流量恢复就是有流量 |
| `no_traffic` 带任何新字段 | 它的 0 就是信号 |

### D7. 评估延迟（全局）

- 新增环境变量 `APM_POLICY_EVALUATION_DELAY`（默认 `60s`，允许 0～600s）。扫描与试算的所有窗口整体后移：当前窗
  `[T−D−W, T−D]`，对照窗同样减 D。`evaluation_cursor` 仍以 T 为键，不影响幂等。
- 快照点的时间戳记窗口结束时刻 `T−D`，告警详情图与「实际发生时间」对齐；`trigger_at` 记 T（发现时刻）。
- 这是唯一一条改变存量策略行为的决策：告警晚 D 秒，但相对计算不再系统性放大下跌。默认值与 OTel SDK 默认批量导出间隔
  （5s）和 collector 批处理（≤ 10s）留了余量；现场可按采集链路调小。
- 不做策略级延迟：客户不知道该填多少；延迟是采集链路属性，不是策略属性。

### D8. 试算、快照、事件、详情

- 试算 `items[]` 新增 `guards`、`hold`、`guard_not_met` verdict、`baseline_days_used`、`hit_history_text`；顶层带 `slow_threshold_ms` /
  `apdex_threshold_ms` 回显。目标上限 20 不变；`baseline_days` 退回 N 次查询时一次 HTTP 内最多 20 × (1 + N) 次 VT 查询，N ≤ 7。
- 快照点 `data_state` 增加 `hold`；`policy_snapshot` 加 `slow_threshold_ms` / `apdex_threshold_ms` / `guard_conditions` / `trigger_window` /
  `recovery_threshold`；`evaluation_snapshot` 加 `guards`。
- 告警中心副本 `labels` 加 `metric_type` 的新值；告警名称模板变量不新增（后端仍不渲染）。
- 告警详情主趋势：`hold` 点与 `info` 点同色，tooltip 写「恢复带内」；恢复阈值画第二条虚线。

### D9. 表单（`policy-editor.tsx`）

- 第 2 步「指标」改为分组下拉：时延 / 错误 / 慢请求 / Apdex / 吞吐 / 无流量；选慢请求出现「慢阈值 (ms)」，选 Apdex 出现「T (ms)」。
  计数类指标隐藏「汇聚方法」。
- 第 3 步「比较基准」加「近 N 天同窗均值」，随之出现天数（2～7）与 Δ / % 单选。
- 阈值表下方新增「前置条件」（0～2 行：指标 / 比较符 / 值 / 单位），默认折叠，有值时展开；「最低请求数」保持独立一行。
- 「触发条件」从「连续 N 次」改为「N 次 ⟨连续 | 在最近 N 个周期内⟩」两段控件，默认连续。
- 「自动恢复」旁加可选「恢复阈值」，占位「不填则与触发线相同」，单位随比较基准。
- 布局沿用第一批修正后的 152px 标签列与 560px 控件宽；新增控件用 Tailwind `className`，不新增 SCSS Module，不硬编码色值。

## Testing Decisions

只锁外部行为：serializer 接受 / 拒绝、`service_red` 返回字段、`test_query` 的窗口与数值、`_advance_target` 三态与 N 中 M、
试算响应与零副作用、快照字段。不测私有方法调用次数。

后端（沿用 `apps.apm.tests`，本地 Postgres `--reuse-db`）：

- 适配器：`final_stats` 并列全部函数的字符串；有 / 无慢阈值与 Apdex T 时 `count() if` 的出现与否；`baseline_days` 一条查询的
  `_time` 多区间与 `stats by (_time:1d)` 字符串，回填 k 的映射；每个新指标在 `ServiceRed` 上的取值。
- 序列化：D6 每条禁则一个拒绝 + 对应接受；存量 payload 接受且新字段缺省；`p95` / `p99` 旧值不变。
- 评估：七个时延统计量与两个计数的 `_series_value` / `_raw_value`；`apdex` 公式；`baseline_days` 可用天数不足 → `missing_baseline`；
  前置不满足 → 不触发且走恢复计数；`trigger_window` 的 `hit_history` 推进 / 不推进 / 触发后清空；`hold` 三态与 `consecutive_*` 不变；
  评估延迟下两段窗起止精确等于 `T−D−W..T−D` 与再减 offset；`absolute` 旧策略在 D=0 时逐字段与升级前一致。
- 试算：`guard_not_met` / `hold` / `baseline_days_used` / `hit_history_text`；零副作用与越权 404 沿用。
- 快照 / 事件：新 `policy_snapshot` 字段；`hold` 点；告警中心副本 `labels.metric_type` 新值。
- 日志回归：`baseline_days` 退回多次查询失败只记一条 WARNING，带 `failed_stage=baseline`，不含查询正文。

前端（`policy-editor.test.tsx` 等）：

- 分组指标下拉与慢阈值 / Apdex T 的出现；计数类隐藏汇聚方法；前置条件最多 2 行；N 中 M 两段控件的 payload；
  恢复阈值单位随比较基准；`baseline_days` 天数范围；`no_traffic` 不带任何新字段；存量 payload 保存不变。
- `pnpm exec vitest run <相关文件>`、`pnpm exec eslint <改动文件>`、`pnpm type-check`。

验收记录必须附：本机 Docker 底座 VictoriaTraces 上，对同一服务同一时段核对 `latency_avg` / `p50` / `slow_request_count(1000ms)` /
`apdex(500ms)` 与 Explore 页按 Span 手算一致；`baseline_days=3` 一条查询的每桶请求数与三次单独查询一致。

## Out of Scope

- 机器学习异常检测、离群检测、时序预测、Watchdog 式自动策略。
- 查询语言框、任意 AND / OR 表达式、基于其它策略状态的复合策略、「任意满足」。
- 距容量线剩余时间；直方图分位；HTTP 4xx / 5xx 按状态码族单独计数（错误定义仍是 Span 状态）。
- 下游依赖调用（client Span 按 `peer.service` / `db.system`）与实例维度：切片 3 评估成本后另起 change。
- SLO 错误预算燃烧率告警：另起 change（见 Further Notes 待确认）。
- 均值 ± k·σ 的动态区间；周级同窗均值（留存 35 天放不下 4 周 + 窗）。
- 静默期、通知间隔、维护窗、级别抑制（告警中心）。
- 策略级评估延迟。

## Further Notes

### 切片顺序

1. **指标面 + 评估延迟**：D1 十二个指标与两个参数、`ServiceRed` 扩字段、D7 全局延迟、D6 对应禁则、表单分组下拉、试算 / 快照回显、
   VT 实跑核对。旧策略回归先绿。
2. **判定规则**：D4 N 中 M、D5 恢复阈值、D3 前置条件、试算三个新 verdict、表单三段控件。
3. **近 N 天同窗均值**：D2，含半开区间边界验收、可用天数不足判定与退回路径。
4. **文档**：本规格 Status 改 implemented；更新 `specs/capabilities/apm-alerting.md` 长期契约；新建
   `docs/design/product-decisions/apm-policy-calc-methods.md` 决策记忆。

约束：切片 1 的评估延迟是切片 2、3 的前提（否则 N 中 M 与均值对照都在被少算的窗上判）；切片 3 的一条查询验证失败不阻塞切片 1、2 发布。

### 主验收

- 旧策略不改保存，`APM_POLICY_EVALUATION_DELAY=0` 时扫描、事件、快照与升级前逐字段一致；默认 60s 时窗口整体后移且告警详情图时间轴对齐。
- 「P90 > 500ms」「最大时延 > 5s」「错误数 ≥ 100」「慢请求（1000ms）占比 > 10%」「Apdex(500ms) < 0.8」各能建告警，试算值与 Explore 手算一致。
- 「吞吐 ≤ 16.67 req/s 且 相对上一等长窗 < −50%」：半夜吞吐 10 req/s 平稳 → 前置满足但主条件不满足 → `ok`；吞吐从 2000 跌到 800 → 前置不满足 → `guard_not_met`；
  从 30 跌到 10 → 触发。
- `trigger_after=3, trigger_window=10`：10 轮内第 3 次命中触发；连续 2 次命中后 7 轮正常再命中 1 次 → 触发；触发后历史清空。
- 触发 `> 800`、恢复 `< 600`：700 保持 `hold`，`consecutive_recoveries` 不增；550 连续 `recover_after` 次恢复。
- `baseline_days=7, percent`：昨天事故日请求数为 0 被剔除，其余 6 天均值作对照；仅 2 天有数据 → `missing_baseline`。
- `no_traffic` 表单看不到任何新控件，payload 不带新字段。

### 已确认成立的现网事实

- `service_red` 的 `final_stats` 是一条 `stats`，`stats_range` 同形；LogsQL 允许同一管道并列多个聚合函数与 `count() if (...)`。
- `ServiceRed` 已带 `request_count` / `error_count`；错误数指标不需要新查询。
- `_INSTANCE_FIELD`、`_PEER_SERVICE_FIELD`、`_DB_SYSTEM_FIELD` 已在适配器里，下游依赖与实例维度在数据面可行，成本未评估。
- `ApmPolicyTargetState` 一目标一行，`consecutive_hits` / `consecutive_recoveries` / `consecutive_no_data` 已是判定状态的落点。
- 评估窗当前以 `evaluated_at` 为右端，没有任何延迟补偿；`_cursor(evaluated_at)` 是幂等键。
- `ApmSlo` 已有 `objective` / `sli_type` / `evaluation_window`，`ServiceSloQuery` 返回 `budget_remaining`。
- 留存 `APM_TRACE_RETENTION` 默认 35d；`RED_EXACT_DEDUP_WINDOW` 为 1d 只约束单次查询窗长。
- 2026-10-27 本机 Docker 底座 VictoriaTraces（`127.0.0.1:10428`，服务 `demo-storefront` / `local`，入口 Span `kind:=2`）实跑：
  - `stats count(), avg(duration), quantile(0.5, duration), max(duration), count() if (duration:>1000000000), count() if (duration:<=500000000)`
    一条查询全部返回实数（10-21 02:07–02:12：requests 474、avg 164.5ms、p50 82.7ms、max 7056.9ms、slow 1、satisfied 428）。
  - `(_time:[…] or _time:[…] or _time:[…]) … | stats by (_time:1d) count(), avg(duration), quantile(0.5, duration)` 返回三个日桶，
    10-21 桶 474 与单窗一致；10-20 桶 612 对比单窗 610，差额来自闭区间 `[s, e]` 把右边界的 Span 算进去，改半开 `[s, e)` 即可。

### 决策记录

- **指标面扩枚举而不是拆「指标 + 统计量」两字段**：`p95` / `p99` 已被快照、告警中心副本、SLO 引用；分组下拉在表单层解决可读性。
- **慢请求与 Apdex 的阈值放策略级而不是服务级**：APM 目前没有服务级配置实体；同一服务的不同策略可以用不同慢阈值（登录 500ms、报表 3s）。
  若后续服务页需要统一 Apdex T，再升到服务级并让策略默认继承。
- **近 N 天均值不做 σ 区间**：均值已覆盖「单日对照被事故带偏」；σ 需要解释「k 倍标准差」且 7 天样本太少。先看现场反馈。
- **前置条件走「全部满足 + 绝对值」而不是 AND / OR**：ARMS 最佳实践里全部多条件示例都是「绝对下限 / 上限 + 环比」，两条就够；
  与监控多指标条件「只有全部满足、前置条件只做门槛」同一立场。
- **前置不满足走恢复而不是保持**：前置条件是「正常业务量下才看」，不满足就是不在观察范围，告警应当恢复；保持态只留给「判不了」。
- **N 中 M 用位串而不是重查前 N 窗**：APM 每次评估是外部查询，重查 N 窗会把成本放大 N 倍；日志域无状态重查是因为它没有目标状态表。
- **评估延迟做全局而不是策略级**：延迟是采集链路属性；默认 60s 对 OTel 默认导出留了余量。
- **下游依赖与 SLO 燃烧率另起 change**：两者都改目标身份（peer）或引入新实体关联（SLO），不是「计算方式」的叠加。

### 自审结论（2026-10-27）

按 `bklite-ops-product-design` 清单复核本方案：

**Blocker（必须随切片 1 落地）**

- 评估延迟（D7）。没有它，第一批已上线的「相对上一等长窗」在导出延迟明显的环境里会系统性误报下跌；本批所有新判定都建立在被少算的窗上。
  它改变存量行为（告警晚 60s），需要产品确认默认值。

**MVP improvement（本批进）**

- 时延统计量族、错误数、慢请求、Apdex（D1）：零额外查询，覆盖竞品指标面最常用的 80%。
- 前置条件（D3）、N 中 M（D4）、恢复阈值（D5）：ARMS / SkyWalking / 蓝鲸 / Datadog 都有，且都只改判定层。
- 近 N 天同窗均值（D2）：在不引入 ML 的前提下回应「基线」诉求；一条查询的写法已在本机 VT 验证，剩余风险只有区间边界（已定半开）。

**Later**

- 下游依赖调用、实例维度、σ 动态区间、SLO 燃烧率、离群。

**Confirm → 已拍板（2026-10-27，产品授权按推荐方案执行）**

1. 评估延迟默认 60s：**采纳**。New Relic 默认 2 分钟，Datadog 对除法类公式建议 60s，SkyWalking / ARMS / 蓝鲸靠分钟桶天然晚 1～2 分钟；
   60s 是偏快的一档，现场可按采集链路调小。
2. 前置条件不满足走「恢复」：**采纳**。前置条件是「正常业务量下才看」，不满足就是不在观察范围；误恢复风险由主指标自身的无数据告警与
   最低请求数的保持态兜底。
3. 慢阈值与 Apdex T 放策略级：**采纳**。APM 没有服务级配置实体；同一服务不同接口确实需要不同慢阈值。服务级统一值另起 change。
4. SLO 错误预算燃烧率：**不进本批**，列为下一批候选。它是以 SLO 为目标的新策略类型，不是计算方式叠加。
5. 下游依赖调用：**不进本批**。切片 3 完成后按目标上限、试算、快照的扩展成本单独评估。

## 切片 1 验收记录

提交 `aa7b2d9aea`。VictoriaTraces 实跑（本机 Docker 底座，不改 D1～D9）：

- `127.0.0.1:10428`，服务 `apm-demo-shop / demo-storefront`，环境 `local`，入口 Span `kind:in("2","5")`
- 窗 `2026-10-21T02:07:00Z`–`02:12:00Z`：requests 474，`avg(duration)` 164.478ms，VT `quantile(0.5, duration)` 82.749ms，`duration:>1000000000` 的慢请求 1，`duration:<=500000000` 的 satisfied 428，`duration:<=2000000000` 的 within_4t 473，tolerating 45，Apdex `(428 + 45/2) / 474 = 0.9504`
- 手算 nearest-rank 中位数 82.536ms；产品与 Explore 都用 VT quantile
- 临时策略 4 条创建后删除；对「现在」试算是 `no_data`（演示 Span 停在 10-21）。演示策略 `ddbe3441-737c-41c5-bac5-b510d2c6e85f` 未改

现场确认：

- pytest `test_policy_calc_catalog`、适配器、memory、`test_policy_service`、快照、契约：141 passed，1 skipped
- `policy-editor.test.tsx` 21 passed；eslint 通过；提交 hook 里的 type-check 通过
- `APM_POLICY_EVALUATION_DELAY=0` 时窗口与升级前逐字段一致；未设置时默认 60s

## 切片 2 验收记录

提交 `af3db59cd1`。

现场确认：

- 前置条件超过 2 条、含无流量、带多余字段，`trigger_window` 小于 `trigger_after` 或大于 20，恢复阈值与阶梯同向，无流量带新字段，serializer 都拒绝
- N 中 M 忽略样本不足轮次，触发后清空 `hit_history`；恢复带内活动告警保持且快照点 `data_state=hold`；越过恢复线走恢复计数；前置不满足不触发并计入恢复
- 试算 `guard_not_met` / `hold` / 「近 4 轮命中 1 / 2」零副作用
- pytest 判定、策略服务、目录、快照、契约：110 passed，1 skipped
- `policy-editor.test.tsx` 22 passed；eslint 与 type-check 通过
- 本机临时策略 `trigger_window=4`、前置吞吐 `gte 1`、恢复 `lt 50` 创建 201；试算 200，当前窗 `verdict=no_data`；删除 200。演示策略未改
- 连续模式 `trigger_after` 上限仍是 60；只有设置 `trigger_window` 时才要求 M ≤ N ≤ 20

## 切片 3 验收记录

提交 `a54e7d70e3`。

VictoriaTraces 实跑（`baseline_days=3`，半开窗 02:07–02:12，去重路径含 `min(_time) as _time`）：

| 日 | 一条 `stats by (_time:1d)` | 三次单独 `service_red` |
|---|---|---|
| 10-19 | 554 请求，avg 184.347ms | 554，184.347ms |
| 10-20 | 610 请求，avg 137.682ms | 610，137.682ms |
| 10-21 | 474 请求，avg 164.478ms | 474，164.478ms |

现场确认：

- 可用天数 `< ⌈N/2⌉` 记 `missing_baseline`，reason `baseline_days_insufficient`；请求数为 0 或低于最低请求数的天不计入
- 一条查询失败后退回逐日 `service_red`，目标上限 20；退回失败只记一条 `apm` WARNING，`failed_stage=baseline`，不含查询正文
- 去重统计若不保留 `_time`，三个日桶会并成一桶；实现在去重段加上 `min(_time) as _time` 后与三次单独查询逐桶一致
- pytest 本切片与策略回归 75 passed，1 skipped；适配器日桶用例 2 passed
- `policy-editor.test.tsx` 23 passed；eslint 与 type-check 通过
- 表单「近 N 天同窗均值」默认 7 天、变化率，可改成 3 天和变化量
- 本机临时策略 `compare_mode=baseline_days`、N=3、变化率创建后试算 `no_data`（当前窗无 Span），已删除。演示策略未改
