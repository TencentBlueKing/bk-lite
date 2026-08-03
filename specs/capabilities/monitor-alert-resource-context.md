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

## 兼容性

- 阈值告警继续按指标实例聚合，不改变既有多维阈值告警粒度。
- 基础对象的父对象变量渲染为空字符串。
- 没有策略实例基准的历史无数据告警继续按原指标实例恢复判定。

## 验证接缝

- `server/apps/monitor/tests/test_policy_scan_alert_detector.py`
- `server/apps/monitor/tests/test_policy_scan_event_alert_manager.py`
- `server/apps/monitor/tests/test_policy_scan_metric_query_service.py`
- `server/apps/monitor/tests/test_policy_scan_scanner.py`
