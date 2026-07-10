# 模块 ARD：CMDB（配置管理）

> 路径 `server/apps/cmdb` ｜ API 前缀 `api/v1/cmdb/`

## 1. 职责【已实现/已存在】
管理基础设施资产清单、模型定义与自动化采集；以图数据库维护资产关系与拓扑，记录变更历史，支持配置文件版本化，并提供 IPAM 子网/IP 视图、IP 发现与自动对账能力。

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
| IPAMReconcileSource | `models/ipam_models.py:7` | IPAM 自动对账来源登记表，记录参与对账的 `(model_id, ip_attr_id)`，默认由迁移预置 `host.ip_addr` 与 `network.ip` |

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

**IPAM 服务**【已实现/已存在】：围绕内置 `subnet` / `ip` 模型提供子网合法性、视图、发现和对账能力。
- `services/ipam_subnet.py`：`validate_subnet_no_overlap` 在创建/更新 `subnet` 实例时校验网段重叠；入口挂在 `services/instance.py:553-555` 与 `services/instance.py:630-636`。
- `services/ipam_view.py`：`build_ipam_view` 汇总单个子网容量、利用率、IP 状态计数与落库 IP 列表（`:7-45`）。
- `services/ipam_discovery.py`：子网发现任务从采集任务 `instances` 字段读取 `subnet_ids` / `scan_method` / `ports`，下发给 Stargazer，并通过回调结果创建/更新 `ip` 实例、标记离线、回写子网利用率（`:16-218`）。
- `services/ipam_reconcile.py`：`run_reconciliation` 从 `IPAMReconcileSource` 读取参与对账的 CI 模型与 IP 字段，匹配子网，创建/更新 `ip` 实例、保护手工记录、识别冲突并回写子网利用率（`:37-228`）。
- `utils/ipam_cidr.py`：承载 CIDR 解析、容量计算、重叠判断与 IP 命中子网等纯逻辑能力。

## 3. 接口【已实现/已存在】
`urls.py` 路由组：`classification`/`model`/`instance`/`change_record`/`collect`/`config_file_versions`/`oid`/`field_groups`/`user_configs`/`public_enum_libraries`/`subscription`/`node_mgmt_sync`/`collect_tool`/`k8s_setup`；开放端点 `open_api/k8s_setup`；企业特性 `custom_reporting/{tasks,ingest}`。

