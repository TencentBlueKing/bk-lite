# APM 告警计算方式丰富：相对计算 + 试算

Status: ready

需求来源：CTeam `p398_716`【APM】告警计算方式丰富：相对计算 + 试算。
Monitor 侧同题 change 见 `specs/changes/monitor-alert-calc-enrichment/spec.md`（已落地），
本 spec 沿用它的用户语义与文案，不复用它的 MetricsQL 编译与业务表；APM 告警独立模型见
`specs/capabilities/apm-alerting.md`。

## Problem Statement

腰部客户在 APM 策略里只能写「错误率 > 5%」「P95 > 200ms」这类固定水位。发布窗口、早高峰、潮汐流量都会被当成故障。客户真正要说的是「比刚才多了 3 个百分点」「比 1 小时前同窗高 50%」，而且保存前要先知道这条策略这一轮会不会响。

现状（`server/apps/apm/services/policies.py`、`web/src/app/apm/events/policies/policy-editor.tsx`）：

- 指标类型 `error_rate / p95 / p99 / throughput / no_traffic`，汇聚 `avg / max / min / last`，只比当前窗绝对值。P95 / P99 已是指标类型，不需要 Monitor 那种分位汇聚。
- `test_query` 只查一段 `metric_window`，没有对照窗。
- 策略页右侧「预览」自动跑 `POST /apm/policies/preview/`，只画当前曲线并给第一个目标的当前值是否越线，回答不了「会不会建告警」，也不逐目标给结论。
- 低流量下错误率百分比失真：窗内 2 个请求 1 个失败就是 50%，没有最低样本门。

## Solution

策略仍是三句叠加，不是互斥下拉：

| 用户要说的 | 表单位置 | 字段 | 现状 |
|---|---|---|---|
| 看哪个数 | 指标类型 + 汇聚方式 | `metric_type` + `aggregation` | 已有，不动 |
| 相对谁 | 告警条件 · 比较基准 | `compare_mode` + `compare_value_kind` | 新增 |
| 怎么比线 | 多级阈值 / 连续触发 / 连续恢复 | `thresholds` + `trigger_after` + `recover_after` | 已有，不动 |
| 够不够数 | 告警条件 · 最低请求数 | `min_request_count` | 新增 |

扫描、预览、试算共用 `test_query` 一条评估路径：对每个目标查两段等长 RED（当前窗、平移窗），用现有汇聚各得一个数，再算 Δ 或 %。缺对照、对照为 0、样本不足统一「本轮不触发、不恢复、不计无数据 + 原因」。策略页新增独立「试算」按钮，只读复用评估，不落 Alert / Event / 快照 / 通知 / 告警中心。

### 竞品覆盖参照（只做能力覆盖与术语输入，不照搬架构）

| 能力 | Datadog APM Monitor / Change Alert | New Relic NRQL | Grafana Alerting | Elastic APM Rules | SkyWalking | 本方案 |
|---|---|---|---|---|---|---|
| 相对上一窗 Δ / % | Change alert：absolute / percentage change，compared to N min / hours / day before | 无内置，靠 NRQL `COMPARE WITH` | 无内置，靠 PromQL `offset` | 无 | 无 | 进：相对上一等长窗 Δ / %；1h / 24h 前同窗 % |
| 延迟分位 | p50～p99 / max 可选 | percentile() | 看数据源 | P95 / P99 / avg | 看 OAL | 已有 P95 / P99 指标类型，不加第二套 |
| 最低样本门 | Require a minimum of N hits over the evaluation window | 无 | 无 | 无 | 无 | 进：`min_request_count`，默认 20，只对错误率 / P95 / P99 |
| 保存前试算 | 编辑页预览图 + Test notifications | Preview chart | 规则编辑页 Preview 返回逐 series 的 Firing / Normal / NoData | 无 | 无 | 进：逐目标 verdict 表（Grafana 形态），不发通知 |
| 连续 N 次 | 有（evaluation delay / recovery） | 有 | For 持续时长 | 有 | `count` within `period` | 已有 `trigger_after / recover_after` |
| 自动基线 / 异常检测 | Anomaly monitor | Baseline alert | ML | Anomaly（ML job） | 无 | 不进 |
| 日历对齐「昨天」 | day before | — | — | — | — | 文案用「24 小时前同窗」 |

