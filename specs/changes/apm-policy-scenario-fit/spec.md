# APM 策略 · 回到 APM 场景（整窗取值、去掉无数据开关、对照窗放开 Δ、窗口 ≥ 频率）

Status: implemented（2026-10-29）

## 实现偏差

- 错误文案写在 `language/zh-Hans.yaml` 与 `language/en.yaml`。仓库没有 `language/zh.yaml`。
- 已发布迁移 `0027_apmpolicy_conditions.backfill_conditions` 在当前模型上不再无条件读 `aggregation`：仅当历史模型仍有该列（`hasattr`）时写入锚点。真实迁移走到 0027 时列还在，行为不变。测试直接调用该函数时模型已是删列之后的状态，否则会抛 `AttributeError`。
- 请求里的 `aggregation / no_data_after / no_data_severity / no_data_alert_name` 在未知字段校验前剔除。DRF 默认会把这些键当成未知字段返回 400，做不到规格里的「忽略且不报错」。
- 响应里 `conditions[]` 若仍残留历史 `aggregation`，由 `to_representation` 去掉该键。没有单独的数据迁移去改 JSON。
- `offset_1h` / `offset_24h` 与 `offset_hours` / `offset_days` 同属对照窗，同样允许 Δ 与 %。
- `slo_burn_rate` 不展示「每 N 分钟评估一次最近 M 分钟」提示。这条策略的评估窗是燃烧长短窗，`metric_window` 不是那个窗。
- 无数据告警样式类 `.noDataAlertName` 仍留在 `event-workspace.module.scss`，已无引用。规格文件清单不含该样式文件。
- 本机 `server/.env` 的 `INSTALL_APPS` 不含 `cmdb`，sqlite 全量迁移会被既有的 `NewSessionEventRelation.event` 挡住。验收因此清空 `INSTALL_APPS`，并加 `--create-db --nomigrations`。`makemigrations apm --check` 在同样清空 `INSTALL_APPS` 后报告 `No changes detected`。
- 上述 sqlite 跑法下仍有 11 个既有失败，与本次契约无关：8 个拓扑接口因 sqlite 不支持 `DISTINCT ON` 返回 500；`test_backfill_table_queries_scale_by_batch_not_release_count` 查询数 162 超过预算；两个迁移测试在 `--nomigrations` 下找不到历史节点。策略相关测试 135 项通过。
- Web：`pnpm exec vitest run src/app/apm` 为 301 通过、1 失败。失败项是 `src/app/apm/services/__tests__/page.test.tsx`「多批 RED 中一批失败只标记该批服务」超时 5000ms，与策略编辑器无关。策略相关 4 个测试文件单独重跑 54 项通过。`pnpm type-check` 通过。`pnpm lint` 的 3 个 error 都在未改文件（`rumBootstrap.ts` 等 `consistent-type-definitions`）；改动文件无新增告警。

产品决策来源：2026-10-29 对 APM / 日志策略「是否照搬监控」的复核。对照监控多指标（`docs/design/product-decisions/monitor-policy-multi-metric.md`）、
APM 长期契约（`specs/capabilities/apm-alerting.md`）与竞品（Datadog APM Monitor、New Relic APM Condition、Elastic APM Rule、SkyWalking Alarm、阿里云 ARMS）后确认：
APM 的数据源是 span，一个评估窗只应算出**一个数**；监控的「汇聚方法 / 无数据告警 / 频率与周期各自独立」是时序引擎概念，不适用于 APM。
决策记忆：`docs/design/product-decisions/apm-policy-calc-methods.md`（已追加本批决策）。

## Problem Statement

