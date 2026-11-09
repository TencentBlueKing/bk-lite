# 日志聚合策略 · 阈值阶梯（同一个数、多档阈值、一条告警取最高档）

Status: implemented（2026-10-29）

## 实现偏差

- `LADDER_OPS` 用 `frozenset`，与同文件常量写法一致。
- 只升不降的落库断言在 `test_policy_scan_db.py`（`create_events` 需要数据库）。`test_policy_scan_pure.py` 锁定档位比较和 `level_rank`。跨窗用例传入 `cursor_time`，否则无游标时会把上一窗事件当成同一次执行的旧事件复用。
- 旧条件的扫描结果不写入 `thresholds` 键，通知正文与升级前一致。显式阶梯才追加「级别」行和「> 200（严重）」。`${level}` 只在显式阶梯时改成命中档；分组字段名叫 `level` 时仍以分组值为准。
- 新窗升级把 `alert.notice` 置回未通知，新事件本身未通知；同一次执行里覆盖已有事件时才清该事件的 `notified / notice_result / notice_retry_count`。更早窗口已通知的事件保持原样，避免补偿任务重发旧窗。
- 编辑器读入旧策略时，若调用方传入 `alert_level`，会收成一档再展示。从编辑器再次保存会写出这一档。未经编辑器打开的存量策略不会被改写。单参数 `normalizeCondition` 不合成 `thresholds`。
- 新建条件的运算符下拉仍是等于、不等于、大于、小于四项。后端接受 `>=` / `<=`，已保存的这两档运算符会在下拉里回显。
- 本机 `server/.env` 的 `INSTALL_APPS` 不含 `cmdb`，sqlite 全量迁移又会被既有的 `NewSessionEventRelation.event` 挡住。验收测试因此清空 `INSTALL_APPS`，并加 `--create-db --nomigrations`。这是既有环境限制，不是本次契约变化。

产品决策来源：2026-10-29 对日志聚合策略「级别」单选的分析。对照监控多指标（`docs/design/product-decisions/monitor-policy-multi-metric.md`）、
APM 策略（`specs/capabilities/apm-alerting.md`）与竞品（阿里云 SLS 分条件严重度、腾讯云 CLS 三级阈值、Datadog Log Monitor warning / alert、
New Relic warning / critical、Elastic 传统 Log Threshold 单级别、Grafana Loki 单阈值）后确认：
日志聚合算出来的是一个数，级别应是这个数的轻重，而不是整条策略一个固定值。
条件模型沿用 `docs/design/product-decisions/log-policy-calc-methods.md`（函数 × 比较方式 × 对照），本次在条件内加阈值阶梯。
决策记忆：实现完成后追加到 `docs/design/product-decisions/log-policy-calc-methods.md`。

## Problem Statement

日志聚合策略的条件是「函数 × 比较方式 × 一个阈值」，级别是策略级 `Policy.alert_level` 三选一（`web/src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx` 第 349 行），
扫描时每个事件直接写这个值（`server/apps/log/tasks/services/policy_scan.py` `aggregate_alert_detection`）。

现场要配「错误超过 10 条警告、超过 50 条错误、超过 200 条严重」只能建三条策略：查询、分组、样本、通知配三遍，同一分组同时躺三条告警。
监控、APM 都是同一个数挂三档阈值，日志是唯一例外。`Alert.level` 的 verbose_name 本来就是「最高告警级别」，模型层已有多级语义。

关键字策略是「命中即告警」，没有可分档的数，保持单选级别不动。

## 已拍板决策（2026-10-29）

1. 活动告警级别**只升不降**：升级覆盖并重新通知；降级时告警级别保持，不重置通知；`Event.level` 仍记本窗真实命中档。
   原因：日志告警人工关闭、不做恢复状态机；若级别跟随当前值回落，计数在档位边界来回穿越会反复重通知，日志侧没有恢复阈值压抖动。
2. `and` 模式下各条件启用的级别集合**必须一致**；`or` 模式不限制。
   原因：`and` 取最轻一档，某条件缺档会让其他条件的高档永远命不中（监控决策记忆里换成「按级别分行」格子的同一原因）。门槛式条件可三档填同一个值。

## Solution

- 阈值阶梯放进条件：`conditions[].thresholds = [{level, value}]`，1～3 项，`op` 条件内共用。
- 单条件命中档取最高；`and` 取各条件命中档最轻一档，`or` 取命中条件最高档。
- 聚合策略隐藏页底「级别」单选，级别在条件卡「触发」行按档填写；关键字策略不变。
- 试算、通知、告警详情、`${level}` 随契约带命中档。
- 无模型列、无迁移。`Policy.alert_level` 列保留，聚合策略由后端推导为条件里启用的最高档。

