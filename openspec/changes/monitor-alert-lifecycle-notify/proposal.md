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