1. **汇聚方法二次汇聚了不可加的量。** `DjangoApmPolicyService._aggregate`（`server/apps/apm/services/policies.py`）对非计数指标取 `red.timeseries` 各点的
   avg / max / min / last。`timeseries` 由适配器按 `step = max(15, window/119)` 切桶（`server/apps/apm/adapters/victoriatraces.py` `service_red`），
   5 分钟窗就是 20 个 15 秒桶。于是 p95 = 20 个「桶内 p95」的平均，错误率 = 20 个桶内比率的**不加权**平均，Apdex 同理。
   低流量服务一个桶只有两三个请求，桶内 p95 就是桶内最大值；1 个「1 请求 1 错误」的桶能把整窗 1.7% 的错误率算成 5%。
   适配器已经算好的整窗 `red.p95_ms / red.error_rate / …` 只在 timeseries 为空时才被使用。前端把方法名写成 `AVG_OVER_TIME / MAX_OVER_TIME`，
   这是 MetricsQL 词汇，APM 引擎里不存在。
2. **「无数据告警」和「无流量」指标是同一件事的两个入口。** APM 的无数据就是窗内 span 数为 0，与 `no_traffic` 判定来源相同；
   现在一个场景两套开关、两套告警名和级别。
3. **对照窗（N 小时前 / N 天前）只允许变化率 %。** `_validate_compare` 的 `compare_offset_percent_only`。「p95 比昨天同时段高 200ms」是 APM 最常见的同比表达；
   `previous_window` 与日志侧都已允许 Δ，这里是三域不一致。
4. **检测频率与汇聚周期无交叉约束。** `evaluation_interval` 1～60、`metric_window` 1～1440 各自独立。频率 10 分钟 + 周期 1 分钟会漏掉 90% 的时间。

## 已拍板决策（2026-10-29）

1. APM 策略**没有汇聚方法**。非计数指标的评估值就是整窗 RED 统计值（`_raw_value`）；计数指标维持整窗总数。`timeseries` 只服务告警详情趋势图与试算预览。
   原因：分位数与比率不可加；竞品没有任何一家对 p95 再做子桶汇聚。
2. 去掉策略级「无数据告警」开关（`no_data_after / no_data_severity / no_data_alert_name`），没有流量时的告警用指标「无流量」表达。
   原因：两者判定来源相同，保留 APM 原生词汇。
3. 对照窗 `offset_hours / offset_days` 与 `previous_window` 一样允许 `delta` 和 `percent`；`baseline_days` 不变（Δ / % / σ）。
4. `metric_window ≥ evaluation_interval`，否则保存被拒绝。`slo_burn_rate` 不受此约束（它没有 `metric_window`）。
5. 吞吐单位维持 `req/s`，不改。

明确不做：按子桶 max 的「尖峰检测」、把评估延迟做成策略级、把触发条件改成按时长表达（只补约束与提示文案）、服务级统一慢阈值。

## Solution

### A1 整窗取值

- `ApmPolicy.aggregation`、`ApmAlertMetricSnapshot.aggregation` 两列删除（一支迁移，两条 `RemoveField`）。快照 JSON 里历史点不含该键，无需回填。
- `policies.py`：删除 `_aggregate`；`test_query`、`_compare_baseline_days`、基线逐日、回放、`policy_conditions._guard_value` 全部改用 `_raw_value(policy, red, metric)`。
  `_series_value` 仅用于趋势图 / `_mean_line`，不再参与判定。
- `policy_conditions.py`：`MIRROR_FIELDS` 去掉 `aggregation`；`anchor_from_policy`、`_guard_metric` 不再产出该键；`_same_mirror` 对条件 JSON 中残留的 `aggregation` 键忽略。
- `serializers/control_plane.py`：`Meta.fields` 去掉 `aggregation`；`_normalize_regular` / `_validated_anchor_fields` 不读不写该键，`conditions[]` 载荷里出现时静默丢弃。
- `services/snapshots.py`、`services/metric_snapshots.py`：策略快照与指标快照不再写 / 读 `aggregation`。
- 前端 `web/src/app/apm/events/policies/policy-editor.tsx`：删除 `AGGREGATION_OPTIONS`、`AggregationSelect`、`aggregationDisplayLabel`、
  `ApmMetricConditionEditor` 里的「汇聚方法」行、`DEFAULT_VALUES.aggregation`、`blankExtraCondition().aggregation`、payload 组装中的 `aggregation`。
  `web/src/app/apm/types.ts` 三处 `aggregation` 字段删除。`locales/zh.json`、`en.json` 删除 `apm.policies.aggregation*` 键。