Datadog 的「最少 N hits」是唯一把低流量失真当成一等问题的竞品，本方案采纳为独立门。

### 能力清单

进方案：

| 能力 | 槽位 | 实现依据 |
|---|---|---|
| 已有：五类指标、四种汇聚、多级阈值、连续 N、无数据 | 保持 | 现扫描链 |
| 相对上一等长窗 Δ / % | 比较基准 | 第二次 `service_red`，窗口向前平移 `metric_window` |
| 1 小时 / 24 小时前同窗 % | 比较基准 | 第二次 `service_red`，平移 1h / 24h，窗长不变 |
| 最低请求数 | 告警条件 | `ServiceRed.request_count` |
| 试算 | 独立按钮 | 只读复用 `test_query`，逐目标 |
| 当前值 / 对照值 / 比较值进事件、快照、告警详情 | 展示 | 扩 `PolicyQueryResult` |

不进表单：7d / 30d 同窗、近 4 周均值、距容量线剩余时间、标准差 / 速率 / 变化次数、Watchdog 式异常检测 / 离群、任意 AND/OR、PromQL / LogsQL 框、第二套 P95 汇聚。

`offset_24h` 依赖 VictoriaTraces 留存 ≥ 24h + 窗长；留存不足按缺对照处理并在预览 / 试算写明原因。

## User Stories

1. 作为现场运维，我想选「相对上一等长窗」并用 Δ 或 % 比线，表达「错误率比刚才高 3 个百分点」「P95 比刚才高 50%」。
2. 作为现场运维，我想选「1 小时前同窗 / 24 小时前同窗」并用 % 比线，让早高峰不再被当成故障。
3. 作为现场运维，我想给错误率、P95、P99 设最低请求数，低流量窗口不评，不被 50% 的假错误率吵醒。
4. 作为现场运维，我想在保存前点「试算」，逐端点 × 版本看到会触发 / 不触发 / 无数据 / 对照缺失 / 样本不足以及当前值、对照值、比较值、命中阈值；试算后告警列表、通知、告警中心没有任何新记录。
5. 作为值班人员，我想告警详情和快照同时显示当前值、对照值和比较值，知道「+50%」是相对谁。
6. 作为既有客户，我不改旧策略就保存，扫描结果与升级前完全一致。
7. 作为售前，我需要表单里不出现查询语言框、不出现「昨天」、不出现第二套 P95。

## Implementation Decisions

### D1. 字段与枚举

`ApmPolicy` 新增字段，缺省对存量策略无感：

```text
compare_mode        absolute | previous_window | offset_1h | offset_24h   默认 absolute
compare_value_kind  "" | delta | percent                                  absolute 时必须为 ""
min_request_count   null | 1..100000                                      null = 不限
```

- `previous_window` 允许 `delta` / `percent`；`offset_1h` / `offset_24h` 只允许 `percent`（跨 1h / 24h 的绝对差没有稳定含义）。
- `no_traffic` 只允许 `absolute`，且 `min_request_count` 必须为 null：它的 0 就是信号。
- `throughput` 允许比较基准，`min_request_count` 必须为 null。
- `min_request_count` 只对 `error_rate / p95 / p99`；前端新建默认 20，存量策略为 null。
- `ApmPolicyTargetState` 不加字段；`ApmAlertMetricSnapshot` 不加列，点内加字段（D6）。

### D2. 评估：两段等长窗，同一汇聚

`DjangoApmPolicyService.test_query` 扩为：

```text
current  = service_red(started_at = T - W,            ended_at = T,            include_breakdown=True)
baseline = service_red(started_at = T - W - offset,   ended_at = T - offset,   include_breakdown=True)
offset   = W (previous_window) | 1h (offset_1h) | 24h (offset_24h)
```

