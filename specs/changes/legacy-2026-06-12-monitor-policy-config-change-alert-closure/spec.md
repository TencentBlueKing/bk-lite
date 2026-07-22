# Historical Superpowers change: 2026-06-12-monitor-policy-config-change-alert-closure

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-12-monitor-policy-config-change-alert-closure-design.md

## 背景

GitHub enhancement issue #3001 指出：监控策略编辑后，如果 `source`、`group_by`、`query_condition`、监控对象或采集类型发生变化，旧范围或旧聚合键下的 threshold 活跃告警可能不再进入后续扫描恢复链路，长期停留在 `status=new`。

本地代码确认：

- `server/apps/monitor/views/monitor_policy.py` 删除策略会关闭该策略下全部活跃告警，原因 `policy_deleted`。
- 禁用策略会关闭该策略下全部活跃告警，原因 `policy_disabled`。
- no_data baseline 变化或关闭 no_data 会关闭活跃 no_data 告警。
- 策略更新时虽然会比较 `source/group_by/query_condition/monitor_object/collect_type` 并刷新 baseline，但没有关闭旧 threshold 活跃告警。
- `server/apps/monitor/tasks/services/policy_scan/scanner.py` 获取活跃告警时会按当前 `instances_map` 过滤，旧范围告警可能脱离恢复链路。

## 目标

- 当策略覆盖范围或告警聚合语义发生变化时，关闭该策略旧 threshold 活跃告警，避免告警中心和本地告警列表长期假活跃。
- 删除策略、禁用策略、no_data baseline 收敛的现有行为不回归。
- 关闭时写入 `operation_logs`，记录操作者、时间和原因。
- 配置变更关闭默认只同步用户已配置渠道中的告警中心渠道，不批量打扰普通通知渠道。
- 通用关闭方法支持参数化通知范围，允许调用方选择不通知、仅告警中心、或全部已配置渠道。

## 非目标

- 不把配置变更关闭标记为 `recovered`，因为故障不一定真实恢复。
- 不自动发现全局告警中心渠道；只使用用户在策略或告警快照中已配置的通知渠道。
- 不新增数据库字段。
- 不改变扫描器的活跃告警过滤策略。
- 不新增普通通知渠道免打扰 UI。

## 设计决策

### 1. 策略配置变更后主动关闭旧 threshold 告警

策略更新成功后，比较更新前后的配置语义状态：

- `source`
- `group_by`
- `query_condition`
- `monitor_object`
- `collect_type`

只要这些字段发生语义变化，就关闭该策略下 `alert_type="alert"` 且 `status="new"` 的活跃告警。

这次设计选择关闭该策略下全部旧 threshold 活跃告警，而不是尝试只关闭“旧范围中不再被新范围覆盖”的子集。原因是 `group_by`、`query_condition`、监控对象、采集类型变化会改变告警键和数据语义，旧告警与新策略已不再可靠等价；全量收敛更清晰，也避免复杂且不稳定的旧/新查询条件反推。

### 2. 关闭原因按主要变更类型归类

原因优先级：

1. `policy_scope_changed`：`source` 变化
2. `policy_group_by_changed`：`group_by` 变化
3. `policy_query_condition_changed`：`query_condition` 变化
4. `policy_monitor_target_changed`：`monitor_object` 或 `collect_type` 变化

如果多个字段同时变化，记录第一个匹配的主要原因。这样 operation log 和告警中心标签可读，不引入复杂多原因结构。

### 3. 抽通用关闭方法并参数化通知范围

在 `MonitorPolicyViewSet` 中抽出通用关闭方法，统一处理：

- 设置 `status="closed"`
- 设置 `end_event_time`
- 设置 `operator`
- 追加 `operation_logs`
- `bulk_update`
- 可选触发生命周期通知

通知范围参数建议为：

- `none`：只关闭本地告警，只写操作记录。
- `alert_center_only`：只推送用户已配置通知渠道中的告警中心渠道。
- `all_configured`：推送用户多选的全部已配置通知渠道。

删除策略、禁用策略、no_data 收敛继续使用 `all_configured`，保持原行为。策略配置变更收敛使用 `alert_center_only`。

