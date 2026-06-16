# 模块 ARD：Log（日志中心）

> 路径 `server/apps/log` ｜ API 前缀 `api/v1/log/`

## 1. 职责【已实现/已存在】
日志采集配置、基于 VictoriaLogs 的查询管线、以及基于日志模式的告警策略执行。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| CollectType | `models/collect_type.py` | 采集方式（采集器、默认查询） |
| CollectInstance / CollectInstanceOrganization / CollectConfig | `models/instance.py` | 采集实例（绑定 node）、组织权限、采集配置 |
| LogGroup / LogGroupOrganization / SearchCondition | `models/log_group.py` | 多租户日志分组、组织权限、保存的搜索条件 |
| Policy / PolicyOrganization / Alert / Event / EventRawData | `models/policy.py` | 日志告警策略、生成的告警/事件/原始日志 |
| AlertSnapshot | `models/policy.py:127` | 告警生命周期快照（存 S3/MinIO，支持压缩） |

**存储**：PostgreSQL（元数据）；**VictoriaLogs**（日志，`utils/query_log.py` + `constants/victoriametrics.py`，环境变量 `VICTORIALOGS_*`）。

## 3. 接口【已实现/已存在】
`collect_types`/`collect_instances`/`collect_configs`/`k8s_collect`/`node_mgmt`/`log_group`/`search`/`search_conditions`/`policy`/`alert`/`event`/`event_raw_data`/`system_mgmt`；开放端点 `open_api/k8s`。

## 4. 依赖与通信【已实现/已存在】
- 依赖 `apps.core`（logger/异常/权限工具）、`apps.rpc.node_mgmt.NodeMgmt`（K8s 节点）。
- Celery：`tasks/policy.py:scan_log_policy_task`（按周期扫描时间窗，支持补扫，更新 `last_run_time`）、`compensate_log_notice_task`（通知补偿，`policy.py:106`）。
- NATS：`nats/log.py` 提供 `log_search`/`log_hits`/`get_vmlogs_disk_usage`/`query_log_alert_segments`。

## 5. 风险 / 待确认
- VictoriaLogs 写入路径（采集器→VLogs）具体配置【推断为 vector/filebeat，需确认】。
- 查询限额（`QUERY_LIMIT_MAX` 等）默认值对大查询的影响【已实现，需运维核对】。

## 6. 证据来源
`server/apps/log/{urls.py,models/*,utils/query_log.py,constants/victoriametrics.py,tasks/policy.py,nats/log.py}`。
