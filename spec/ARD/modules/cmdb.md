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

**存储**：PostgreSQL（ORM）；**Neo4j / FalkorDB**（关系图谱，驱动实现 `graph/{neo4j,falkordb}.py`，运行期由 `graph/drivers/graph_client.py:46-52` 按环境变量 `FALKORDB_HOST` 动态二选一——设置则用 FalkorDB，否则回落 Neo4j，并非两者并存【已实现/已存在】）；Neo4j 搜索/过滤路径已参数化（`graph/neo4j.py:10,301`，引入 `FORMAT_TYPE_PARAMS + ParameterCollector`，`format_search_params/format_final_params` 返回 `(params_str, query_params)` 元组并以 `session.run(**query_params)` 执行，权限过滤条件同步参数化，该路径的 Cypher 注入风险已消除【已实现/已存在】；但写入与按 id 取详情等路径仍为 f-string 拼接、未参数化——`create_entity` `CREATE (n:{label} {properties_str})`（`:197`）、`MATCH (n) WHERE id(n) = {id}`（`:408`），属局部加固而非全面消除【已实现/待确认风险】）；MinIO（配置文件，`cmdb-config-file` bucket）；VictoriaMetrics（K8s 指标查询，`collection/query_vm.py`）。

**内置模型字段（rack / server_room）新增布局属性**【已实现/已存在】：`support-files/model_config.xlsx` 新增以下字段供机房俯视图与机柜正视 U 图使用，消费方为 `services/rack_room.py`（`get_rack_layout`:146-159 读 `rack_u_start`/`u_size`/`u_count`；`get_room_layout`:162-198 读 `row`/`col`/`u_count`）：
| 字段 | 所属模型 | 说明 |
|------|----------|------|
| `row` | rack | 机柜在机房网格中的行坐标（1-based） |
| `col` | rack | 机柜在机房网格中的列坐标（1-based） |
| `u_count` | rack | 机柜总 U 数 |
| `rack_u_start` | 服务器等设备 | 设备在机柜中的起始 U 位 |
| `u_size` | 服务器等设备 | 设备占用 U 数 |

**机房机柜布局服务**（`services/rack_room.py`）【已实现/已存在】：纯只读服务，不写入实例数据。核心函数：
- `build_room_layout(racks)` — 将机柜列表组装为俯视平面图，计算 `col_letter`/`usage`，标记同格冲突，未定位机柜单独成列不丢弃（`:20-55`）。
- `build_rack_layout(u_count, devices)` — 将设备列表组装为正视 U 图，检测越界与 U 段重叠，计算空闲 U 统计（`:58-85`）。
- `free_u_stats(u_count, ranges)` — 计算总空闲 U 与最大连续空闲段（`:88-105`）。
- `get_room_layout(server_room_id, ...)` — 取数入口：通过 `InstanceManage.instance_association_instance_list` 取机房下关联机柜，按 `_has_topology_view_permission` 过滤，组装利用率（`:162-198`）。
- `get_rack_layout(rack_id, ...)` — 取数入口：取机柜实体及其 contains 设备，按权限过滤，组装 U 图（`:146-159`）。

## 3. 接口【已实现/已存在】
`urls.py` 路由组：`classification`/`model`/`instance`/`change_record`/`collect`/`config_file_versions`/`oid`/`field_groups`/`user_configs`/`public_enum_libraries`/`subscription`/`node_mgmt_sync`/`collect_tool`/`k8s_setup`；开放端点 `open_api/k8s_setup`；企业特性 `custom_reporting/{tasks,ingest}`。

**instance 路由组新增只读端点**【已实现/已存在】（`views/instance.py:1030-1072`，权限装饰器 `@HasPermission("asset_info-View")`）：
| 端点 | 方法 | 说明 |
|------|------|------|
| `GET instance/room_layout/<model_id>/<inst_id>` | `InstanceViewSet.room_layout` | 机房俯视平面图：返回该机房下机柜的 row/col/类型/U 占用率供前端布局渲染 |
| `GET instance/rack_layout/<model_id>/<inst_id>` | `InstanceViewSet.rack_layout` | 机柜正视 U 图：返回机柜总 U 数及其 contains 设备的 U 位排布 |

**instance / collect 路由组增量端点**【已实现/已存在】：
| 端点 | 方法 | 说明 |
|------|------|------|
| `GET collect/network_config_file_supported_brands` | `CollectModelViewSet.network_config_file_supported_brands` | 返回网络设备配置文件采集支持的品牌选项，供任务配置页动态展示 |
| `GET instance/application_resource_apps/<model_id>/<inst_id>` | `InstanceViewSet.application_resource_apps` | 仅对 `system` 模型返回应用清单入口 |
| `GET instance/application_resource_topology/<model_id>/<inst_id>` | `InstanceViewSet.application_resource_topology` | 返回应用资源拓扑图，支持 `depth` 查询参数 |
| `GET instance/application_resource_resources/<model_id>/<inst_id>` | `InstanceViewSet.application_resource_resources` | 返回应用拓扑节点的资源汇总数据 |
| `POST instance/application_resource_instances/<model_id>/<inst_id>` | `InstanceViewSet.application_resource_instances` | 按选中节点返回分组后的资源实例明细 |
| `POST instance/application_resource_export/<model_id>/<inst_id>` | `InstanceViewSet.application_resource_export` | 导出当前选中节点对应的资源实例 Excel |
| `GET instance/ipam_view/<inst_id>` | `InstanceViewSet.ipam_view` | 返回子网视角的 IP 容量、利用率与地址列表 |

