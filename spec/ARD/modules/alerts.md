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
| EnrichmentRule | `models/enrichment.py` | 告警丰富规则（provider_type、input_binding、output_projection、preset_key） |
| ActionRule / ActionExecution | `models/action.py` | 告警处理动作规则与执行记录（动作类型、触发事件、幂等键、作业回调结果） |
| OperatorLog | `models/operator_log.py`（operator_log.py:10） | 操作审计 |
| SystemSetting | `models/sys_setting.py`（sys_setting.py:11） | 配置开关（如 `alert_enrich`，键常量 INIT_ALERT_ENRICH） |

## 3. 接口【已实现/已存在】
所有 ViewSet 路由组均以 `router.register(r"api/<name>", ...)` 注册（urls.py:35-55），故完整路径统一带 `api/` 段，例如 `api/v1/alerts/api/alert_source/`。路由组：`api/alert_source`/`api/alerts`/`api/events`/`api/level`/`api/settings`/`api/assignment`/`api/shield`/`api/enrichment`/`api/incident`(+`/(?P<incident_pk>\d+)/updates`)/`api/alarm_strategy`/`api/log`/`api/action_rule`/`api/action_execution`；开放端点 `open_api/k8s`（urls.py:35-55）。
path 端点（urls.py:57-63）：`api/test/`（request_test，receiver.py:107）、`api/receiver_data/`（receiver_data）、`api/source/<str:source_id>/webhook/`（receiver_source_data）、`api/action_callback/`（作业回调入口）、`api/action_job/scripts/` 与 `api/action_job/scripts/<int:script_id>/`（代理 job_mgmt 脚本列表与详情）。完整路径分别为 `api/v1/alerts/api/test/`、`api/v1/alerts/api/action_callback/` 等。

## 4. 接入与富化【已实现/已存在】
- 适配器 `common/source_adapter/`：Prometheus / Zabbix / NATS / webhook / monitor / restful；基类 `base.py` 负责字段映射、恢复检测、屏蔽校验、富化开关（`enable_rich_event`）。
- `main()` 执行顺序【已实现/已存在】（`base.py:552-568`）：① `event_operator(bulk_events)`（屏蔽写入） → ② `InstantAlertDispatcher.dispatch(bulk_events)`（即时旁路） → ③ `handle_recovery_events()`（聚合/恢复）。屏蔽必须先于即时旁路执行，确保即时旁路按库内最新屏蔽状态过滤；本次调整将 `event_operator` 从即时旁路之后前移至之前（`base.py:557`）。
- 聚合主路径显式排除已屏蔽事件【已实现/已存在】：`AggregationProcessor.get_events_for_strategy()` 查询时追加 `.exclude(status=EventStatus.SHIELD)`（`aggregation/processor/aggregation_processor.py:136`），被屏蔽事件不参与指纹聚合也不产出告警。
- 即时旁路新增前置屏蔽过滤【已实现/已存在】：`InstantAlertDispatcher.dispatch()` 在收集命中规则之前调用 `_exclude_shielded(events)` 静态方法（`instant_dispatcher.py:273,310`），该方法按 `event_id` 查库过滤 `status=SHIELD` 的事件；内存中 `Event` 对象的状态可能滞后，故以库内当前值为准。
- 富化规则配置层【已实现/已存在】：`EnrichmentRuleModelViewSet` 提供规则 CRUD 与 `metrics` 指标接口；规则模型以 `provider_type`、`input_binding`、`output_projection`、`preset_key` 描述外部提供方、入参绑定和结果投影（`views/enrichment.py:18-109`、`serializers/enrichment.py:7-25`、`models/enrichment.py`）。
- 富化运行时【已实现/已存在】：告警富化仍经 `common/source_adapter/base.py` 的 `enable_rich_event` 开关与 `enrich_event()` 入口控制，并通过 `apps.rpc.cmdb.CMDB` 获取资源元数据；配置层与运行时入口已打通在同一模块内。
- 聚合 `aggregation/` 子目录：`processor` / `strategy`（指纹分组）/ `builder` / `recovery`（超时恢复）/ `window` / `core` / `engine` / `query` / `templates`【已实现/已存在，目录均存在】。

