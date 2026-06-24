# 监控阈值告警触发条件设计

## 背景

监控策略当前的阈值告警逻辑是：每次策略扫描查询汇聚周期内的数据，计算阈值，若本轮结果满足阈值，则立即生成 threshold 事件并创建或更新告警。

这会让短时毛刺直接触发告警。产品已将需求调整为使用底层已预留的连续点判断能力：

```text
触发条件：连续 N 个汇聚周期结果满足告警阈值，触发告警。
```

默认值为 `1`。用户已有监控策略、全部告警模板也使用该默认值。

本地代码确认，底层阈值计算已预留单次检测内“多点连续满足才触发”的能力：

- `server/apps/monitor/tasks/utils/policy_calculate.py`
- `calculate_alerts(alert_name, df, thresholds, template_context=None, n=1)`
- 该函数会取 `row["values"][-n:]`，并要求这些点全部满足同一阈值条件。

因此本次设计不需要新增跨扫描状态表，只需要把策略配置中的连续点数传入现有 `calculate_alerts(..., n)`，并明确连续点触发时的告警等级选择规则。

## 目标

- 阈值告警支持“连续 N 个汇聚周期结果满足告警阈值后触发”。
- 默认配置为 `trigger_count=1`，保持现有行为不变。
- 用户已有监控策略通过数据迁移获得默认值。
- 所有告警模板默认配置包含同样默认值。
- 该触发条件只作用于 threshold 告警，不作用于 no_data 告警。
- 复用现有 `calculate_alerts(..., n)`，避免重复实现阈值比较、单位格式化、维度解析和告警内容模板。
- 连续 N 个点满足多个等级阈值时，按最高告警等级生成告警。

## 非目标

- 不改变无数据告警的触发和恢复逻辑。
- 不改变自动恢复语义；自动恢复仍表示活跃告警连续多少个检测周期不满足阈值后恢复。
- 不做“最近 X 次检测累计 N 次命中”的跨扫描滑动窗口。
- 不新增扫描状态表。
- 不调整阈值配置结构或告警名称模板变量。

## 推荐方案

新增一个策略配置字段，用于控制本轮检测结果中需要连续满足阈值的点数。

### 策略字段

在 `MonitorPolicy` 增加字段：

```text
trigger_count: SmallIntegerField(default=1)
```

字段含义：

- `trigger_count`：需要连续满足阈值的汇聚周期结果数量 N。

校验规则：

- `trigger_count >= 1`
- `trigger_count` 必须是整数。

旧策略迁移时统一补 `1`。

字段命名选择 `trigger_count`，避免和自动恢复的 `recovery_condition` 混淆；UI 文案展示为“连续 N 个汇聚周期结果满足告警阈值，触发告警”。

## 查询与计算语义

每次策略扫描仍按当前策略的查询周期和汇聚周期查询一段时间序列，然后在返回数据中取最近 N 个点判断是否连续满足阈值。

示例：

```text
检测频率 schedule = 5 分钟
汇聚周期 period = 5 分钟
触发条件 trigger_count = 2
```

一次扫描会按现有查询逻辑拿到汇聚后的时间序列，例如：

```text
10:00  70
10:05  91
10:10  92
```

扫描时取最近 2 个点：

```text
10:05  91
10:10  92
```

如果这两个点都满足同一等级阈值，则触发告警；只要其中一个点不满足，就不触发。

这不是跨两次 Celery 扫描累计结果，而是单次查询结果内最近 N 个汇聚点连续满足。

## 阈值等级选择

当前 `calculate_alerts()` 会按 `thresholds` 列表顺序遍历，找到第一个满足条件的阈值就生成事件并 `break`。本次需求增加“取最高告警等级”，因此需要在连续 N 点判断时确保等级优先级稳定。

推荐实现：

1. 在计算前按告警等级权重排序阈值：
   - `critical`
   - `error`
   - `warning`
   - `info`
2. 对每个等级阈值，检查最近 N 个点是否全部满足该阈值。
3. 第一个满足的等级就是最高告警等级。
4. 告警事件的 `value` 使用最近一个点的值，保持现有展示和事件记录语义。

示例：

```text
阈值：
critical > 90
error    > 80
warning  > 70

最近 2 个点：
85, 95
```

结果：

- `critical > 90`：85 不满足，不触发 critical。
- `error > 80`：85 和 95 都满足，触发 error。
- 最终等级为 `error`，不是 `critical`。

如果最近 2 个点是：

```text
91, 95
```

