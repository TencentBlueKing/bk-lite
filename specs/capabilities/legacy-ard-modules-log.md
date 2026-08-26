# 模块 ARD：Log（日志中心）

> Migrated from `spec/ARD/modules/log.md` as legacy capability evidence.

> 路径 `server/apps/log` ｜ API 前缀 `api/v1/log/`

## 1. 职责【已实现/已存在】
日志采集配置、基于 VictoriaLogs 的查询管线、以及基于日志模式的告警策略执行。

## 2. 数据模型与存储【已实现/已存在】

本轮补录：`LogExtractor`（六类抽取动作，按采集实例排序）、`SystemVectorConfigState` / `SystemVectorToken`（中心 Vector 配置拉取）、`UserHabit`（用户检索习惯）。路由：`log_extractors`、`open_api/system_vector`、`user_habits`。

> 证据来源：server/apps/log/urls.py:33-35，server/apps/log/models/extractor.py:7-24　|　同步基线：61bace9f　|　【已实现】
| 模型 | 文件 | 说明 |
|------|------|------|
| CollectType | `models/collect_type.py` | 采集方式（采集器、默认查询） |
| CollectInstance / CollectInstanceOrganization / CollectConfig | `models/instance.py` | 采集实例（绑定 node）、组织权限、采集配置 |
| LogGroup / LogGroupOrganization / SearchCondition | `models/log_group.py` | 多租户日志分组、组织权限、保存的搜索条件 |
| Policy / PolicyOrganization / Alert / Event / EventRawData | `models/policy.py` | 日志告警策略、生成的告警/事件/原始日志 |
| AlertSnapshot | `models/policy.py:127` | 告警生命周期快照（存 S3/MinIO，支持压缩） |

**存储**：PostgreSQL（元数据）；**VictoriaLogs**（日志，`utils/query_log.py` + `constants/victoriametrics.py`，环境变量 `VICTORIALOGS_*`）；MinIO/S3 bucket `log-alert-raw-data`（`EventRawData.data` 与 `AlertSnapshot.snapshots` 均使用 `S3JSONField`，raw data 保存失败会回滚主事务）。

## 3. 接口【已实现/已存在】
`collect_types`/`collect_instances`/`collect_configs`/`k8s_collect`/`node_mgmt`/`log_group`/`search`/`search_conditions`/`policy`/`alert`/`event`/`event_raw_data`/`system_mgmt`；开放端点 `open_api/k8s`。

