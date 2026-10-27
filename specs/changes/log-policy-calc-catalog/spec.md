# 日志策略计算方式目录：函数 × 比较方式 × 对照 + 占比 / 无数据 / 连续次数

Status: approved

需求来源：CTeam 需求 p398_715 的第二批。第一批（速率、变化量、试算、样本回跳）已按
`specs/changes/log-policy-calc-methods/spec.md` 落地（提交 `437e5c1f24`）。产品在 2026-10-27 复核后要求
按客户实际场景补齐竞品具备的计算能力，并以本仓库技术栈（VictoriaLogs LogsQL、Django、Ant Design 表单）
为准选落法，而不是照搬竞品的表达式编辑器。
决策记忆：`docs/design/product-decisions/log-policy-calc-methods.md`。
监控侧词汇对照：`web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts` 的
`COMPARE_MODE_*` 与 `COMPARE_VALUE_KIND_*`。

## Problem Statement

第一批只覆盖「错误突增」一条场景线。按客户会配的日志告警逐项对照 Datadog Log Monitor、Elastic Custom /
Log Threshold、Grafana Loki、Splunk、阿里云 SLS，下面这些场景今天配不出来：

| 场景 | 竞品 | 现状 |
|---|---|---|
| 服务 10 分钟没写日志（断流） | Loki `absent_over_time`、SLS 无数据告警、Datadog `count < 1` | 本窗无行时分组为空，条件不评估，告不出来 |
| 错误 / 总请求 > 5%（占比） | Elastic ratio、Loki 两个 rate 相除 | 不支持 |
| 比对照涨 50%（变化率） | Datadog `% change`、Splunk rises by %、SLS `compare` | 只有绝对差，小主机 10 → 20 与大主机 1000 → 1010 分不开 |
| 失败登录来自多少个 IP、多少台主机在报错（影响面） | Splunk Number of Hosts、Datadog 唯一值、Elastic cardinality | 不支持 |
| 和昨天 / 上周同一时段比（同比） | SLS `compare(x, 86400)`、Datadog shift | 对照锁死上一等长窗 |
| 耗时字段 P95 > 2s（分位） | Datadog pc95 / pc99、Elastic percentile | 只有 avg / max |
| 连续 N 窗满足才告警（抖动抑制） | SLS 连续触发阈值、Loki `for` | 不支持 |
| 日志量字节暴涨 | Loki `bytes_rate` | 不支持 |

第一批把速率、变化量做成了函数枚举。再往上铺，函数 × 比较方式会膨胀成二十多个枚举，表单和校验都不可维护。

## Solution

三条技术栈事实决定了落法：

1. VictoriaLogs `stats` 管道原生有 `count_uniq`、`quantile`、`sum_len`，以及条件计数 `count() if (<filter>)`。
   去重计数、分位数、占比、字节量都能在**现有那一条聚合查询**里算出，不开第二条查询。
2. 扫描器的上一窗查询已经是「同一条查询换起止」，对照时段就是把起止平移。
3. 条件模型是 `alert_condition.rule.conditions[]` 的 JSON，加字段不动表结构、不做迁移。

因此：

- 条件模型改为正交三元：**函数 × 比较方式 × 对照**。函数增加 `count_uniq`、`quantile`、`ratio`、`bytes_rate`；
  比较方式 `absolute | delta | percent`；对照 `previous_window | offset_1h | offset_24h | offset_7d`。
  已上线的 `count_delta` 在读写两侧归一为 `count + delta + previous_window`，老策略零改动。
- 对照窗改为「同一条聚合查询平移后再跑一次」，一次拿到所有函数的对照值，变化量 / 变化率对
  `count / sum / avg / max / min / count_uniq / quantile` 都可用（Datadog Change Alert 的覆盖面）。
- 策略级「无数据告警」开关：无分组看本窗 0 行；有分组看「上一等长窗出现过、本窗缺失」的分组。
- 规则级「连续满足次数」`trigger_count`（1..5），无状态实现：当前窗加前 N−1 个窗各跑一次判定。
- 试算、通知命中行、告警名称模板、详情样本回跳随契约扩展。

