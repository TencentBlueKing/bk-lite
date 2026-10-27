# 日志策略计算方式丰富：速率 / 变化量 + 保存前试算 + 样本回跳

Status: implemented

需求来源：CTeam 需求 p398_715「【日志系统】告警计算方式丰富：速率/变化量 + 试算 + 样本回跳」。
腰部客户在日志策略用表单配「单位时间更快了 / 比上一窗变了」，保存前能试算，响了能带样本跳回检索。
决策记忆：`docs/design/product-decisions/log-policy-calc-methods.md`。
监控侧对照实现：`server/apps/monitor/services/policy_dry_run.py`、`server/apps/monitor/tasks/utils/policy_methods.py`（`previous_window` + `delta`）。

竞品对照（Datadog Change Alert、Elastic Log Threshold、Splunk 告警）见「决策记录」。

## Problem Statement

日志聚合策略今天只能对本窗聚合值（`count / sum / avg / max / min`）比固定阈值。客户两类常见诉求配不出来：

- 「每秒错误超过 0.5 条」：窗口长度一改，阈值就要跟着换算。
- 「比上一窗多了 50 条」：新服务上线、某分组突然刷错，固定阈值要么漏报要么长期误报。

同时三处闭环缺口让已有能力也用不顺：

- 保存前看不到会不会响。策略保存后要等一个检测周期才知道配错了。
- 聚合告警没有日志样本。事件 `raw_data` 只有聚合结果行，详情页看不到一条原始日志。
- 回跳不准。详情页「查看更多」用「告警开始 → 现在」的时间，聚合告警还把查询改写成 `stats`，打开后看不到命中的那几条日志。
- 通知只有告警内容和告警列表链接，没有命中条数、样本和检索链接。

## Solution

- 聚合策略条件函数枚举新增 `count_rate`（速率，条/秒）与 `count_delta`（变化量，较上一等长窗）。两者都从本窗 `count()` 派生，复用现有「条件 = 函数 + 字段 + 比较符 + 阈值」与 `and / or` 组合，关键字策略不变。
- 新增只读「试算」端点，复用正式扫描的判定函数，按分组返回本窗条数、上一窗条数、速率、变化量与判定，不写任何告警数据。
- 聚合触发分组按关键字路径取样（≤10 条），事件冻结「回跳查询」（原始查询 + 分组精确过滤 + 命中窗口）；详情页、公共组件、通知都用这份冻结数据回跳。
- 通知正文加命中数 / 速率 / 变化量、检测窗口、「查看命中日志」链接与截断样本；告警中心通道加结构化字段。

明确不做：1h / 24h 环比、百分比变化、异常 / 突增检测、自动恢复、错误占比。

## User Stories

1. 作为现场运维，我想配「level:error 按 service 分组，速率 > 0.5 条/秒」，改检测窗口不用重算阈值。
2. 作为现场运维，我想配「比上一等长窗多 50 条」，新分组第一次刷出 100 条也能响。
3. 作为现场运维，我想配「比上一等长窗少 100 条」抓业务日志骤降。
4. 作为现场运维，我在保存前点「试算」，看到每个分组本窗多少条、上一窗多少条、算出来多少、会不会响，再决定保不保存。
5. 作为值班人员，我收到的通知里有命中条数、算出的速率 / 变化量、几条样本和一个链接，点开就是命中当时那个时间窗的原始日志。
6. 作为值班人员，我在告警详情和告警中心的日志组件里能看到 ≤10 条样本，并能一键在检索里打开命中窗口。
7. 作为既有客户，我的旧策略不改就保存，扫描、通知、快照与升级前一致。

## Implementation Decisions

### D1. 数据契约

`alert_condition.rule.conditions[].func` 枚举扩展为 `count / sum / avg / max / min / count_rate / count_delta`，其他结构不变，旧策略零迁移、无新模型列。