**instance 路由组新增拓扑 / 布局 / IPAM 端点**【已实现/已存在】（`views/instance.py:993-1133`）：
| 端点 | 方法 | 说明 |
|------|------|------|
| `GET instance/ipam_view/<inst_id>` | `InstanceViewSet.ipam_view` | 子网 IP 视图：返回容量、利用率、状态计数与落库 IP 列表 |
| `GET instance/room_layout/<model_id>/<inst_id>` | `InstanceViewSet.room_layout` | 机房俯视平面图：返回该机房下机柜的 row/col/类型/U 占用率供前端布局渲染 |
| `GET instance/rack_layout/<model_id>/<inst_id>` | `InstanceViewSet.rack_layout` | 机柜正视 U 图：返回机柜总 U 数及其 contains 设备的 U 位排布 |
| `POST instance/ipam_reconcile` | `InstanceViewSet.ipam_reconcile` | 手动触发一次 IPAM 与 CMDB 自动对账，内部调用 `services/ipam_reconcile.run_reconciliation` |
| 3D 机房大屏数据源（**非 ViewSet REST 端点**）【已实现/已存在】：运营分析 3D 大屏组件通过内置数据源 `cmdb/get_room3d_layout`（注册于 `server/apps/operation_analysis/support-files/source_api.json:406`，`rest_api` 类型，`chartType: room3D`）消费 CMDB NATS `get_room3d_layout`（`nats/nats.py:951`），由通用取数器按 path 动态解析调用，不在 ViewSet 路由表内 |

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
- NATS：`nats/nats.py` 注册 26 个 `@nats_client.register` handler（取数前按角色/团队构建实例分组权限过滤），对外提供五类能力【已实现/已存在】：
  - **实例/模型取数**：`get_cmdb_module_data`(:264)、`get_cmdb_module_list`(:303)、`search_instances`(:354)、`search_instances_batch`(:368)、`model_inst_count`(:1147)。
  - **实例 CRUD / 显示字段**：`update_instance`(:396)、`sync_display_fields`(:736)。
  - **采集结果回传（Stargazer→CMDB）**：`receive_config_file_result`(:696，配置文件落库为 ConfigFileVersion)、`receive_collect_credential_result`(:711，凭据探测命中)。**注：原 `receive_ip_discovery_result` handler 已下线，IP 发现结果回写由服务层 `services/ipam_discovery.py:205` `apply_discovery_result`（落库 `ip` 台账并更新在线/离线状态）与 `:299` `apply_ip_discovery_vm_rows`（回写 VictoriaMetrics 离线 IP 行）协同完成。**
  - **运营分析统计取数**：`get_cmdb_statistics`(:758)、`get_change_trend`(:887)、`get_instance_group_by`(:960)、`get_model_inst_statistics`(:1024)、`get_cmdb_model_instance_top`(:1075)、`get_cmdb_collect_statistics`(:1120)。
  - **机房 3D 布局取数**【已实现/已存在】：`get_room3d_layout`(`nats/nats.py:952-1050`) 返回机房的 row/col 网格、U 占用与设备摘要；payload 中 `rack_type`（`datacenter_type` 枚举 id）由 `_get_room3d_rack_type_name_map`(`nats/nats.py:942-949`) 解析为可读名称 `rack_type_name`（无值时不带该字段），供 3D 大屏图例与机柜顶贴图渲染；`rack_id`/`rack_name` 字段源统一改取 `item['rack_id']` / `item['rack_name']`（当 `instance_name` 缺失时 fallback 到 `rack_id`）。
  - **实例/模型/关联通用查询与 CRUD（对外 RPC 供数与维护）**【已实现/已存在】（`nats/nats.py:453-679`，供跨模块经 RPC 调用）：
    | handler | 行号 | 说明 |
    |---------|------|------|
    | `create_instance` | :453 | 创建实例，支持 model_id + instance_info + operator + allowed_org_ids |
    | `delete_instance` | :482 | 删除实例，支持 inst_ids 批量 / inst_id 单个 / model_id+inst_name 定位 |
    | `list_instances` | :522 | 分页查询单模型实例列表，支持过滤条件与 format 转换 |
    | `search_model_attrs` | :562 | 查询模型属性定义列表 |
    | `search_models` | :576 | 查询模型列表，可按 classification_id 过滤 |
    | `search_classifications` | :596 | 查询模型分类列表 |
    | `search_model_associations` | :610 | 查询模型关联定义（源/目标维度） |
    | `search_instance_associations` | :624 | 查询实例关联列表（按 model_asst_id 分组） |
    | `create_instance_association` | :643 | 创建实例关联（写，需 src_inst_id/dst_inst_id/model_asst_id） |
    | `delete_instance_association` | :675 | 删除实例关联（写，需 asso_id） |
- **RPC 客户端**（`apps/rpc/cmdb.py:44-94`）：为上述第五类 NATS handler 中的 8 个新增 RPC 包装方法供跨模块调用：`list_instances`、`search_model_attrs`、`search_models`、`search_classifications`、`search_model_associations`、`search_instance_associations`、`create_instance_association`、`delete_instance_association`；`search_instances`/`search_instances_batch` 为原有包装方法。注意：第五类 NATS handler 中的 `create_instance`、`delete_instance` 暂无对应 RPC 包装方法，仅可经 NATS 主题直接调用【已实现/已存在】。
- Celery：`tasks/celery_tasks.py` 注册 14 个 `@shared_task`，详见 §5。

## 5. 核心数据流 / 任务

### 任务（Celery）【已实现/已存在】
`tasks/celery_tasks.py` 注册 14 个 `@shared_task`：
| 任务 | 行号 | 作用 |
|------|------|------|
| `sync_collect_task` | :38 | 执行单次采集，分发到 `CollectDispatchService`/协议采集，更新状态并触发订阅通知 |
| `sync_periodic_update_task_status` | :202 | 周期巡检并更新采集任务状态 |
| `sync_collect_credential_results_task` | :232 | 同步凭据探测结果 |
| `sync_cmdb_display_fields_task` | :242 | 同步实例展示字段配置 |
| `execute_collect_tool_debug_task` | :287 | 采集工具调试执行 |
| `sync_public_enum_library_snapshots_task` | :305 | 同步共享枚举库快照 |
| `check_subscription_rules` | :313 | 巡检变更订阅规则 |
| `send_subscription_notifications` | :318 | 发送订阅通知 |
| `daily_data_cleanup_task` | :325 | 每日数据清理 |
| `reconcile_instance_auto_association_task` | :333 | 单实例自动关联对账 |
| `full_sync_auto_association_rule_task` | :341 | 自动关联规则全量同步 |
| `sync_node_mgmt_hosts` | :349 | 同步节点管理主机 |
| `collect_node_mgmt_hosts` | :361 | 采集节点管理主机 |
| `reconcile_ipam_task` | :372 | 周期执行 IPAM 与 CMDB 自动对账，调用 `services/ipam_reconcile.run_reconciliation` |