明确不做：公式编辑器 / 任意 SQL / 自定义触发表达式、近 N 周均值基线、异常检测、自动恢复、实时逐条触发。

## User Stories

1. 作为现场运维，我想配「level:error 按 service 分组，计数比昨天同一时段涨 50% 且本窗 ≥ 20 条」，小服务和大服务用同一条策略。
2. 作为现场运维，我想配「`status:500` 占全部请求的比例 > 5%」，分母就是策略查询本身，不用再写一条查询。
3. 作为安全运维，我想配「登录失败日志的 `client_ip` 去重数 > 50」抓撞库。
4. 作为现场运维，我想配「`duration` 字段 P95 > 2000」抓慢请求，不用先把日志转成指标。
5. 作为现场运维，我想在策略上打开「无数据告警」，某个 `host` 上一窗还在写日志、这一窗一条都没有时收到通知。
6. 作为现场运维，我想配「连续 3 个检测窗都满足才告警」，把抖动过滤掉。
7. 作为现场运维，我在保存前试算时能看到每个分组每条条件的当前值、对照值、变化量 / 变化率、分母和为什么没触发。
8. 作为既有客户，我第一批配的 `count_delta` 策略不改，保存、扫描、通知与升级前一致。

## Implementation Decisions

### D1. 数据契约

`alert_condition` 新增字段全部可选，缺省行为等于今天。

```json
{
  "query": "level:error",
  "group_by": ["service"],
  "no_data": { "enabled": true, "level": "warning" },
  "rule": {
    "mode": "and",
    "trigger_count": 3,
    "conditions": [
      { "func": "count",      "field": "_msg",      "op": ">=", "value": "20" },
      { "func": "count",      "field": "_msg",      "op": ">",  "value": "50",
        "compare": { "kind": "percent", "to": "offset_24h" } },
      { "func": "count_uniq", "field": "client_ip", "op": ">",  "value": "50" },
      { "func": "quantile",   "field": "duration",  "op": ">",  "value": "2000",
        "params": { "quantile": 0.95 } },
      { "func": "ratio",      "field": "_msg",      "op": ">",  "value": "5",
        "params": { "filter": "status:500" } }
    ]
  }
}
```

| 字段 | 取值 | 说明 |
|---|---|---|
| `func` | `count / sum / avg / max / min / count_uniq / quantile / ratio / count_rate / bytes_rate` | `count_delta` 仍被接受，读写两侧归一（见 D3） |
| `field` | 字符串 | `count / count_rate / bytes_rate / ratio` 固定 `_msg`；其余必填 |
| `compare.kind` | 缺省 `absolute`；`delta`；`percent` | 只允许用于 `count / sum / avg / max / min / count_uniq / quantile` |
| `compare.to` | `previous_window / offset_1h / offset_24h / offset_7d` | `kind ≠ absolute` 时必填 |
| `params.quantile` | `0.5 / 0.9 / 0.95 / 0.99` | 仅 `quantile` |
| `params.filter` | LogsQL 过滤表达式，1..500 字符，不含 `\|` | 仅 `ratio`，是分子；分母是策略查询 |
| `rule.trigger_count` | 整数 1..5，缺省 1 | 连续满足次数 |
| `no_data.enabled` | 布尔，缺省 false | 无数据告警开关 |
| `no_data.level` | `info / warning / error / critical`，缺省同策略 `alert_level` | 无数据告警级别 |

事件 `raw_data.aggregate_result` 形状扩展（键名规则 `<func>_<field>`，`field` 中 `.` 换 `_`；`quantile` 带分位
`quantile_0_95_duration`；`ratio` 用条件序号 `ratio_0`）：

```json
{
  "count": 180, "count__msg": 180, "window_seconds": 300,
  "count_uniq_client_ip": 63,
  "quantile_0_95_duration": 2310.5,
  "ratio_0": 7.2, "ratio_0_hit": 13, "ratio_0_total": 180,
  "baseline": {
    "to": "offset_24h", "window": { "start": 1761463700, "end": 1761464000 },
    "status": "ok",
    "values": { "count__msg": 120, "count_uniq_client_ip": 40 }
  },
  "conditions": [
    { "func": "count", "field": "_msg", "compare": { "kind": "percent", "to": "offset_24h" },
      "current": 180, "baseline": 120, "value": 50.0, "op": ">", "threshold": "50", "matched": true, "reason": "" }
  ]
}
```