```json
{
  "query": "level:error",
  "group_by": ["service"],
  "rule": {
    "mode": "and",
    "conditions": [
      { "func": "count",       "field": "_msg", "op": ">", "value": "100" },
      { "func": "count_rate",  "field": "_msg", "op": ">", "value": "0.5" },
      { "func": "count_delta", "field": "_msg", "op": ">", "value": "50"  }
    ]
  }
}
```

- `count_rate` / `count_delta` 的 `field` 固定写 `_msg`，前端不展示字段选择。
- 事件 `raw_data`（聚合）形状：

```json
{
  "aggregate_result": {
    "count": 180, "count__msg": 180,
    "count_rate": 0.6, "count_delta": 130, "previous_count": 50,
    "window_seconds": 300
  },
  "rule": { "...": "原样" },
  "query_result": { "service": "order", "count__msg": 180 },
  "samples": [ { "_time": "...", "_msg": "...", "service": "order" } ],
  "jump_query": {
    "query": "level:error AND service:=\"order\" (已含日志分组与采集类型过滤，未加 stats)",
    "window_start": 1761550000,
    "window_end": 1761550300
  }
}
```

- 扫描内部的事件 dict（`events[]`）新增顶层键 `jump_query`（聚合与关键字都有）；聚合事件另把它复制进 `raw_data.jump_query`。关键字事件 `raw_data` 保持为样本数组，不改形状。
- 快照条目（`AlertSnapshot.snapshots[]` 每项）新增顶层 `jump_query`，由 `_create_snapshots_for_alerts` 从事件 dict 提升，前端读快照条目即可，不解析 `raw_data`。
- `alert_condition.limit`（样本条数）保持可选、默认 5；后端读取时 `min(max(limit,1), 10)`，表单不新增字段。

### D2. 计算语义

| 项 | 规则 |
|---|---|
| 本窗 | 正式扫描 `[window_start, window_end]`（`tasks/policy.py::_run_policy_window` 给定）；试算 `[safe_now − period, safe_now]`，`safe_now = now − INGEST_DELAY_SECONDS` |
| `count_rate` | `count / (window_end − window_start)`，单位条/秒，浮点 |
| 上一窗 | `[window_start − (window_end − window_start), window_start)`，用同一条带日志分组、采集类型过滤的基础查询和同一组 `group_by` 跑 `stats by (...) count()` |
| `count_delta` | `count − previous_count`；上一窗该分组没有行时 `previous_count = 0`（对照存在，新分组突增能响） |
| 上一窗不可用 | 上一窗查询抛异常 → `previous_count = None`、`count_delta = None`；含 `count_delta` 的条件本轮判 False，不发告警、不发通知；记一条 WARNING（模板 + 惰性参数，含 policy_id、`failed_stage=previous_window`、`error_type`，不含查询正文） |
| 只在需要时查 | 只有 `conditions` 含 `count_delta` 才查上一窗 |
| 比较符 | 数值比较 `> < >= <= = !=`；`count_delta` 允许负阈值表示骤降 |
| `and / or` | 不变；`None` 值条件不参与「成立」，`or` 模式下其他条件仍可触发 |
| 事件 `value` | 仍为本窗 `count`（与今天一致）；速率 / 变化量进 `aggregate_result` |
| 告警名称模板 | 上下文追加 `aggregate_result`，支持 `${count}`、`${count_rate}`、`${count_delta}`、`${previous_count}`；`count_rate` 渲染保留两位小数 |
| 分组上限 | 聚合查询 `limit=1000` 不变 |

留存风险：VictoriaLogs 留存截断落在上一窗内时，`previous_count` 偏小、变化量偏大。本期不做留存探测，靠试算把上一窗条数摆出来。

### D3. 后端改造（`server/apps/log`）

**`tasks/services/policy_scan.py`**

