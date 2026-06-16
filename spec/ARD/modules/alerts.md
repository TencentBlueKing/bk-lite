# 模块 ARD：Alerts（统一告警）

> 路径 `server/apps/alerts` ｜ API 前缀 `api/v1/alerts/`

## 1. 职责【已实现/已存在】
多源事件接入、标准化、富化、指纹聚合/降噪、事件→告警→事件单（Incident）生命周期管理与通知分派。

## 2. 数据模型与存储【已实现/已存在 / PostgreSQL】
| 模型 | 文件 | 说明 |
|------|------|------|
| Event / Alert / Incident / IncidentUpdate / Level | `models/models.py` | 原始事件、聚合告警（指纹去重）、事件单、协作、级别 |
| AlertSource | `models/alert_source.py` | 告警源（secret/team_secrets/config） |
| AlertAssignment / AlertShield / AlertReminderTask / AlertEscalationTask / AlarmStrategy / NotifyResult | `models/alert_operator.py` | 分派/抑制/提醒/升级/降噪策略/通知审计 |
| OperatorLog / SystemSetting | `models/*.py` | 操作审计、配置开关（如 INIT_ALERT_ENRICH） |

## 3. 接口【已实现/已存在】
`alert_source`/`alerts`/`events`/`level`/`settings`/`assignment`/`shield`/`incident`(+`/updates`)/`alarm_strategy`/`log`；接入端点 `api/receiver_data/`、`api/source/<source_id>/webhook/`（urls.py:49，注意此处含额外 `api/` 段，完整路径为 `api/v1/alerts/api/source/<id>/webhook/`）；开放端点 `open_api/k8s`。

## 4. 接入与富化【已实现/已存在】
- 适配器 `common/source_adapter/`：Prometheus / Zabbix / NATS / webhook / monitor / restful；基类 `base.py` 负责字段映射、恢复检测、屏蔽校验、富化开关（`enable_rich_event`）。
- 富化经 `apps.rpc.cmdb.CMDB` 获取资源元数据。
- 聚合 `aggregation/`：processor / strategy（指纹分组）/ builder / recovery（超时恢复）/ window。

## 5. 任务与 NATS【已实现/已存在】
- Celery（`tasks/tasks.py`，均 `@shared_task`）：`event_aggregation_alert`、`beat_close_alert`、`check_and_send_reminders`、`cleanup_reminder_tasks`、`check_and_send_escalations`（升级）、`async_auto_assignment_for_alerts`（自动分派）、`build_instant_alerts`（即时告警构建）、`sync_notify`、`sync_shield`、`sync_no_dispatch_alert_notice_task`。
- NATS（`nats/nats.py`）：`receive_alert_events` 接收；统计类 `get_alert_*`/`get_notification_*` 供运营分析。
- 通知经 `utils/system_mgmt_util.py:SystemMgmtUtils.send_msg_with_channel()`（委托 system_mgmt 渠道）。

## 6. 风险 / 待确认
- 与 monitor/log 各自产生的 Alert 如何统一收敛到本模块【待确认】。
- `INIT_ALERT_ENRICH` 等开关的默认值与运维含义【推断为富化引擎渐进开关，见记忆"告警丰富引擎"】。

## 7. 证据来源
`server/apps/alerts/{urls.py,models/*,common/source_adapter/*,aggregation/*,tasks/tasks.py,nats/nats.py,utils/system_mgmt_util.py}`。