- `conditions[]` 是逐条件的解析结果，试算、通知命中行、详情页都读它，不再各自从 `aggregate_result` 拼。
- 无数据事件：`content` 为 `无数据：<渲染后的告警名称>`，`value = 0`，`raw_data.aggregate_result = {"count": 0, "no_data": true, "baseline": {...}}`，
  `samples = []`，`jump_query` 仍冻结本窗与分组过滤。`source_id` 在分组身份后追加 `:no_data`，与正常告警互不归并。
- 快照条目、`jump_query`、样本 ≤10 条规则沿用第一批。

### D2. 计算语义

| 项 | 规则 |
|---|---|
| 本窗 | 沿用：正式扫描 `[window_start, window_end]`；试算 `[safe_now − period, safe_now]` |
| 对照窗 | `previous_window`：`[start − d, start)`，`d = end − start`；`offset_1h / 24h / 7d`：`[start − off, end − off)`。一条策略允许多条条件各自不同 `to`，每个不同的 `to` 查一次 |
| 对照查询 | 和本窗**同一条**聚合查询（同 `stats by` 与全部函数），只换起止。失败 → 该 `to` 的 `baseline.status = unavailable`，依赖它的条件判 False，不告警不通知，WARNING `event=log_policy_baseline_failed policy_id=%s failed_stage=baseline compare_to=%s error_type=%s` |
| `delta` | `current − baseline` |
| `percent` | `(current − baseline) / baseline × 100`；`baseline == 0` → `None`，`reason = baseline_zero`，该条件判 False（Elastic、Datadog 一致） |
| 对照窗缺该分组 | `count / count_uniq / sum` 记 0（业务事实：没日志）；`avg / max / min / quantile` 记 `None`，`reason = baseline_missing`，条件判 False |
| `count_uniq` | `count_uniq(<field>) limit 1000000 as count_uniq_<field>`；达到上限按上限值比较 |
| `quantile` | `quantile(<q>, <field>) as quantile_<q>_<field>`；VictoriaLogs 对非数值字段返回空或 NaN → `None`，`reason = not_numeric` |
| `ratio` | `count() if (<filter>) as ratio_<i>_hit` 与 `count() as count__msg` 同一条查询；`ratio = hit / total × 100`；`total == 0` → `None`，`reason = denominator_zero` |
| `count_rate` | 沿用 `count / window_seconds` |
| `bytes_rate` | `sum_len(_msg) as bytes__msg`；`bytes__msg / window_seconds`，单位字节/秒 |
| `trigger_count = N > 1` | 对 `i = 1..N−1` 用本窗平移 `i × d` 再跑一次 `evaluate_aggregate`（含各自对照）；分组在全部 N 窗都 `triggered` 才触发。任一窗查询失败 → 本轮该分组不判，`reason = window_failed`。试算返回 `streak`（连续满足窗数） |
| 无数据 · 无分组 | 本窗聚合结果 0 行（关键字策略：`total_count == 0`）→ 一条无数据事件 |
| 无数据 · 有分组 | 取上一等长窗（固定 `previous_window`，与条件的 `to` 无关）的分组集合，减去本窗分组集合，差集每组一条无数据事件。上一等长窗查询失败 → 本轮不判无数据，WARNING 同上。关键字策略有分组时同样适用：用 `_build_keyword_group_query` 查上一等长窗分组集合 |
| 无数据 · 连续次数 | `trigger_count` 不作用于无数据事件；无数据只看本窗 |
| 无数据与正常条件 | 互不影响：本窗有行走条件判定，缺失分组走无数据；同一分组不会同时产生两种事件 |
| 比较符 | 数值 `> < >= <= = !=`；`delta` 允许负阈值 |
| `and / or` | 不变；`None` 值条件不参与「成立」 |
| 事件 `value` | 仍为本窗 `count` |
| 告警名称模板 | 上下文合并整个 `aggregate_result` 顶层键与 `baseline.values`（前缀 `baseline_`），`${count_uniq_client_ip}`、`${ratio_0}`、`${baseline_count__msg}` 可用；浮点渲染两位小数 |