- `_build_aggregation_query`：`count_rate` / `count_delta` 都映射为 `count() as count__msg`，现有去重保证只查一次。
- 新增 `_query_previous_window_counts(base_query_with_groups, group_by, window_start, window_end) -> dict | None`：返回 `{group_key_tuple: count}`，异常返回 `None` 并按 D2 记 WARNING。`group_key_tuple` 用 `group_by` 顺序的字符串值元组；无分组时 key 为 `()`。
- `_extract_aggregate_data(result, rule, *, window_seconds, previous_counts)`：新增两个关键字参数（默认 `None`，旧调用兼容）；按 D2 填 `count_rate` / `count_delta` / `previous_count` / `window_seconds`。
- `_check_rule_conditions`：条件取值为 `None` 时该条件结果为 False，并 DEBUG 记录 `reason=missing_baseline`。
- 把 `aggregate_alert_detection` 的查询 + 逐行判定抽成 `evaluate_aggregate(window_start, window_end) -> list[dict]`，每行 `{group_values, result, aggregate_data, triggered, reason}`，`reason ∈ {"", "missing_baseline"}`；`aggregate_alert_detection` 只把 `triggered` 行变事件。试算复用 `evaluate_aggregate`。
- 关键字路径同理抽 `evaluate_keyword(window_start, window_end) -> list[dict]`（每分组 `total_count`），`keyword_alert_detection` 复用。
- 聚合触发行取样：复用 `_build_group_sample_query` + `_fetch_group_sample` 的线程池路径，`sample_limit = min(limit, 10)`，写入 `raw_data.samples`；取样失败只影响该行的 `samples=[]`，不影响事件。
- 事件生成时冻结 `jump_query`：`query` = `_build_query_with_log_groups(base_query)` 再拼 `_build_exact_field_filter` 的分组过滤（无分组则不拼），`window_start / window_end` = 本窗。放在事件 dict 顶层；聚合事件同时复制进 `raw_data.jump_query`。关键字事件也冻结（无分组时与 clue 查询相同）。
- `_render_alert_name` 上下文合并 `aggregate_data`。
- `_create_snapshots_for_alerts`：快照条目新增顶层 `jump_query`，从事件 dict 顶层读取；旧条目没有该键，前端按缺省处理。

**`serializers/policy.py`** 新增 `validate_alert_condition`，只对 `alert_type == aggregate` 校验：

| 规则 | 拒绝信息（中文，走 `serializer_text` 同类机制或直接字符串，与文件内既有风格一致） |
|---|---|
| `rule.conditions[].func` ∈ 七个枚举 | 不支持的聚合函数 |
| `count_rate` / `count_delta` 的 `op` ∈ `> < >= <= = !=` | 该函数只支持数值比较 |
| `count_rate` / `count_delta` 的 `value` 为有限数（允许负数） | 阈值必须是数字 |
| `group_by` 为字符串列表 | 分组字段格式错误 |
| `limit` 若提供须为 1..10 整数 | 样本条数须在 1 到 10 之间 |

旧枚举（`count / sum / avg / max / min`）不新增校验，避免回溯拒绝旧策略。

**`constants/alert_policy.py`** 新增 `AGGREGATE_FUNCS`、`COUNT_DERIVED_FUNCS = {"count_rate", "count_delta"}`、`SAMPLE_LIMIT_MAX = 10`。

**通知 `_format_notice_content`**（普通渠道）正文顺序：

```
时间：…
告警内容：…
策略名称：…
命中条数：180（速率 0.60 条/秒，较上一窗 +130）   ← 只在 aggregate_result 有对应键时拼接
检测窗口：2026-10-27 15:50:00 ~ 15:55:00
样本（最多 10 条）：
  - <message 字段，单行，超过 200 字符截断加 …>
查看命中日志：<a href="{URL}/log/search?query=…&startTime=…&endTime=…&log_groups=…">点击查看</a>
查看告警详情：<a href="{URL}/log/event/alert">点击查看详情</a>
```

- 样本只取 `message`/`_msg` 字段；无样本时省略该段。
- `alert_lifecycle_notify.py` 告警中心 payload 增加 `samples`（同样 ≤10、单行截断）、`search_url`、`aggregate_result`。
- 通知正文、日志里不得出现完整查询之外的无界对象；日志不记正文。