- 回归测试（必须新增）：给定 `ServiceRed`（整窗 `p95_ms=300`、`error_rate=0.017`、`request_count=58`）且 `timeseries` 里各桶 p95 / 错误率明显偏离整窗值，
  断言 p95 / 错误率 / Apdex / 慢请求占比 / 吞吐策略的 `current_value` 等于整窗值；`compare_mode=previous_window` 时 `baseline_value` 亦取整窗值。
  `test_policy_calc_catalog.py` 等现有断言按新口径更新。

### C2 去掉无数据告警开关

- 模型删除 `no_data_after / no_data_severity / no_data_alert_name` 三列（与 A1 同一支迁移）。
- `policies.py`：`_evaluation_threshold` 与状态推进（`consecutive_no_data` 累加后直接 `return None`）去掉 `no_data_after` 分支；`consecutive_no_data` 字段保留给试算 verdict。
  已存在、`threshold.comparator == "no_data"` 的活动告警不在迁移里结束：数据恢复后它们走现有的不命中 → 连续恢复计数 → 自动恢复路径。
- 序列化器 `Meta.fields` 去掉三项；请求里出现这些键由 DRF 忽略。
- 前端：删除「无数据告警」`Switch`、`noDataOpen` 状态、`defaultNoDataAlertName`、三个 `Form.Item`、payload 中三键；`types.ts` 652～654 行三字段删除。
  历史快照 / 告警里 `comparator: 'no_data'` 与 `type: 'no_data'` 的类型联合**保留**（只读旧数据）。
- 指标下拉「无流量」分组文案保持；不再另加提示。

### A3 对照窗放开变化量

- `_validate_compare`：`offset_modes` 允许 `kind ∈ {delta, percent}`；错误键 `error.compare_offset_percent_only` 改名为 `error.compare_offset_kind`，
  文案「N 小时前 / N 天前同窗只能选变化量或变化率」（`language/zh.yaml`、`en.yaml`）。
- `_validate_thresholds` / `_validate_recovery` 对比率指标 Δ 的 `-1..1` 校验已覆盖 offset 模式，不改。
- `metric_snapshots.resolve_result_unit` 与通知 / 详情的 `result_unit` 对 `offset_* + delta` 给出与 `previous_window + delta` 相同的单位（实现时核对，缺则补）。
- 前端：`compare_value_kind` 的 `Radio.Group` 对 `offset_hours / offset_days` 也渲染（选项 Δ / %）；`applyCompareMode` 切到 offset 模式时默认 `percent` 不变；
  `thresholdUnitFor` 已按 `kind` 给单位，无需改。
- `specs/capabilities/apm-alerting.md`「比较基准」一条补上「`previous_window / offset_hours / offset_days` 允许 Δ 与 %」。

### A2 窗口 ≥ 频率

- 序列化器 `validate`：`metric_type != slo_burn_rate` 且 `metric_window < evaluation_interval` → `{"metric_window": error.window_shorter_than_interval}`，
  文案「汇聚周期不能短于检测频率，否则两次评估之间的数据不会被检查」。
- 前端 `metric_window` 的 `Form.Item` 加同规则 validator；「触发条件」下方加一行次级说明：「每 {interval} 分钟评估一次最近 {window} 分钟的数据」（`Form.useWatch` 取值）。

## 数据契约变化

