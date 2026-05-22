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