**试算 `services/policy_dry_run.py::LogPolicyDryRunService`**

- 入口：`PolicyViewSet` 新增 `@action(methods=["post"], detail=False, url_path="dry_run")`。内部前端接口，与监控 `dry_run` 同类，不经 OpenAPI 网关、不新增对外端口。
- 载荷 = 新建 / 编辑同一份（含 `organizations`，可选 `id`）。
- 步骤与 `failed_stage`：
  1. `authorize`：`organizations` 必填并经 `validate_assignable_organizations`；有 `id` 时还要对该策略有 `Operate`（复用 `_authorize_policy`）。
  2. `serialize`：`PolicySerializer(data=payload, instance=<id 对应实例或 None>, context={..., "dry_run": True})`；`validate_name` 在 `dry_run` 上下文跳过唯一性校验；`validate_log_groups` 照常走 `LogAccessScopeService.resolve_scope`。
  3. `build_policy`：用 `validated_data` 构造未保存 `Policy(...)`（`collect_type` 赋对象），不调用 `save()`。
  4. `evaluate`：`LogPolicyScan(policy, scan_time=safe_now, window_start, window_end).evaluate_aggregate(...)` 或 `evaluate_keyword(...)`。
  5. `sample`：取前 1 个 `triggered` 行（无则第 1 行）拉 ≤10 条样本作 `sample_preview`。
- 零副作用：不写 Alert / Event / EventRawData / AlertSnapshot / `last_run_time`，不发通知。测试断言各表行数与 `last_run_time` 不变。
- 响应：

```json
{
  "alert_type": "aggregate",
  "window": {"start": 1761550000, "end": 1761550300},
  "previous_window": {"start": 1761549700, "end": 1761550000},
  "baseline_status": "ok | unavailable | not_required",
  "items": [
    {"group": {"service": "order"}, "count": 180, "previous_count": 50,
     "count_rate": 0.6, "count_delta": 130,
     "verdict": "would_trigger", "reason": ""}
  ],
  "truncated": false,
  "sample_preview": [ {"_time": "...", "_msg": "..."} ]
}
```

- `verdict ∈ would_trigger | no_trigger | missing_baseline | no_data`；`items` 上限 200，超出 `truncated=true`。无任何行时 `items=[]` 且 `verdict` 不出现，前端显示「本窗无匹配日志」。
- 失败：业务异常（校验、授权）按既有 `WebUtils.response_error` / 403；其他异常在服务边界记一条 ERROR（`event=log_policy_dry_run_failed policy_id=%s failed_stage=%s error_type=%s`，`exc_info=True`），对外返回「试算失败」。

### D4. 前端改造（`web/src/app/log`）

- `constants/index.ts`：`FUNCTION_LIST` 改为 `{ value, labelKey, needsField, unitKey? }[]`：
  `count / sum / avg / max / min` 不变（`needsField: true`）；`count_rate`（`log.event.funcCountRate` = 「速率（条/秒）」，`needsField: false`）；`count_delta`（`log.event.funcCountDelta` = 「变化量（较上一等长窗）」，`needsField: false`）。