则两个点都满足 critical，最终等级为 `critical`。

## 数据流

### 当前阈值扫描路径

```text
scan_policy_task
  -> MonitorPolicyScan.run()
    -> AlertDetector.detect_threshold_alerts()
      -> MetricQueryService.query_aggregation_metrics()
      -> calculate_alerts(..., n=1)
    -> AlertDetector.count_events()
    -> AlertDetector.recover_threshold_alerts()
    -> EventAlertManager.create_events_and_alerts()
```

### 新阈值扫描路径

```text
scan_policy_task
  -> MonitorPolicyScan.run()
    -> AlertDetector.detect_threshold_alerts()
      -> MetricQueryService.query_aggregation_metrics(policy.period)
      -> convert_metric_values(...)
      -> calculate_alerts(..., n=policy.trigger_count)
    -> AlertDetector.count_events()
    -> AlertDetector.recover_threshold_alerts()
    -> EventAlertManager.create_events_and_alerts()
```

当 `trigger_count=1` 时，行为与当前系统一致。

当 `trigger_count>1` 时，`calculate_alerts()` 如果发现返回点数少于 N，会跳过该维度，不生成告警事件。这沿用现有预留逻辑：

```python
values = row["values"][-n:]
if len(values) < n:
    continue
```

## 查询范围要求

为了让 `trigger_count > 1` 有足够数据点，策略扫描查询必须能返回至少 N 个汇聚结果点。

现有 `MetricQueryService.query_aggregation_metrics(policy.period)` 的返回点数取决于当前查询构造、时间范围和 step。实现时需要验证：

- 当前查询结果是否已经包含多个汇聚点。
- 若只返回单点，需要扩展查询范围为 `period * trigger_count` 或等价时间窗口。
- 扩展查询范围时，单个汇聚点仍使用原 `period` 语义，不能把 N 个周期合成一个大周期。

推荐规则：

```text
查询时间范围 = period * trigger_count
汇聚步长/汇聚周期 = period
取最近 trigger_count 个汇聚结果点
```

这样 `trigger_count=2` 时，系统可以拿到最近两个汇聚周期各自的计算结果，再判断两个点是否连续满足阈值。

## 活跃告警行为

触发条件只改变“是否生成 threshold 事件”的判定，不改变活跃告警后的生命周期。

- 最近 N 个点不连续满足阈值：生成 `info_events`，不创建 threshold 事件和告警。
- 最近 N 个点连续满足阈值：生成 threshold 事件，按现有逻辑创建或更新告警。
- 已有活跃 threshold 告警时，后续连续满足更高等级阈值仍按现有 `EventAlertManager` 升级逻辑处理。
- 自动恢复仍由 `info_event_count` 和 `recovery_condition` 控制。

需要注意：如果最近 N 个点未连续满足任何阈值，则该维度应进入 `info_events`，从而让已有活跃告警的自动恢复计数正常增加。

## 无数据告警

无数据告警完全不读取 `trigger_count`。

现有流程保持：

```text
AlertDetector.detect_no_data_alerts()
AlertDetector.recover_no_data_alerts()
```

这符合已确认范围：触发条件只用于阈值告警，不用于无数据告警。

## API 与序列化

`MonitorPolicySerializer` 增加字段校验：

- 缺省时使用模型默认值。
- 非整数、0、负数返回明确错误。

NATS 创建策略路径复用同一个 serializer，因此自动获得校验和默认值。

批量模板创建路径 `build_bulk_policy_payloads()` 需要把配置透传到策略 payload：

```text
trigger_count = config.get("trigger_count", template.get("trigger_count", 1))
```

## 前端设计

### 策略详情页

位置：`web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`

在自动恢复上方新增 Form.Item：

```text
触发条件：连续 [trigger_count] 个汇聚周期结果满足告警阈值，触发告警。
```

交互规则：

- 输入框为整数输入。
- 最小值 1。
- 默认值 1。

`page.tsx` 新增表单回填：

- 新增模式初始化 `trigger_count=1`。
- builtIn 模式读取模板值，缺省回退 `1`。
- 编辑旧策略时后端已有默认值；前端仍做兜底。
- 提交时随策略 payload 传给 `/monitor/api/monitor_policy/`。

### 批量模板应用

位置：

- `web/src/app/monitor/(pages)/event/template/bulkApplyModal.tsx`
- `web/src/app/monitor/(pages)/event/template/templateBulkUtils.ts`

默认配置增加：

```text
trigger_count: 1
```