- 两段都走 `_aggregate(policy, red)`，对照窗必须也带 `include_breakdown`，否则 `_aggregate` 会退回整窗原始值，与当前窗汇聚口径不一致。
- `compared = cur - base`（delta）或 `(cur - base) / base * 100`（percent）。阈值作用于 `compared`。
- `PolicyQueryResult` 扩字段：`current_value`（当前窗汇聚值）、`baseline_value`、`baseline_series`；`value` 继续表示「拿去比阈值的那个数」，absolute 时 `value == current_value`。下游 `alert.current_value` / `event.value` / 快照 `value` / 告警中心副本 `value` 不改语义。
- `MetricDataState` 扩两个值：`missing_baseline`、`insufficient_samples`。
- `error_rate` 库内 0～1 不变。`delta` 结果仍是 0～1 的比例差（界面按百分点显示 ×100）；`percent` 结果是百分数，不再 ×100。

对照窗结果映射：

| 情况 | `data_state` | 评估行为 |
|---|---|---|
| 当前窗无请求 | `no_data` | 现有无数据路径不变 |
| 当前窗 `request_count < min_request_count` | `insufficient_samples` | 保持（D3） |
| 对照窗无请求、留存不足、或对照窗 `request_count < min_request_count` | `missing_baseline` | 保持（D3） |
| `percent` 且 `baseline_value == 0` | `missing_baseline`（reason `baseline_zero`） | 保持（D3） |
| `delta` 且 `baseline_value == 0` | `available` | 正常比较（0 → 5% 就是 +5 个百分点） |

每个目标的 VictoriaTraces 查询从 1 次变成 2 次；运行时目标上限仍是 `MAX_POLICY_TARGETS = 100`，单次 `evaluate` 上限 200 次查询。对照窗不需要 `top_endpoints`，`ServiceMetricQuery` 加 `include_endpoints: bool = True`，对照窗传 `False`，避免每个目标多两次端点统计。

`offset_24h` 的对照窗长度 ≤ `metric_window` ≤ 1440 分钟，仍落在 `RED_EXACT_DEDUP_WINDOW` 精确去重路径内。

### D3. 判定：保持态

`_advance_target` 对 `missing_baseline` / `insufficient_samples`：

- 不改 `status`、`current_severity`、`active_alert_id`；`consecutive_hits` / `consecutive_recoveries` / `consecutive_no_data` 全部不增不清。
- 不产生 Event；若已有活动告警，快照追加一个 `info` 点，`data_state` 写明原因（D6）。
- `evaluation_cursor` 照常推进，避免重复扫描。

与 Monitor 「缺对照行不进任何一类，活动告警保持」语义一致。`no_data` 路径只看当前窗，不感知比较基准。

### D4. 组合禁则（serializer 一次拒绝）

| 禁止 | 原因 |
|---|---|
| `compare_mode = absolute` 且 `compare_value_kind != ""` | 没有对照不能选 Δ / % |
| `offset_1h` / `offset_24h` + `delta` | 跨窗绝对差无稳定含义 |
| `no_traffic` + 非 `absolute` | 0 就是信号 |
| `no_traffic` / `throughput` + `min_request_count` | 门只对错误率、时延 |
| `percent` 下 `error_rate` 阈值套 0～1 范围 | 现 `_validate_thresholds` 的 0～1 校验只在 `absolute` 生效；`delta` 改为 -1～1；`percent` 只要求有限 |
| 未知字段 | 现有 `to_internal_value` 已拒绝，新字段要加进 `Meta.fields` |

多级阈值单调性、同一比较符的校验不变。

### D5. 试算

新增内部端点 `POST /apm/policies/dry-run/`（`detail=False`），不扩 `preview`，也不复用 `test-query`（后者只评第一个目标）。