留存风险：`offset_7d` 落在 VictoriaLogs 留存之外时对照为 0 或缺失，变化率会判 `baseline_zero` 不告警，变化量会偏大。
试算把对照值摆出来，不做留存探测。

### D3. 后端改造（`server/apps/log`）

**`constants/alert_policy.py`**

- `AGGREGATE_FUNCS` 扩为十个；`COMPARE_KINDS = {absolute, delta, percent}`；`COMPARE_TARGETS = {previous_window, offset_1h, offset_24h, offset_7d}`；
  `COMPARE_OFFSET_SECONDS = {offset_1h: 3600, offset_24h: 86400, offset_7d: 604800}`；`COMPARABLE_FUNCS`（七个）；
  `QUANTILE_CHOICES = (0.5, 0.9, 0.95, 0.99)`；`RATIO_FILTER_MAX_LEN = 500`；`TRIGGER_COUNT_MAX = 5`；`COUNT_UNIQ_LIMIT = 1_000_000`。
- 保留 `COUNT_DERIVED_FUNCS = {count_rate, count_delta}` 供归一。

**条件归一 `services/policy_condition.py`（新）**

- `normalize_condition(condition) -> dict`：`count_delta` → `{"func": "count", "field": "_msg", "compare": {"kind": "delta", "to": "previous_window"}}`；
  缺省补 `compare = {"kind": "absolute"}`；`params` 缺省 `{}`。序列化写入与扫描读取都经过它。
- `condition_alias(condition) -> str`：生成 `stats` 别名与 `aggregate_result` 键，是本规格唯一的键名来源。
- `stats_expression(condition, index, filter_mapper) -> str | None`：返回该条件的 `stats` 函数片段；`count_rate` 返回 `count() as count__msg`，
  `bytes_rate` 返回 `sum_len(_msg) as bytes__msg`，`ratio` 返回 `count() if (<mapped filter>) as ratio_<i>_hit`，并额外保证 `count() as count__msg` 在列表里。
  `filter_mapper` 用 `SearchService._build_storage_query(filter, None)[0]` 做 `message → _msg` 映射。

**`tasks/services/policy_scan.py`**

- `_build_aggregation_query` 改为遍历归一后的条件调用 `stats_expression`，去重后拼 `stats`。
- `_query_previous_window_counts` 改为 `_query_baseline(aggregation_query, compare_to, window_start, window_end) -> dict | None`：
  返回 `{group_key_tuple: result_row}`；按 D2 计算对照窗起止；异常返回 `None` 并记 WARNING。`evaluate_aggregate` 对条件里出现的每个 `to` 调一次，
  结果放 `self.baselines = {to: {"status": ..., "window": ..., "rows": ...}}`。现有 `self.baseline_status` 保留：没有任何对照为 `not_required`，
  任一 `to` 失败为 `unavailable`，否则 `ok`（试算顶层字段继续读它）。
- `_build_aggregation_query` 对 `ratio` 的 `params.filter`：先 `SearchService._build_storage_query(filter, None)[0]` 做 `message → _msg` 映射，再以 `count() if ((<mapped>)) as ratio_<i>_hit` 拼接；
  不走 `_build_query_with_log_groups`（日志分组与采集类型过滤已在基础查询上，分子不重复加）。
- `_extract_aggregate_data` 改为：先按 `condition_alias` 取本窗值（类型转换规则：`count*` / `ratio_*_hit` 为 int，其余 float，`None` 保留），
  再对每条条件调 `_resolve_condition(condition, current_row, baselines, group_key, window_seconds) -> dict`（即 D1 的 `conditions[]` 元素，含 `value / reason / matched`）。
  `aggregate_result["conditions"]` 与 `aggregate_result["baseline"]` 由此填充。`count / count__msg / window_seconds / count_rate` 等旧键继续写，锁回归。
