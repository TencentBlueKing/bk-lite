# 日志策略 · 回到日志场景（聚合自动恢复、关键字命中条数、运算符收口、告警值、文案）

Status: implemented（2026-10-29）

## 实现偏差

- 文案在 `language/zh-Hans.yaml` / `en.yaml`，没有 `zh.yaml`。错误键是 `error.policy_recover_after_range`、`error.policy_min_hits_range`。
- `Alert.info_event_count` 的 `verbose_name` 仍是「正常事件计数」。改文案会生成无意义的 `AlterField`。字段上方注释说明聚合策略复用为连续不满足窗数。
- `Event.action` 增加 `recovered` 后，Django 会把 choices 变更收成迁移。同字段上次加「转派」时已有 `0029_event_reassign_action`。按同样做法补了 `0030_alter_event_action`（只改 choices，不改列）。`makemigrations --check`：No changes detected。
- 同一 `execution_key` 在告警尚未恢复时重跑，会再次累加 `info_event_count`。没有单独的计数哨兵行：空 `action` 会被时间线当成命中，写进 `operator` / `content` 又会污染关闭人和正文。恢复当窗用确定性事件 id，状态离开 `new` 后重跑不再累加、不重复投递。
- 已关闭或已恢复的告警，同一 `execution_key` 重跑不改原告警；换一个执行再触发则新开一条 `new`。这样恢复后的下一窗可以重新告警，同一窗重试也不会把已关闭告警改回去。
- 对 `recovered` 调用关闭接口与已关闭告警相同：更新条件是 `status=new`，匹配不到则返回 200，状态和操作人不变。认领、分派、转派返回 409。
- 关键字未分组先查命中条数，再取样本。条数为 0 时不再用样本条数兜底。
- 查询直接抛错时扫描中断，不进入恢复对账，计数不变。`window_failed` 或对照不可用时对账直接返回。
- 本机 `server/.env` 的 `INSTALL_APPS` 不含 `cmdb`，sqlite 全量迁移又会被既有的 `NewSessionEventRelation.event` 挡住。验收因此清空 `INSTALL_APPS`，并加 `--create-db --nomigrations`。
- 该跑法下 19 个失败里，与本次相关的没有。其中 3 个并发创建事件在改动前的 `policy_scan.py` 上同样是 sqlite `database table is locked`。`test_create_events_atomic_3367` 用 `__new__` 跳过初始化，访问既有的 `self.organizations` 报错，该行在本次之前就存在。其余失败是 Vector 镜像平台、sqlite 不支持 `contains`、`--nomigrations` 下迁移节点缺失、检索时间参数和日志分组接口，与策略恢复无关。全量：19 failed，1215 passed，4 skipped。
- Web `pnpm exec vitest run src/app/log` 在机器负载下有 2 个 5000ms 超时（策略表单、条件运算符）和 1 个检索页用例；单独重跑这 3 个文件 30 passed。`information.hit.test.tsx`「有 conditions 时逐行显示」找文本 `count`，页面实际是 `log.event.funcCount`，相关文件本次未改。其余策略与时间线用例通过。改动文件 `pnpm exec eslint` 无告警。全量 `pnpm lint` 仍是 3 errors / 98 warnings，错误都在未改文件（`automaticPolicyApply.ts`、`rum-bootstrap.tsx`、`rumBootstrap.ts`）。`pnpm type-check` 通过。

产品决策来源：2026-10-29 对 APM / 日志策略「是否照搬监控」的复核。对照监控策略（`docs/design/product-decisions/monitor-policy-multi-metric.md`）、
日志决策记忆（`docs/design/product-decisions/log-policy-calc-methods.md`）与竞品（Datadog Log Monitor、Elastic Log Threshold、Grafana Loki、阿里云 SLS、Splunk）后确认：
日志的两类策略语义不同——关键字是「出现即告警」的事件型，聚合是「一个数比阈值」的指标型；两者不该共用监控那套「连续满足次数 + 永不恢复」。
决策记忆：`docs/design/product-decisions/log-policy-calc-methods.md`（已追加本批决策）。

