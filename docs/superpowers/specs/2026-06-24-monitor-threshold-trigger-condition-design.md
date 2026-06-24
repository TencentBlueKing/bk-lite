# 监控阈值告警触发条件设计

## 背景

监控策略当前的阈值告警逻辑是：每次策略扫描查询汇聚周期内的数据，计算阈值，若本轮结果满足阈值，则立即生成 threshold 事件并创建或更新告警。

这会让短时毛刺直接触发告警。产品希望在告警条件区域、自动恢复配置上方增加“触发条件”：

```text
触发条件：在 5 个周期内累计满足 1 次检测算法，触发告警。
```

默认值为 `5/1`。旧监控策略、所有告警模板默认配置也使用该默认值。

本地代码确认，底层阈值计算已预留单次检测内“多点连续满足才触发”的能力：

- `server/apps/monitor/tasks/utils/policy_calculate.py`
- `calculate_alerts(alert_name, df, thresholds, template_context=None, n=1)`
- 该函数会取 `row["values"][-n:]`，并要求这些点全部满足阈值。

但这次需求的语义是跨检测周期的滑动窗口：“连续 X 次检测中累计 N 次检测满足阈值”，不是单次检测查询结果中的最近 n 个数据点连续满足。因此设计需要复用现有单次检测判断能力，并在外层增加跨检测周期的触发状态。

## 目标

- 阈值告警支持“最近 X 次检测中累计 N 次满足阈值后触发”。
- 默认配置为 `trigger_window=5`、`trigger_count=1`，保持现有策略行为基本不变。
- 用户已有监控策略通过数据迁移获得默认值。
- 所有告警模板默认配置包含同样默认值。
- 该触发条件只作用于 threshold 告警，不作用于 no_data 告警。
- 复用现有 `calculate_alerts(..., n=1)` 作为“本轮检测是否满足阈值”的判定入口，避免重复实现阈值比较、告警内容模板、单位格式化和维度解析。

## 非目标

- 不改变无数据告警的触发和恢复逻辑。
- 不改变自动恢复语义；自动恢复仍表示活跃告警连续多少个周期不满足阈值后恢复。
- 不把“触发条件”解释为单次检测周期内的连续采样点数量。
- 不批量修改所有插件 `policy.json` 文件来硬编码默认值，除非后续产品要求模板文件本身显式带字段。
- 不调整告警等级判定优先级、阈值配置结构或告警名称模板变量。

## 推荐方案

新增策略配置字段，并新增轻量触发状态模型记录每个策略维度的检测窗口。

### 策略字段

在 `MonitorPolicy` 增加两个字段：

```text
trigger_window: SmallIntegerField(default=5)
trigger_count: SmallIntegerField(default=1)
```

字段含义：

- `trigger_window`：参与判断的最近检测次数 X。
- `trigger_count`：窗口内至少满足阈值的检测次数 N。

校验规则：

- `trigger_window >= 1`
- `trigger_count >= 1`
- `trigger_count <= trigger_window`

旧策略迁移时统一补 `5/1`。

### 触发状态模型

新增模型建议命名为 `PolicyTriggerState`：

```text
policy: ForeignKey(MonitorPolicy)
monitor_instance_id: CharField
metric_instance_id: CharField
dimensions: JSONField
recent_results: JSONField(default=list)
last_event_time: DateTimeField(null=True)
```

唯一约束：

```text
(policy, metric_instance_id)
```

`recent_results` 存储最近 X 次检测中该维度是否满足阈值，例如：

```json
[true, false, true, false, false]
```

每轮扫描只保留最后 `trigger_window` 个结果。窗口中 `true` 的数量大于等于 `trigger_count` 时，该维度本轮允许生成阈值事件。

## 数据流

### 当前阈值扫描路径

```text
scan_policy_task
  -> MonitorPolicyScan.run()
    -> AlertDetector.detect_threshold_alerts()
      -> MetricQueryService.query_aggregation_metrics()
      -> calculate_alerts(...)
    -> AlertDetector.count_events()
    -> AlertDetector.recover_threshold_alerts()
    -> EventAlertManager.create_events_and_alerts()
```

### 新阈值扫描路径

```text
scan_policy_task
  -> MonitorPolicyScan.run()
    -> AlertDetector.detect_threshold_alerts()
      -> query and convert metrics
      -> calculate_alerts(..., n=single_detection_points)
      -> apply trigger window filter
    -> AlertDetector.count_events()
    -> AlertDetector.recover_threshold_alerts()
    -> EventAlertManager.create_events_and_alerts(filtered_alert_events)
```