- `_check_rule_conditions` 改为读 `aggregate_result["conditions"][i]["matched"]` 按 `mode` 组合；`matched` 为 False 且 `reason` 非空时 DEBUG `event=log_policy_condition_skipped policy_id=%s reason=%s`。
- `evaluate_aggregate(window_start, window_end)` 行结构加 `reason`（取第一条未匹配且有 `reason` 的条件）；新增 `evaluate_no_data(window_start, window_end, current_rows) -> list[dict]`
  按 D2 产出缺失分组行 `{group_values, no_data: True, baseline_window}`；`evaluate_keyword` 无分组且 `total_count == 0` 时同样可产出无数据行。
- `aggregate_alert_detection` / `keyword_alert_detection`：
  - `trigger_count > 1` 时调 `_evaluate_streak(window_start, window_end, n)`：对 `i = 1..n−1` 平移窗口重跑 `evaluate_aggregate`，得到每组 `streak`；只把 `streak == n` 的行变事件。
  - `no_data.enabled` 时追加 `evaluate_no_data` 的行为无数据事件，`level = no_data.level or policy.alert_level`。
- `_render_alert_name` 上下文按 D2 合并 `baseline.values`。
- 聚合取样、`jump_query` 冻结、快照条目沿用第一批；无数据事件 `samples = []`。

**`serializers/policy.py::validate_alert_condition`**（函数 / 比较 / 参数校验只对 `aggregate` 生效；`no_data` 与 `trigger_count` 对两种 `alert_type` 都校验，
现有「非聚合直接返回」的早退要改成只跳过条件部分）

| 规则 | 拒绝信息键（`language/zh-Hans.yaml`、`en.yaml` 同步） |
|---|---|
| `func` ∈ 十个枚举（含 `count_delta`） | `error.policy_aggregate_func_unsupported`（已有） |
| `compare.kind` ∈ 三个；`kind ≠ absolute` 时 `to` ∈ 四个 | `error.policy_compare_invalid` |
| `compare.kind ≠ absolute` 只用于 `COMPARABLE_FUNCS` | `error.policy_compare_func_unsupported` |
| `quantile` 的 `params.quantile` ∈ 四个 | `error.policy_quantile_invalid` |
| `ratio` 的 `params.filter` 非空、≤500、不含 `\|` | `error.policy_ratio_filter_invalid` |
| 需要 `field` 的函数 `field` 非空字符串 | `error.policy_field_required` |
| 新函数与带 `compare` 的条件 `op` ∈ 数值比较、`value` 为有限数 | `error.policy_numeric_op_only`、`error.policy_threshold_number`（已有） |
| `trigger_count` 整数 1..5 | `error.policy_trigger_count_range` |
| `no_data.level` ∈ 四级 | `error.policy_no_data_level_invalid` |

写入前把 `conditions[]` 逐条 `normalize_condition`，落库即归一；旧枚举 `count / sum / avg / max / min` 的绝对值条件不新增校验。

**试算 `services/policy_dry_run.py`**

- `items[]` 保留 `count / previous_count / count_rate / count_delta`（兼容），新增 `conditions`（即 `aggregate_result["conditions"]`）、`streak`、`no_data`；
  顶层 `previous_window` 保留，新增 `baselines = {to: {window, status}}`。
- `verdict` 增加 `would_trigger_no_data`；`reason` 取值 `missing_baseline | baseline_zero | baseline_missing | denominator_zero | not_numeric | window_failed`。
- `trigger_count > 1` 时试算同样跑前 N−1 窗（查询次数 ≤ 5 × (1 + 对照数)）。
- 零副作用、授权、失败日志沿用第一批。

**通知 `services/alert_notice_format.py`**

- `format_hit_line` 改为按 `aggregate_result["conditions"]` 逐条渲染，第一行仍是「命中条数：N」，之后每条件一行：
  `去重计数(client_ip)：63`、`计数：180（较 24 小时前 +50.0%，对照 120）`、`占比(status:500)：7.2%（13 / 180）`、`P95(duration)：2310.50`。
- 无数据事件正文第二行固定「本窗无日志，上一窗 N 条」，不含样本段，保留检索链接与详情链接。
- 告警中心 payload `aggregate_result` 原样带 `conditions` 与 `baseline`。