- payload 与保存同源，先过同一 serializer 与 D4 禁则；可选 `policy_id` 表示在已保存策略上试算。
- 权限 `policies-Operate`，与 `preview` 相同；服务可见性走 `_visible_service` fail-closed；带 `policy_id` 时该策略必须在当前组织可见，否则 404。
- 用 `ApmPolicy(service=..., **values)` 内存构造，逐目标调 `test_query`（只读）。不碰 `ApmPolicyTargetState`、不写 Alert / Event / 快照 / outbox、不投递、不推进 `evaluation_cursor`。
- 目标上限 20（`_targets` 顺序取前 20），超出 `truncated: true` 并返回 `total_targets`；一次 HTTP 内最多 40 次 VictoriaTraces 查询。表单选中的端点优先包含。
- `trigger_after > 1` 时，草稿没有连续计数，命中只能写「本轮命中 1/N，现网不会建告警」；带 `policy_id` 时用该目标 `consecutive_hits + 1` 填 k。
- 带 `policy_id` 且目标 `status = active`：本轮不命中 → `would_recover`（附「需连续 recover_after 次」）；命中更高级别 → `would_escalate`。草稿不评恢复。
- 返回：

```json
{
  "evaluated_at": "...",
  "compare_mode": "previous_window",
  "compare_value_kind": "percent",
  "result_unit": "percent",
  "total_targets": 36,
  "truncated": true,
  "items": [
    {
      "endpoint": "GET /api/orders",
      "version": "",
      "verdict": "would_trigger | ok | would_recover | would_escalate | no_data | missing_baseline | insufficient_samples",
      "current_value": "0.062",
      "baseline_value": "0.041",
      "compared_value": "51.2",
      "request_count": 318,
      "matched_threshold": {"severity": "error", "comparator": "gt", "value": "50"},
      "reason": "本轮命中 1/3，现网不会建告警"
    }
  ]
}
```

- `TelemetryStoreUnavailable` 按现有 `telemetry_error_payload` 返回 503。其他失败只记一条 WARNING（`exc_info=True`），带 `policy_id`（草稿为空）、`failed_stage`、`error_type`，不记查询正文和响应体；对外抛不带 traceback 的 `BaseAppException`。

### D6. 快照、事件、告警详情

- `ApmAlertMetricSnapshotStore.record` 点内新增 `current_value`、`baseline_value`、`result_unit`；`value` 仍是比较值。`unit` 列在 `get_or_create` 时按 `resolve_result_unit(policy)` 写：`percent` → `percent`；`delta` / `absolute` 沿用指标单位。
- `ApmEventSnapshotStore.stage` 的 `policy_snapshot` 加 `compare_mode / compare_value_kind / min_request_count`；`evaluation_snapshot` 加 `current_value / baseline_value / result_unit`；`pending_payload.series` 加 `baseline_series`。
- `_record_event` 的 `description` 在非 `absolute` 时写「当前 X，对照 Y，变化 Z」；告警中心副本 `payload.labels` 加 `compare_mode`。
- `alert_name` 模板变量不动：后端当前不渲染 `${...}`（只存库并进 `policy_snapshot`），本 change 不新增渲染器，也不在前端变量列表里新增 `${baseline_value}`。
- 告警详情主趋势：`percent` 下 Y 轴按 `result_unit` 画，并叠对照线；点 tooltip 显示当前值 / 对照值。

### D7. 表单与页面（`policy-editor.tsx`）

- 「告警条件」里阈值上方新增「比较基准」Select：当前值（默认）/ 相对上一等长窗 / 1 小时前同窗 / 24 小时前同窗。选相对上一等长窗再出现「变化量 Δ / 变化率 %」Radio；选同窗固定 %。`no_traffic` 隐藏整组。
- 阈值单位随结果单位变：`error_rate + absolute` → `%`（现有 ×100）；`error_rate + delta` → `个百分点`（×100）；任意指标 `+ percent` → `%`（不换算）；时延 / 吞吐 `+ delta` → 原单位。`thresholdToEditorValue` / `normalizeThresholds` 按 `(metric_type, compare_value_kind)` 决定是否 ×100。
- 「最低请求数」InputNumber 放阈值下方，只对 `error_rate / p95 / p99` 出现，新建默认 20，可清空为「不限」，Tooltip 写明「本窗请求数低于该值时不评，试算记为样本不足」。
- 右侧预览仍叫预览：非 `absolute` 时叠画当前曲线与对照曲线（`baseline_series`），阈值线按结果单位；状态文案增加对照缺失 / 样本不足。
- 预览旁新增「试算」按钮（独立于自动刷新），结果以表格展示：目标、结论 Tag、当前值、对照值、比较值、请求数、命中阈值、说明；`truncated` 时顶部提示「共 N 个目标，只试算前 20 个，请在端点里缩小范围」。
- 布局用 Tailwind `className`，沿用现有 AntD 组件与 `styles.*` 结构；不新增 SCSS Module，不硬编码色值。`ApmPolicyInput` / `ApmPolicyQueryResult` 类型同步扩字段。

