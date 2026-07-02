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
| OperatorLog | `models/operator_log.py`（operator_log.py:10） | 操作审计 |
| SystemSetting | `models/sys_setting.py`（sys_setting.py:11） | 配置开关（如 `alert_enrich`，键常量 INIT_ALERT_ENRICH） |
| EnrichmentRule | `models/enrichment.py:8` | 声明式 Lookup 富化规则模型，供富化引擎批量执行并写回 Alert/Event enrichment 结果 |
| ActionRule / ActionExecution | `models/action.py:8,29` | 告警动作规则与执行记录，承载动作匹配、执行状态与回调链路 |

## 3. 接口【已实现/已存在】
所有 ViewSet 路由组均以 `router.register(r"api/<name>", ...)` 注册（urls.py:27-44），故完整路径统一带 `api/` 段，例如 `api/v1/alerts/api/alert_source/`。路由组：`api/alert_source`/`api/alerts`/`api/events`/`api/level`/`api/settings`/`api/assignment`/`api/shield`/`api/incident`(+`/(?P<incident_pk>\d+)/updates`)/`api/alarm_strategy`/`api/log`；开放端点 `open_api/k8s`（urls.py:44）。
path 端点（urls.py:47-49）：`api/test/`（request_test，receiver.py:107）、`api/receiver_data/`（receiver_data）、`api/source/<str:source_id>/webhook/`（receiver_source_data）。完整路径分别为 `api/v1/alerts/api/test/` 等。
动作规则与执行记录接口已纳入路由：`action_rule`、`action_execution` 与 `action_callback`，并包含供 job_mgmt 调用的 action job scripts 入口（证据：`urls.py:54-61`、`views/action.py:65,100,182`）。

## 4. 接入与富化【已实现/已存在】
- 适配器 `common/source_adapter/`：Prometheus / Zabbix / NATS / webhook / monitor / restful；基类 `base.py` 负责字段映射、恢复检测、屏蔽校验、富化开关（`enable_rich_event`）。
- `main()` 执行顺序【已实现/已存在】（`base.py:552-568`）：① `event_operator(bulk_events)`（屏蔽写入） → ② `InstantAlertDispatcher.dispatch(bulk_events)`（即时旁路） → ③ `handle_recovery_events()`（聚合/恢复）。屏蔽必须先于即时旁路执行，确保即时旁路按库内最新屏蔽状态过滤；本次调整将 `event_operator` 从即时旁路之后前移至之前（`base.py:557`）。
- 聚合主路径显式排除已屏蔽事件【已实现/已存在】：`AggregationProcessor.get_events_for_strategy()` 查询时追加 `.exclude(status=EventStatus.SHIELD)`（`aggregation/processor/aggregation_processor.py:136`），被屏蔽事件不参与指纹聚合也不产出告警。
- 即时旁路新增前置屏蔽过滤【已实现/已存在】：`InstantAlertDispatcher.dispatch()` 在收集命中规则之前调用 `_exclude_shielded(events)` 静态方法（`instant_dispatcher.py:273,310`），该方法按 `event_id` 查库过滤 `status=SHIELD` 的事件；内存中 `Event` 对象的状态可能滞后，故以库内当前值为准。
- 声明式富化已落地为 `EnrichmentRule` + 批量引擎：`enrichment/engine.py:21` 执行规则，`common/source_adapter/base.py:26,198` 接入事件处理链路，聚合构建器在 `aggregation/builder/alert_builder.py:122` 写回 Alert/Event enrichment 结果；不再按“源码缺失”处理。
- 富化仍可经 `apps.rpc.cmdb.CMDB` 获取资源元数据。
- 聚合 `aggregation/` 子目录：`processor` / `strategy`（指纹分组）/ `builder` / `recovery`（超时恢复）/ `window` / `core` / `engine` / `query` / `templates`【已实现/已存在，目录均存在】。

