# Monitor Alert Lifecycle Notify

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/monitor-alert-lifecycle-notify/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

监控模块当前通知机制以事件（MonitorEvent）为粒度触发：每次策略扫描产生告警事件时即发送通知。这导致同一告警在其生命周期内会产生大量重复通知，且"告警升级"等关键状态变化没有通知。需要将通知主体从事件切换为告警（MonitorAlert），仅在告警生命周期关键状态变化时触发通知。

此外，当策略通知方式变更时，活跃告警的通知渠道归属不明确。需要在告警创建时快照通知配置，使告警成为自包含的生命周期实体。

## What Changes

- MonitorAlert 模型新增 `notice_type_id` 和 `notice_users` 字段，创建时从策略快照。
- 移除 `EventAlertManager.notify_events()` 中的事件级通知逻辑（不再对每个事件发通知）。
- 扩展 `AlertLifecycleNotifier`，支持四种生命周期动作的通知：created、upgraded、closed、recovered。
- 告警创建时（`_create_alerts_from_events`）触发 created 通知。
- 告警升级时（`_update_existing_alerts_from_events` 中 level 提升）触发 upgraded 通知。
- `AlertLifecycleNotifier` 改为从 alert 自身的 `notice_type_id`/`notice_users` 取通知配置，不再依赖 policy 实时状态。
- 渠道不存在时记录日志跳过，不 fallback 到策略当前渠道。
- 普通通知渠道（邮件/企微/飞书等）也统一走告警通知模型，不再只限于告警中心 NATS。

## Capabilities

### New Capabilities
- `monitor-alert-lifecycle-notify`: 基于告警生命周期状态变化的统一通知能力，覆盖 created/upgraded/closed/recovered 四种动作，支持所有通知渠道。

### Modified Capabilities

None.

## Impact

- `server/apps/monitor/models/monitor_policy.py`: MonitorAlert 新增 notice_type_id、notice_users 字段。
- `server/apps/monitor/tasks/services/policy_scan/event_alert_manager.py`: 移除 notify_events，创建告警时快照通知配置并触发 created 通知，升级时触发 upgraded 通知。
- `server/apps/monitor/services/alert_lifecycle_notify.py`: 重构为从 alert 取通知配置，支持所有渠道和四种动作。
- `server/apps/monitor/tasks/services/policy_scan/alert_detector.py`: recovered 通知保持不变（已走 lifecycle notifier）。
- `server/apps/monitor/views/monitor_policy.py`: closed 通知保持不变（已走 lifecycle notifier）。
- `server/apps/monitor/views/monitor_alert.py`: 手动关闭通知保持不变。
- 需要新增数据库迁移文件。

## Implementation Decisions

## 设计概述

将通知触发点从 MonitorEvent 上移至 MonitorAlert 生命周期状态变化。告警创建时快照通知配置（渠道 + 接收人），后续生命周期内所有通知均使用快照配置。

## 数据模型变更

### MonitorAlert 新增字段

```python
notice_type_id = models.IntegerField(default=0, verbose_name="通知方式ID")
notice_users = models.JSONField(default=list, verbose_name="通知人")
```

创建告警时从 `MonitorPolicy` 快照：
- `alert.notice_type_id = policy.notice_type_id`
- `alert.notice_users = policy.notice_users`

### MonitorEvent.notice_result 字段

保留但不再主动写入。历史数据兼容，新事件该字段为空 list。

## 通知触发点

| 动作 | 触发位置 | 条件 |
|------|---------|------|
| created | EventAlertManager._create_alerts_from_events 之后 | 新告警创建成功 |
| upgraded | EventAlertManager._update_existing_alerts_from_events 中 | level 权重提升 |
| closed | 现有逻辑不变 | 手动关闭/策略删除/策略禁用/no_data禁用 |
| recovered | 现有逻辑不变 | info_event_count >= recovery_condition / no_data恢复 |

## AlertLifecycleNotifier 重构

### 核心变更：通知配置来源

Before:
```python
class AlertLifecycleNotifier:
    def __init__(self, policy):
        self.policy = policy
        # 从 policy 取 notice_type_id
```

After:
```python
class AlertLifecycleNotifier:
    @staticmethod
    def notify(alerts, action, operator="", reason=""):
        # 从每个 alert 自身取 notice_type_id / notice_users
        # 按 notice_type_id 分组批量发送
```

### 渠道分发逻辑

```
notify(alerts, action):
    按 alert.notice_type_id 分组
    对每组:
        查询 Channel
        if channel 不存在:
            log warning, skip
        elif channel 是 alert center (nats + receive_alert_events):
            构建 alert center payload, 批量推送
        else:
            构建通用通知内容, 通过 SystemMgmtUtils.send_msg_with_channel 发送
```

### 通知内容模板

普通渠道通知内容按动作区分：

| 动作 | 标题模板 | 内容要素 |
|------|---------|---------|
| created | 告警产生：{policy_name} | 资源、级别、告警内容、时间 |
| upgraded | 告警升级：{policy_name} | 资源、旧级别→新级别、告警内容、时间 |
| closed | 告警关闭：{policy_name} | 资源、操作人、原因、时间 |
| recovered | 告警恢复：{policy_name} | 资源、持续时长、时间 |