明确不做：自动恢复 / 恢复阈值（滞回）/ 级别回落通知；关键字多档；按级别路由通知渠道；每级独立运算符；`info` 档；监控式「级别 × 条件」二维格子。

## 数据契约

```json
{
  "func": "count", "field": "_msg",
  "compare": {"kind": "absolute"},
  "op": ">",
  "thresholds": [
    {"level": "warning",  "value": "10"},
    {"level": "error",    "value": "50"},
    {"level": "critical", "value": "200"}
  ],
  "value": "10"
}
```

- `thresholds` 为权威字段。`level ∈ {warning, error, critical}`（与 `web/src/app/log/hooks/event.ts` `useLevelList`、监控 `CANONICAL_LEVELS` 一致；`AlertConstants.LEVEL_INFO` 不开放）。
- `value` 保留，镜像最轻一档的阈值，供旧读取方与告警详情只读摘要继续工作。
- 兼容读入：条件没有 `thresholds` 时视为 `[{level: policy.alert_level, value: condition.value}]`。
- `aggregate_result.conditions[]`（事件 `raw_data`、快照、试算）扩展：`thresholds: [{level, value, matched}]`、`level`（本条件命中档或 `null`）；原有 `op / threshold / matched` 保留，`threshold` 取命中档阈值，未命中取最轻一档。
- `aggregate_result.level`：本行合成级别。
- `Policy.alert_level`：聚合策略由 `PolicySerializer` 推导为所有条件启用级别的最高档；关键字策略仍由用户选。

## 判定语义

- 单条件：对同一个算出的 `value` 按 `op` 逐档比较，命中档取最高；`matched = 命中档非空`。
- `and`：全部条件 `matched`，级别 = 各条件命中档中最轻；`or`：任一 `matched`，级别 = 命中条件中最高。
- `trigger_count` 的 streak 只看是否命中，不看级别；`_apply_streak` 不改。
- `=`、`!=`、`in`、`nin` 及非数值比较只允许一档。
- 旧路径 `_check_rule_conditions_legacy` 不改，仍按策略 `alert_level`。

## 校验（`PolicySerializer._validate_aggregate_condition` 为准，前端同规则预检）

| 规则 | 说明 |
|---|---|
| 级别合法、不重复、至少一档 | |
| 阈值为有限数 | 复用 `_is_finite_number` |
| 阶梯严格单调 | `>` / `>=`：warning < error < critical；`<` / `<=`：warning > error > critical |
| 单档运算符 | `= != in nin` 或非数值比较时只允许一档 |
| `and` 级别集合一致 | 各条件 `thresholds[].level` 集合相同 |
| `or` 不限制 | |

## 活动告警级别只升不降

`policy_scan.py` `_create_events` 的两处「级别变化 → 覆盖 + 重置通知」分支（既有 Event 路径与既有 Alert 路径）改为：

- `rank(event.level) > rank(alert.level)`：覆盖 `alert.level`、`alert.notice = False`，既有 Event 的 `notified / notice_result / notice_retry_count` 重置。
- 否则：`alert.level` 不动、不重置通知；`value / content / end_event_time` 照常更新；`Event.level` 写本窗命中档。
- 事务内二次校正段（`select_for_update` 后按 `desired_alert` 刷新）同样按只升不降处理。

## 表单

```
触发  [大于 ▾]   警告 [10    ]  错误 [50    ]  严重 [200   ]  条/秒
```

- `conditionSelector.tsx`「触发」行：运算符后三个 `InputNumber` 并排，`addonBefore` 为级别名，留空即不启用；至少填一档。单位 addon 与现状一致。
- 运算符为 `=` / `!=` / `in` / `nin`，或非数值比较时，退化为「一个阈值输入 + 级别 `Select`（默认 warning）」。
- `alertConditionsForm.tsx`：`policyType === 'aggregate'` 时不渲染页底 `alert_level` `Radio.Group`；关键字保留。
- 校验错误仍由「规则」`Form.Item` 展示（`validateStatus=""` 不动）。
- 布局用 Tailwind `className`，颜色只用语义 token；不新建 SCSS。

## 试算、通知、详情

- 试算 `items[]` 加 `level`；`conditions[]` 带 `thresholds[].matched`、`level`。`dryRunResultModal.tsx` 判定 Tag 带级别文案与 `LEVEL_MAP` 颜色。
- 通知 `alert_notice_format.py`：聚合正文「告警内容」后加一行「级别：严重」；`format_condition_line` 阈值文本改为「> 200（严重）」。
- 告警详情 `aggregateConditionHit.tsx` 阈值列展示阶梯，命中档加粗或着色。
- `_render_alert_name` 的 `${level}` 取本窗命中档。

