# CMDB 新增配置采集对象扩展设计

日期：2026-06-30

## 背景

本设计用于补齐 `/Users/windyzhao/Downloads/cmdb-new-objects` 中 48 类新增配置采集对象。经过讨论，边界调整为：

- 模型、模型字段、模型关联关系全部放在社区版，沿用现有 `server/apps/cmdb/support-files/model_config.xlsx` 链路。
- 配置采集能力全部放在商业版，走 `server/apps/cmdb_enterprise/collect/` 的 `CollectEnterpriseExtension` 扩展链路。
- Stargazer 新增采集插件全部放在 `agents/stargazer/enterprise/plugins/inputs/`，社区 agent 不暴露这些商业采集入口。
- 先用 5 个对象跑通端到端链路，再批量补齐剩余对象。

## 现有链路依据

模型元数据以 `server/apps/cmdb/support-files/model_config.xlsx` 为准：

- `classifications` 表定义模型分组。
- `models.classification_id` 决定模型所属分组。
- 字段、唯一键、关联关系继续跟随当前 Excel 导入链路，不额外新增旁路配置。

配置采集链路以社区版现有实现为准：

- 采集对象树：`server/apps/cmdb/constants/constants.py` 的 `COLLECT_OBJ_TREE`。
- 采集参数：`server/apps/cmdb/node_configs/` 下的 `BaseNodeParams`、`SSHNodeParamsMixin` 及协议类配置。
- 采集插件注册：`server/apps/cmdb/collection/plugins/community/`。
- 指标到模型转换：`server/apps/cmdb/collection/collect_plugin/`。
- 指标类型映射：`server/apps/cmdb/collection/constants.py`。
- Agent 端采集脚本：`agents/stargazer/plugins/inputs/`。

## 分组判断规则

模型分组不从配置采集对象树推断，而从 `model_config.xlsx` 的既有分组体系归类。采集入口分类和模型分组可以一致，也可以不同；例如采集入口可能是 `storage_device`，但模型主对象仍可落在 `harware`，部件落在 `hardware_components`。

本次采用以下规则：

1. 中间件及其内部子对象放入 `middleware`。
2. 数据库、数据库集群及内部拓扑对象放入 `database`。
3. 物理硬件主设备放入现有 `harware`，保持既有拼写。
4. 硬件部件、存储池、磁盘、卷、端口、控制器等放入 `hardware_components`。
5. 网络、安全、负载均衡、FC 交换相关对象放入 `network_device`。
6. 云平台、虚拟化平台、超融合平台的模型分组保持产品域表达；采集入口首期统一收敛到 `cloud`。
7. 图标 `icn` 首期复用现有图标，后续再按产品体验补齐专用图标。

## 首批跑通对象

首批选择 5 个对象，覆盖协议采集、JOB 采集、数据库复用、REST Redfish、多对象关系建模几类典型路径：

| 对象 | 主模型 | 模型分组 | 采集入口 | Driver | 目标 |
| --- | --- | --- | --- | --- | --- |
| Nacos | `nacos` | `middleware` | `middleware` | `PROTOCOL` | REST/token 类中间件多对象样板 |
| IBM MQ | `ibmmq` | `middleware` | `middleware` | `JOB` | SSH/JOB 命令发现类中间件样板 |
| OceanBase | `oceanbase` | `database` | `databases` | `PROTOCOL` | SQL 协议多层数据库样板 |
| HighGo | `highgo` | `database` | `databases` | `PROTOCOL` | PostgreSQL 兼容数据库复用样板 |
| Server BMC Redfish | `server_bmc` | `harware` | `host_manage` | `PROTOCOL` | 带外管理硬件及部件样板 |

### Nacos

模型：

- `nacos`
- `nacos_node`
- `nacos_namespace`
- `nacos_service`

关系：

- `nacos_node` belong `nacos`
- `nacos_namespace` belong `nacos`
- `nacos_service` belong `nacos`

采集：

- NodeParams：协议参数，支持 endpoint、port、username、password、token、ssl。
- Stargazer：`agents/stargazer/plugins/inputs/nacos/`。
- 指标：`nacos_info_gauge`、`nacos_node_info_gauge`、`nacos_namespace_info_gauge`、`nacos_service_info_gauge`。

### IBM MQ

模型：

- `ibmmq`
- `ibmmq_channel`
- `ibmmq_listener`
- `ibmmq_localqueue`
- `ibmmq_remotequeue`

关系：

- 所有子对象 belong `ibmmq`。

采集：