共享配置步骤中增加同样的触发条件输入。`normalizeBulkConfig()` 保留或补齐默认值，`buildBulkApplyPayload()` 原样提交。

## 告警模板默认配置

`PolicyTemplate.templates` 是从各插件 `policy.json` 导入到数据库的 JSON 模板。默认配置建议在模板读取和策略生成入口统一补齐，避免批量修改所有模板文件：

- `PolicyService.get_policy_templates()` 返回模板时，为每个 template 补 `trigger_count=1`。
- `build_bulk_policy_payloads()` 生成策略时优先使用批量配置，其次使用模板字段，最后回退 `1`。
- 单模板 builtIn 创建时，前端读取 `sessionStorage.strategyInfo` 中的模板字段；缺省回退 `1`。

如果后续需要某些模板默认连续 2 个点才触发，可在对应模板 JSON 中显式配置：

```json
{
  "trigger_count": 2
}
```

## 配置变更影响

本方案不新增扫描状态表，因此策略删除、禁用、范围变更不需要清理触发状态。

如果修改以下字段，下一轮扫描自然按新配置计算：

- `threshold`
- `algorithm`
- `period`
- `trigger_count`
- `query_condition`
- `group_by`
- `source`

已有的策略配置变更告警收敛逻辑仍按现有设计处理活跃告警，不因本次字段新增改变。

## 错误处理

- `trigger_count` 缺失时按 `1` 处理，兼容旧数据和旧调用方。
- 查询返回点数少于 `trigger_count` 时，该维度不触发阈值告警，并应进入 `info_events`。
- 阈值 method 非法仍沿用现有 `BaseAppException`。
- 单位转换失败或查询失败沿用现有扫描失败处理。

## 测试策略

### 后端

新增或扩展测试：

1. `MonitorPolicySerializer` 接受合法 `trigger_count`。
2. serializer 拒绝 `trigger_count < 1` 和非整数。
3. 默认 `trigger_count=1` 下，第一次阈值命中即可创建告警，保持现有行为。
4. `trigger_count=2` 下，最近两个汇聚点都满足 warning 阈值才触发 warning。
5. `trigger_count=2` 下，最近两个汇聚点只有一个满足阈值时不触发，并产生 info event。
6. `trigger_count=2` 下，最近两个点同时满足多个等级阈值时取最高连续满足等级。
7. `trigger_count=2` 下，`85, 95` 对 `critical>90/error>80/warning>70` 触发 `error`。
8. no_data 告警不读取触发条件，行为不变。
9. 批量模板 payload 默认包含 `trigger_count=1`。

最小验证命令：

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_policy_serializer_validation.py apps/monitor/tests/test_policy_bulk_payload.py apps/monitor/tests/test_alert_name_template.py -q
```

若改动涉及查询范围或扫描流程，再补充执行：

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_scan_failure_handling.py apps/monitor/tests/test_policy_preview_query.py -q
```

### 前端

新增或扩展脚本测试：

```bash
cd web && pnpm exec tsx scripts/monitor-template-bulk-logic-test.ts
```

重点覆盖：

- `normalizeBulkConfig()` 补齐默认触发条件。
- `buildBulkApplyPayload()` 保留触发条件配置。
- 无数据告警开关不影响触发条件字段。

如果策略详情页已有可测工具函数，可补充新增/编辑/内置模板三种初始值归一化测试。

## 风险与控制

### 风险

- 如果当前查询只返回一个汇聚点，直接传 `n=2` 会导致永远无法触发。
- 阈值列表如果未按等级优先级排序，可能无法稳定取最高告警等级。
- 扩展查询范围时，如果把多个周期合成一个大周期，会偏离“连续 N 个汇聚周期结果”的语义。

### 控制

- 实现前先用测试锁定 `calculate_alerts(..., n=2)` 的连续点行为。
- 在 `calculate_alerts()` 内或调用前按 `AlertConstants.LEVEL_WEIGHT` 对阈值排序，保证最高等级优先。
- 查询范围扩展为 `period * trigger_count`，但单点汇聚语义仍保持 `period`。
- 默认 `trigger_count=1` 保持现有用户体验，降低上线风险。

## 预期结果

完成后，用户可以在阈值告警策略中配置“连续 N 个汇聚周期结果满足告警阈值才触发告警”。短时单点毛刺不会立刻创建新阈值告警；连续多个汇聚点都异常时才触发，并按连续满足的最高告警等级生成告警。旧策略和模板默认采用 `1`，行为与当前系统兼容。