对应 PRD：[[spec/prd/CMDB/自动发现.md#3.1 采集对象树与插件]]、[[spec/prd/CMDB/资产.md#3.8 资产详情 · 应用资源总览]]；对应功能清单：[[spec/fuctionlist/01-CMDB配置管理-功能清单.md#3. 资产详情]]
> 证据来源：server/apps/cmdb/views/collect.py:66-68，server/apps/cmdb/views/instance.py:999-1150　|　同步基线：83091efe　|　【已实现】

## 4. 依赖与通信【已实现/已存在】
- 依赖 `apps.core`（logger/异常/加密/模板沙箱）。
- NATS：`nats/nats.py` 注册 25 个 `@nats_client.register` handler（取数前按角色/团队构建实例分组权限过滤），对外提供五类能力【已实现/已存在】：
  - **实例/模型取数**：`get_cmdb_module_data`(:264)、`get_cmdb_module_list`(:303)、`search_instances`(:354)、`search_instances_batch`(:368)、`model_inst_count`(:884)。
  - **实例 CRUD / 显示字段**：`update_instance`(:378)、`sync_display_fields`(:473)。
  - **采集结果回传（Stargazer→CMDB）**：`receive_config_file_result`(:417，配置文件落库为 ConfigFileVersion)、`receive_collect_credential_result`(:431，凭据探测命中)。
  - **运营分析统计取数**：`get_cmdb_statistics`(:495)、`get_change_trend`(:624)、`get_instance_group_by`(:697)、`get_model_inst_statistics`(:761)、`get_cmdb_model_instance_top`(:812)、`get_cmdb_collect_statistics`(:857)。
  - **实例/模型/关联通用查询与 CRUD（对外 RPC 供数与维护）**【已实现/已存在】（`nats/nats.py:436-676`，供跨模块经 RPC 调用）：
    | handler | 行号 | 说明 |
    |---------|------|------|
    | `create_instance` | :437 | 创建实例，支持 model_id + instance_info + operator + allowed_org_ids |
    | `delete_instance` | :466 | 删除实例，支持 inst_ids 批量 / inst_id 单个 / model_id+inst_name 定位 |
    | `list_instances` | :506 | 分页查询单模型实例列表，支持过滤条件与 format 转换 |
    | `search_model_attrs` | :545 | 查询模型属性定义列表 |
    | `search_models` | :559 | 查询模型列表，可按 classification_id 过滤 |
    | `search_classifications` | :579 | 查询模型分类列表 |
    | `search_model_associations` | :593 | 查询模型关联定义（源/目标维度） |
    | `search_instance_associations` | :607 | 查询实例关联列表（按 model_asst_id 分组） |
    | `create_instance_association` | :627 | 创建实例关联（写，需 src_inst_id/dst_inst_id/model_asst_id） |
    | `delete_instance_association` | :659 | 删除实例关联（写，需 asso_id） |
- **RPC 客户端**（`apps/rpc/cmdb.py:44-94`）：为上述第五类 NATS handler 中的 8 个新增 RPC 包装方法供跨模块调用：`list_instances`、`search_model_attrs`、`search_models`、`search_classifications`、`search_model_associations`、`search_instance_associations`、`create_instance_association`、`delete_instance_association`；`search_instances`/`search_instances_batch` 为原有包装方法。注意：第五类 NATS handler 中的 `create_instance`、`delete_instance` 暂无对应 RPC 包装方法，仅可经 NATS 主题直接调用【已实现/已存在】。
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
- **网络设备配置文件采集**【已实现/已存在】：对象树新增 `network_config_file`，节点参数封装登录账号、口令、特权口令、命令列表与配置名称，回调仍走 `receive_config_file_result`，因此复用既有配置文件版本存储与详情查看链路（`constants/constants.py:377-387`、`node_configs/network_config_file.py:5-63`）。
- **IP 地址管理发现回写**【已实现/已存在】：对象树新增 `ip_discovery`；服务层从任务的 `instances/params` 合并读取 `subnet_ids`、`scan_method`、`ports`，再把 VictoriaMetrics 中的 `ip_info` 行按子网回写为在线 / 离线地址，同时重算子网利用率；手工维护地址不被覆盖（`constants/constants.py:391-403`、`services/ipam_discovery.py:8-175`）。

对应 PRD：[[spec/prd/CMDB/自动发现.md#3.2 采集任务]]；对应功能清单：[[spec/fuctionlist/01-CMDB配置管理-功能清单.md#5. 自动发现（采集）]]
> 证据来源：server/apps/cmdb/constants/constants.py:377-403，server/apps/cmdb/node_configs/network_config_file.py:5-63，server/apps/cmdb/services/ipam_discovery.py:8-175　|　同步基线：83091efe　|　【已实现】

## 6. 风险 / 待确认
- 双图库后端按 `FALKORDB_HOST` 环境变量在运行期单选（`graph/drivers/graph_client.py:46-52`），非并存；切换条件已明确【已实现/已存在】。
- Neo4j 搜索/过滤/权限取数路径已参数化（`graph/neo4j.py:10,301`），该路径 Cypher 注入风险已消除；但 `create_entity`（`:197` `CREATE (n:{label} {properties_str})`）、按 id 取详情（`:408` `WHERE id(n) = {id}`）等写入/查询路径仍为 f-string 拼接，参数化尚未覆盖全部查询，存量注入面仍需收口【已实现/待确认风险】。
- 凭据加密密钥管理与轮转策略【待确认】。

## 7. 证据来源
`server/apps/cmdb/{urls.py,models/*,graph/*,graph/neo4j.py,graph/drivers/graph_client.py,collection/*,collection/collect_plugin/oceanstor.py,constants/constants.py,tasks/celery_tasks.py,nats/nats.py,services/rack_room.py,services/ipam_discovery.py,node_configs/network_config_file.py,views/collect.py:66-68,views/instance.py:999-1150,support-files/model_config.xlsx}`；`server/apps/rpc/cmdb.py:44-94`。