- NodeParams：SSH/JOB 参数，使用 `SSHNodeParamsMixin`。
- Stargazer：`agents/stargazer/plugins/inputs/ibmmq/`。
- 指标：`ibmmq_info_gauge`、`ibmmq_channel_info_gauge`、`ibmmq_listener_info_gauge`、`ibmmq_localqueue_info_gauge`、`ibmmq_remotequeue_info_gauge`。
- 安全边界：只执行查询类 MQ 命令，不执行变更、删除、重启类命令。

### OceanBase

模型：

- `oceanbase`
- `oceanbase_zone`
- `oceanbase_server`
- `oceanbase_tenant`

关系：

- `oceanbase_zone` belong `oceanbase`
- `oceanbase_server` belong `oceanbase_zone`
- `oceanbase_tenant` belong `oceanbase`

采集：

- NodeParams：数据库协议参数，支持 host、port、username、password、database、ssl。
- Stargazer：`agents/stargazer/plugins/inputs/oceanbase/`。
- 指标：`oceanbase_info_gauge`、`oceanbase_zone_info_gauge`、`oceanbase_server_info_gauge`、`oceanbase_tenant_info_gauge`。

### HighGo

模型：

- `highgo`

关系：

- 首批不新增内部子对象，先作为单实例数据库对象跑通。

采集：

- NodeParams：复用 PostgreSQL 兼容协议参数。
- Stargazer：`agents/stargazer/plugins/inputs/highgo/`。
- 指标：`highgo_info_gauge`。
- 实现策略：优先复用 PostgreSQL 采集器能力，formatter 只做 HighGo 字段映射和模型 ID 差异处理。

### Server BMC Redfish

模型：

- `server_bmc`
- `server_bmc_cpu`
- `server_bmc_memory`
- `server_bmc_disk`
- `server_bmc_vdisk`
- `server_bmc_nic`

关系：

- 所有部件对象 belong `server_bmc`。
- `server_bmc` 与 `physcial_server` 的关联在采集数据拉取入库阶段完成，优先基于序列号、BMC IP、MAC 等稳定标识匹配。

采集：

- NodeParams：Redfish 协议参数，支持 endpoint、port、username、password、ssl、timeout。
- Stargazer：`agents/stargazer/plugins/inputs/server_bmc/`。
- 指标：`server_bmc_info_gauge`、`server_bmc_cpu_info_gauge`、`server_bmc_memory_info_gauge`、`server_bmc_disk_info_gauge`、`server_bmc_vdisk_info_gauge`、`server_bmc_nic_info_gauge`。
- 安全边界：只使用 Redfish GET 查询接口，不调用 Reset、Power、Update、Delete 等变更接口。

## 全量对象分组建议