## Testing Decisions

只锁外部行为：serializer 接受 / 拒绝、`test_query` 两段窗参数与比较值、`_advance_target` 保持态、试算响应与零副作用、快照与事件字段。不测私有方法调用次数。

后端（沿用 `apps.apm.tests` 既有 pytest + sqlite + mocker 风格）：

- serializer：D4 每条禁则一个拒绝用例 + 对应合法组合一个接受用例；存量 payload（无新字段）接受且缺省 `absolute / "" / null`。先例：`test_policy_api.py`、`test_policy_contract_views.py`。
- 评估：`previous_window` 两段窗的 `started_at / ended_at` 精确等于 `T-2W..T-W` 与 `T-W..T`；`offset_1h` / `offset_24h` 平移正确且窗长不变；对照窗 `include_breakdown=True, include_endpoints=False`；delta / percent 数值；`baseline == 0` 下 percent → `missing_baseline`、delta → 正常；`request_count < min` → `insufficient_samples`；`absolute` 路径只查一次且结果与升级前逐字段一致。先例：`test_policy_service.py::test_metric_type_value_mapping`。
- 判定：`missing_baseline` / `insufficient_samples` 下 `consecutive_*` 不变、无 Event、活动告警保持、`evaluation_cursor` 推进；`no_data` 路径不受 `compare_mode` 影响。先例：`test_policy_service.py::test_firing_policy_does_not_recover_when_metric_window_has_no_samples`。
- 试算：草稿与 `policy_id` 两种入口；越权服务 / 策略 404；七种 verdict 各一；调用前后 `ApmAlert` / `ApmEvent` / `ApmAlertMetricSnapshot` / `ApmEventSnapshot` / `ApmAlertOutbox` 计数不变、`ApmPolicyTargetState` 未创建或未变、通知 dispatcher 未被调用；目标 > 20 时 `truncated` 与 `total_targets`；`trigger_after > 1` 文案。先例：`test_policy_contract_views.py::test_policy_preview_queries_real_adapter_without_persisting_a_policy`。
- 快照与事件：点含 `current_value / baseline_value / result_unit`；`policy_snapshot` / `evaluation_snapshot` 新字段；告警中心副本 `labels.compare_mode`。先例：`test_policy_snapshot_lifecycle_service.py`。
- 日志回归：试算失败路径只产生一条 WARNING，模板与独立参数校验，查询正文 / VT 响应哨兵不出现在任何等级日志。

前端（沿用 `web/src/app/apm/events/policies/__tests__/policy-editor.test.tsx`）：

- 保存 payload：各组合字段正确；`error_rate` 在 absolute / delta 下 ÷100、percent 下不换算；`no_traffic` 不带比较字段；`min_request_count` 只对三类指标写入，清空为 null。
- 比较基准切换时阈值单位标签与 Radio 可见性。
- 试算结果表渲染各 verdict、`truncated` 提示、连续 N 次文案。
- `pnpm lint` 与相关 `pnpm test:*`；改布局后 `pnpm type-check`。

验收记录必须附：本机 Docker 底座 VictoriaTraces 上对同一服务跑 `previous_window percent` 与 `offset_24h percent`，核对对照窗请求数与 Explore 页同一时段一致。

## Out of Scope