- `ApmPolicy`：删除 `aggregation / no_data_after / no_data_severity / no_data_alert_name`。
- `ApmAlertMetricSnapshot`：删除 `aggregation`。
- `conditions[]`：不再含 `aggregation`；读入含该键的旧值时忽略。
- 策略读写 API：上述字段从响应中消失；请求中出现被忽略（不报错）。
- `compare_value_kind` 在 `offset_hours / offset_days` 下接受 `delta`。

## 改动清单

### server/apps/apm

| 文件 | 改动 |
|---|---|
| `models/control_plane.py` | 删除 `Aggregation` 枚举与 4 个策略列、快照 `aggregation` 列 |
| `migrations/00xx_remove_aggregation_and_no_data.py` | `RemoveField` ×5 |
| `services/policies.py` | 删除 `_aggregate`，统一 `_raw_value`；去掉 `no_data_after` 分支 |
| `services/policy_conditions.py` | `MIRROR_FIELDS`、`anchor_from_policy`、`_guard_metric`、`_guard_value` 去掉汇聚 |
| `services/snapshots.py`、`services/metric_snapshots.py` | 不写 / 读 `aggregation`；`resolve_result_unit` 覆盖 `offset_* + delta` |
| `serializers/control_plane.py` | 字段删除、`_validate_compare` 放开 Δ、新增窗口 ≥ 频率校验、条件载荷丢弃 `aggregation` |
| `language/zh.yaml`、`en.yaml` | `error.compare_offset_kind`、`error.window_shorter_than_interval` |
| 测试 | 新增整窗取值回归；`test_policy_calc_catalog.py`、`test_policy_conditions.py`、`test_policy_judgment.py`、`test_policy_api.py`、`test_policy_snapshot_lifecycle_service.py`、`test_policy_contract_views.py`、`test_policy_baseline_days.py`、`test_policy_scope.py`、`test_policy_slo_burn.py`、`test_victoriatraces_adapter.py` 按新契约更新 |

### web/src/app/apm

| 文件 | 改动 |
|---|---|
| `events/policies/policy-editor.tsx` | 删除汇聚方法与无数据告警 UI 及 payload；offset 模式显示 Δ / %；窗口 ≥ 频率校验与提示 |
| `types.ts` | 删除 `aggregation`（598 / 640 / 880 行）、`no_data_*`（652～654 行） |
| `locales/zh.json`、`en.json` | 删除 `apm.policies.aggregation*`、`apm.policies.noData*`；新增 `apm.policies.windowShorterThanInterval`、`apm.policies.evaluationHint` |
| `events/policies/__tests__/*.test.tsx`、`events/alerts/__tests__/*.test.tsx` | 夹具去掉 `aggregation / no_data_*`；补 offset + Δ 与窗口校验用例 |

### 文档

- `specs/capabilities/apm-alerting.md`：长期契约补「非计数指标评估值为整窗 RED 统计值，策略没有汇聚方法」「没有策略级无数据开关，无流量用 `no_traffic`」「对照窗允许 Δ / %」「`metric_window ≥ evaluation_interval`」。
- 本文件 Status 改为 implemented 并记录偏差。

## 验收

- Server：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/apm/tests --no-cov` 全绿；`uv run python manage.py makemigrations --check apm` 无待生成迁移。
- Web：`cd web && pnpm exec vitest run src/app/apm` 全绿；`pnpm lint` 对改动文件无新增告警；`pnpm type-check` 通过。
- 低流量回归：整窗 58 请求 1 错误、20 个桶里 19 个 0 错误 1 个 100% 错误时，错误率策略 `current_value == 1/58`（保留 6 位），不是 0.05。
- p95 策略 `current_value == red.p95_ms`，与各桶 p95 无关；`compare_mode=offset_days + delta` 可保存并按 ms 差值比较。
- 保存 `evaluation_interval=10, metric_window=5` 被拒绝并返回 `metric_window` 字段错误；`slo_burn_rate` 不受影响。
- 策略编辑器不再出现「汇聚方法」「无数据告警」；旧策略打开 / 保存不报错。
