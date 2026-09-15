# Monitor 告警计算方式丰富

Status: ready

需求来源：CTeam `p398_714`【监控系统】告警计算方式丰富；三域覆盖目录见
[PR #28](https://github.com/baiyf-git/bk-lite/pull/28)。本 spec 只覆盖 Monitor，
APM / Log 另起 change。

## Problem Statement

腰部私有化客户配监控策略只能写「当前值 vs 固定阈值」。早高峰、发布窗口、日常潮汐都会被当成故障。客户真正想说的是：

1. 看分布不看均值：「接口延迟 P95 > 200ms」。
2. 看相对变化不看绝对水位：「比刚才多了 200 个错误」「比 1 小时前同窗高 50%」「按这个速度还有多久写满」。
3. 配完先验：相对计算配错的代价是静默误报，现场没人帮他们盯一夜。

现网策略页汇聚方式只有 avg / max / min / sum / count / last，没有比较基准，恢复只能「连续 N 次不再满足触发阈」，无数据检测窗和恢复窗在表单里被写成同一个值，曲线预览只画线不回答「会不会响」。

## Solution

策略仍是三句话，对应三个可叠加的槽位，不是互斥下拉：

| 用户要说的 | 表单位置 | 字段 |
|---|---|---|
| 这个数怎么来 | 定义指标 · 汇聚方式 | `algorithm`（扩枚举） |
| 相对谁 | 告警条件 · 比较基准 | `compare_mode` + `compare_value_kind` |
| 怎么比线 | 告警条件 · 阈值 / 恢复阈值 / 连续 N | `threshold` + 可选 `recovery_threshold` |

扫描、预览、试跑共用同一条查询编译；缺对照、除零、非有限值统一「本轮不触发 + 原因」。策略页新增独立「试跑」按钮，只读复用扫描判定，不落告警、事件、快照、通知。

用户不写 PromQL / Zabbix 表达式；对外不说「对齐 Zabbix」。

### 能力清单

进方案：

| 能力 | 槽位 | 引擎依据 |
|---|---|---|
| 已有：公式、avg/max/min/sum/count/last、绝对值、多级阈值、连续 N、无数据 | 保持 | 现扫描链 |
| P90 / P95 / P99 | 汇聚方式 | `quantile_over_time`，窗内点值分位 |
| 标准差 | 汇聚方式 | `stddev_over_time` |
| 条件计数（窗内满足内阈的点数） | 汇聚方式 | `count_over_time` 套比较谓词 |
| 速率 | 汇聚方式（逐序列类） | `rate` |
| 变化次数 | 汇聚方式（逐序列类） | `changes` |
| 斜率（含单调增 / 减 / 该涨却停） | 汇聚方式（逐序列类） | `deriv` |
| 变化量 Δ / % | 比较基准 | `offset <汇聚周期>` |
| 1h / 24h / 7d / 30d 同窗 | 比较基准 | `offset`；文案「N 前同窗」，不写「昨天 / 上月」 |
| 近 4 周同窗均值 | 比较基准 | 4 个 `offset 7d·k` 求均 |
| 距容量线剩余时间 | 比较基准 | `(target - q) / deriv(q[回看窗])` |
| 滞回（独立恢复阈值） | 阈值旁 | 判定层 |
| 无数据检测窗 / 恢复窗分开 | 无数据 | 模型已分开，补表单绑定 |
| 试跑 | 独立按钮 | 只读复用 `AlertDetector` |

不进表单：直方图分位（采集目录几乎没有 `_bucket`）、季节分解 / 异常检测（引擎没有）、日历「昨天 / 上月 / 去年」（用 N 前同窗）、任意分位滑条、手写对照 PromQL、维护窗 / 静默 / 抑制（归告警中心）。

`offset_30d` 与近 4 周基线依赖 VictoriaMetrics 留存（分别需 ≥ 31 天、≥ 22 天）。留存后续改为可配置；本 change 不砍这两项，留存不足时按缺对照处理并在预览 / 试跑写明原因。

## User Stories

1. 作为现场运维，我想在汇聚方式里直接选 P95，让「延迟 P95 > 200ms」不必用均值硬套，也不写 `quantile_over_time`。
2. 作为现场运维，我想选「相对上一等长窗 / 1 小时前同窗 / 24 小时前同窗 / 7 天前同窗 / 30 天前同窗 / 近 4 周同窗均值」并用 Δ、% 或倍数比线，让潮汐波动不再被当成故障。
3. 作为现场运维，我想给磁盘配「按当前斜率距 90% 还剩 < 24 小时」，提前处理容量。
4. 作为现场运维，我想让 P95 和「比 1 小时前同窗高 50%」叠在一条策略里，不必二选一。
5. 作为现场运维，我想对计数器指标选「速率」，对状态类指标选「变化次数」，对水位类指标选「斜率」，而不用知道 rate / changes / deriv。
6. 作为现场运维，我想配「窗内超过内阈的点数 ≥ N」，表达「失败超过 N 次」。
7. 作为现场运维，我想触发 > 80、恢复 < 70，让 79～81 抖动不再振铃；不填恢复阈值时行为和现在完全一样。
8. 作为现场运维，我想无数据检测 10 分钟、恢复 2 分钟分别可配。
9. 作为现场运维，我想在保存前点「试跑」，逐实例看到会触发 / 不触发 / 无数据 / 对照缺失 / 样本不足以及当前值、对照值、阈值；试跑后告警列表、通知、告警中心没有任何新记录。
10. 作为值班人员，我想告警内容和快照里同时看到当前值、对照值和变换后的比较值（含正确单位），知道「-35%」是相对谁。
11. 作为既有客户，我不改旧策略就保存，扫描结果与升级前完全一致。
12. 作为售前，我需要表单里不出现 PromQL 框、不出现「环比 5m」「昨天」，也不出现第二套 P95。

## Implementation Decisions

### D1. 字段与枚举

`MonitorPolicy` 新增字段，缺省对存量策略无感：

```text
compare_mode        absolute | previous_window | offset_1h | offset_24h | offset_7d | offset_30d | baseline_4w | timeleft   默认 absolute
compare_value_kind  "" | delta | percent | ratio | hours
count_predicate     {} | {"method": ">", "value": 80}   仅 algorithm = count_if_over_time 必填
forecast_target     null | number                        仅 timeleft 必填
forecast_lookback   {"type": "hour", "value": 1}         仅 timeleft，默认 1h，允许 1h / 4h / 24h
recovery_threshold  {} | {"method": "<", "value": 70}    空 = 沿用「不再满足触发阈」
```

`algorithm` 扩白名单并分两类编译：

- 窗口聚合类：现有 `*_over_time` + `p90_over_time` / `p95_over_time` / `p99_over_time` / `stddev_over_time` / `count_if_over_time`
- 逐序列类：`rate` / `changes` / `deriv`

条件计数用独立枚举 `count_if_over_time`，不复用 `count_over_time`；后者仍是「窗内样本点数」，历史映射不动。

算法白名单单一来源在 `policy_methods`，serializer、模板归一化、迁移测试全部从它导入，不再手抄第五份。

### D2. 查询编译：拆「存在性」与「比较」两条

现网 `MetricQueryService.query_aggregation_metrics` 同时喂阈值判定、无数据检测、无数据恢复和 `PolicyBaselineService` 基线同步。对照窗缺失时 VictoriaMetrics 不返回该序列，若把变换编进这条查询，会误报无数据、建不出基线。因此拆为两条：

- **存在性查询** `query_existence_metrics(period)`：固定 `last_over_time((group_algorithm(base) by (g))[period:step])`，不带 `algorithm` 变换和 `compare_mode`。供无数据检测、无数据恢复、基线同步、试跑的 `no_data` 判定使用。
- **比较查询** `query_comparison_metrics(period, points)`：带全部变换。供阈值判定、预览、试跑、快照记录（含告警前快照）使用。

编译入口统一为 `compile_policy_query(policy_like) -> str`，`PolicyPreviewService`、`AlertDetector`、`SnapshotRecorder`、试跑服务只调它，不再各自拼字符串。`SnapshotRecorder` 告警前快照不再直接查 `METHOD[algorithm]`。

编译形态（来自现网两段结构，φ 是 `quantile_over_time` 第一个参数）：

```text
# 窗口聚合类（现网形态不变）
avg_over_time((avg(m) by (g))[5m:10s])
quantile_over_time(0.95, ((avg(m) by (g))[5m:10s]))
stddev_over_time((avg(m) by (g))[5m:10s])
count_over_time(((avg(m) by (g)) > 80)[5m:10s])            # count_if_over_time，谓词不加 bool

# 逐序列类：先逐序列算，再分组
avg(rate(m[5m])) by (g)
avg(changes(m[5m])) by (g)
avg(deriv(m[5m])) by (g)

# 比较基准包在最外层，一次 MetricsQL；q 为上面任一结果
q - q offset 5m                                             # previous_window · delta
(q - q offset 1h) / (q offset 1h) * 100                     # offset_1h · percent
q / (q offset 24h)                                          # offset_24h · ratio
(q - b) / b * 100,  b = (q offset 7d + q offset 14d + q offset 21d + q offset 28d) / 4   # baseline_4w
clamp_min(forecast_target - w, 0) / clamp_min(deriv((avg(m) by (g))[1h:step]), 1e-9) / 3600   # timeleft · hours
```

`timeleft` 的 `w` 为 `last_over_time` 水位，不套 `algorithm`；斜率背离容量线或 ≈ 0 时结果为 `+Inf` 或 0 → 由判定层的非有限值过滤和 `< 阈值` 语义自然不触发。

公式策略：先 `build_formula_query`，再套窗口聚合类与比较基准；逐序列类对公式禁用。Trap 策略编译短路，行为不变。

切片 1 必须在部署的 VictoriaMetrics 版本上实跑确认两点，写入验收记录：`expr offset 1h` 作用于聚合结果外层被接受；`rate(expr[5m])` 对非裸选择器的隐式子查询被接受。

### D3. 结果单位解析替代固定单位换算

现网按 `metric_unit → calculation_unit` 换算 VM 值、阈值和展示单位。变换后结果不再是指标量纲时必须停用。新增 `resolve_result_unit(policy_like)`：

| 变换 | 结果单位 |
|---|---|
| `*_over_time`、分位、标准差、`delta` | 沿用指标量纲，换算照旧 |
| `percent` | `percent`，停用换算 |
| `ratio` | 无量纲，停用换算 |
| `hours` | `hour`，停用换算 |
| `rate` / `deriv` | 指标量纲 / 秒；前端阈值单位选项按「速率体系」过滤，后端停用体系换算 |
| `changes` / `count_if_over_time` | `count`，停用换算 |

`convert_metric_values`、`convert_thresholds`、`get_display_unit`、前端阈值单位选项、阈值单位选择器可见性、预览图单位都改用该解析。Enum 指标禁用全部新 `algorithm` 与非 `absolute` 的比较基准。

### D4. 组合禁则（serializer 一次拒绝，不拖到扫描）

| 禁止 | 原因 |
|---|---|
| `timeleft` + `algorithm` 非 avg/max/min/last 类 | 预测只对水位 |
| `timeleft` + 任何对照窗 / 基线 | 变换套变换 |
| `count_if_over_time` + 非 `absolute` | 先算次数再比对照，语义缠绕 |
| `rate` + 编译后基础查询已含 `rate` / `irate` / `increase` | 大量 SNMP 指标查询已是 `rate(...)[5m]` |
| 逐序列类 + 公式 | 比值的 rate / changes 无意义 |
| Enum 指标 + 任何新算法或非 `absolute` | 枚举不是连续量 |
| 汇聚周期等于对照 offset（如 5m 策略选环比 5m） | 与变化量撞车；表单不出现该项 |
| 非法分位、`compare_value_kind` 与 `compare_mode` 不匹配 | `previous_window`/`baseline_4w` 只允许 delta/percent；`offset_*` 只允许 percent/ratio；`timeleft` 只允许 hours |
| `recovery_threshold` 方向与触发阈相同侧 | 触发 `>80` 时恢复必须是 `<` 或 `<=` |
| 无数据检测窗 < 恢复窗 | 语义倒置 |
| Trap 策略携带任何新字段 | 忽略并清空 |

`offset_7d` / `offset_30d` / `baseline_4w` 保存不拦，留存不足按缺对照处理。

### D5. 判定：第三类事件与滞回

`calculate_alerts` 返回从两类扩为三类：`alert_events`（触发）、`info_events`（已越过恢复线或未配恢复阈值时不满足触发阈）、`hold_events`（滞回带内）。

- `count_events` 只对 `info_events` 累加 `info_event_count`，对 `alert_events` 清零，对 `hold_events` 不增不清。
- 快照记录接收 `info_events + hold_events + alert_events`，带内点作为普通扫描点。
- `recovery_threshold` 是一条线，作用于告警整体恢复；多级阈值只升不降的语义不变。
- 未配 `recovery_threshold`：判定与现在完全一致。

缺对照的行 VM 不返回，行不进任何一类：活动告警既不新建也不恢复（保持）。这是既定语义，试跑显示为 `missing_baseline`。

`_parse_finite_float` 继续过滤 `inf/nan`，除零和背离斜率靠它自然不触发。

### D6. 无数据双窗

模型已有 `no_data_period` 与 `no_data_recovery_period`。改动仅在策略页保存逻辑：不再把恢复窗写成检测窗，表单露出两个时长；serializer 校验检测窗 ≥ 恢复窗。存在性查询保证新 `algorithm` / `compare_mode` 不影响无数据路径。

### D7. 试跑

新增内部端点 `monitor_policy/dry_run`，不扩现有 `preview`。

- payload 与保存同源，先过同一 serializer 与 D4 禁则。
- 权限：`strategy_list-Add` 或 `strategy_list-Edit`；实例按策略可见范围服务端二次过滤（沿用 `InstanceConfigService._get_authorized_monitor_instances`），fail-closed。现有 `preview` 同步补权限装饰器并对 `preview.instance_id_values` 做同样过滤。
- 内存构造策略对象并显式设置 `last_run_time = now`；调用与扫描相同的 `AlertDetector` 阈值判定（含 `trigger_count` 的最近 N 个汇聚点），不调 `EventAlertManager`，不写 Alert / Event / 快照，不通知，不推告警中心，不推进 `last_run_time`。
- 同时执行存在性查询：实例不在存在性结果中 → `no_data`；在存在性结果中但不在比较结果中 → `missing_baseline`；比较结果点数 < `trigger_count` → `insufficient_samples`。`no_data` 判定不依赖 `PolicyInstanceBaseline`，草稿也能评。
- 已保存策略且存在活动告警时，按 D5 结果标 `would_recover` / `hold`；草稿不评恢复。
- 实例上限 200，超出截断并说明；预览当前选中实例必须包含。
- 返回逐实例：`verdict ∈ {would_trigger, ok, hold, would_recover, no_data, missing_baseline, insufficient_samples}`、`current_value`、`baseline_value`、`compared_value`、`result_unit`、`matched_threshold`、`reason`；`trigger_count > 1` 时附「本轮命中 k/N，现网不会建告警」，不得显示成会建单。
- 试跑不经过现网把整段 VM 返回打 INFO 的日志分支；失败只记一条 WARNING，带策略 ID（草稿为空）、`failed_stage`、`error_type`，不记查询正文和响应体。

### D8. 快照、通知与告警详情

- 快照点在 `raw_data` 之外记录 `current_value`、`baseline_value`、`compared_value`、`result_unit`，告警详情图按 `result_unit` 画并显示对照值。
- 告警模板 `${value}` 渲染变换后的比较值并带结果单位；新增 `${current_value}`、`${baseline_value}` 变量。
- 快照 `_MAX` 与生命周期语义不变。

### D9. 模板与可移植

策略模板归一化和 portable 导出 / 导入包含全部新字段；缺省值与 D1 一致。旧模板不含新字段时行为与现在相同。

### D10. 表单

- 汇聚方式追加：P90 / P95 / P99 / 标准差 / 条件计数 / 速率 / 变化次数 / 斜率。条件计数展开内阈运算符与值。Tooltip 写明：分位基于窗内约 30 个采样点（5 分钟窗 P99 接近最大值）；速率仅适用于单调计数器；斜率单位为「指标单位 / 秒」。
- 告警条件在阈值上方新增「比较基准」：当前值（默认）/ 相对上一等长窗 / 1 小时前同窗 / 24 小时前同窗 / 7 天前同窗 / 30 天前同窗 / 近 4 周同窗均值 / 距容量线剩余时间。随之出现 Δ / % / 倍数 / 小时选择；`timeleft` 再出现容量线与回看窗。结果单位不是指标量纲时阈值单位锁死。
- 恢复条件旁新增可选「恢复阈值」，占位「不填则与触发线相同」。
- 无数据拆「检测窗」「恢复窗」。
- 右侧预览仍叫预览：比较基准非当前值时叠画当前曲线与对照曲线，阈值线按结果单位；试跑是另一个按钮，结果以表格展示。
- 布局用 Tailwind `className`，沿用现有 `w-[100px]` 标签宽与 AntD 组件；不新增 SCSS Module，不硬编码色值。

## Testing Decisions

好的测试只锁外部行为：编译出的 MetricsQL 字符串、serializer 接受 / 拒绝、判定三类事件的划分、试跑响应与零副作用、单位解析结果。不测内部私有方法的调用次数。

后端（沿用 `apps.monitor.tests` 既有 pytest 风格，sqlite 内存库，`METHOD` / VM API 用 monkeypatch）：

- 编译：每个新 `algorithm` × 每个 `compare_mode` 锁 PromQL 字符串；公式路径；Trap 短路；`rate` 对已含 `rate(...)` 的基础查询拒绝。先例：`test_policy_methods_service`、`test_formula_compiler`。
- serializer：D4 每条禁则一个拒绝用例 + 对应合法组合一个接受用例；存量 payload（无新字段）接受且缺省正确。先例：`test_monitor_policy_serializer_validation`、`test_api_boundary_validation`。
- 存在性 / 比较拆分：对照缺失时无数据检测不产生事件、基线同步仍能建基线；`rate` 单样本窗不误报无数据。先例：`test_policy_scan_alert_detector`、`test_policy_baseline`。
- 判定：滞回 70～80 带内进 `hold_events`，`info_event_count` 不变；未配恢复阈值与旧行为逐点一致；`trigger_count` 与 offset 共存；缺对照行不进任何一类。先例：`test_policy_calculate_service`、`test_policy_scan_scanner`。
- 单位：每种变换的结果单位；`percent` / `ratio` / `hours` / `count` 下不换算 VM 值与阈值；`display_unit` 正确。先例：`test_metric_query_trigger_count`、单位换算相关测试。
- 试跑：草稿与已保存两种入口；越权实例被过滤（fail-closed）；`no_data` / `missing_baseline` / `insufficient_samples` / `would_trigger` / `hold` / `would_recover` 各一；调用后 `MonitorAlert` / `MonitorEvent` / 快照计数不变、通知与告警中心投递 mock 未被调用、`last_run_time` 未变；`trigger_count > 1` 文案。先例：`test_policy_preview_service`、`test_monitor_permission_business_flows`。
- 快照与模板：快照点含对照值；`${value}` / `${current_value}` / `${baseline_value}` 渲染；portable 导出 / 导入包含新字段；旧模板缺省。先例：`test_policy_template_portability`、`test_policy_templates_aggregation`。
- 日志回归：试跑失败路径只产生一条 WARNING，模板与独立参数校验，敏感哨兵（查询正文、VM 响应）不出现在任何等级日志。

前端（沿用 `web/scripts/monitor-policy-formula-payload-test.ts` 与 `__tests__` 风格）：

- 保存 payload：各组合字段正确；无数据双窗分别写入；Trap 不带新字段。
- 结果单位驱动的阈值单位选项与选择器可见性。
- 试跑结果表渲染各 verdict 与连续 N 次文案。
- `pnpm lint` 与相关 `pnpm test:*`；改布局后 `pnpm type-check`。

验收记录必须附：在部署 VictoriaMetrics 版本上实跑 `offset` 外层写法与非裸选择器 `rate` 的结果。

## Out of Scope

- APM、Log 的计算方式与试算。
- 直方图分位、季节分解、异常检测、离群、任意 AND/OR 复合条件。
- 日历对齐的「昨天 / 上月 / 去年」。
- 维护窗、静默、级别抑制、通知编排、升级分派（告警中心）。
- 三域公共扫描库或 `calc_mode` 公共模型。
- 试跑做成 24 小时历史回放。
- VictoriaMetrics 留存时间可配置（另起 change）。
- 现网 `_log_alert_events` 将 VM 全量响应打 INFO 的清理（试跑绕开即可，不在本 change 修）。
- 探针安装、覆盖一览、采集插件、仪表盘。

## Further Notes

### 切片顺序（可独立验收，不可并行抢工时的约束见后）

1. **编译骨架**：`compile_policy_query`、存在性 / 比较拆分、`resolve_result_unit`、算法白名单单一来源、D4 禁则、分位 + 上一窗 / 1h / 24h、预览叠对照、旧策略回归、VM 版本实跑确认。
2. **其余函数与长对照**：标准差、条件计数、速率（拒重包）、变化次数、斜率、7d / 30d、近 4 周基线、timeleft、快照记录改走编译。
3. **试跑**：端点、权限（含补 `preview`）、四种非触发原因、零副作用、连续 N 次文案、页面入口与结果表。
4. **滞回 + 无数据双窗 + 展示收口**：`hold_events`、恢复阈值、双窗表单、快照对照值、模板变量、portable、i18n、`ALGORITHM_LABELS`。

约束：切片 2 不得先于切片 1 的存在性 / 比较拆分与单位解析落地；切片 3 不得排到最后几天——相对计算没有试跑不算可上生产；切片 4 与切片 3 抢工时则整条推后，不拆半套。

### 主验收

- 旧策略不改保存，扫描、通知、快照与升级前逐点一致。
- P95 策略编译含 `quantile_over_time(0.95, …)`，扫描用分位不是均值。
- 本窗 120、上一窗 80：Δ = 40，% = 50；上一窗缺失则不建告警、不恢复、不误报无数据，试跑写「对照缺失」而不是「下降 100%」。
- 触发 >80、恢复 <70：越过 80 触发；70～80 保持活跃且 `info_event_count` 不增；低于 70 连续 N 次才恢复。
- 已是 `rate(...)` 的 SNMP 指标不能再选速率，保存被拒。
- `timeleft` 在斜率为负或 ≈ 0 时不触发。
- 无数据检测 10m、恢复 2m 分别落库并按各自窗口扫描。
- 试跑后 `MonitorAlert` / `MonitorEvent` / 快照 / 通知 / 告警中心均无新记录；越权实例不可选、接口也出不了数。
- 表单无 PromQL 框、无「环比 5m」、无「昨天」、无第二套 P95；文案为「N 前同窗」。
- 留存不足时 `offset_30d` / `baseline_4w` 在预览与试跑写明「留存不足 / 对照缺失」，不当 0。

### 已确认成立的现网事实

- `calculate_alerts` 已过滤 `inf/nan`，`values[-n:]` 不足 N 点时跳过该行。
- 缺对照时 VM 不返回序列 → 行不进任何事件类 → 活动告警保持。
- `enable_alerts` 已分开阈值与无数据；存在性查询落地后无数据路径完全不感知新字段。
- `MonitorPolicy.no_data_period` 与 `no_data_recovery_period` 已是两个字段，只需改前端赋值。

### 决策记录

- 百分位放汇聚方式（与 avg 同槽），比较基准放告警条件与阈值叠加。理由：「P95 比 1 小时前同窗高 50%」是真实说法，互斥模型做不出来。
- `offset_30d` 与近 4 周基线保留，不因默认留存砍掉；留存改为可配置另起 change。
- 条件计数独立枚举 `count_if_over_time`，不复用 `count_over_time`。
- 逐序列函数先逐序列算再分组；窗口聚合函数先分组再窗口。
- 试跑独立端点，不扩 `preview`；两者权限与实例过滤同步补齐。

## 切片 1 验收记录

VictoriaMetrics 实跑（本机 Docker 底座，不改 D1～D10）：

- 容器 `bklite-dev-victoria-metrics`
- 镜像 `bk-lite.tencentcloudcr.com/bklite/victoriametrics/victoria-metrics:v1.106.1`
- 接口 `http://127.0.0.1:8428/api/v1/query`

两点均 `status=success` 且返回实数，可以按现网外层 offset / 非裸选择器隐式子查询落地：

| 查询 | 结果 |
|---|---|
| `avg_over_time((avg(cpu_usage_user) by (instance_id))[5m:10s]) offset 1h` | success，1 条，value≈14.36 |
| `q - q offset 5m`（q 为上式无 offset） | success，1 条，value≈12.48 |
| `(q - q offset 1h) / (q offset 1h) * 100` | success，1 条，value≈95.80 |
| `rate((avg(cpu_usage_user) by (instance_id))[5m])` | success，1 条，value≈0.030 |
| `rate((avg(cpu_usage_user) by (instance_id))[5m:10s])` | success，1 条，value≈0.110 |
| `quantile_over_time(0.95, ((avg(cpu_usage_user) by (instance_id))[5m:10s]))` | success，1 条，value≈41.79 |

现场确认（不改写 D1～D10 原文）：

- `offset_7d` / `offset_30d` / `baseline_4w` 保存不拦、切片 1 不编译：表单选不到，不为此加拦截。
- 存在性查询用策略原汇聚、不套 `compare_mode`，不采用 D2 字面的固定 `last_over_time`。切片 2 上速率时再评估。

## 切片 2 验收记录

现场确认（不改写 D1～D10 原文）：

- 窗口聚合类（含 stddev、count_if、分位）存在性仍用策略原汇聚、不套对照。旧 avg 策略无数据字符串与升级前一致。
- 逐序列类 `rate` / `changes` / `deriv` 的存在性改用 `last_over_time((group(base) by g)[period:step])`，避免单样本窗误报无数据。比较查询仍先逐序列再分组。
- `offset_7d` / `offset_30d` 与 1h/24h 同形态；`baseline_4w` percent 为四窗均值对照；`timeleft` 水位固定 `last_over_time`、斜率用回看窗 `deriv`，预览只画剩余小时、不叠对照线。
- `count_if` 只允许 absolute；公式 + 逐序列编译拒绝；仅 `algorithm=rate` 且基础查询已含 `rate`/`irate`/`increase` 时拒重包。

## 切片 3 验收记录

现场确认（不改写 D1～D10 原文）：

- 新增内部端点 `monitor_policy/dry_run`，payload 与保存同源；`preview` 同步补 `strategy_list-Add` 或 `strategy_list-Edit`，越权 `preview.instance_id` fail-closed。
- 试跑内存构造策略、`last_run_time=now` 不落库；不写 Alert / Event / 快照，不调 EventAlertManager / 通知 / 告警中心。本机 Host `cpu_usage_total` 试跑前后计数均为 27 / 14196 / 24。
- 判定：`would_trigger`（CPU>1）、`ok`（CPU>80 未命中）、`missing_baseline`（`offset_30d` 对照缺失或留存不足）、`insufficient_samples` / `no_data` 由单测锁定；连续 N 文案「本轮命中 k/N，现网不会建告警」。
- `hold` 仍留切片 4（依赖扫描滞回）；已保存活动告警本轮不满足阈值时标 `would_recover`，草稿不评恢复。

## 切片 4 验收记录

现场确认（不改写 D1～D10 原文）：

- `calculate_alerts` 返回三类事件：未配 `recovery_threshold` 时 `hold_events=[]`，与升级前两类判定一致；触发 `>80`、恢复 `<70` 时 70～80 进 `hold_events`，`count_events` 不改 `info_event_count`。
- 试跑：已保存且活动告警 + 带内 → `hold`；草稿带内不评恢复 → `ok`。本机 Host `cpu_usage_total` 当前值≈21.14，触发 `>30`、恢复 `<10`、已保存活动告警试跑为 `hold`，`info_event_count` 仍为 3、告警状态仍为 `new`。
- 本机补跑 `migrate monitor 0069` 后策略 GET/POST 恢复。临时策略 POST 落库 `recovery_threshold={<, 70}`、无数据检测 `10m` / 恢复 `2m`，GET 核对后已删除。
- 快照点在 `raw_data` 之外带 `current_value` / `baseline_value` / `compared_value` / `result_unit`；告警详情图 `chart_unit` 在变换后量纲下用 `result_unit`；模板 `${value}` / `${current_value}` / `${baseline_value}`；portable 旧模板补 D1 缺省，`ALGORITHM_LABELS` 覆盖新算法。