- 7d / 30d 同窗、近 4 周均值、距容量线剩余时间、标准差 / 速率 / 变化次数、第二套 P95 汇聚。
- 异常检测、离群、任意 AND/OR 复合条件、日历对齐「昨天 / 上月」。
- 跨组织 Trace 按 Span 裁剪的图语义（不可见节点替换为不透明远端节点、跨边标 `scope_cut`）。详情接口当前已先裁 Span 再返回（`trace_access.filter_detail`），列表已滤后分页；补图语义另起 change，不与本 change 抢工时。
- 三域公共扫描库或 `calc_mode` 公共模型。
- 试算做成 24 小时历史回放。
- 滞回（独立恢复阈值）、无数据双窗：APM 已有 `recover_after` 连续恢复，本轮不加。
- 策略评估 ScanRun / WorkItem、Outbox fencing token 等架构项（见 `docs/design-docs/apm-module-architecture-analysis.md`）。

## Further Notes

### 切片顺序

1. **比较基准**：D1 字段与迁移、D2 两段窗评估与 `PolicyQueryResult` 扩字段、D4 禁则、D6 快照 / 事件字段、D7 比较基准表单与预览叠对照、旧策略回归、VT 实跑确认。
2. **最低请求数**：`min_request_count` 字段、`insufficient_samples` 状态、D3 保持态、表单。
3. **试算**：端点、权限、七种 verdict、零副作用、目标上限、页面按钮与结果表。

约束：切片 3 必须与切片 1 同一发布，相对计算没有试算不算可上生产；切片 2 很小，与切片 1 抢工时时并入切片 1。

### 主验收

- 旧策略不改保存，扫描、事件、快照与升级前逐字段一致。
- 本窗错误率 6%、上一窗 4%：Δ = +2 个百分点，% = +50；上一窗无请求则不建告警、不恢复、不计无数据，试算写「对照缺失」而不是「+100%」。
- 本窗 12 个请求、最低 20：不评，试算写「样本不足」；活动告警保持。
- `no_traffic` 策略表单看不到比较基准和最低请求数，payload 不带这些字段。
- 试算后 `ApmAlert` / `ApmEvent` / 两类快照 / outbox 均无新记录，`ApmPolicyTargetState` 未变；越权服务 404。
- 表单无查询语言框、无「昨天」、无第二套 P95；文案为「N 小时前同窗」。

### 已确认成立的现网事实

- `test_query` 是纯读取，`evaluate` 才写状态；试算直接复用无需拆分。
- `_aggregate` 依赖 `red.timeseries`，对照窗必须也带 `include_breakdown`。
- `ServiceRed.request_count` 已返回，最低请求数门不需要新查询。
- `ApmPolicySerializer.to_internal_value` 对未知字段直接拒绝；新字段必须进 `Meta.fields`。
- `_targets` 已把目标封顶 100；评估查询翻倍后上限 200 次。
- Trace 详情已按 Span 裁剪后返回（`filter_detail`），不存在「任一 Span 可见即全量返回」。
- 后端不渲染 `alert_name` 模板变量；`ApmAlertMetricSnapshotStore.record` 对非 `no_data` 且无 Event 的点统一写 `info`，新状态点自然落为 `info` + `data_state`。
- `visible_organization_ids`（`services/access.py`）与 `ApmPolicyViewSet._visible_service` 已存在，试算端点直接复用。

### 决策记录

- 对照用第二次 RED 查询而不是把 Monitor 的 `offset` 编译搬过来：APM 数据面是 VictoriaTraces LogsQL 流式聚合，没有 MetricsQL offset；两段窗同一汇聚最直观，也不引入新查询语法。
- `offset_1h` / `offset_24h` 只给 %，`previous_window` 才给 Δ：跨窗绝对差对错误率、时延都没有稳定业务含义。
- 最低请求数做成独立字段而不是第四种比较基准：它回答「够不够数」，与「相对谁」正交；参照 Datadog「minimum N hits」。
- 最低请求数新建策略默认 20 并默认开启，存量策略 null 不限（产品确认 2026-10-27）：档位未拍板不挡变化量 / 同窗上线，后续只改前端默认值。
- 试算目标封顶 20：试算是人在等的 HTTP 请求，不能像扫描那样顺序跑 100 × 2 次外部查询。
- `value` 字段语义不变（比阈值的数），新增 `current_value` / `baseline_value`：避免改 Alert / Event / 告警中心副本的既有字段含义。