### D4. 前端改造（`web/src/app/log`）

- `constants/index.ts`：`FUNCTION_LIST` 项扩为 `{ value, labelKey, needsField, unitKey?, comparable, needsQuantile?, needsFilter? }`，
  下拉去掉 `count_delta`（旧策略读入时归一为「计数 + 变化量 + 上一窗」，`funcCountDelta` 词条保留给 `count_delta` 兼容显示与通知）；
  新增 `COMPARE_KIND_LIST`、`COMPARE_TARGET_LIST`、`QUANTILE_LIST`，词条与监控 `compareMode*` 中文一致（绝对值 / 变化量 / 变化率；上一窗 / 1 小时前 / 24 小时前 / 7 天前）。
- `conditionSelector.tsx` 一行：函数（中文（方法名）双语，沿用现状）→ 字段 / 分位下拉 / 分子筛选输入（按函数三选一）→ 比较方式 → 对照（`kind ≠ absolute` 时出现）→ 比较符 → 阈值（`percent`、`ratio` 后缀 `%`；`count_rate` 后缀 `条/秒`；`bytes_rate` 后缀 `字节/秒`）。
  控件固定宽度放 `style`（与第一批修正后一致），行容器 Tailwind；超宽自动换行。`percent` 行下提示「对照为 0 时不判定」，`ratio` 行下提示「分母是上方查询条件，分母为 0 不判定」。
- `alertConditionsForm.tsx`：规则区下方新增「无数据告警」`Switch` + 级别 `Radio`（开关关时隐藏级别）；频率行旁新增「连续满足次数」`InputNumber`（1..5，缺省 1，带提示「连续 N 个检测窗都满足才告警」）。
- `policyFormUtils.ts`：载荷写入 `compare / params / no_data / trigger_count`；读取旧策略时 `count_delta` 显示为「计数 + 变化量 + 上一窗」（前端也调 `normalizeCondition`，与后端同一规则）；
  `hasIncompleteCondition` 对 `percent / delta` 要求 `to`，对 `quantile` 要求分位，对 `ratio` 要求分子筛选。
- `dryRunResultModal.tsx`：主表列 分组 / 本窗条数 / 连续满足 / 判定；行可展开显示 `conditions` 子表：条件、当前值、对照值、算出值、阈值、是否成立、原因。顶部胶囊加 `would_trigger_no_data`；`baselines` 多个时逐个显示窗口与状态。
- `information.tsx` / `AlertRawLogWidget.tsx`：命中区按 `conditions` 渲染逐条件行，无数据告警显示「本窗无日志」。
- i18n：`log.event` 下新增 `compareKind`、`compareKindAbsolute / Delta / Percent`、`compareTo`、`compareToPreviousWindow / Offset1h / Offset24h / Offset7d`、
  `funcCountUniq`、`funcQuantile`、`funcRatio`、`funcBytesRate`、`quantileLabel`、`ratioFilter`、`ratioFilterTip`、`percentTip`、`noDataAlert`、`noDataLevel`、`noDataTip`、
  `triggerCount`、`triggerCountTip`、`verdictWouldTriggerNoData`、`reasonBaselineZero / BaselineMissing / DenominatorZero / NotNumeric / WindowFailed`、`streak`、`baselineValue`、`computedValue`。

### D5. 权限、安全与数据范围

- 试算与保存同一授权，沿用第一批。
- `params.filter` 是用户输入拼进 `count() if (...)`：序列化拒绝 `|`，扫描前再经 `SearchService._build_storage_query` 映射，拼接时整体加括号。测试用含 `| delete` 的字符串断言被拒绝。
- 对照窗、连续窗、无数据窗的查询都带与本窗相同的日志分组与采集类型过滤，不会越出策略数据范围。
- 日志不记 `filter` 原文与查询正文。

## Testing Decisions