## 4. 依赖与通信【已实现/已存在】
- 依赖 `apps.core`（logger/异常/权限工具）、`apps.rpc.node_mgmt.NodeMgmt`（K8s 节点）。
- 业务服务层：`services/`（`access_scope.py` 权限范围 `LogAccessScopeService`、`collect_type.py` `CollectTypeService`、`k8s_collect.py` `K8sLogCollectService`、`search.py` `SearchService`）封装采集/查询/权限的业务逻辑（注：`services/policy.py` 为 0 字节空占位文件，策略业务逻辑实际落在 `views/policy.py` 与 `tasks/services/policy_scan.py`）；策略评估核心为 `tasks/services/policy_scan.py:22` `LogPolicyScan`（窗口计算、关键字分组查询、阈值比较等扫描逻辑）。
- 日志正文契约【已实现/已存在】：18 种内置采集类型在 Collector、NATS、中心归一化、日志提取器和查询接口中统一使用顶层 `message`，不得自动保留 `_msg`、`log_message`、`trap_message` 或 `raw_message` 正文副本；VictoriaLogs 物理 `_msg` 只在最终写入适配器中通过移动语义产生，查询响应再恢复为逻辑 `message`。语义不同的模块解析属性（例如 `nginx.error.message`）不属于正文副本。
- 日志时间契约【已实现/已存在】：中心系统 Vector 的 NATS source 使用 `log_namespace: true` 隔离 Vector 元数据与上报负载；消费事件后，把尚未归一化的负载顶层 `timestamp` 原样移动到可选字段 `collect_timestamp`，再以 UTC `now()` 生成唯一的 `timestamp`；已有 `collect_timestamp` 时保留最早值。VictoriaLogs 只以新的 `timestamp` 生成 `_time`，`@timestamp` 与嵌套 `*.timestamp` 不在此契约范围。`timestamp` 和 `collect_timestamp` 都是日志提取器保护字段。
- 被动接收日志提取器【已实现】：syslog / snmptrap 的提取规则归属采集类型而非日志采集实例，中心 Vector 按 `collect_type` 匹配；其余采集类型仍按实例 `instance_id` 匹配。契约见 `specs/changes/log-extractor-passive-collect/spec.md`。
- Vector 采集配置编辑约定【已实现/已存在】：`file` 与 `docker` 两类 Vector 采集器在前端编辑模式中统一读写 `child.content` 扁平结构；保存与回显保持同构，避免多行合并、容器过滤等字段在“保存后再次编辑”时丢失（`web/src/app/log/hooks/integration/collectors/vector/fileDefaults.ts:4-75`、`web/src/app/log/hooks/integration/collectors/vector/dockerDefaults.ts:4-92`）。
- Celery（静态 beat）：仅 `compensate_log_notice_task`（通知补偿，`config.py:5` 静态注册于 `CELERY_BEAT_SCHEDULE`，crontab `*/5` 每 5 分钟一次；实现见 `tasks/policy.py`）。
- Celery（动态 PeriodicTask）：`tasks/policy.py:scan_log_policy_task(policy_id)` 不在静态 `CELERY_BEAT_SCHEDULE` 中，而是在策略保存/启停时由 `views/policy.py:482` `update_or_create_task` 按策略动态创建 `django-celery-beat` 的 `PeriodicTask`（name=`log_policy_task_<policy_id>`，crontab 调度，`args=[policy_id]`）来周期触发（扫描时间窗，支持补扫，更新 `last_run_time`）。
- 策略删除路径同事务原子化【已实现/已存在】：`PolicyViewSet.destroy`（`views/policy.py:438-444`）以 `transaction.atomic()` 包裹「先按 `name=log_policy_task_<policy_id>` 删除关联 `PeriodicTask`、再调 `super().destroy` 删除策略本身」两步；任一步抛异常时整体回滚，避免产生周期性漏扫的孤儿策略（issue #3948）。配套静态分析测试 `test_policy_destroy_atomic_3948.py` 校验 `transaction.atomic` 块与 `from django.db import transaction` 同时存在、且包裹顺序敏感（先 `PeriodicTask.delete` 后 `super().destroy`），不依赖 Django/DB，任意环境可跑。
- 管理命令：`management/commands/log_init.py:7,12,16` 调用 `management/services/plugin.py:11` 的 `migrate_collect_type` 同步采集插件，并调用 `management/services/stream.py:5` 的 `init_stream` 创建默认 LogGroup/组织绑定。
- NATS：`nats/log.py` 提供 `log_search`/`log_hits`/`get_vmlogs_disk_usage`/`query_log_alert_segments`；`nats/permission.py` 提供 `get_log_module_data`（获取日志模块权限数据）与 `get_log_module_list`（获取日志模块列表），供系统管理侧获取日志模块权限数据/列表。
- 日志分组规则模式【已实现/已存在】：`LogGroup.rule.mode` 缺省为 `AND`，写入仅接受大小写不敏感的 `AND` / `OR`，校验 `conditions` 容器、字段、操作和值，并对 LogsQL 字段/值做字面量编码与旧语法安全校验；普通字段名直接输出，`@timestamp`、含 `/` 等合法特殊字段名使用双引号编码。读取 `strict` 模式下未知值、falsey 非对象或畸形结构进入 `invalid_rule` 并 deny-all。首轮滚动前冻结日志分组写入，以新镜像 one-off 运行 legacy 目标 audit，修正旧字段/正则/prefix 语法无法安全表达的存量规则；旧 `endswith` 生成器对所有值均不可解析，legacy 目标会将其整类阻断。保持写冻结部署 `LOG_GROUP_RULE_MODE_ENFORCEMENT=legacy`，排空旧 writer 后再次通过 legacy 目标 audit 才恢复写入，新 legacy writer 持续封住不兼容写入。随后执行 strict 目标 audit，falsey 非对象/畸形规则须修正，未知字符串须修正或通过 `LOG_GROUP_LEGACY_OR_GROUP_IDS` 按 ID 显式保留原 `OR`。安全编码会修正历史正则与 prefix/suffix 语法，因此 `legacy`↔`strict` 必须冻结写入、停止并排空搜索流量，分别运行 `audit_log_group_rule_modes --target-enforcement <strict|legacy> --fail-on-uncovered` 后一次性切换全部实例，禁止滚动混部；legacy 目标预检未通过时不得部署 legacy 或回滚旧镜像。查询兼容状态分别为 `legacy_empty_rule` / `legacy_or`，数据库无需逆向迁移。