## Problem Statement

1. **聚合告警只升不降又永不恢复。** 聚合策略已经长成指标型（三档阶梯、同比环比、分位、级别只升不降），但告警只能人工关闭。
   一次突增升到 critical 后流量回落它仍挂着，活跃列表越积越多。Datadog / Elastic / Grafana / SLS 对阈值型日志告警都会自动恢复；只有 Splunk 这类事件型不恢复。
   `Alert.info_event_count`（`server/apps/log/models/policy.py` 第 80 行，「正常事件计数」）是从监控搬来的字段，日志从未写入；前端 `useStateList / useStateMap` 已有 `recovered`（「自动恢复」）但没有数据会落到这个状态。
2. **关键字策略被套上「连续满足次数」。** `_detection_rows`（`server/apps/log/tasks/services/policy_scan.py`）对关键字也走 `_rows_with_streak`，表单提示「连续 N 个检测窗都有命中才告警」。
   错误码、异常栈、敏感操作这类场景要的抑噪旋钮是「本窗命中 ≥ N 条」，不是「连续 N 个窗都出现」——后者会吞掉偶发但严重的异常。决策记忆写的是「关键字策略保持命中即告警」。
3. **聚合「连续满足次数」文案与实现不一致。** 文案说「连续 N 个检测窗」，实现是按 `period` 长度向前平移出 N−1 个窗（`_rows_with_streak`）。
   频率 1 分钟 + 周期 5 分钟时，前一个检测窗是 1 分钟前的 5 分钟窗，平移出的却是 5 分钟前的窗，两者不是一回事。
4. **聚合条件的运算符是关键字时代的。** `useConditionList`（`web/src/app/log/hooks/event.ts`）给出 `= != > < in nin`：后端 `LADDER_OPS` 支持的 `>=` / `<=` 选不到，
   `in` / `nin` 对聚合出来的数毫无意义。
5. **聚合告警的 `value` 恒为计数。** `aggregate_alert_detection` 写 `"value": aggregate_data.get("count", 0)`；`avg(...) > 500` 的策略 `Alert.value` 为 0，并经 `nats/log.py` 推到告警中心。
6. **频率 / 周期提示是监控原文。** `zh.json` `setFrequency`「…收集一次监控数据」、`setPeriod`「…收集监控数据的时间范围」。

## 已拍板决策（2026-10-29）

1. **聚合策略可自动恢复，关键字策略维持人工关闭。** 规则级 `rule.recover_after`（1..10）：同一分组连续 N 个检测窗不满足条件则告警进入 `recovered`。
   缺省 / `null` = 不自动恢复，存量策略行为不变；表单新建聚合策略默认开启、N = 3。
   恢复只推送告警中心生命周期事件（与人工关闭同一口径），普通通知渠道不发恢复通知。
2. 恢复计数里，**分组消失视为本窗不满足**（日志空窗是常态；活跃告警的分组不再出现就是回落）。本轮查询失败（`window_failed`、对照查询失败）**既不计数也不清零**。
3. `recovered` 是终态：不可再认领、分派、转派、关闭（接口与 `closed` 同样处理）。再次满足条件时新开一条告警。
4. 关键字策略去掉 `trigger_count`，改为 `rule.min_hits`（1..100000，默认 1，「本窗命中 ≥ N 条才告警」）。已保存的关键字 `trigger_count` 读入即忽略，再保存时不写出。
5. 聚合「连续满足次数」**保持无状态平移窗实现**，只把文案改为如实描述：「最近 N 个相邻周期（按周期长度向前平移）都满足才告警」。
   有状态计数记为可后置项。
