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

## 3. 接口【已实现/已存在】
所有 ViewSet 路由组均以 `router.register(r"api/<name>", ...)` 注册（urls.py:27-44），故完整路径统一带 `api/` 段，例如 `api/v1/alerts/api/alert_source/`。路由组：`api/alert_source`/`api/alerts`/`api/events`/`api/level`/`api/settings`/`api/assignment`/`api/shield`/`api/incident`(+`/(?P<incident_pk>\d+)/updates`)/`api/alarm_strategy`/`api/log`；开放端点 `open_api/k8s`（urls.py:44）。
path 端点（urls.py:47-49）：`api/test/`（request_test，receiver.py:107）、`api/receiver_data/`（receiver_data）、`api/source/<str:source_id>/webhook/`（receiver_source_data）。完整路径分别为 `api/v1/alerts/api/test/` 等。

## 4. 接入与富化【已实现/已存在】
- 适配器 `common/source_adapter/`：Prometheus / Zabbix / NATS / webhook / monitor / restful；基类 `base.py` 负责字段映射、恢复检测、屏蔽校验、富化开关（`enable_rich_event`）。
- 富化经 `apps.rpc.cmdb.CMDB` 获取资源元数据。
- 聚合 `aggregation/` 子目录：`processor` / `strategy`（指纹分组）/ `builder` / `recovery`（超时恢复）/ `window` / `core` / `engine` / `query` / `templates`【已实现/已存在，目录均存在】。

## 5. 任务与 NATS【已实现/已存在】
- Celery（`tasks/tasks.py`，均 `@shared_task`）：`event_aggregation_alert`、`beat_close_alert`、`check_and_send_reminders`、`cleanup_reminder_tasks`、`check_and_send_escalations`（升级）、`async_auto_assignment_for_alerts`（自动分派）、`build_instant_alerts`（即时告警构建）、`sync_notify`、`sync_shield`、`sync_no_dispatch_alert_notice_task`。
  - `async_auto_assignment_for_alerts` 自带分片自调度：常量 `AUTO_ASSIGNMENT_CHUNK_SIZE=200`（tasks.py:17），当待处理 alert_ids 超过该阈值时按片切分并 `.delay` 再投（tasks.py:132,154-157）【已实现/已存在】。
  - `build_instant_alerts` 配置重试策略 `autoretry_for=(Exception,)`、`retry_backoff=True`、`max_retries=3`（tasks.py:198-202）【已实现/已存在】。
- NATS（`nats/nats.py`）：`receive_alert_events` 接收事件（nats.py:532）；测试桩 `alert_test`（nats.py:675）。统计类 handler：`get_alert_trend_data`（:188）、`get_alert_source_event_top`（:265）、`get_alert_source_statistics`（:297）、`get_notification_statistics`（:350）、`get_notification_channel_stats`（:404）、`get_alert_data_quality`（:457）、`get_alert_statistics`（:684）、`get_alert_level_distribution`（:741）、`get_active_alert_top`（:782）供运营分析。
- 通知经 `utils/system_mgmt_util.py:SystemMgmtUtils.send_msg_with_channel()`（委托 system_mgmt 渠道）。

## 6. 风险 / 待确认
- 与 monitor/log 各自产生的 Alert 如何统一收敛到本模块【待确认】。
- 富化逻辑实现位置【已实现/已存在】：本分支（rogerly）`enrichment/` 目录下无任何 `.py` 源码，仅残留 `__pycache__`（engine/matcher/keys/projection 的 `.pyc`）及一个同样仅含 `__pycache__` 的 `providers/` 子目录（base/cmdb 的 `.pyc`），整目录 git 未跟踪；`apps.alerts.enrichment.matcher` 等模块实测无法 import（ModuleNotFoundError）。生产代码中无任何 `import apps.alerts.enrichment`；仅有未纳入 git 跟踪的测试文件引用，且这些测试均无法通过：6 个 `tests/test_enrichment_*.py`（keys/engine/projection/matcher/provider_cmdb/provider_base）直接 `import apps.alerts.enrichment.*`，因源码缺失在收集期即 ModuleNotFoundError；另一未跟踪测试 `tests/test_alert_builder_enrichment.py` 不引用 enrichment 包，而是 import 现存的 `apps.alerts.aggregation.builder.alert_builder.AlertBuilder` 并断言其 `_merge_enrichment` 方法，但该方法在 `alert_builder.py` 中不存在，故 3 个用例均 AttributeError 失败（实测 pytest：3 failed）。即"声明式 Lookup 富化引擎"模块在本分支并未落地为源码，配套合并逻辑 `_merge_enrichment` 亦未实现。实际生效的富化逻辑在 `common/source_adapter/base.py`：`enable_enrich()`（@staticmethod，base.py:48-57）读取 `SystemSetting`（键 `alert_enrich`，常量 INIT_ALERT_ENRICH），无该行或 `value.enable` 缺省时返回 False；实例属性 `enable_rich_event` 在构造时由其赋值（base.py:44），并在 `rich_event()`（def base.py:432）入口处作为开关判断（`if not self.enable_rich_event` 直接 return，base.py:434）；开关通过时 `rich_event()` 调用 `enrich_event()`（def base.py:442），后者经 `apps.rpc.cmdb.CMDB().search_instances` 取资源元数据（base.py:462）。内置初始化数据为该键播种 `value.enable=True`（constants/init_data.py:124-130）。

## 7. 证据来源
`server/apps/alerts/{urls.py:27-49, models/operator_log.py:10, models/sys_setting.py:11, models/models.py, models/alert_source.py, models/alert_operator.py, common/source_adapter/*（base.py:44,48-57,432,434,442,462）, aggregation/{processor,strategy,builder,recovery,window,core,engine,query,templates}/, tasks/tasks.py:17,132,154-157,198-202, nats/nats.py:188,265,297,350,404,457,532,675,684,741,782, views/receiver.py:107, constants/init_data.py:108,124-130, utils/system_mgmt_util.py}`；enrichment 目录现状见 `server/apps/alerts/enrichment/`（仅 `__pycache__` 与同样仅含 `__pycache__` 的 `providers/`，无 `.py` 源码，git 未跟踪）；直接 import 该包的未跟踪测试见 `tests/test_enrichment_*.py`（6 个，ModuleNotFoundError）；另 `tests/test_alert_builder_enrichment.py` 不引用该包，断言 `aggregation/builder/alert_builder.py` 中未实现的 `AlertBuilder._merge_enrichment`，实测 3 用例 AttributeError 失败。
