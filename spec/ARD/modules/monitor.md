# 模块 ARD：Monitor（监控告警策略）

> 路径 `server/apps/monitor` ｜ API 前缀 `api/v1/monitor/`

## 1. 职责【已实现/已存在】
管理监控对象/实例、指标定义、插件化采集配置与告警策略；基于 VictoriaMetrics 周期扫描评估阈值，维护告警生命周期。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| MonitorObjectType / MonitorObject / MonitorInstance | `models/monitor_object.py` | 监控对象类型/定义/目标实例（实例含 `fallback_sampling_rate` 兜底采样率、`enabled_protocols` Flow 协议） |
| MonitorInstanceOrganization / MonitorObjectOrganizationRule | `models/monitor_object.py:70,80` | 实例-组织关联表（权限隔离载体）、对象分组规则 |
| MetricGroup / Metric | `models/monitor_metrics.py` | 指标分组与定义（PromQL、单位、维度） |
| MonitorPlugin / MonitorPluginConfigTemplate / MonitorPluginUITemplate | `models/plugin.py:8,26,39` | 采集插件（telegraf）、配置模板、UI 模板 |
| MonitorPolicy / PolicyTemplate / PolicyOrganization | `models/monitor_policy.py:21,10,72` | 告警策略、模板、策略-组织关联表（权限隔离载体） |
| MonitorEvent / MonitorEventRawData / MonitorAlert / MonitorAlertMetricSnapshot | `models/monitor_policy.py` | 事件/原始数据/告警聚合/生命周期快照（S3JSONField） |
| PolicyInstanceBaseline / CollectConfig | `models/*.py` | 无数据基线、采集配置 |
| MonitorCondition / MonitorConditionOrganization | `models/monitor_condition.py:7,21` | 可复用监控条件、条件-组织关联表（权限隔离载体） |
| CollectDetectTask | `models/collect_detect.py` | 接入前采集探测任务（状态、阶段、结果、错误信息） |
| Setting | `models/setting.py:7` | 监控全局设置（`name` + `value` JSONField 键值对） |

**存储**：PostgreSQL（ORM）；VictoriaMetrics（指标查询，`utils/victoriametrics_api.py`）；MinIO（`monitor-alert-raw-data` 等，S3JSONField）。

## 3. 接口【已实现/已存在】
各为独立 ViewSet 路由：`monitor_object`、`monitor_object_type`、`metrics_group`、`metrics`、`metrics_instance`、`organization_rule`、`monitor_instance`、`monitor_policy`、`monitor_plugin`、`monitor_alert`、`monitor_event`、`manual_collect`、`collect_detect`、`unit`、`monitor_condition`、`system_mgmt`、`node_mgmt`；开放端点 `open_api/infra`。
- `collect_detect`【已实现/已存在】：用于接入前采集探测任务的创建与结果查询。创建前会校验当前用户对监控对象与节点实例的访问权限；结果查询只允许创建人于所属组织范围内读取。`POST /api/v1/monitor/api/collect_detect/` 创建异步探测任务并返回 `task_id/status`，`GET /api/v1/monitor/api/collect_detect/{id}/` 返回任务状态、阶段、结果与错误信息（`views/collect_detect.py:15-86`）。

- Celery 任务与调度【已实现/已存在】：
  - `tasks/grouping_rule.py:sync_instance_and_group`（同步实例分组，查 VM）—— 由 beat 每 10 分钟触发（`config.py:8-11`）。
  - `tasks/monitor_policy.py:retry_alert_center_lifecycle_notify_task`（告警中心生命周期通知重试，`monitor_policy.py:100`）—— 由 beat 每 5 分钟触发（`config.py:12-15`）。
  - `tasks/monitor_policy.py:scan_policy_task`（策略扫描评估）—— 不在静态 `config.py` 中，而是按每条策略的 `schedule`（min/hour/day）动态注册为 django-celery-beat 的 `PeriodicTask`（任务名 `scan_policy_task_{policy_id}`），在策略保存时由 `views/monitor_policy.py:380-395` 创建/更新（crontab 由 `format_crontab` 依策略调度生成，`views/monitor_policy.py:340-378`）；仍属周期调度，只是周期随策略而定，非 NATS 触发。
- 策略扫描服务层 `tasks/services/policy_scan/`：`scanner.py`、`metric_query.py`、`alert_detector.py`、`event_alert_manager.py`、`snapshot_recorder.py`（入口 `MonitorPolicyScan`）。
- `retry_alert_center_lifecycle_notify_task` 关键约束【已实现/已存在】：每次最多取 200 条待重试告警（`monitor_policy.py:110`）；单条最大重试 10 次（`alert_center_retry_count__lt=10`，`monitor_policy.py:109`）；达上限的告警以 ERROR 汇总告警并不再补偿，需人工介入（`monitor_policy.py:149-154`）。
- NATS【已实现/已存在】：`nats/monitor.py` 注册大量 handler，经 `apps/rpc/monitor.py` 暴露并被 operation_analysis、opspilot 消费：
  - 创建类（`monitor.py:471-519`）：`create_monitor_object_type` / `create_monitor_object` / `create_monitor_plugin` / `create_metric_group` / `create_metric` / `create_monitor_policy`。
  - 查询类（`monitor.py:520-1063`）：`monitor_objects` / `monitor_object_instance_count` / `monitor_metrics` / `monitor_object_instances` / `query_monitor_data_by_metric` / `monitor_instance_metrics` / `query_monitor_alert_segments` / `query_latest_active_alerts` / `mm_query` / `mm_query_range` / `get_monitor_statistics`。
  - 权限授权类：`_get_authorized_monitor_instances` 等内部辅助（`monitor.py:425-462`）；`nats/permission.py:7,33` 另注册 `get_monitor_module_data` / `get_monitor_module_list`，按组织过滤实例/策略/条件。