6. 聚合运算符收口为 `> >= < <= = !=`；已保存的 `in` / `nin` 继续回显与评估，不迁移。
7. 聚合告警 `Alert.value` / `Event.value` 取**第一条常规条件的算出值**（`aggregate_result.conditions[0].value`），拿不到数值时回落到 `count`。关键字仍为命中条数。
8. 速率单位维持「条/秒」，不改。

明确不做：关键字多档级别、恢复通知走普通渠道、恢复阈值（滞回）、级别回落、按级别路由、有状态连续计数、`in` / `nin` 的数据迁移。

## Solution

### C1 聚合自动恢复

数据：

- `AlertConstants`：`STATUS_RECOVERED = "recovered"`，加入 `STATUS_CHOICES`；`RECOVER_AFTER_MAX = 10`。
- `Event.Action` 新增 `RECOVERED = "recovered", "自动恢复"`。
- `Alert.info_event_count` 复用为「连续不满足窗数」；无迁移。
- `alert_condition.rule.recover_after`: `int | null`；序列化器校验 1..10，仅聚合策略接受，关键字出现则丢弃。

扫描（`LogPolicyScan`，聚合分支）：

- `aggregate_alert_detection` 之后、`create_events` 之前或之后均可，新增 `reconcile_recoveries(rows, events)`：
  1. 读 `rule.recover_after`，为空直接返回。
  2. 本轮 `window_observed` 为 False、或任一行 `reason == "window_failed"`、或 `baseline_status` 表示对照查询失败 → 直接返回（不计数、不清零）。
  3. 本窗触发的 `source_id` 集合 = 各事件 `source_id` ∪ `source_id_aliases`。
  4. 查 `Alert(policy=self.policy, status=new)`；在集合内的 `info_event_count = 0`（在 `_create_events` 更新活动告警的两处一并置 0）；不在集合内的 `info_event_count += 1`。
  5. `info_event_count >= recover_after` 的告警：`status = recovered`、`end_event_time = scan_time`、`operator = ""`；同事务写一条 `Event(action="recovered", level=alert.level, value=None, content=alert.content, event_time=scan_time, source_id=alert.source_id)`。
  6. `select_for_update` 加锁、只更新仍为 `new` 的行；同一 `execution_key` 重跑幂等。
- 关键字分支不调用。

通知：

- `LogAlertLifecycleNotifier.build_recovered_event(alert)` 与 `notify_recovered(alert)`：字段与 `build_closed_event` 同契约，`action = "recovered"`（告警中心 `source_adapter/base.py` 已接受）。
- 恢复后若 `policy.notice` 且 `is_alert_center_channel()`，`transaction.on_commit` 投递；失败只记有界 WARNING，由现有补偿路径按 `notice=False` 重投（与 `_deliver_closed_event` 同一做法，抽成共用函数放 `services/alert_lifecycle_notify.py` 或 `services/alert_handlers.py`，视图与扫描共用）。

接口与页面：

- `AlertViewSet` 列表与分布图 `status` 参数支持逗号分隔多值（`status__in`）；单值行为不变。
- 认领 / 分派 / 转派 / 关闭：对 `recovered` 的告警与 `closed` 同样拒绝（现有 `status != new` 分支已覆盖，补测试）。
- 前端告警页历史页签 `status: 'closed,recovered'`；`STATE_MAP` 已有 `recovered`；状态 Tag 颜色：`recovered` 用 `var(--color-success)`。
- 策略表单（`alertConditionsForm.tsx`，仅聚合）：「自动恢复」一行 = `Switch` + `InputNumber`（1..10，`addonBefore`「连续」`addonAfter`「个周期不满足」）。
  读入：`rule.recover_after` 为数 → 开、回填；否则关。写出：开 → `rule.recover_after = N`；关 → `null`。新建默认开、3。
- 告警详情时间线显示「自动恢复」事件（`Event.Action` 文案）。

### L1 关键字命中条数