### 管理命令【已实现/已存在】
- `management/commands/model_init.py:7`：初始化 CMDB 模型种子。
- `management/commands/init_oid.py:11`：初始化 SNMP OID 映射。
- `management/commands/init_field_groups.py:15`：初始化字段分组。
- `management/commands/init_display_fields.py:24`：初始化 `_display` 字段与相关展示配置。

### 采集插件【已实现/已存在】
采集能力分两层：`collection/collect_plugin/` 下的采集映射实现（Python 文件），与 `constants/constants.py` 中面向 UI 的插件目录（`COLLECTION_METRICS` 分组，含 Beta 标记，部分条目由 Stargazer 以 JOB/PROTOCOL 驱动，无独立映射文件）。

- **协议 / 网络**：SNMP/SSH、网络拓扑（LLDP/CDP/FDB/ARP）（`network.py`、`topology/`、`protocol.py`）。
- **云平台**（constants.py:488-562）：阿里云、腾讯云（`qcloud.py`，id=`qcloud`，目录中仅此一项，不存在独立 Tencent 插件）、华为云、ManageOne、OpenStack、SmartX、FusionInsight（`aliyun.py`/`qcloud.py`/`hwcloud.py`/`manageone.py`/`openstack.py`/`smartx.py`/`fusioninsight.py`）。
- **容器 / 虚拟化**（constants.py:318-359）：K8s、Docker（`k8s.py`）；VMware vCenter（`vmware.py`）。目录中无 Hyper-V 条目，亦无 hyperv 插件文件。
- **存储设备**（constants.py:472-485，近期新增 git 640548eab）：华为存储 OceanStor（`oceanstor.py`），对象树 `storage_device→storage`，采集存储设备/存储池/磁盘/卷（LUN），主对象 `storage`，子对象 `storage_pool/storage_disk/storage_volume`，复用云家族机制（`oceanstor.py:17-19`）。
- **数据库**（constants.py:376-471）：MySQL、InfluxDB、PostgreSQL、MSSQL、Redis、MongoDB、Elasticsearch、HBase、TiDB（实现集中于 `databases.py`）。目录与映射中均无 Oracle 条目。
- **中间件**（constants.py:611-855）：Nginx、MinIO、Zookeeper、Kafka、Tomcat、Jetty、WebLogic、KeepAlive、Spark（id=`spark`，constants.py:846）等共 20+ 项，多为 JOB 驱动。目录中无 Hadoop 条目；大数据相关现仅 Spark（中间件分组）与 FusionInsight（云平台分组）。
- **配置文件采集**（task_type=`config_file`，constants.py:578）：由 Stargazer 采集后经 NATS `receive_config_file_result`(nats.py:680) 回传，落库为 `ConfigFileVersion`，内容存 MinIO。
- **网络设备配置文件采集**【已实现/已存在】：对象树新增 `network_config_file`，节点参数封装登录账号、口令、特权口令、命令列表与配置名称，回调仍走 `receive_config_file_result`，因此复用既有配置文件版本存储与详情查看链路（`constants/constants.py:377-387`、`node_configs/network_config_file.py:5-63`）。
- **IP 地址管理发现回写**【已实现/已存在】：对象树新增 `ip_discovery`；服务层从任务的 `instances/params` 合并读取 `subnet_ids`、`scan_method`、`ports`，再把 VictoriaMetrics 中的 `ip_info` 行按子网回写为在线 / 离线地址，同时重算子网利用率；手工维护地址不被覆盖（`constants/constants.py:391-403`、`services/ipam_discovery.py:8-175`）。
- **IP 发现采集**（task_type=`ip` 且 `input_method=CollectInputMethod.SUBNET`）：`sync_collect_task` 在 `tasks/celery_tasks.py:72-74` 派发子网扫描任务，由 Stargazer 执行；结果经 Stargazer 回传后由 `services/ipam_discovery.py`（`apply_discovery_result` 在 `:205` 创建/更新在线 IP、标记离线并回写子网利用率；`apply_ip_discovery_vm_rows` 在 `:299` 处理 VictoriaMetrics 离线行）落库。**注：原 NATS `receive_ip_discovery_result` handler 与 `services.ipam_discovery.maybe_dispatch_ip_discovery` 函数在本轮已下线（被 `tests/test_ipam_discovery_task.py:64` 显式断言不存在），功能改由服务层直连 Stargazer 回调完成。**

