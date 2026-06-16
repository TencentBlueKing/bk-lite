# 模块 ARD：CMDB（配置管理）

> 路径 `server/apps/cmdb` ｜ API 前缀 `api/v1/cmdb/`

## 1. 职责【已实现/已存在】
管理基础设施资产清单、模型定义与自动化采集；以图数据库维护资产关系与拓扑，记录变更历史，支持配置文件版本化。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| CollectModels / OidMapping | `models/collect_model.py` | 采集任务（SNMP/云/协议/K8s/DB/拓扑），加密凭据，结果 JSON |
| ChangeRecord | `models/change_record.py` | 变更审计（前后快照、操作类型、场景） |
| ConfigFileVersion | `models/config_file_version.py` | 配置文件版本，内容存 MinIO |
| FieldGroup / UserPersonalConfig / PublicEnumLibrary | `models/*.py` | UI 字段分组、个人偏好、共享枚举 |
| SubscriptionRule | `models/subscription_rule.py` | 变更订阅 |
| NodeMgmtSyncConfig / NodeMgmtSyncRun | `models/node_mgmt_sync.py:7,22` | 节点管理同步配置与运行记录（两个独立模型） |
| CollectTaskCredentialHit | `models/collect_task_credential_hit.py` | 采集任务凭据使用审计 |

**存储**：PostgreSQL（ORM）；**Neo4j / FalkorDB**（关系图谱，`graph/{neo4j,falkordb}.py`）；MinIO（配置文件，`cmdb-config-file` bucket）；VictoriaMetrics（K8s 指标查询，`collection/query_vm.py`）。

## 3. 接口【已实现/已存在】
`urls.py` 路由组：`classification`/`model`/`instance`/`change_record`/`collect`/`config_file_versions`/`oid`/`field_groups`/`user_configs`/`public_enum_libraries`/`subscription`/`node_mgmt_sync`/`collect_tool`/`k8s_setup`；开放端点 `open_api/k8s_setup`；企业特性 `custom_reporting/{tasks,ingest}`。

## 4. 依赖与通信【已实现/已存在】
- 依赖 `apps.core`（logger/异常/加密/模板沙箱）。
- NATS：`nats/nats.py` 基于角色/团队构建实例分组权限过滤。
- Celery：`tasks/celery_tasks.py:sync_collect_task` 执行采集，分发到 `CollectDispatchService`/协议采集，更新状态并触发订阅通知。

## 5. 采集插件【已实现/已存在】
`collection/collect_plugin/`：SNMP/SSH/网络拓扑（LLDP/CDP/FDB/ARP）；云（AWS/Aliyun/华为云/OpenStack/QCloud/Tencent）；K8s/Docker；虚拟化（VMware/Hyper-V/SmartX/ManageOne）；中间件（Kafka/Jetty/WebLogic/ES）；大数据（Spark/FusionInsight/Hadoop）；数据库（MySQL/Oracle/MongoDB）。

## 6. 风险 / 待确认
- 双图库（Neo4j 与 FalkorDB）并存的选型与切换条件【待确认】。
- 凭据加密密钥管理与轮转策略【待确认】。

## 7. 证据来源
`server/apps/cmdb/{urls.py,models/*,graph/*,collection/*,tasks/celery_tasks.py,nats/nats.py}`。