- `conditionSelector.tsx`：`needsField=false` 时不渲染字段 `Select`，提交时 `field='_msg'`；阈值输入对 `count_rate` 允许小数并带后缀「条/秒」；`count_delta` 行下一行提示 `log.event.countDeltaTip`：「上一窗 0 条时变化量等于本窗条数；上一窗查询失败则本轮不判定」。布局 Tailwind `className`，不新增 SCSS。
- `policyFormUtils.ts::buildStrategyPayload` 不变（透传 `func`）；`validateConidtion` 对 `needsField=false` 的行不要求 `field`。
- `api/event.ts` 新增 `dryRunPolicy(data) => post('/log/policy/dry_run/', data)`。
- 策略详情页 `detail/page.tsx` 底部按钮区新增「试算」（`log.event.dryRun`），位于「保存」左侧；点击先 `form.validateFields()`，再用 `buildStrategyPayload` 产出载荷调用 `dryRunPolicy`，结果用 app-local `detail/dryRunResultModal.tsx` 展示：
  - 顶部：检测窗口、上一窗（有则显示）、verdict 计数胶囊、截断提示。
  - 表格列：分组（无分组显示「全部」）/ 本窗条数 / 上一窗条数 / 速率 / 变化量 / 判定（Tag 色：would_trigger 用 `var(--color-fail)` 语义色、missing_baseline 用 warning、其他 default）。
  - 关键字策略只显示分组与本窗条数，判定 `would_trigger` 当条数 > 0。
  - 底部 `sample_preview` 用现有 `AlertRawLogWidget` 的表格渲染方式（`parseRawLogData`）。
  - 监控的 `dryRunResultModal` 依赖实例语义，不升 shared；两边形态趋同后再按 `web/COMPONENT_GOVERNANCE.md` 合并。
- `event/alert/information.tsx::checkDetail`：点击时调用已有 `getAlertSnapshots(alert.id)`，取最后一个快照条目的 `jump_query`（query / window_start / window_end，`log_groups` 仍来自告警）构建检索 URL；请求失败或旧告警没有 `jump_query` 时退回现有逻辑；删除聚合告警改写 `stats` 的分支。URL 构建抽成纯函数 `buildSearchJumpUrl(...)`。
- `components/public/AlertRawLogWidget.tsx`：快照条目有 `jump_query` 时，在查询线索区显示「在检索中打开」按钮（新开标签 `/log/search?...`）；聚合快照 `raw_data.samples` 存在时表格优先渲染样本，聚合结果行仍可在 JSON 视图查看。`alertRawLogEvidence.ts` 的类型与 `parseRawLogData` 相应扩展。
- i18n：`locales/zh.json`、`locales/en.json` 的 `log.event` 下新增 `funcCountRate`、`funcCountDelta`、`countDeltaTip`、`dryRun`、`dryRunResult`、`dryRunWindow`、`dryRunPreviousWindow`、`dryRunNoMatch`、`verdictWouldTrigger`、`verdictNoTrigger`、`verdictMissingBaseline`、`verdictNoData`、`openInSearch`、`currentCount`、`previousCount`、`countRate`、`countDelta`、`truncatedHint`。

### D5. 权限与数据范围

- 试算与保存同一授权：组织可分配校验、日志分组数据范围、编辑时的策略 `Operate`。试算不能查出当前人不可见的日志分组。
- 回跳链接只携带查询与时间，打开后由检索页自身的数据范围再过滤一次。
- 通知正文带样本属于主动外发；本期按截断规则发送，不做策略级开关（见「仍待确认」已关闭：用户确认默认带截断样本）。

## Testing Decisions