## 5. 风险 / 待确认
- VictoriaLogs 写入路径（采集器→VLogs）的采集器实现【已实现】：采集器插件以目录形式注册（`constants/plugin.py:5` DIRECTORY=`apps/log/support-files/plugins`，`management/services/plugin.py:23` 扫描各子目录 `collect_type.json`），共 6 类采集器、合计 18 个采集类型——**Filebeat**（9 类：apache/elasticsearch/kafka/mongodb/mysql/nginx/postgresql/rabbitmq/redis，`support-files/plugins/Filebeat/*/collect_type.json`，各文件 `"collector": "Filebeat"`）、**Vector**（4 类：docker/file/kubernetes/syslog，`support-files/plugins/Vector/syslog/collect_type.json:3`）、**Packetbeat**（2 类：flows/http）、**Auditbeat**（file_integrity）、**Snmptrapd**（SNMP Trap，`support-files/plugins/Snmptrapd/network/collect_type.json:3`）、**Winlogbeat**（Windows 事件日志）。
- 查询限额默认值与对应环境变量【已实现，见 `constants/victoriametrics.py:16-22`，均可由环境变量覆盖】：
  - `QUERY_LIMIT_MAX`=1000（env `VICTORIALOGS_QUERY_LIMIT_MAX`，单次日志检索条数上限）
  - `FIELD_VALUES_LIMIT_MAX`=1000（env `VICTORIALOGS_FIELD_VALUES_LIMIT_MAX`，字段值枚举上限）
  - `HITS_FIELDS_LIMIT_MAX`=100（env `VICTORIALOGS_HITS_FIELDS_LIMIT_MAX`，hits 分组字段上限）
  - SSE 连接：`MAX_CONNECTION_TIME`=1800s（env `SSE_MAX_CONNECTION_TIME`）、`KEEPALIVE_INTERVAL`=45s（env `SSE_KEEPALIVE_INTERVAL`）
  - 上述限额对大查询的影响【需运维核对】。

## 2026-07-01 Code-ARD 校准
- `[log#20260701-010]` 补录 `log_init` 管理命令的插件同步与默认日志分组初始化链路。
- `[log#20260701-011]` 补录 `EventRawData.data` 与 `AlertSnapshot.snapshots` 均使用 S3JSONField/bucket `log-alert-raw-data`，并记录 raw data 保存失败回滚主事务。
- `[log#20260701-012]` 动态 PeriodicTask 证据从 `views/policy.py:461` 更新到 `views/policy.py:482` 及相关调用点。

## 2026-07-09 Code-ARD 校准
- `[log#20260709-001]` 策略删除路径同事务原子化：`PolicyViewSet.destroy` 以 `transaction.atomic()` 包裹「先 `PeriodicTask.objects.filter(name=f"log_policy_task_{policy_id}").delete()`、再 `super().destroy(request, *args, **kwargs)`」，任一步异常整体回滚，避免孤儿策略持续按不存在 policy_id 周期漏扫（issue #3948）。

## 6. 证据来源
`server/apps/log/{urls.py,models/*,services/*,utils/query_log.py,constants/victoriametrics.py:16-22,constants/plugin.py:5,config.py:5,views/policy.py:461-476,tasks/policy.py:14-15,tasks/services/policy_scan.py:22,nats/log.py,nats/permission.py:6-7,29-30,management/services/plugin.py:23,support-files/plugins/{Filebeat,Vector,Packetbeat,Auditbeat,Snmptrapd,Winlogbeat}/*/collect_type.json,support-files/plugins/Vector/syslog/collect_type.json:3,support-files/plugins/Snmptrapd/network/collect_type.json:3}`、`web/src/app/log/hooks/integration/collectors/vector/{fileDefaults.ts,dockerDefaults.ts}`。