初始实现中 `single_detection_points` 保持为 `1`，即沿用现有“本轮检测结果满足阈值”的判断。这样复用已预留的 `n` 参数入口，但不把本次 X/N 需求混淆成单次查询内连续采样点判断。

如果未来产品要同时支持“本轮最近 M 个采样点连续满足”与“最近 X 次检测累计 N 次满足”，可以在策略中再增加独立字段，例如 `trigger_datapoints`，并传给 `calculate_alerts(..., n=trigger_datapoints)`。

## 触发窗口逻辑

对每个策略扫描出的维度，先得到本轮检测结果：

- 在 `alert_events` 中：本轮满足阈值。
- 在 `info_events` 中：本轮不满足阈值。

然后更新触发状态：

1. 用 `metric_instance_id` 找到或创建 `PolicyTriggerState`。
2. 追加本轮结果：
   - 命中阈值追加 `true`
   - 未命中阈值追加 `false`
3. 截断为最近 `trigger_window` 个结果。
4. 计算 `sum(recent_results) >= trigger_count`。
5. 对命中阈值且达到触发条件的事件，允许进入后续创建事件和告警流程。
6. 对命中阈值但未达到触发条件的事件，只更新状态，不创建 MonitorEvent/MonitorAlert。

示例：`trigger_window=5`，`trigger_count=3`

```text
检测序号     1      2      3      4      5
本轮命中     是     否     是     否     是
窗口命中数   1      1      2      2      3
是否告警     否     否     否     否     是
```

默认值 `5/1` 下，第一次命中就满足触发条件，与当前行为保持一致。

## 活跃告警行为

触发条件用于“创建阈值事件/告警之前”的降噪，不改变活跃告警后的生命周期。

- 如果没有活跃告警，且本轮命中但窗口未达标：不创建事件，不创建告警。
- 如果没有活跃告警，且本轮命中且窗口达标：按现有逻辑创建事件和告警。
- 如果已有活跃 threshold 告警，后续命中仍按现有逻辑记录事件和升级等级。
- 自动恢复仍由 `info_event_count` 和 `recovery_condition` 控制。

实现时建议让窗口过滤只拦截“未达到触发条件的新命中事件”。已有活跃告警的同维度命中不应被过滤，否则会影响告警升级、事件追踪和快照记录。

## 无数据告警

无数据告警完全不读取 `trigger_window` 和 `trigger_count`。

现有流程保持：

```text
AlertDetector.detect_no_data_alerts()
AlertDetector.recover_no_data_alerts()
```

这符合已确认范围：触发条件只用于阈值告警，不用于无数据告警。

## API 与序列化

`MonitorPolicySerializer` 增加字段校验：

- 缺省时使用模型默认值。
- 非整数、0、负数、`trigger_count > trigger_window` 返回明确错误。

NATS 创建策略路径复用同一个 serializer，因此自动获得校验和默认值。

批量模板创建路径 `build_bulk_policy_payloads()` 需要把配置透传到策略 payload：

```text
trigger_window = config.get("trigger_window", 5)
trigger_count = config.get("trigger_count", 1)
```

## 前端设计

### 策略详情页

位置：`web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`

在自动恢复上方新增 Form.Item：

```text
触发条件：在 [trigger_window] 个周期内累计满足 [trigger_count] 次检测算法，触发告警。
```

交互规则：

- 两个输入框均为整数输入。
- `trigger_window` 最小值 1。
- `trigger_count` 最小值 1。
- `trigger_count` 最大值受 `trigger_window` 约束。
- 默认 `5/1`。

`page.tsx` 新增状态和表单回填：

- 新增模式初始化 `trigger_window=5`、`trigger_count=1`。
- builtIn 模式读取模板值，缺省回退 `5/1`。
- 编辑旧策略时后端已有默认值；前端仍做兜底。
- 提交时随策略 payload 传给 `/monitor/api/monitor_policy/`。

### 批量模板应用

位置：

- `web/src/app/monitor/(pages)/event/template/bulkApplyModal.tsx`
- `web/src/app/monitor/(pages)/event/template/templateBulkUtils.ts`

默认配置增加：

```text
trigger_window: 5
trigger_count: 1
```

