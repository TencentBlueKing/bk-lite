# 监控告警资源上下文与无数据聚合

## 业务契约

- 告警名称模板必须支持当前监控实例的 `${resource_id}` 与
  `${resource_name}`。
- 子对象告警必须额外支持 `${parent_resource_id}` 与
  `${parent_resource_name}`；普通告警和无数据告警使用同一套资源上下文。
- 子对象指标只携带部分身份维度时，只能在策略已选实例范围内唯一匹配后解析
  为监控实例；存在歧义时不得猜测归属。
- 同一策略、同一监控实例产生的无数据事件聚合为一条活动 Alert。不同缺失
  维度仍分别保留 MonitorEvent，并关联到该 Alert，避免丢失审计证据。
- 聚合后的无数据 Alert 只有在该监控实例的全部策略实例基准均恢复数据后才
  自动恢复；部分维度恢复时 Alert 保持活动。
- 用户页面删除、自动发现超时清理和历史墓碑回收都通过统一实例移除入口；
  实例物理删除前必须把关联的活动阈值/无数据 Alert 置为 `closed`，并清理该
  实例的策略基准，避免留下活动孤儿告警或下一轮重新打开。
- 自动发现仅把实例标记为 `is_active=False` 时不关闭告警；VictoriaMetrics
  查询失败也不得触发实例移除或告警关闭。
- 实例移除只关闭活动 Alert，不物理删除历史 Alert、MonitorEvent 和快照；
  关闭原因区分页面人工删除与自动清理，生命周期通知在数据库事务提交后发送。

## 兼容性

- 阈值告警继续按指标实例聚合，不改变既有多维阈值告警粒度。
- 基础对象的父对象变量渲染为空字符串。
- 没有策略实例基准的历史无数据告警继续按原指标实例恢复判定。

## 验证接缝

- `server/apps/monitor/tests/test_policy_scan_alert_detector.py`
- `server/apps/monitor/tests/test_policy_scan_event_alert_manager.py`
- `server/apps/monitor/tests/test_policy_scan_metric_query_service.py`
- `server/apps/monitor/tests/test_policy_scan_scanner.py`
- `server/apps/monitor/tests/test_monitor_instance_removal_service.py`
- `server/apps/monitor/tests/test_monitor_instance_view.py`
- `server/apps/monitor/tests/test_sync_instance_service.py`