- `_detection_rows`：关键字直接 `evaluate_keyword(window_start, window_end)`，不走 streak。
- `evaluate_keyword`：`min_hits = rule.get("min_hits", 1)`（非法按 1）；分组与未分组两条路径 `triggered = total_count >= min_hits`。未分组路径先 `_get_keyword_match_count` 再判，不再用 `len(logs)` 兜底判定（样本仍取 `limit=sample_limit`）。
- `PolicySerializer.validate_alert_condition`：关键字 → 校验 `rule.min_hits`（1..100000），丢弃 `trigger_count`；聚合 → 校验 `trigger_count`，丢弃 `min_hits`。
- 试算 `policy_dry_run.py` 关键字项带 `min_hits` 与 `total_count`，判定一致。
- 前端：`alertConditionsForm.tsx` 关键字不渲染 `trigger_count`，渲染「命中条数」`InputNumber`（1..100000，默认 1，提示「本窗命中达到该条数才告警」）；
  `policyFormUtils.ts` `readPolicyMinHits` / `buildStrategyPayload` 按类型写 `rule.min_hits` 或 `rule.trigger_count`；`page.tsx` `dealDetail` 回填。
  删除 `log.event.keywordTriggerCountTip`，新增 `log.event.minHits`、`log.event.minHitsTip`（zh / en）。

### L2 连续满足次数文案

- `log.event.triggerCountTip` → 「最近 N 个相邻周期（按周期长度向前平移）都满足才告警」；en 同步。实现不改。

### L3 运算符收口

- `web/src/app/log/hooks/event.ts` 新增 `useAggregateOperatorList`：`> >= < <= = !=`（文案复用 `log.moreThan` 等，`>=` / `<=` 新增 `log.moreThanOrEqual` / `log.lessThanOrEqual`）。
  `useConditionList` 保留给集成页过滤使用，不改。
- `conditionSelector.tsx` 改用新列表；删除「`>=` / `<=` 不在列表时临时 push」逻辑；已保存的 `in` / `nin` 仍追加到当前条件的选项里回显（现有逻辑保留）。
- 后端不改（已接受六个运算符）。

### L4 告警值

- `aggregate_alert_detection`：`value = _first_regular_value(aggregate_data)`：取 `aggregate_data["conditions"][0]["value"]`，`parse_metric` 成功则用，否则回落 `aggregate_data.get("count", 0)`。
- 现有计数策略断言（`test_policy_scan_db.py` 的 `alert.value == 5` 等）不受影响；新增 `avg` 策略断言 `alert.value == 算出值`。

### L5 文案

- `setFrequency` → 「多久扫描一次日志」；`setPeriod` → 「每次统计最近多长时间的日志」；en 同步。

## 数据契约

```json
{
  "query": "level:ERROR",
  "group_by": ["host"],
  "rule": {
    "mode": "and",
    "conditions": [...],
    "trigger_count": 2,
    "recover_after": 3
  }
}
```

关键字：

```json
{ "query": "OutOfMemoryError", "group_by": [], "rule": { "min_hits": 1 } }
```

- `Alert.status ∈ {new, recovered, closed}`；`Event.action` 新增 `recovered`。
- 告警中心生命周期事件新增 `action: "recovered"`，字段与 `closed` 同契约。
- 列表 / 分布图 `status` 接受 `a,b` 多值。

## 改动清单

### server/apps/log

| 文件 | 改动 |
|---|---|
| `constants/alert_policy.py` | `STATUS_RECOVERED`、`RECOVER_AFTER_MAX`、`MIN_HITS_MAX` |
| `models/policy.py` | `Event.Action.RECOVERED`；`Alert.info_event_count` 注释改为「连续不满足窗数」 |
| `serializers/policy.py` | 按类型校验 `trigger_count / recover_after / min_hits` 并丢弃不适用键 |
| `tasks/services/policy_scan.py` | 关键字不走 streak、`min_hits` 判定；`_first_regular_value`；`reconcile_recoveries`；`_create_events` 触发时清零 `info_event_count` |
| `services/alert_lifecycle_notify.py` | `build_recovered_event` / `notify_recovered`；关闭 / 恢复投递共用函数 |
| `services/policy_dry_run.py` | 关键字项带 `min_hits` |
| `views/policy.py` | `status` 多值；复用共用投递函数 |
| `language/` | 新错误键：`error.policy_recover_after_range`、`error.policy_min_hits_range` |
| 测试 | `test_policy_alert_condition_validation.py`（三键按类型）、`test_policy_scan_pure.py`（关键字 `min_hits`、告警值）、`test_policy_scan_db.py`（恢复计数 / 清零 / 终态 / 幂等 / 查询失败不计数 / 分组消失计数 / 恢复后再触发新开告警）、`test_policy_alert_actions_views.py`（`recovered` 拒绝操作、`status` 多值）、生命周期通知测试 |

