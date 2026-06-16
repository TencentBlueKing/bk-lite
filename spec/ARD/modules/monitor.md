# 模块 ARD：Monitor（监控告警策略）

> 路径 `server/apps/monitor` ｜ API 前缀 `api/v1/monitor/`

## 1. 职责【已实现/已存在】
管理监控对象/实例、指标定义、插件化采集配置与告警策略；基于 VictoriaMetrics 周期扫描评估阈值，维护告警生命周期。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| MonitorObjectType / MonitorObject / MonitorInstance | `models/monitor_object.py` | 监控对象类型/定义/目标实例（含组织范围） |
| MetricGroup / Metric | `models/monitor_metrics.py` | 指标分组与定义（PromQL、单位、维度） |
| MonitorPlugin / *ConfigTemplate / *UITemplate | `models/plugin.py` | 采集插件（telegraf）、配置/UI 模板 |
| MonitorPolicy / PolicyTemplate / PolicyOrganization | `models/monitor_policy.py` | 告警策略、模板、组织范围 |
| MonitorEvent / MonitorEventRawData / MonitorAlert / MonitorAlertMetricSnapshot | `models/monitor_policy.py` | 事件/原始数据/告警聚合/生命周期快照（S3JSONField） |
| PolicyInstanceBaseline / MonitorCondition / CollectConfig | `models/*.py` | 无数据基线、可复用条件、采集配置 |

**存储**：PostgreSQL（ORM）；VictoriaMetrics（指标查询，`utils/victoriametrics_api.py`）；MinIO（`monitor-alert-raw-data` 等，S3JSONField）。

## 3. 接口【已实现/已存在】
各为独立 ViewSet 路由：`monitor_object`、`monitor_object_type`、`metrics_group`、`metrics`、`metrics_instance`、`organization_rule`、`monitor_instance`、`monitor_policy`、`monitor_plugin`、`monitor_alert`、`monitor_event`、`manual_collect`、`unit`、`monitor_condition`、`system_mgmt`、`node_mgmt`；开放端点 `open_api/infra`。

## 4. 依赖与通信【已实现/已存在】
- Celery：`tasks/grouping_rule.py:sync_instance_and_group`（同步实例分组，查 VM）、`tasks/monitor_policy.py:scan_policy_task`（策略扫描评估）、`tasks/monitor_policy.py:retry_alert_center_lifecycle_notify_task`（告警中心生命周期通知重试，`monitor_policy.py:100`）。
- 策略扫描服务层 `tasks/services/policy_scan/`：`scanner.py`、`metric_query.py`、`alert_detector.py`、`event_alert_manager.py`、`snapshot_recorder.py`（入口 `MonitorPolicyScan`）。
- NATS：`nats/monitor.py` 处理策略创建/更新事件与权限规则同步。

## 5. 数据流【已实现/已存在】
telegraf 采集 → VictoriaMetrics →（PromQL）scan_policy_task → 阈值/聚合/恢复评估 → MonitorEvent → MonitorAlert（原始快照存 MinIO）。

## 6. 风险 / 待确认
- VM 高基数查询的性能与限流策略【待确认】。
- 与 alerts 模块的告警职责边界（monitor 自有 Alert vs 统一 alerts）【推断为分层，需确认收敛路径】。

## 7. 证据来源
`server/apps/monitor/{urls.py,models/*,tasks/*,utils/victoriametrics_api.py,nats/monitor.py}`。