### 4. alert_center_only 不做隐式渠道发现

`alert_center_only` 的语义是从当前告警快照或策略通知配置中筛选告警中心渠道：

- `Channel.channel_type == "nats"`
- `Channel.config.method_name == "receive_alert_events"`

如果用户没有为策略配置告警中心通知渠道，则不会触发告警中心同步。无论是否存在告警中心渠道，本地旧告警都会被关闭并写入 `operation_logs`。

### 5. 通知过滤尽量复用 AlertLifecycleNotifier

优先扩展 `AlertLifecycleNotifier.notify_alerts()` 支持通知范围参数，让关闭逻辑仍通过生命周期通知服务完成 payload 构造、notice log 记录和异常处理。

为了最小改动，`all_configured` 保持默认值；现有调用点不传新参数时行为不变。

## 数据流

### 策略更新

1. `update()` 或 `partial_update()` 读取旧策略配置状态。
2. 调用 DRF 更新并重新读取策略。
3. 保持现有 schedule、organizations、baseline、enable 处理。
4. 如果配置语义状态发生变化，关闭旧 threshold 活跃告警：
   - 查询 `MonitorAlert.objects.filter(policy_id=policy.id, alert_type="alert", status="new")`
   - 关闭原因按变更字段归类。
   - 通知范围使用 `alert_center_only`。

### 通用关闭

1. 接收待关闭告警列表。
2. 追加 operation log：
   - `action="closed"`
   - `reason=<reason>`
   - `operator=<operator>`
   - `time=<now.isoformat()>`
3. 批量更新告警字段。
4. 如果通知范围不是 `none`，调用生命周期通知服务。
5. 生命周期通知服务按通知范围过滤渠道。

## 错误处理

- 没有待关闭告警时直接返回，不触发通知。
- 没有配置告警中心渠道时，`alert_center_only` 不发送外部消息，不阻断本地关闭。
- 通知发送异常沿用 `AlertLifecycleNotifier` 现有捕获和 notice log 记录逻辑，不回滚本地关闭。
- 如果策略更新后策略对象不存在，不执行配置变更收敛。

## 测试策略

采用 TDD，先写失败测试再改实现。

重点用例：

1. `source` 变化后，旧 threshold 活跃告警被关闭，原因 `policy_scope_changed`，通知范围为 `alert_center_only`。
2. `group_by` 变化后，旧 threshold 活跃告警被关闭，原因 `policy_group_by_changed`。
3. `query_condition` 变化后，旧 threshold 活跃告警被关闭，原因 `policy_query_condition_changed`。
4. no_data baseline 收敛仍只关闭 no_data 告警，不关闭 threshold 告警。
5. 删除策略、禁用策略仍使用全部已配置通知渠道。
6. `AlertLifecycleNotifier` 在 `alert_center_only` 下只发送用户已配置的告警中心渠道；未配置告警中心时不发送普通渠道。

最小验证命令：

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_scan_failure_handling.py -q
```

如果环境可用，再执行：

```bash
cd server && make test
```

## 风险与控制

### 风险

- 配置变更后关闭全部旧 threshold 告警可能比“只关闭不再覆盖的子集”更激进。
- 通知过滤涉及 `AlertLifecycleNotifier`，需要保证现有生命周期通知默认行为不变。
- 当前测试大量使用轻量 monkeypatch 导入模块，新增测试需要避免引入完整 Django 依赖。

### 控制措施

- 只在配置语义字段变化后触发，不因 schedule、notice、threshold 值等无关字段变化关闭告警。
- `notify_scope` 默认值设为 `all_configured`，现有调用不传参时保持原行为。
- 配置变更收敛的通知范围显式传 `alert_center_only`。
- 先用单元测试锁定 no_data、删除、禁用、配置变更四类行为。

## 预期结果

完成后，用户修改策略范围、分组、查询条件、监控对象或采集类型时，旧 threshold 活跃告警会被明确关闭并记录配置变更类原因。告警中心在用户已配置对应渠道时收到关闭事件；未配置时只进行本地生命周期收敛。后续新范围内若仍满足阈值，将按新策略重新生成新告警。