## 切片 1 验收记录

VictoriaTraces 实跑（本机 Docker 底座，不改 D1～D7）：

- 容器 `bk-lite-apm-apm-victoria-traces-1`，`127.0.0.1:10428`
- 最近一条 Span 在 `2026-10-21T02:12:00Z`，近 24 小时没有新 Span，所以窗取这段末尾，而不是「现在」
- 服务 `apm-demo-shop / demo-storefront`，环境 `local`，汇聚窗 5 分钟
- 对照窗走策略路径（`include_breakdown=True`、`include_endpoints=False`）；Explore 对照是同一时段再查一次 `include_endpoints=True`。请求数一致

| 窗 | 时段 (UTC) | 请求数 | 错误率 |
|---|---|---|---|
| 当前窗 | 02:07–02:12 | 474 | 0.111814 |
| 上一等长窗 | 02:02–02:07 | 596（Explore 同为 596） | 0.125839 |
| 24 小时前同窗 | 10-20 02:07–02:12 | 610（Explore 同为 610） | 0.113115 |

变化率：相对上一等长窗约 -11.15%；相对 24 小时前同窗约 -1.15%。

现场确认（不改写 D1～D7 原文）：

- `min_request_count` 与比较基准写在同一条迁移 `0020_apmpolicy_compare_baseline`，没有第二条迁移。
- 切换比较基准不重算已经填在输入框里的阈值数字。`error_rate + delta` 编辑范围是 -100～100（库存 -1～1）；`percent` 不再套 0～100 的上限。
- `no_traffic` 保存 payload 不带 `compare_mode` / `compare_value_kind` / `min_request_count`，而不是送缺省值。
- 告警详情在 `result_unit=percent` 时，评估值和阈值走变化率轴，不再因为绝对值 ≤ 1 而 ×100；当前值和对照值放到第二条 Y 轴，按指标展示单位画。绝对比较仍是原来的三条序列（评估值 / 当时阈值 / 生命周期事件）。点 tooltip 用现成的轴 tooltip，靠多出来的序列名带出当前值和对照值，没有改共享图表组件。

## 切片 2 验收记录

现场确认（不改写 D1～D7 原文）：

- 新建表单最低请求数默认 20；已保存策略没有该值时回显为空（不限），清空后保存 `null`。只对错误率、P95、P99 写入。
- `request_count < min` 记 `insufficient_samples`，不查对照窗；`consecutive_*` 不动、不产生 Event、活动告警保持，`evaluation_cursor` 仍推进。`min_request_count` 为空表示不限。
- 门与比较基准正交：`absolute` 的错误率 / P95 / P99 策略同样受门控制（评审修正，用例 `test_request_count_gate_applies_to_absolute_threshold_too`）。

## 切片 3 验收记录

现场确认（不改写 D1～D7 原文）：

- 试算是内部 `POST /apm/policies/dry-run/`，权限与 preview 相同（`policies-Operate`），不进 OpenAPI 网关。`policy_id` 在进 serializer 之前取出，避免被未知字段拒绝。
- 已保存且活动、本轮命中但级别不高于当前级别时，verdict 为 `ok`，`matched_threshold` 仍带回命中的阈值。草稿不评恢复。
- 试算失败不向外抛 `BaseAppException`：视图自己打一条 `apm` WARNING，并用代理异常带上原始 traceback，异常消息只保留类型名，避免查询正文进日志；响应是 `{data: {}, result: false, message: 试算失败}`。`TelemetryStoreUnavailable` 仍走原来的 503，不打这条 WARNING。请求超过 1 秒时，计时中间件可能另打一条 Slow Request，与试算失败无关，回归只锁定 `apm` logger 的这一条 WARNING。
- 同级活动命中记 `ok` 是本切片的判定取舍：规格只写了更高级别升为 `would_escalate`，同级或更低沿用「未构成升级」。