后端（`apps.log.tests`，pytest；Cursor Cloud 用 sqlite：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/log/tests/<file> --no-cov`）：

- 纯函数（沿用 `test_policy_scan_pure.py` 风格）：
  - 聚合语句含 `count_rate` / `count_delta` / `count` 三条件时只出现一个 `count() as count__msg`。
  - `count_rate = count / window_seconds`；`count_delta = count − previous`；上一窗缺分组 `previous_count = 0`；`previous_counts=None` 时 `count_delta=None` 且条件判 False；`or` 模式下另一条件仍可触发。
  - 负阈值 `count_delta < -100` 触发。
  - `_render_alert_name` 渲染 `${count_rate}`（两位小数）、`${count_delta}`、`${previous_count}`。
  - 上一窗查询异常：返回 `None`，日志为稳定模板 + 独立参数，`failed_stage=previous_window`，不含查询正文（用哨兵字符串断言）。
  - 样本上限：`limit=50` → 10；`limit=0` → 1。
  - `jump_query.query` 含分组精确过滤与转义，`window_start/end` 等于本窗。
  - `_format_notice_content`：含命中条数 / 速率 / 变化量行、检测窗口、检索链接 href 正确插值、样本 ≤10 且每条 ≤200 字符加省略号；无 `aggregate_result` 时与今天输出一致（锁回归）。
- 序列化：七个 `func` 接受；未知 `func` 拒绝；`count_rate` 配 `in` 拒绝；`value="abc"` 拒绝；`limit=11` 拒绝；旧策略载荷（无 `limit`、`count` 任意 `op`）接受。
- 试算（DB，沿用 `test_policy_alert_actions_views.py` 的双租户夹具风格）：
  - 租户 A 用租户 B 的日志分组 / 组织试算 → 400/403。
  - 成功路径：mock `vlogs_api.query` 固定返回，断言 `items` 的数值与 verdict、`baseline_status`、`truncated`。
  - 零副作用：Alert / Event / EventRawData / AlertSnapshot 行数与 `last_run_time` 不变；未调用通知。
  - 编辑场景：同名策略带 `id` 试算不报名称重复；他人策略 `id` 试算 → 403。
  - 上一窗 mock 抛异常 → `baseline_status=unavailable`，含 `count_delta` 的行 `verdict=missing_baseline`。
- 扫描 DB（`test_policy_scan_db.py` 风格）：聚合触发事件 `raw_data.samples ≤ 10`、快照条目含 `jump_query`；关键字事件快照条目含 `jump_query`。
- 告警中心 payload：`samples`、`search_url`、`aggregate_result` 存在且样本截断。

前端：

- `__tests__/policyFormUtils.test.ts`：`count_rate` / `count_delta` 条件透传且 `field='_msg'`；`needsField=false` 行不要求字段。
- `conditionSelector` Vitest：选 `count_rate` 后字段选择不渲染、阈值可输入 `0.5`；选 `count_delta` 显示提示。
- `dryRunResultModal` Vitest：verdict 标签、`truncated` 提示、空结果文案、关键字模式列。
- `information.tsx` 的 URL 构建抽成纯函数 `buildSearchJumpUrl(...)` 并测试：有 `jump_query` 用冻结窗口；无则退回旧逻辑；聚合不再拼 `stats`。
- `AlertRawLogWidget` 测试追加：`jump_query` 存在时出现「在检索中打开」且 href 正确；`samples` 优先渲染。
- 新 i18n 键在 zh / en 两份都存在（沿用既有 locale 键测试方式）。
- 命令：`cd web && pnpm lint`，`pnpm exec vitest run <相关文件>`，`pnpm test:log-policy-form`，`pnpm test:log-alert-raw-columns`；改布局后 `pnpm type-check`。

本机联调（可选，有 Docker 底座时）：`make -C deploy/local dev-up`，`dev-server` + `dev-celery` + `dev-celery-beat`；建 5 分钟窗口速率策略，造日志，验证试算与下一轮正式扫描触发分组一致、详情回跳能看到样本。

## Out of Scope

- 1h / 24h / 7d 环比、百分比变化、倍数、近 N 周均值。
- 异常 / 突增检测、自动恢复状态机（日志告警仍人工关闭）。
- 错误占比（两次计数相除）。
- 留存不足探测。
- 表单暴露样本条数字段；通知样本的策略级开关。
- 试算弹窗升级为跨 app 共享组件。
- OpenAPI 网关新增端点；新模型列或迁移。

## Further Notes

### 切片顺序

1. **T1 后端计算**：D1 契约、D2 语义、`evaluate_aggregate` / `evaluate_keyword` 抽取、序列化校验、常量、纯函数与序列化测试。旧策略回归先绿。
2. **T2 表单**：`FUNCTION_LIST` 结构、`conditionSelector`、校验、i18n、前端测试。依赖 T1 契约。
3. **T3 试算**：`LogPolicyDryRunService` + 端点 + 双租户 / 零副作用测试；`dryRunPolicy` API、「试算」按钮、`dryRunResultModal`、前端测试。依赖 T1。
4. **T4 样本回跳**：聚合取样、`jump_query` 冻结与快照条目、`information.tsx` / `AlertRawLogWidget` 回跳、通知正文与告警中心 payload、相关测试。与 T2 / T3 可并行。
5. **T5 文档**：本规格 Status 改 implemented 并写 `verification.md`；`docs/changelog/` 条目。

### 主验收

- 旧聚合 / 关键字策略不改保存，扫描、通知、快照与升级前逐点一致。
- 策略「level:error 按 service 分组，`count_rate > 0.5` 且 `count_delta > 50`」，5 分钟窗口：order 本窗 180 条、上一窗 50 条 → 触发，告警内容可渲染 `0.60` 与 `130`；pay 本窗 100 条、上一窗 90 条 → 不触发；上一窗查询失败 → 不触发，试算显示 `missing_baseline`。
- 新分组 cart 上一窗无行、本窗 100 条、`count_delta > 50` → 触发。
- 试算与下一轮正式扫描的触发分组一致；试算后数据库无新行、`last_run_time` 不变。
- 通知含命中条数、速率 / 变化量、≤10 条截断样本、检索链接；链接打开为命中窗口的原始日志，不是 `stats`。
- 告警详情与告警中心日志组件显示 ≤10 条样本并能「在检索中打开」。

### 已确认成立的现网事实

- 聚合检测一次查全部聚合值再逐条件比较（`_build_aggregation_query` / `_extract_aggregate_data` / `_check_rule_conditions`），新增函数可在此三处落地。
- 正式扫描窗口由 `_run_policy_window` 传入 `window_start / window_end`，补偿窗按完整 period 对齐，上一窗可直接由本窗长度回推。
- 查询线索已在命中时冻结 query / log_groups / alert_condition / window；快照是展示时的唯一事实来源，不回读策略。
- 关键字路径已有按分组并发取样（`_fetch_group_sample`）与精确过滤转义（`_build_exact_field_filter`），聚合取样与回跳查询可直接复用。
- `alert_condition` 目前没有后端校验；`limit` 没有上限。
- 监控预检已证明「只读复用扫描判定 + 明确 `missing_baseline` verdict」的形态可落地。

### 决策记录

- **函数枚举而不是策略级「计算方式」字段**：现有条件模型就是「函数 + 字段 + 比较符 + 阈值」，加两个函数能和 `count > 100` 用 `and / or` 组合（Elastic 允许多条件，Datadog Change Alert 不能与阈值组合）。策略级字段会让一条策略只能选一种算法，并新增模型列。
- **对照固定为上一等长窗，只做绝对差**：Datadog 的 `a − b` 与可配置偏移里，十月只要「比上一窗变了」；百分比在上一窗为 0 时无定义，会把「新分组突增」变成不触发，与需求 2 冲突。
- **上一窗缺行记 0、查询失败记缺对照**：缺行是业务事实（没日志），失败是系统事实。Elastic Ratio「任一边为 0 不触发」是针对除法的，不适用于减法。监控预检对「对照缺失或留存不足」统一跳过，这里沿用「失败即跳过」的一半，另一半（留存探测）后置。
- **速率单位固定条/秒**：需求原文如此；窗口长度已在策略上，不再引入每分钟档位。
- **试算复用正式判定函数**：监控预检的经验是另写一套判定会漂；抽 `evaluate_*` 让两条路只差「要不要落库」。
- **样本上限 10、默认 5 不动、不进表单**：Splunk 邮件默认 100 条上限可配，但需求明确 ≤10；默认值不动避免旧策略通知变长。
- **通知默认带截断样本和检索链接**：Splunk 默认带结果链接、正文内联可选；这里需求要求通知带样本，取「带但截断」。策略级开关后置。
- **回跳用后端冻结的 `jump_query`**：分组过滤转义已在后端，前端再写一份会漂；告警产生时冻结也让策略改了之后旧告警仍打开当时的条件。