共享配置步骤中增加同样的触发条件输入。`normalizeBulkConfig()` 保留或补齐默认值，`buildBulkApplyPayload()` 原样提交。

## 告警模板默认配置

`PolicyTemplate.templates` 是从各插件 `policy.json` 导入到数据库的 JSON 模板。为了避免修改大量模板文件，默认配置建议在模板读取和策略生成入口统一补齐：

- `PolicyService.get_policy_templates()` 返回模板时，为每个 template 补 `trigger_window=5`、`trigger_count=1`。
- `build_bulk_policy_payloads()` 生成策略时优先使用批量配置，其次使用模板字段，最后回退 `5/1`。
- 单模板 builtIn 创建时，前端读取 `sessionStorage.strategyInfo` 中的模板字段；缺省回退 `5/1`。

如果后续要求模板 JSON 文件本身可表达不同默认触发条件，再允许单个模板显式配置：

```json
{
  "trigger_window": 5,
  "trigger_count": 3
}
```

## 状态清理

触发状态是策略扫描的派生状态，需要在策略生命周期中收敛：

- 删除策略时，级联删除 `PolicyTriggerState`。
- 策略禁用时可保留状态；重新启用后继续窗口判断。若产品希望禁用后重新计数，可在禁用时清理。
- 策略关键语义变更时建议清理该策略状态：
  - `source`
  - `group_by`
  - `query_condition`
  - `monitor_object`
  - `collect_type`
  - `threshold`
  - `algorithm`
  - `period`
  - `trigger_window`
  - `trigger_count`

这些字段变化会改变“同一维度是否命中”的语义，保留旧窗口容易造成误触发。

## 并发与补偿

`scan_policy_task` 使用 `celery_singleton.Singleton`，同一策略通常不会并发扫描。仍建议更新 `PolicyTriggerState` 时使用事务，并在批量读取状态后统一 `bulk_create`/`bulk_update`。

补偿扫描会按历史周期顺序运行 `_run_scan_and_record_success(policy_obj, scan_time)`。触发窗口应自然按补偿顺序更新，避免系统恢复后一次性用当前时刻覆盖多个周期。

## 错误处理

- 状态更新失败应让本轮 threshold 扫描失败并重试，避免“状态未更新但告警已创建”的不一致。
- 找不到状态时创建状态，`recent_results=[]`。
- `recent_results` 中存在异常值时按空列表重建，并记录 warning。
- `trigger_window/trigger_count` 缺失时按 `5/1` 处理，兼容旧数据和旧调用方。

## 测试策略

### 后端

新增或扩展测试：

1. `MonitorPolicySerializer` 接受合法 `trigger_window/trigger_count`。
2. serializer 拒绝 `trigger_window < 1`、`trigger_count < 1`、`trigger_count > trigger_window`。
3. 默认 `5/1` 下，第一次阈值命中即可创建告警，保持现有行为。
4. `5/3` 下，前两次命中不创建告警，第三次命中创建告警。
5. `5/3` 下，命中次数滑出窗口后不触发。
6. 已有活跃 threshold 告警时，命中事件不被触发窗口过滤。
7. no_data 告警不读取触发条件，行为不变。
8. 批量模板 payload 默认包含 `trigger_window=5`、`trigger_count=1`。

最小验证命令：

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_policy_serializer_validation.py apps/monitor/tests/test_policy_bulk_payload.py apps/monitor/tests/test_policy_scan_failure_handling.py -q
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

- 新增状态表会增加每轮扫描的读写成本。
- 策略配置变更后如果不清理旧状态，可能基于旧阈值或旧维度误触发。
- 若把 X/N 误接到 `calculate_alerts(..., n)`，会把“跨检测次数”错误实现成“单次检测内连续采样点”。

### 控制

- 状态按 `policy_id + metric_instance_id` 唯一，读写范围只限当前策略扫描结果。
- 配置语义变化时清理触发状态。
- 文档和代码命名明确区分：
  - `trigger_window/trigger_count`：跨检测周期。
  - `calculate_alerts(..., n)`：单次检测内采样点数量。
- 默认 `5/1` 保持现有用户体验，降低上线风险。

## 预期结果

完成后，用户可以在阈值告警策略中配置“最近 X 次检测累计 N 次命中阈值才触发告警”。短时毛刺不会立刻创建新阈值告警；已经触发的告警仍按现有事件、升级、自动恢复链路运行。旧策略和模板默认采用 `5/1`，行为与当前系统兼容。