后端（sqlite：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/log/tests/<file> --no-cov --create-db --nomigrations`）：

- `test_policy_condition_pure.py`（新）：`normalize_condition` 把 `count_delta` 归一；`condition_alias` 对 `quantile 0.95 duration`、`ratio` 序号、`count_uniq client.ip` 的键名；`stats_expression` 输出与去重（`count__msg` 只出现一次）；`ratio` 的 `filter` 经 `message → _msg` 映射并加括号。
- `test_policy_scan_pure.py` 追加：
  - `percent`：`(180−120)/120×100 = 50.0` 触发 `> 49`；`baseline == 0` → `None`、`reason = baseline_zero`、条件 False、`or` 模式下另一条件仍可触发。
  - `delta` 对 `count_uniq`、`sum`、`avg`；对照缺分组：`count / count_uniq / sum` 为 0，`avg / quantile` 为 `None` 且 `reason = baseline_missing`。
  - `offset_24h` 的对照窗起止 `[start − 86400, end − 86400)`；两个不同 `to` 产生两次对照查询；同一 `to` 只查一次。
  - `ratio`：`hit / total × 100`；`total == 0` → `denominator_zero`。
  - `quantile` 非数值 → `not_numeric`。
  - `bytes_rate = bytes__msg / window_seconds`。
  - 对照查询异常：返回 `None`，WARNING 模板含 `failed_stage=baseline compare_to=offset_24h`，不含查询正文（哨兵断言）。
  - `trigger_count = 3`：三窗都触发才产事件；第二窗不触发不产；某窗异常 → `window_failed`。
  - 无数据：无分组 0 行产一条，`source_id` 以 `:no_data` 结尾，`level` 取 `no_data.level`；有分组上一窗 `{a, b}` 本窗 `{a}` → `b` 一条；开关关则不产。
  - `_render_alert_name` 渲染 `${count_uniq_client_ip}`、`${ratio_0}`、`${baseline_count__msg}`。
- 序列化：十个 `func` 接受；`compare.kind = percent` 无 `to` 拒绝；`ratio` 配 `compare` 拒绝；`filter` 含 `|` 拒绝；`quantile = 0.8` 拒绝；`trigger_count = 6` 拒绝；`no_data.level = fatal` 拒绝；第一批载荷（`count_delta`）接受且落库归一。
- 试算（DB）：`conditions` 逐条数值与 `matched`；`verdict = would_trigger_no_data`；`streak`；`baselines` 两个 `to`；零副作用与双租户沿用。
- 扫描 DB：无数据事件写入 Alert / Event / 快照，`raw_data.aggregate_result.no_data = true`；正常事件 `aggregate_result.conditions` 持久化。
- 通知：命中行逐条件渲染样例（上文四条）；无数据正文第二行；旧 `aggregate_result`（无 `conditions`）仍输出第一批格式（锁回归）。

前端：

- `policyFormUtils.test.ts`：`compare / params / no_data / trigger_count` 透传；`count_delta` 读入显示为计数 + 变化量 + 上一窗；`hasIncompleteCondition` 三种缺项。
- `conditionSelector.test.tsx`：选变化率后出现对照下拉与 `%` 后缀；选 `quantile` 出现分位下拉不出现字段；选 `ratio` 出现分子筛选输入。
- `alertConditionsForm` 测试：无数据开关打开后出现级别；连续次数上限 5。
- `dryRunResultModal.test.tsx`：展开行显示条件子表与原因；`would_trigger_no_data` 胶囊。
- `logPolicyCalcMethods.i18n.test.ts` 追加新键 zh / en 齐全且不相同。
- 命令：`pnpm exec vitest run <相关文件>`，`pnpm test:log-policy-form`，`pnpm exec eslint <改动文件>`，`pnpm type-check`。

## Out of Scope

- 公式编辑器、任意 SQL、自定义触发表达式。
- 近 N 周均值基线、异常 / 突增检测、自动恢复状态机、实时逐条触发。
- 留存不足探测。
- 多字段去重（`count_uniq(a, b)`）、`ratio` 的分母另写查询。
- 新模型列或迁移；OpenAPI 网关端点；`docs/changelog/`（由发布流程另记）。

## Further Notes

### 切片顺序

1. **B1 条件模型与对照**：常量、`policy_condition.py`、归一、`stats_expression`、`_query_baseline`、`_resolve_condition`、`percent / delta` 对七个函数、`count_uniq`、`quantile`、`bytes_rate`、序列化校验、试算 `conditions / baselines`、表单比较方式与对照、试算弹窗展开行、i18n、测试。旧策略与第一批回归先绿。
2. **B2 占比与无数据**：`ratio`、`evaluate_no_data`、无数据事件与通知、表单开关与分子筛选、试算 `would_trigger_no_data`、测试。
3. **B3 连续次数**：`trigger_count`、`_evaluate_streak`、试算 `streak`、表单、测试。
4. **B4 文档**：本规格 Status 改 implemented，写 `verification.md`；更新决策记忆。

### 主验收

- 第一批 `count_rate > 0.5 且 count_delta > 50` 策略不改保存，落库后 `count_delta` 已归一，扫描、通知与升级前逐点一致。
- 「按 service 分组，`count` 变化率 `> 50`（对照 24 小时前）且 `count >= 20`」：order 本窗 180、昨天同窗 120 → 触发并渲染 `+50.0%`；pay 本窗 15 → 不触发；cart 昨天同窗 0 → `baseline_zero` 不触发，试算可见。
- 「`ratio(status:500) > 5`」：13 / 180 → 触发；本窗 0 行 → 不触发。
- 「`count_uniq(client_ip) > 50`」63 → 触发；「`quantile 0.95 duration > 2000`」2310.5 → 触发，字段非数值 → 试算显示 `not_numeric`。
- 无数据开关：host-b 上一窗 300 条、本窗 0 条 → 一条无数据告警，级别 warning；host-a 正常不受影响。
- `trigger_count = 3`：仅最近两窗满足 → 不触发，试算 `streak = 2`。
- 试算查询次数：`N × (1 + 不同对照数)` 且 ≤ 5 × 5。

### 已确认成立的现网事实

- `_build_aggregation_query` / `_extract_aggregate_data` / `_check_rule_conditions` 是聚合判定的三处落点；`evaluate_aggregate` 已把查询与判定抽成只读函数，试算复用。
- `_query_previous_window_counts` 已按「同一基础查询换起止」实现，对照窗只是起止不同。
- VictoriaLogs LogsQL 文档确认：`count() if (<filters>) as name`、`count_uniq(field) limit N as name`、`quantile(phi, field) as name`、`sum_len(field)`、`stats by (...)` 同一查询内可混用多个函数。
- 第一批已提交但未发版，`count_delta` 归一不构成对外契约破坏；仍保留接受以防表单缓存载荷。
- 监控侧 `COMPARE_MODE_*` / `COMPARE_VALUE_KIND_*` 词汇可直接复用于中文文案。

### 决策记录

- **函数 × 比较方式 × 对照，替代函数枚举**：七个可比较函数乘三种比较方式是二十一种组合，正交字段把表单压成两个下拉、校验压成两张表；与监控 `compare_mode` 同一套词，客户两边看到的是一回事。第一批「函数枚举」决策据此替代。
- **对照窗跑同一条聚合查询而不是只查 count**：代价相同（一次查询），换来 Datadog Change Alert 全覆盖；`count_delta` 的「缺分组记 0」只对计数类成立，均值 / 分位缺分组是「没有值」，所以区分 0 与 `None`。
- **占比用 `count() if`，不开第二条查询**：VictoriaLogs 原生支持，分子分母同窗同分组同过滤，天然对齐；Elastic 的「两条查询相除」是因为 ES 没有条件计数，不必照搬。
- **无数据是策略级开关而不是 `count < 1` 条件**：竞品都叫无数据告警，监控已有「无数据」概念；`count < 1` 需要凭空造 0 行并与分组语义纠缠。有分组时以上一等长窗为分组全集，是 Loki `absent_over_time` 的按流语义。
- **连续次数无状态实现**：重查前 N−1 窗与现有补偿扫描同一路数，不新增游标表；N ≤ 5 限住查询放大。
- **不做公式编辑器**：表达式框让校验、试算、回跳、通知渲染全部退化成字符串；上面十个命名函数加两个下拉覆盖同样场景。