## 5. 任务与 NATS【已实现/已存在】
- Celery（`tasks/tasks.py`，均 `@shared_task`）：`event_aggregation_alert`、`beat_close_alert`、`check_and_send_reminders`、`cleanup_reminder_tasks`、`check_and_send_escalations`（升级）、`async_auto_assignment_for_alerts`（自动分派）、`build_instant_alerts`（即时告警构建）、`sync_notify`、`sync_shield`、`sync_no_dispatch_alert_notice_task`。
  - `async_auto_assignment_for_alerts` 自带分片自调度：常量 `AUTO_ASSIGNMENT_CHUNK_SIZE=200`（tasks.py:17），当待处理 alert_ids 超过该阈值时按片切分并 `.delay` 再投（tasks.py:132,154-157）【已实现/已存在】。
  - `build_instant_alerts` 配置重试策略 `autoretry_for=(Exception,)`、`retry_backoff=True`、`max_retries=3`（tasks.py:198-202）【已实现/已存在】。
- 缺失检测告警自动分派【已实现/已存在】：`_trigger_missing_alert()` 创建告警后，通过 `transaction.on_commit(lambda: self._schedule_auto_assignment([alert_id]))` 延迟到事务提交后再触发自动分派（`aggregation_processor.py:419`）。延迟调度原因：该方法在 `select_for_update` 事务内执行，提交前调度可能因回滚造成空跑；`on_commit` 保证仅在事务成功持久化后才将 alert_id 送入分派链路，使缺失检测合成告警与常规聚合/即时告警一致进入自动分派。
- NATS（`nats/nats.py`）：`receive_alert_events` 接收事件（nats.py:532）；测试桩 `alert_test`（nats.py:675）。统计类 handler：`get_alert_trend_data`（:188）、`get_alert_source_event_top`（:265）、`get_alert_source_statistics`（:297）、`get_notification_statistics`（:350）、`get_notification_channel_stats`（:404）、`get_alert_data_quality`（:457）、`get_alert_statistics`（:684）、`get_alert_level_distribution`（:741）、`get_active_alert_top`（:782）供运营分析。
- 通知经 `utils/system_mgmt_util.py:SystemMgmtUtils.send_msg_with_channel()`（委托 system_mgmt 渠道）。
- 告警动作链路【已实现/已存在】：`tasks/action_tasks.py:10` 注册动作处理任务，`action/engine.py:13` 执行动作规则匹配与派发；动作回调与 job_mgmt 脚本执行入口由 `views/action.py` 与 `urls.py:54-61` 暴露。

## 2026-07-01 Code-ARD 校准
- `[alerts#20260701-002]` webhook 路由证据路径已更新为当前 `server/apps/alerts/urls.py` 与本 ARD 的接口段，避免沿用漂移行号。
- `[alerts#20260701-008]` 移除“声明式 Lookup 富化源码缺失”的旧结论，改为记录 EnrichmentRule、Engine、接口和 Alert/Event enrichment 写回链路已存在。
- `[alerts#20260701-009]` 补录动作规则、执行记录、Celery 任务、ActionEngine 与 job_mgmt 回调入口。

## 6. 风险 / 待确认
- 与 monitor/log 各自产生的 Alert 如何统一收敛到本模块【待确认】。

## 7. 证据来源
`server/apps/alerts/{urls.py:27-61, models/operator_log.py:10, models/sys_setting.py:11, models/models.py, models/alert_source.py, models/alert_operator.py, models/enrichment.py:8, models/action.py:8,29, common/source_adapter/*（base.py:26,44,48-57,198,432,434,442,462,552-568,557）, enrichment/engine.py:21, aggregation/builder/alert_builder.py:122, aggregation/processor/aggregation_processor.py:136,419, aggregation/processor/instant_dispatcher.py:273,310,315, aggregation/{strategy,builder,recovery,window,core,engine,query,templates}/, tasks/tasks.py:17,132,154-157,198-202, tasks/action_tasks.py:10, action/engine.py:13, nats/nats.py:188,265,297,350,404,457,532,675,684,741,782, views/receiver.py:107, views/action.py:65,100,182, constants/init_data.py:108,124-130, utils/system_mgmt_util.py}`。
