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
| ShowField | `models/show_field.py:7` | 实例列表展示字段配置，按 创建人×model_id 保存 `show_fields` 列表（JSON） |
| FieldGroup / UserPersonalConfig / PublicEnumLibrary | `models/*.py` | UI 字段分组、个人偏好、共享枚举 |
| SubscriptionRule | `models/subscription_rule.py` | 变更订阅 |
| NodeMgmtSyncConfig / NodeMgmtSyncRun | `models/node_mgmt_sync.py:7,22` | 节点管理同步配置与运行记录（两个独立模型） |
| CollectTaskCredentialHit | `models/collect_task_credential_hit.py` | 采集任务凭据使用审计 |

**存储**：PostgreSQL（ORM）；**Neo4j / FalkorDB**（关系图谱，驱动实现 `graph/{neo4j,falkordb}.py`，运行期由 `graph/drivers/graph_client.py:46-52` 按环境变量 `FALKORDB_HOST` 动态二选一——设置则用 FalkorDB，否则回落 Neo4j，并非两者并存【已实现/已存在】）；MinIO（配置文件，`cmdb-config-file` bucket）；VictoriaMetrics（K8s 指标查询，`collection/query_vm.py`）。

## 3. 接口【已实现/已存在】
`urls.py` 路由组：`classification`/`model`/`instance`/`change_record`/`collect`/`config_file_versions`/`oid`/`field_groups`/`user_configs`/`public_enum_libraries`/`subscription`/`node_mgmt_sync`/`collect_tool`/`k8s_setup`；开放端点 `open_api/k8s_setup`；企业特性 `custom_reporting/{tasks,ingest}`。

## 4. 依赖与通信【已实现/已存在】
- 依赖 `apps.core`（logger/异常/加密/模板沙箱）。
- NATS：`nats/nats.py` 注册 15 个 `@nats_client.register` handler（取数前按角色/团队构建实例分组权限过滤），对外提供四类能力【已实现/已存在】：
  - **实例/模型取数**：`get_cmdb_module_data`(:264)、`get_cmdb_module_list`(:303)、`search_instances`(:354)、`search_instances_batch`(:368)、`model_inst_count`(:884)。
  - **实例 CRUD / 显示字段**：`update_instance`(:378)、`sync_display_fields`(:473)。
  - **采集结果回传（Stargazer→CMDB）**：`receive_config_file_result`(:417，配置文件落库为 ConfigFileVersion)、`receive_collect_credential_result`(:431，凭据探测命中)。
  - **运营分析统计取数**：`get_cmdb_statistics`(:495)、`get_change_trend`(:624)、`get_instance_group_by`(:697)、`get_model_inst_statistics`(:761)、`get_cmdb_model_instance_top`(:812)、`get_cmdb_collect_statistics`(:857)。
- Celery：`tasks/celery_tasks.py` 注册 13 个 `@shared_task`，详见 §5。

## 5. 核心数据流 / 任务

### 任务（Celery）【已实现/已存在】
`tasks/celery_tasks.py` 注册 13 个 `@shared_task`：
| 任务 | 行号 | 作用 |
|------|------|------|
| `sync_collect_task` | :38 | 执行单次采集，分发到 `CollectDispatchService`/协议采集，更新状态并触发订阅通知 |
| `sync_periodic_update_task_status` | :195 | 周期巡检并更新采集任务状态 |
| `sync_collect_credential_results_task` | :225 | 同步凭据探测结果 |
| `sync_cmdb_display_fields_task` | :235 | 同步实例展示字段配置 |
| `execute_collect_tool_debug_task` | :280 | 采集工具调试执行 |
| `sync_public_enum_library_snapshots_task` | :298 | 同步共享枚举库快照 |
| `check_subscription_rules` | :306 | 巡检变更订阅规则 |
| `send_subscription_notifications` | :311 | 发送订阅通知 |
| `daily_data_cleanup_task` | :318 | 每日数据清理 |
| `reconcile_instance_auto_association_task` | :326 | 单实例自动关联对账 |
| `full_sync_auto_association_rule_task` | :334 | 自动关联规则全量同步 |
| `sync_node_mgmt_hosts` | :342 | 同步节点管理主机 |
| `collect_node_mgmt_hosts` | :354 | 采集节点管理主机 |

### 采集插件【已实现/已存在】
采集能力分两层：`collection/collect_plugin/` 下的采集映射实现（Python 文件），与 `constants/constants.py` 中面向 UI 的插件目录（`COLLECTION_METRICS` 分组，含 Beta 标记，部分条目由 Stargazer 以 JOB/PROTOCOL 驱动，无独立映射文件）。

- **协议 / 网络**：SNMP/SSH、网络拓扑（LLDP/CDP/FDB/ARP）（`network.py`、`topology/`、`protocol.py`）。
- **云平台**（constants.py:488-562）：阿里云、腾讯云（`qcloud.py`，id=`qcloud`，目录中仅此一项，不存在独立 Tencent 插件）、华为云、ManageOne、OpenStack、SmartX、FusionInsight（`aliyun.py`/`qcloud.py`/`hwcloud.py`/`manageone.py`/`openstack.py`/`smartx.py`/`fusioninsight.py`）。
- **容器 / 虚拟化**（constants.py:318-359）：K8s、Docker（`k8s.py`）；VMware vCenter（`vmware.py`）。目录中无 Hyper-V 条目，亦无 hyperv 插件文件。
- **存储设备**（constants.py:472-485，近期新增 git 640548eab）：华为存储 OceanStor（`oceanstor.py`），对象树 `storage_device→storage`，采集存储设备/存储池/磁盘/卷（LUN），主对象 `storage`，子对象 `storage_pool/storage_disk/storage_volume`，复用云家族机制（`oceanstor.py:17-19`）。
- **数据库**（constants.py:376-471）：MySQL、InfluxDB、PostgreSQL、MSSQL、Redis、MongoDB、Elasticsearch、HBase、TiDB（实现集中于 `databases.py`）。目录与映射中均无 Oracle 条目。
- **中间件**（constants.py:611-855）：Nginx、MinIO、Zookeeper、Kafka、Tomcat、Jetty、WebLogic、KeepAlive、Spark（id=`spark`，constants.py:846）等共 20+ 项，多为 JOB 驱动。目录中无 Hadoop 条目；大数据相关现仅 Spark（中间件分组）与 FusionInsight（云平台分组）。
- **配置文件采集**（task_type=`config_file`，constants.py:578）：由 Stargazer 采集后经 NATS `receive_config_file_result`(nats.py:417) 回传，落库为 `ConfigFileVersion`，内容存 MinIO。

## 6. 风险 / 待确认
- 双图库后端按 `FALKORDB_HOST` 环境变量在运行期单选（`graph/drivers/graph_client.py:46-52`），非并存；切换条件已明确【已实现/已存在】。
- 凭据加密密钥管理与轮转策略【待确认】。

## 7. 证据来源
`server/apps/cmdb/{urls.py,models/*,graph/*,graph/drivers/graph_client.py,collection/*,collection/collect_plugin/oceanstor.py,constants/constants.py,tasks/celery_tasks.py,nats/nats.py}`。