对应 PRD：[[spec/prd/CMDB/自动发现.md#3.2 采集任务]]；对应功能清单：[[spec/fuctionlist/01-CMDB配置管理-功能清单.md#5. 自动发现（采集）]]

## 6. 风险 / 待确认
- 双图库后端按 `FALKORDB_HOST` 环境变量在运行期单选（`graph/drivers/graph_client.py:46-52`），非并存；切换条件已明确【已实现/已存在】。
- Neo4j 搜索/过滤/权限取数路径已参数化（`graph/neo4j.py:10,301`），该路径 Cypher 注入风险已消除；但 `create_entity`（`:197` `CREATE (n:{label} {properties_str})`）、按 id 取详情（`:408` `WHERE id(n) = {id}`）等写入/查询路径仍为 f-string 拼接，参数化尚未覆盖全部查询，存量注入面仍需收口【已实现/待确认风险】。
- 凭据加密密钥管理与轮转策略【待确认】。

## 2026-07-01 Code-ARD 校准
- `[cmdb#20260701-001]` IPAM 视图、发现与自动对账能力已收录到职责、模型、接口、数据流与证据来源。
- `[cmdb#20260701-002]` NATS handler 数量与 Celery 任务清单按 IPAM 入口新增后的当前位置更新。
- `[cmdb#20260701-005]` 补录模型初始化、OID 初始化、字段分组初始化、`_display` 字段初始化等管理命令入口。

## 2026-07-09 Code-ARD 校准
- `[cmdb#20260709-001]` NATS `get_room3d_layout` payload 增 `rack_type_name` 字段：依据 `rack` 模型 `datacenter_type` 枚举属性将 id 解析为可读名称（计算/网络/存储/安全/其他/未分类），无值时不带该字段。消费方为运营分析 3D 大屏 `web/src/app/ops-analysis/components/widgets/room3D/`（数据源 `cmdb/get_room3d_layout` 注册于 `server/apps/operation_analysis/support-files/source_api.json:406`）。
- `[cmdb#20260709-002]` `get_room3d_layout` 中 `rack_id`/`rack_name` 来源统一为 `item['rack_id']` / `item['rack_name']`（`instance_name` 缺失时 fallback 到 `rack_id`），并配套新增 `test_get_room3d_layout_falls_back_to_rack_id_when_name_missing`、`test_get_room3d_layout_returns_rack_type_name_from_cmdb_enum` 两个测试。
- `[cmdb#20260709-003]` 双向校验修订：`InstanceViewSet.room3d_layout` REST 端点**不存在**（3D 数据走内置数据源 rest_api，不在 ViewSet 路由表内）；NATS `receive_ip_discovery_result` handler 与 `services.ipam_discovery.maybe_dispatch_ip_discovery` 函数**已下线**（功能下沉到 `services/ipam_discovery.py:205,299` 服务层直连 Stargazer 回调）。spec 删除相关端点行，证据行按代码当前位置刷新。

## 7. 证据来源
`server/apps/cmdb/{urls.py,models/*,models/ipam_models.py:7,graph/*,graph/neo4j.py,graph/drivers/graph_client.py,collection/*,collection/collect_plugin/oceanstor.py,constants/constants.py,tasks/celery_tasks.py:72-74,397,408,nats/nats.py:696,711,942-949,952-1050,services/rack_room.py,services/ipam_*.py,services/ipam_discovery.py:205,299,services/ipam_reconcile.py,utils/ipam_cidr.py,node_configs/network_config_file.py:5-63,views/collect.py:66-68,views/instance.py:1145,1190,1212,1282,management/commands/{model_init.py:7,init_oid.py:11,init_field_groups.py:15,init_display_fields.py:24},support-files/model_config.xlsx}`、`server/apps/operation_analysis/support-files/source_api.json:406`（3D 机房数据源 `cmdb/get_room3d_layout` 注册）；`server/apps/rpc/cmdb.py:44-94`。