| 编号 | 对象 | 主模型建议 | 主模型分组 | 子对象分组策略 |
| --- | --- | --- | --- | --- |
| 1 | IBM MQ | `ibmmq` | `middleware` | MQ channel/listener/queue 等放 `middleware` |
| 2 | TongLinkQ | `tonglinkq` | `middleware` | 队列、通道等放 `middleware` |
| 3 | TongGTP | `tonggtp` | `middleware` | 实例、节点等放 `middleware` |
| 4 | IHS | `ihs` | `middleware` | vhost、listener 等放 `middleware` |
| 5 | CICS | `cics` | `middleware` | region、transaction 等放 `middleware` |
| 6 | IBM Storwize SMI-S | `ibm_storwize` | `harware` | pool、volume、disk、port 等放 `hardware_components` |
| 7 | IBM DS SMI-S | `ibm_ds` | `harware` | pool、volume、disk、port 等放 `hardware_components` |
| 8 | EMC Symmetrix | `emc_symmetrix` | `harware` | pool、volume、disk、port 等放 `hardware_components` |
| 9 | HDS VSP | `hds_vsp` | `harware` | pool、volume、disk、port 等放 `hardware_components` |
| 10 | MacroSAN | `macrosan` | `harware` | pool、volume、disk、port 等放 `hardware_components` |
| 11 | Pure Storage | `pure_array` | `harware` | volume、host、port 等放 `hardware_components` |
| 12 | NetApp | `netapp_cluster` | `harware` | svm、aggregate、volume、lif 等放 `hardware_components` |
| 13 | Oracle ZFS | `oraclezfs` | `harware` | pool、project、share、disk 等放 `hardware_components` |
| 14 | Infinidat | `infinidat` | `harware` | pool、volume、host、port 等放 `hardware_components` |
| 15 | Tape Library | `tape_library` | `harware` | drive、slot、media、robot 等放 `hardware_components` |
| 16 | Brocade FC | `brocade_fc` | `network_device` | port、zone、alias 等放 `network_device` |
| 17 | Cisco FC | `cisco_fc` | `network_device` | port、vsan、zone 等放 `network_device` |
| 18 | F5 | `f5` | `network_device` | pool、virtual_server、node 等放 `network_device` |
| 19 | Informix | `informix` | `database` | dbspace、chunk、database 等放 `database` |
| 20 | Sybase | `sybase` | `database` | database、device、login 等放 `database` |
| 21 | Couchbase | `couchbase` | `database` | bucket、node 等放 `database` |
| 22 | Mycat | `mycat` | `database` | schema、data_node、data_host 等放 `database` |
| 23 | SAP HANA | `sap_hana` | `database` | tenant、host、service 等放 `database` |
| 24 | IRIS | `iris` | `database` | namespace、database、mirror 等放 `database` |
| 25 | AIX | `aix` | `host_manage` | CPU、内存、磁盘、网卡等如独立建模则放 `hardware_components` |
| 26 | HP-UX | `hpux` | `host_manage` | CPU、内存、磁盘、网卡等如独立建模则放 `hardware_components` |
| 27 | HMC | `hmc` | `harware` | managed_system、lpar 等放 `hardware_components` |
| 28 | Server BMC Redfish | `server_bmc` | `harware` | CPU、内存、磁盘、网卡、虚拟盘放 `hardware_components` |
| 29 | HDFS | `hdfs` | `middleware` | namenode、datanode、namespace 等放 `middleware` |
| 30 | YARN | `yarn` | `middleware` | resource_manager、node_manager、queue 等放 `middleware` |
| 31 | Storm | `storm` | `middleware` | supervisor、topology、worker 等放 `middleware` |
| 32 | Ambari | `ambari` | `middleware` | cluster、host、service、component 等放 `middleware`；后续可独立分组 |
| 33 | Nacos | `nacos` | `middleware` | node、namespace、service 等放 `middleware` |
| 34 | Redis Sentinel | `redis_sentinel` | `database` | master、sentinel、instance 等放 `database` |
| 35 | BES | `bes` | `middleware` | server、app、datasource 等放 `middleware` |
| 36 | Apusic | `apusic` | `middleware` | server、app、datasource 等放 `middleware` |
| 37 | InforSuite AS | `inforsuite_as` | `middleware` | server、app、datasource 等放 `middleware` |
| 38 | OceanBase | `oceanbase` | `database` | zone、server、tenant 等放 `database` |
| 39 | GBase 8s | `gbase8s` | `database` | dbspace、chunk、database 等放 `database` |
| 40 | Oscar | `oscar` | `database` | 首批可单实例，后续库/表空间等放 `database` |
| 41 | Security Device | `security_device` | `network_device` | interface、policy、zone 等放 `network_device` |
| 42 | Domestic Linux Host | `domestic_linux` | `host_manage` | CPU、内存、磁盘、网卡等如独立建模则放 `hardware_components` |
| 43 | HighGo | `highgo` | `database` | 首批单实例，后续库/表空间等放 `database` |
| 44 | TongRDS | `tongrds` | `database` | instance、database、tablespace 等放 `database` |
| 45 | TDSQL | `tdsql` | `database` | shard、set、node、tenant 等放 `database` |
| 46 | ZStack | `zstack` | `zstack` | host、vm、cluster、network、volume 等放 `zstack` |
| 47 | H3C CAS | `h3c_cas` | `h3c_cas` | host、vm、cluster、datastore、network 等放 `h3c_cas` |
| 48 | XSKY | `xsky` | `harware` | pool、volume、host、disk 等放 `hardware_components` |

## 采集对象树策略

采集入口延续现有 `COLLECT_OBJ_TREE`，不为每个模型分组都新增入口：

- `middleware`：IBM MQ、TongLinkQ、TongGTP、IHS、CICS、HDFS、YARN、Storm、Ambari、Nacos、BES、Apusic、InforSuite AS。
- `databases`：Informix、Sybase、Couchbase、Mycat、SAP HANA、IRIS、Redis Sentinel、OceanBase、GBase 8s、Oscar、HighGo、TongRDS、TDSQL。
- `storage_device`：IBM Storwize、IBM DS、EMC Symmetrix、HDS VSP、MacroSAN、Pure Storage、NetApp、Oracle ZFS、Infinidat、Tape Library、XSKY。
- `network`：Brocade FC、Cisco FC、F5、Security Device。
- `host_manage`：AIX、HP-UX、Domestic Linux Host、Server BMC Redfish、HMC。
- `cloud`：ZStack、H3C CAS。

## 通用实现模式

### 社区模型配置

新增对象统一写入 `model_config.xlsx`：

- `models`：模型 ID、模型名称、图标、`classification_id`。
- 字段表：每个模型按文档定义字段，优先使用稳定标识字段作为唯一键。
- 关联关系：主从对象统一用 belong 关系，避免首批引入复杂跨域关系。

唯一键建议：