- 流量监控接入（NetFlow/sFlow）【已实现/已存在】：服务层 `services/flow_*.py` 承载流量接入能力，对应 PRD「集成·流量监控接入」：
  - `flow_access_guide.py:10` 定义协议监听端口 `PROTOCOL_PORT_MAP = {netflow:2055, sflow:6343}`，依赖 `apps/rpc/node_mgmt` 拼接云区域接入地址。
  - `flow_onboarding.py:17` 创建/绑定流量资产，兜底采样率默认 1000（`DEFAULT_FALLBACK_SAMPLING_RATE`）。
  - `flow_env_config.py` 按云区域刷新采集器环境变量（`refresh_collect_configs`）。
  - `flow_sampling.py:10` 的 `FlowSamplingService.normalize_payload` 归一化上报载荷，产出 `effective_sampling_rate` 字段及来源标记 `sampling_rate_source`（上报值 `reported_effective_sampling_rate` / 派生 `normalized_from_*` / 兜底 `fallback_sampling_rate`）。
- 接入前采集探测【已实现/已存在】：插件模型新增 `support_collect_detect` 能力标记；`CollectDetectService.create_task()` 创建任务后通过 `run_collect_detect_task.delay(...)` 异步执行一次性探测，结果记录到 `CollectDetectTask`，用于接入向导中的“先探测再落配置”场景。服务层会对超时时间做 1~600 秒钳制，并把请求快照中的敏感值脱敏存档（`models/plugin.py:17`、`services/collect_detect.py:29-69,198-213`、`tasks/collect_detect.py:7`）。
- 内置网络设备模板增量【已实现/已存在】：SNMP 目录本轮新增 `access_topvision`、`access_icotera`、`switch_ipinfusion`、`transmission_ifotec`、`wireless_xirrus` 五组内置模板；其中 IP Infusion 模板附带电源温度默认告警策略，其余四组提供对象接入模板但不内置策略（`support-files/plugins/Telegraf/snmp/*/policy.json`）。

对应 PRD：[[spec/prd/监控系统/集成.md#3.1 集成（插件管理）]]；对应功能清单：[[spec/fuctionlist/02-监控系统-功能清单.md#7. Integration - 资产管理]]
> 证据来源：server/apps/monitor/views/collect_detect.py:15-86，server/apps/monitor/services/collect_detect.py:29-69,198-213，server/apps/monitor/support-files/plugins/Telegraf/snmp/access_topvision/policy.json:1-5，server/apps/monitor/support-files/plugins/Telegraf/snmp/access_icotera/policy.json:1-5，server/apps/monitor/support-files/plugins/Telegraf/snmp/switch_ipinfusion/policy.json:1-18，server/apps/monitor/support-files/plugins/Telegraf/snmp/transmission_ifotec/policy.json:1-5，server/apps/monitor/support-files/plugins/Telegraf/snmp/wireless_xirrus/policy.json:1-5　|　同步基线：8a12d3b　|　【已实现】

## 5. 数据流【已实现/已存在】
- 指标采集与告警评估：telegraf 采集 → VictoriaMetrics →（PromQL）scan_policy_task → 阈值/聚合/恢复评估 → MonitorEvent → MonitorAlert（原始快照存 MinIO）。
- 流量监控接入：网络设备发送 NetFlow(2055)/sFlow(6343) → 采集器按云区域环境变量监听（`flow_env_config.py`） → 采样率归一化（`flow_sampling.py`） → 入 VictoriaMetrics，复用上述告警评估链路。
- 漏跑补偿机制【已实现/已存在】：`scan_policy_task` 基于策略 `last_run_time` 与当前时间计算 gap，按周期数自动补偿历史扫描点（`tasks/monitor_policy.py:59-77`）。补偿上限：单次最多 `MAX_BACKFILL_COUNT=30` 个周期、最大补偿时间范围 `MAX_BACKFILL_SECONDS=24*3600` 秒，超出范围的历史数据不再补偿（`constants/alert_policy.py:5-7`）。

## 6. 风险 / 待确认
- VM 高基数查询的性能与限流策略【待确认】。
- 与 alerts 模块的告警职责边界（monitor 自有 Alert vs 统一 alerts）【推断为分层，需确认收敛路径】。

## 7. 证据来源
`server/apps/monitor/{urls.py,config.py,constants/alert_policy.py,models/*,tasks/*,views/monitor_policy.py,views/collect_detect.py:15-86,services/flow_*.py,services/collect_detect.py:29-69,198-213,utils/victoriametrics_api.py,nats/monitor.py,nats/permission.py,support-files/plugins/Telegraf/snmp/access_topvision/policy.json,support-files/plugins/Telegraf/snmp/access_icotera/policy.json,support-files/plugins/Telegraf/snmp/switch_ipinfusion/policy.json,support-files/plugins/Telegraf/snmp/transmission_ifotec/policy.json,support-files/plugins/Telegraf/snmp/wireless_xirrus/policy.json}`、`server/apps/rpc/monitor.py`、`web/src/app/monitor/api/integration.ts:220-239`。