### web/src/app/log

| 文件 | 改动 |
|---|---|
| `hooks/event.ts` | `useAggregateOperatorList` |
| `types/event.ts` | `rule.recover_after?`、`rule.min_hits?`、`StrategyFields.recover_after? / min_hits?` |
| `(pages)/event/strategy/detail/alertConditionsForm.tsx` | 关键字：命中条数；聚合：自动恢复开关 + 次数；`trigger_count` 仅聚合 |
| `(pages)/event/strategy/detail/conditionSelector.tsx` | 运算符列表 |
| `(pages)/event/strategy/detail/policyFormUtils.ts`、`page.tsx` | 读写 `recover_after / min_hits` |
| `(pages)/event/alert/page.tsx` | 历史页签 `status=closed,recovered`；Tag 颜色 |
| 告警详情时间线组件 | `recovered` 事件文案 |
| `locales/zh.json`、`en.json` | `minHits`、`minHitsTip`、`recoverAfter`、`recoverAfterTip`、`moreThanOrEqual`、`lessThanOrEqual`、`triggerCountTip`、`setFrequency`、`setPeriod`；删除 `keywordTriggerCountTip` |
| `web/src/stories/log-policy-condition-editor.stories.tsx` | 运算符列表随之更新 |
| 测试 | `alertConditionsForm.test.tsx`、`conditionSelector.test.tsx`、`policyFormUtils.test.ts`、`logPolicyCalcMethods.i18n.test.ts` |

### 文档

- `docs/design/product-decisions/log-policy-calc-methods.md`：已追加本批决策（见「2026-10-29 场景回归」）。
- `specs/capabilities/legacy-ard-modules-log.md` 不改；若存在日志告警长期契约文件则补「聚合策略自动恢复、关键字 `min_hits`」。
- 本文件 Status 改为 implemented 并记录偏差。

## 验收

- Server：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/log/tests --no-cov` 全绿（本机 `INSTALL_APPS` 限制见 `specs/changes/log-policy-level-ladder/spec.md` 实现偏差，必要时加 `--create-db --nomigrations`）。
- Web：`cd web && pnpm exec vitest run src/app/log` 全绿；`pnpm lint` 对改动文件无新增告警；`pnpm type-check` 通过。
- 聚合策略 `recover_after=2`：分组 A 第 1 窗触发（new）、第 2 窗不满足（`info_event_count=1`，仍 new）、第 3 窗不满足（`recovered`，有 `recovered` 事件，告警中心收到 `action=recovered`）、第 4 窗再触发（新开一条 new 告警）。
- 第 2 窗查询失败（`window_failed`）：`info_event_count` 不变。
- 第 2 窗分组 A 消失：计数 +1。
- 存量聚合策略（无 `recover_after`）：永不自动恢复，与升级前一致。
- 关键字 `min_hits=3`：本窗 2 条不告警、3 条告警；`trigger_count` 对关键字不再生效；`in` / `nin` 在新建聚合条件里不可选，旧条件仍回显。
- `avg(duration) > 500` 触发后 `Alert.value` 等于算出的均值，不是 0。
- 对 `recovered` 告警调用关闭 / 认领 / 分派接口被拒绝，状态不变。