## 改动清单

### server/apps/log

| 文件 | 改动 |
|---|---|
| `constants/alert_policy.py` | `POLICY_LEVELS = ("warning", "error", "critical")`、`LEVEL_RANK`、`LADDER_OPS = {">", ">=", "<", "<="}` |
| `services/policy_condition.py` | `condition_thresholds(condition, default_level)`、`highest_hit_level(...)`、`combine_levels(levels, mode)`；`normalize_condition` 保持不读策略级别（由调用方传 `default_level`） |
| `serializers/policy.py` | 阶梯校验；存储归一后的 `thresholds` 并镜像 `value`；聚合推导 `alert_level`；`and` 集合一致校验在 `validate_alert_condition` 做 |
| `tasks/services/policy_scan.py` | `_resolve_condition` 逐档比较；`_check_rule_conditions` 返回 `(triggered, level)` 并写 `aggregate_data["level"]`；事件 `level` 取行级别；`_render_alert_name` 用命中档；`_create_events` 只升不降 |
| `services/policy_dry_run.py` | `_aggregate_item` 带 `level` |
| `services/alert_notice_format.py` | 级别行、阈值文本带档位 |
| 测试 | `test_policy_alert_condition_validation.py`（阶梯 / 单调 / 单档运算符 / `and` 集合）、`test_policy_scan_pure.py`（三档命中、`and` 取最轻、`or` 取最高、旧条件兼容、只升不降与通知重置）、`test_policy_dry_run.py`、通知格式 |

### web/src/app/log

| 文件 | 改动 |
|---|---|
| `types/integration.ts` | `FilterItem.thresholds?: Array<{ level: string; value: string }>` |
| `(pages)/event/strategy/detail/conditionSelector.tsx` | 「触发」行三档输入与退化态 |
| `(pages)/event/strategy/detail/policyFormUtils.ts` | `normalizeCondition(condition, alertLevel)` 归一旧值；`hasIncompleteCondition` / `hasNonNumericThreshold` 改看 `thresholds`；新增 `hasThresholdOrderError`、`hasMismatchedLevelSets`；`buildStrategyPayload` 推导 `alert_level` |
| `(pages)/event/strategy/detail/alertConditionsForm.tsx` | 聚合隐藏级别单选；校验器接两条新规则 |
| `(pages)/event/strategy/detail/page.tsx` | `dealDetail` 把 `alert_level` 传给 `normalizeCondition` |
| `components/aggregateConditionHit.tsx`、`components/public/alertRawLogEvidence.ts` | 阈值列展示阶梯 + 命中档；类型扩展 |
| `(pages)/event/strategy/detail/dryRunResultModal.tsx` | 判定 Tag 带级别 |
| `locales/zh.json` / `en.json`、`__tests__/logPolicyCalcMethods.i18n.test.ts` | 新文案 key 双语齐全 |
| `web/src/stories/log-policy-condition-editor.stories.tsx` | 加三档阈值 story 与退化态 story |
| 测试 | `conditionSelector.test.tsx`、`policyFormUtils.test.ts`、`alertConditionsForm.test.tsx` |

### 文档

- `docs/design/product-decisions/log-policy-calc-methods.md`：追加「阈值阶梯」范围、两条拍板决策、明确不做。
- 本文件 Status 改为 implemented 并记录偏差。

## 验收

- Server：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/log/tests/test_policy_alert_condition_validation.py apps/log/tests/test_policy_scan_pure.py apps/log/tests/test_policy_scan_db.py apps/log/tests/test_policy_dry_run.py apps/log/tests/test_tasks_policy.py --no-cov` 全绿；通知格式相关测试全绿。
- Web：`cd web && pnpm exec vitest run 'src/app/log/(pages)/event/strategy/detail/__tests__' src/app/log/__tests__/logPolicyCalcMethods.i18n.test.ts` 全绿；`pnpm lint` 对改动文件无新增告警；`pnpm type-check` 通过。
- 旧策略（条件只有 `op / value`）不改保存、扫描、通知、试算行为与升级前一致，级别仍为 `alert_level`。
- 新策略三档：同一分组从 12 → 60 → 300 → 60 条，告警级别 warning → error → critical → critical，通知在前三次重发、第四次不重发；事件级别依次 warning / error / critical / error。
- `and` 两条件级别集合不一致时保存与试算均被拒绝；`or` 允许。