- 管理类主对象：`inst_name` 或产品稳定 ID。
- 协议对象：优先产品原生 uuid/id，其次 name + endpoint。
- 部件对象：父对象唯一键 + 本地 stable id/name。
- 不使用易变化状态字段作为唯一键。

### NodeParams

- REST/token 类：继承 `BaseNodeParams`，`executor_type="protocol"`。
- DB 协议类：复用或扩展现有数据库 NodeParams。
- SSH/JOB 类：继承 `SSHNodeParamsMixin`。
- SNMP 类：复用网络设备 SNMP 参数模式。
- SMI-S/CIM 类：新增通用 SMI-S NodeParams，供 IBM/EMC/HDS 等存储复用。

### Stargazer 插件

每个对象在 `agents/stargazer/plugins/inputs/<model_id>/` 下提供：

- `plugin.yml`
- 采集脚本或协议实现
- 必要的只读查询封装

安全要求：

- 默认只读。
- JOB 类脚本必须避免重启、删除、变更配置。
- 支持超时、失败降级、局部失败不影响其他指标输出。
- 输出稳定结构，避免因字段缺失导致 formatter 崩溃。

### Formatter

formatter 负责把 Stargazer 指标转换为 CMDB 图实例：

- 单对象可复用现有协议 formatter 模式。
- 多对象用类似 OceanStor 的 `MODEL_ORDER`、`field_mappings`、belong helper。
- 关系创建只基于本批采集到的稳定 key。
- Server BMC 与 `physcial_server` 的跨模型关联在采集数据拉取入库阶段完成，避免前置到 Agent 侧。

## 批次计划

### Batch 1：完整链路样板

对象：Nacos、IBM MQ、OceanBase、HighGo、Server BMC Redfish。

交付目标：

- 模型、字段、关系进入社区模型 Excel。
- 采集对象树可选择。
- NodeParams 可生成前端采集表单。
- Stargazer 可输出指标。
- Server formatter 可入库主对象和子对象。
- 单测覆盖模型注册、NodeParams 注册、formatter 转换、插件输出解析。

### Batch 2：同类扩展

对象：

- 中间件：TongLinkQ、TongGTP、IHS、CICS、BES、Apusic、InforSuite AS。
- 数据库：Informix、Sybase、Couchbase、Mycat、SAP HANA、IRIS、Redis Sentinel、GBase 8s、Oscar、TongRDS、TDSQL。

策略：

- 复用 Batch 1 的 JOB、REST、DB 协议样板。
- 先单对象或主从一层关系，避免一次性做深层拓扑。

### Batch 3：存储与网络设备

对象：

- 存储：IBM Storwize、IBM DS、EMC Symmetrix、HDS VSP、MacroSAN、Pure Storage、NetApp、Oracle ZFS、Infinidat、Tape Library、XSKY。
- 网络：Brocade FC、Cisco FC、F5、Security Device。

策略：

- 提炼 SMI-S/CIM 通用参数和插件基类。
- SNMP/SSH-CLI 设备延续网络采集样板。
- 存储主对象归 `harware`，部件归 `hardware_components`，采集入口仍在 `storage_device`。

### Batch 4：主机、HMC、大数据、平台

对象：

- 主机：AIX、HP-UX、Domestic Linux Host。
- 管理：HMC。
- 大数据：HDFS、YARN、Storm、Ambari。
- 平台：ZStack、H3C CAS。

策略：

- 主机类谨慎复用现有 host manage 链路，避免与现有主机模型冲突。
- ZStack、H3C CAS 采集入口统一放在 `cloud`。
- 大数据组件先放 `middleware`，后续如产品导航需要再独立分组。

## 测试与验收

最小验收：

- 模型 Excel 可被现有导入流程解析。
- 每个新增 NodeParams 注册 `(model_id, driver_type)` 成功。
- 每个新增采集插件注册 `(task_type, model_id)` 成功。
- Stargazer 插件在 mock 输入下输出预期指标。
- Formatter 对缺字段、空数组、局部失败有稳定行为。
- 多对象关系写入时不依赖采集顺序以外的隐式状态。

推荐测试：

- `server/apps/cmdb/tests/` 增加 NodeParams、plugin registry、formatter 单测。
- `agents/stargazer/tests/` 增加插件配置和输出解析单测。
- 对 JOB 类插件加入命令白名单或 dry-run 测试，确认只读。

## 已确认决策

- HMC 首期放入 `harware`，不新增独立 `hmc` 模型分组。
- XSKY 按存储统一规则归 `harware`/`hardware_components`，不新增独立 `xsky` 模型分组。
- ZStack、H3C CAS 的采集入口共用 `cloud`。
- Server BMC 与 `physcial_server` 的自动关联在采集完成后的数据拉取入库阶段实现。
- 每个对象的图标 `icn` 首期使用现有图标。