告警中心 NATS payload 的 action 映射：

| 内部动作 | alert center action |
|---------|-------------------|
| created | created |
| upgraded | updated |
| closed | closed |
| recovered | recovery |

## EventAlertManager 变更

### 移除 notify_events

`notify_events` 方法整体移除（或保留为空操作 + deprecation warning）。调用方不再调用此方法。

### 创建告警时快照 + 通知

```python
def _create_alerts_from_events(self, events):
    # ... 现有逻辑 ...
    for event in events:
        create_alerts.append(MonitorAlert(
            ...
            notice_type_id=self.policy.notice_type_id,  # 新增
            notice_users=self.policy.notice_users,       # 新增
        ))
    new_alerts = MonitorAlert.objects.bulk_create(...)

    # 新增：触发 created 通知
    AlertLifecycleNotifier.notify(new_alerts, action="created")

    return new_alerts
```

### 升级时通知

```python
def _update_existing_alerts_from_events(self, event_data_list):
    # ... 现有升级逻辑 ...
    if alert_level_updates:
        MonitorAlert.objects.bulk_update(...)
        # 新增：触发 upgraded 通知
        AlertLifecycleNotifier.notify(alert_level_updates, action="upgraded")
```

## 兼容性

### 存量活跃告警

已存在的 MonitorAlert 没有 notice_type_id/notice_users 字段值（默认为 0/[]）。处理策略：

- 迁移时不回填（避免大量数据更新）
- AlertLifecycleNotifier 中判断：如果 alert.notice_type_id == 0，fallback 到 policy 取配置
- 这样存量告警的关闭/恢复通知不受影响

### MonitorEvent.notice_result

字段保留，新事件不再写入。前端如果展示该字段，不受影响（空 list 表示无通知记录）。

## 不做的事

- 不提供"批量更新活跃告警通知方式"的 UI/API
- 不 fallback 到策略当前渠道（渠道不存在就跳过）
- 不改变 MonitorEvent 的创建逻辑（事件仍正常记录）
- 不改变告警中心 receive_alert_events 的接收端逻辑

## Work Checklist

## 1. 数据模型与迁移

- [x] 1.1 MonitorAlert 模型新增 `notice_type_id`（IntegerField, default=0）和 `notice_users`（JSONField, default=list）字段
- [x] 1.2 生成并应用数据库迁移文件（不回填存量数据）

## 2. AlertLifecycleNotifier 重构

- [x] 2.1 重构 `AlertLifecycleNotifier`，改为从 alert 自身取 notice_type_id/notice_users（alert.notice_type_id == 0 时 fallback 到 policy）
- [x] 2.2 支持普通渠道通知（邮件/企微/飞书等），不再仅限 alert center NATS
- [x] 2.3 按 notice_type_id 分组批量发送，渠道不存在时 log warning 跳过
- [x] 2.4 支持四种动作的通知内容模板：created/upgraded/closed/recovered
- [x] 2.5 告警中心 NATS payload 的 action 映射：created→created, upgraded→updated, closed→closed, recovered→recovery

## 3. 告警创建时快照通知配置并触发通知

- [x] 3.1 `EventAlertManager._create_alerts_from_events` 中创建告警时写入 notice_type_id/notice_users（从 policy 快照）
- [x] 3.2 创建告警成功后调用 `AlertLifecycleNotifier.notify(new_alerts, action="created")`

## 4. 告警升级时触发通知

- [x] 4.1 `EventAlertManager._update_existing_alerts_from_events` 中 level 提升并 bulk_update 后调用 `AlertLifecycleNotifier.notify(alert_level_updates, action="upgraded")`

## 5. 移除事件级通知

- [x] 5.1 移除 `EventAlertManager.notify_events` 方法的实际通知逻辑（保留方法签名为空操作或直接删除）
- [x] 5.2 移除 `EventAlertManager.send_notice` 方法
- [x] 5.3 移除 `EventAlertManager._push_to_alert_center` 方法（created 推送已迁移到 lifecycle notifier）
- [x] 5.4 移除 `EventAlertManager._check_alert_center_channel` 及相关初始化逻辑
- [x] 5.5 清理 policy scan 主流程中对 `notify_events` 的调用

## 6. 验证

- [x] 6.1 确认现有 closed/recovered 通知路径不受破坏（AlertLifecycleNotifier 调用点在 alert_detector.py、monitor_policy.py、monitor_alert.py）
- [x] 6.2 确认 MonitorEvent 创建逻辑不受影响（事件仍正常记录，notice_result 字段保留但不写入）
- [ ] 6.3 执行 `cd server && make test` 确认测试通过（阻塞：当前环境无法连通 PostgreSQL；补充：`uv run pytest apps/monitor/tests/test_policy_scan_failure_handling.py -q` 中本次相关 monitor 用例已通过）
- [ ] 6.4 检查 lsp_diagnostics 确认无类型错误（阻塞：本地未安装 basedpyright-langserver；补充：变更文件已通过 `python3 -m py_compile` 语法校验）