## 5. 任务与 NATS【已实现/已存在】
- Celery（`tasks/tasks.py`，均 `@shared_task`）：`event_aggregation_alert`、`beat_close_alert`、`check_and_send_reminders`、`cleanup_reminder_tasks`、`check_and_send_escalations`（升级）、`async_auto_assignment_for_alerts`（自动分派）、`build_instant_alerts`（即时告警构建）、`sync_notify`、`sync_shield`、`sync_no_dispatch_alert_notice_task`。
  - `async_auto_assignment_for_alerts` 自带分片自调度：常量 `AUTO_ASSIGNMENT_CHUNK_SIZE=200`（tasks.py:17），当待处理 alert_ids 超过该阈值时按片切分并 `.delay` 再投（tasks.py:132,154-157）【已实现/已存在】。
  - `build_instant_alerts` 配置重试策略 `autoretry_for=(Exception,)`、`retry_backoff=True`、`max_retries=3`（tasks.py:198-202）【已实现/已存在】。
- 缺失检测告警自动分派【已实现/已存在】：`_trigger_missing_alert()` 创建告警后，通过 `transaction.on_commit(lambda: self._schedule_auto_assignment([alert_id]))` 延迟到事务提交后再触发自动分派（`aggregation_processor.py:419`）。延迟调度原因：该方法在 `select_for_update` 事务内执行，提交前调度可能因回滚造成空跑；`on_commit` 保证仅在事务成功持久化后才将 alert_id 送入分派链路，使缺失检测合成告警与常规聚合/即时告警一致进入自动分派。
- 告警处理动作任务【已实现/已存在】：`tasks/action_tasks.py:10-22` 新增 `process_alert_actions(alert_id, event_name)`，异步装配 `ActionEngine` 评估动作规则；执行记录落库为 `ActionExecution`，作业结果经 `ActionCallbackView` 的 HMAC-SHA256 签名回调更新状态（`views/action.py:31-97`）。
- NATS（`nats/nats.py`）：`receive_alert_events` 接收事件（nats.py:532）；测试桩 `alert_test`（nats.py:675）。统计类 handler：`get_alert_trend_data`（:188）、`get_alert_source_event_top`（:265）、`get_alert_source_statistics`（:297）、`get_notification_statistics`（:350）、`get_notification_channel_stats`（:404）、`get_alert_data_quality`（:457）、`get_alert_statistics`（:684）、`get_alert_level_distribution`（:741）、`get_active_alert_top`（:782）供运营分析。
- 统计口径权限收敛【已实现/已存在】：面向运营分析的告警源统计、通知统计与通知渠道统计会先按当前组织与对象权限过滤可见告警，再反推可见告警源与通知结果，避免把无权查看的对象计入汇总（`nats/nats.py:68-137,403-470`）。
- 通知经 `utils/system_mgmt_util.py:SystemMgmtUtils.send_msg_with_channel()`（委托 system_mgmt 渠道）。

## 6. 风险 / 待确认
- 与 monitor/log 各自产生的 Alert 如何统一收敛到本模块【待确认】。
- 动作处理目前仅落地 `job` 类型，其它动作类型（如 ITSM/Webhook）在前端配置中仍为禁用态【已实现/已存在，范围受限】。
- 富化提供方当前仍以现有提供方与投影配置为主，跨外部系统的丰富度与失败补偿策略【待确认】。

## 7. 证据来源
`server/apps/alerts/{urls.py:35-63, models/operator_log.py:10, models/sys_setting.py:11, models/models.py, models/alert_source.py, models/alert_operator.py, models/action.py, models/enrichment.py, common/source_adapter/*（base.py:44,48-57,432,434,442,462,552-568,557）, aggregation/processor/aggregation_processor.py:136,419, aggregation/processor/instant_dispatcher.py:273,310,315, aggregation/{strategy,builder,recovery,window,core,engine,query,templates}/, tasks/tasks.py:17,132,154-157,198-202, tasks/action_tasks.py:10-22, nats/nats.py:188,265,297,350,404,457,532,675,684,741,782, views/action.py:31-246, views/enrichment.py:18-109, views/receiver.py:107, serializers/action.py:6-18, serializers/enrichment.py:7-25, constants/init_data.py:108,124-130, utils/system_mgmt_util.py}`。
