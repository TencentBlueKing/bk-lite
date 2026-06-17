# CMDB 配置管理 · 功能清单

**文档版本：** V1.0
**发布日期：** 2026-06-02
**适用范围：** BK-Lite CMDB 配置管理模块
**编制依据：** CMDB PRD v1.5（2026-05-28）与 `server/apps/cmdb` 源代码核对

---

## 一、模块定位

CMDB 是平台统一的资产与配置数据中心，围绕模型定义、资产维护、关系管理、自动采集、变更追踪五类场景提供能力。模型元数据存于 PostgreSQL，实例与关系存于图数据库（FalkorDB），对外输出资产清单、关系拓扑、变更档案与订阅提醒。本清单仅列已实现能力。

## 二、功能清单

### 1. 模型管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 模型分类管理 | 模型分类的新增、编辑、删除、列表查看 | — | GA |
| 模型管理 | 模型的新增、编辑、删除、详情查看 | 删除模型前须先清理该模型下的实例与关系 | GA |
| 模型复制 | 基于已有模型复制创建新模型 | 可按需复制属性、字段分组、联合唯一规则与关系 | GA |
| 属性管理 | 模型属性的新增、编辑、删除 | 默认含"实例名""所属组织"两个基础字段；字段类型创建后不可直接切换 | GA |
| 字段类型 | 属性支持的数据类型 | 10 种：字符串、整数、枚举、标签、时间、用户、密码、布尔、组织、表格 | GA |
| 枚举字段 | 枚举属性支持单选/多选，可复用公共选项库 | 创建后选项来源方式与单选/多选模式保持稳定，不可直接切换 | GA |
| 字段分组 | 字段分组的新增、编辑、删除、排序与字段归组 | — | GA |
| 模型关系管理 | 模型间关系的新增、删除、批量删除、列表查看 | 关系须基于已存在的源模型与目标模型建立 | GA |
| 关系类型 | 模型关系可选的业务语义类型 | 6 种：属于、组成、运行于、安装于、包含、关联 | GA |
| 映射约束 | 关系的数量映射约束 | 1:1、1:n、n:1、n:n | GA |
| 联合唯一规则 | 对单字段或多字段组合设置唯一约束 | 规则生效后实例新增/编辑均须满足唯一约束 | GA |
| 自动关联规则 | 基于字段匹配在实例间自动建立/刷新关联 | 依附于具体模型关系配置，同一关系可配多条规则；规则变更后触发关系同步 | GA |
| 模型配置导入导出 | 模型定义的导入导出，用于模板复用与跨环境迁移 | 内容含关系与自动关联规则定义 | GA |

### 2. 资产管理（实例）

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 实例查询 | 按模型查询实例，支持筛选、分页、排序 | 支持大小写敏感控制 | GA |
| 实例增删改 | 实例的新增、编辑、删除 | — | GA |
| 批量操作 | 实例批量更新、批量删除 | 须对目标实例全部具备操作权限 | GA |
| 实例导入 | 下载导入模板，Excel 批量导入 | 按组织权限生效，仅能导入到有权限的组织范围 | GA |
| 实例导出 | 按字段或关联关系导出实例 | 支持仅导出所选字段与所选关联关系 | GA |
| 实例关联 | 实例之间建立/解除关联关系 | — | GA |
| 展示字段配置 | 按模型配置列表展示字段 | 按模型与用户分别生效 | GA |
| 实例总数查看 | 查看模型实例总数，用于资产总览与跳转 | — | GA |

### 3. 资产详情

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 基础属性查看 | 查看实例基础属性与关联关系 | — | GA |
| 轻量拓扑 | 以实例为中心查看拓扑，支持按节点继续展开 | 默认先返回首批关系层级，再按需展开下一层 | GA |
| 变更记录查看 | 查看实例相关变更记录 | — | GA |
| 配置文件版本 | 查看配置文件列表、版本历史、内容与版本差异（Diff） | 仅面向已启用配置采集并采集到的实例；仅可读取内容的版本支持查看与对比 | GA |

### 4. 资产检索与视图

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 全局全文检索 | 跨模型全文检索资产 | 可配置是否区分大小写 | GA |
| 按模型统计 | 检索结果先按模型汇总命中数，再进入单模型分页查看 | 不依赖单一模型入口 | GA |
| 常用筛选保存 | 用户保存常用筛选条件并按模型复用 | 保存于用户个人配置，非浏览器本地临时记录 | GA |
| 资产视图 | 按模型统计资产数量并提供快速跳转入口 | — | GA |

### 5. 自动发现（采集）

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 采集对象树 | 按采集对象树查看可采集对象 | 内置约 40 个采集对象，覆盖云、虚拟化、容器、网络、数据库、主机、中间件、配置文件 | GA |
| 采集任务管理 | 采集任务的新增、编辑、删除、列表与详情 | — | GA |
| 任务执行 | 手动执行采集任务 | 任务对象可选节点、模型实例、云区域等 | GA |
| 任务状态汇总 | 查看任务执行状态汇总 | — | GA |
| 采集结果摘要 | 查看新增、更新、删除、关联等结果统计 | 各类明细可展开 | GA |
| 插件说明 | 查看采集插件说明文档 | — | GA |
| 实例侧关联任务 | 在实例侧查看可关联的采集任务名称 | — | GA |
| 部分数据库采集 | MongoDB、Elasticsearch、HBase、TiDB、MSSQL 等数据库对象采集 | 部分对象处于试验阶段 | Beta |

### 6. SOID 特征库

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| sysObjectID 映射维护 | 设备 sysObjectID 映射的新增、编辑、删除、列表查询 | 用于 SNMP 网络设备类型识别 | GA |

### 7. 数据订阅

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 订阅规则管理 | 围绕模型配置订阅规则，支持启用、停用、编辑、删除、分页查看 | 规则在当前组织及下级组织可见；仅所属组织可编辑/启停 | GA |
| 订阅范围 | 选择条件筛选模式或指定实例模式 | 条件模式至少配 1 个筛选条件；指定实例模式至少选 1 个实例 | GA |
| 触发条件 | 配置触发事件类型 | 5 种：属性变化、关联变化、临近到期、实例新增、实例删除；至少选 1 种 | GA |
| 多模型关系监听 | 关联关系变更可在一条规则中监听多个关联模型 | — | GA |
| 通知配置 | 配置接收人、接收组与通知渠道 | 通知对象与通知渠道均不可为空 | GA |
| 通知聚合 | 单次通知展示实例数超限时聚合展示 | 默认展示上限 5 个实例 | GA |

### 8. 个人配置

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 展示字段配置 | 用户级保存展示字段 | 按模型与用户隔离 | GA |
| 常用筛选保存 | 用户级保存常用筛选条件 | 按用户隔离，互不影响 | GA |

### 9. 公共选项库

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 选项库管理 | 公共选项库的新增、编辑、删除、列表查询 | 被模型字段引用的选项库不允许删除 | GA |
| 引用关系查看 | 查看公共选项库被哪些模型字段引用 | — | GA |
| 枚举复用 | 枚举属性复用公共选项库统一选项定义 | 选项更新后已引用字段保持同步 | GA |

### 10. 变更记录

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 变更记录查询 | 变更记录列表与详情查看 | — | GA |
| 多维筛选 | 按变更类型、变更场景、操作人、时间范围筛选 | — | GA |
| 变更场景归类 | 每条记录归入一种变更场景 | 5 类：设备流转、关系变更、普通属性变更、自动采集/自动化变更、模型管理变更 | GA |
| 场景判定与修正 | 固定入口场景由系统判定且不可改；通用编辑入口给默认场景，可在少量相邻场景间轻量修正 | 首期不开放任意切换 | GA |
| 来源分类 | 记录变更来源（人工、自动采集、系统、导入、同步），与变更场景分开 | — | GA |

## 三、能力边界与约束

字段类型与枚举的单选/多选模式在创建后保持稳定，不支持直接切换。删除模型前必须先清理其实例与关系。配置文件版本能力只面向已采集到的配置文件，且只有可读取内容的版本才支持内容查看与对比。资产详情展示的是轻量拓扑，按需逐层展开，而非一次性加载全量关系。实例导入、批量更新、批量删除均受组织权限约束。订阅规则的管理边界严格按组织范围隔离。

## 四、平台协同

CMDB 作为统一数据底座，向监控/告警提供资产上下文与责任人信息，向作业管理提供执行目标清单，向 OpsPilot 提供资产与关系的事实数据；自动发现的采集任务由节点管理提供的采集通道（Stargazer / NATS-Executor）执行；订阅与变更通知经系统管理统一配置的通知渠道送达。

## 五、支持的采集对象与内置模型范围

以下为自动发现内置的采集对象（约 40 个，含子对象），以及随平台预置的内置模型；标注【BETA】者为试验状态采集对象。配置项（CI）以内置模型为载体，亦可由用户自定义模型扩展。

### 5.1 采集对象（自动发现）

| 采集域 | 采集对象 | 状态 |
|---|---|---|
| 容器 | Kubernetes（集群/命名空间/工作负载/Pod/节点）、Docker | GA |
| 虚拟化 | VMware vCenter（vCenter / ESXi 主机 / 虚拟机 / 数据存储） | GA |
| 网络设备 | 基于 SNMP + SOID 特征库识别的交换机、路由器、防火墙、负载均衡等 | GA |
| 云平台 | 阿里云、腾讯云 | GA |
| 主机 | Linux / Windows 主机（含磁盘、内存、网卡、GPU 等）、配置文件采集、物理服务器（SSH） | GA |
| 物理服务器（IPMI） | 通过 IPMI 采集物理服务器硬件信息 | Beta |
| 数据库 | MySQL、PostgreSQL、Redis | GA |
| 数据库（试验） | MSSQL、MongoDB、Elasticsearch、HBase、TiDB | Beta |
| 中间件 | Nginx、Apache、Tomcat、Zookeeper、Kafka、Consul、Etcd、RabbitMQ、ActiveMQ、RocketMQ、Jetty、WebLogic、WebSphere、JBoss、IIS、OpenResty、HAProxy、Squid、Tuxedo、Memcached、Ceph、Spark | GA |

### 5.2 内置模型（配置项类型）

平台预置约 40 个内置模型作为开箱即用的配置项类型，按分类组织如下；用户可在其上自定义扩展模型与字段：

| 模型分类 | 内置模型 |
|---|---|
| 主机与硬件 | 主机（host）、物理服务器（physcial_server）、网络设备（network） |
| 容器与虚拟化 | K8S 集群（k8s_cluster）、Docker（docker）、VMware vCenter（vmware_vc） |
| 云账号 | 阿里云账号（aliyun_account）、腾讯云（qcloud） |
| 数据库 | MySQL、PostgreSQL、MSSQL、Redis、MongoDB、Elasticsearch（es）、HBase、TiDB |
| 中间件 | Nginx、Apache、Tomcat、Zookeeper、Kafka、Consul、Etcd、RabbitMQ、ActiveMQ、RocketMQ、Jetty、WebLogic、WebSphere、JBoss、IIS、OpenResty、HAProxy、Squid、Tuxedo、Memcached、Ceph、Spark |
| 配置文件 | 配置文件（config_file） |

> 说明：采集对象与内置模型基本一一对应——采集对象负责把资产数据写入对应模型形成配置项实例。内置模型的属性字段、关系与唯一规则均可由用户按需调整或新增。


## 六、采集配置项（字段）明细（逐项）

> 本节逐项列出 CMDB 各采集对象（内置模型）可采集 / 维护的配置项字段，源自内置模型定义 `model_config.xlsx`。共 64 个对象、800 个字段；字段标识为模型属性 `field_id`，中文含义为属性名称口径。用户可在内置模型上自定义扩展字段。

### 主机与硬件

#### 主机（模型 `host` · 15 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `cloud` | 所属云区域 |
| `hostname` | 主机名 |
| `os_type` | 操作系统类型 |
| `os_name` | 操作系统名称 |
| `os_version` | 操作系统版本 |
| `os_bit` | 操作系统位数（32/64 位） |
| `cpu_model` | CPU 型号 |
| `cpu_core` | CPU 核数 |
| `memory` | 内存大小（GB） |
| `disk` | 磁盘容量（GB） |
| `cpu_arch` | CPU 架构（x86/ARM 等） |
| `inner_mac` | 内网 MAC 地址 |
| `proc` | 运行进程列表 |

#### 物理服务器（模型 `physcial_server` · 14 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `serial_number` | 设备序列号 |
| `cpu_vendor` | CPU 厂商 |
| `cpu_model` | CPU 型号 |
| `cpu_core` | CPU 核数 |
| `cpu_threads` | CPU 线程数 |
| `cpu_arch` | CPU 架构（x86/ARM 等） |
| `board_vendor` | 主板厂商 |
| `board_model` | 主板型号 |
| `board_serial` | 主板序列号 |
| `ip_addr` | IP 地址 |
| `model` | 设备型号 |
| `brand` | 厂商品牌 |
| `asset_code` | 资产编码 |

#### 网络设备（模型 `network` · 7 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `soid` | 设备 sysObjectID（SOID） |
| `port` | 端口号 |
| `model` | 设备型号 |
| `brand` | 厂商品牌 |
| `model_id` | 所属模型 ID |

### 容器与虚拟化

#### Docker 容器（模型 `docker` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `container_id` | 容器 ID |
| `status` | 运行状态 |
| `command` | 启动命令 |
| `created` | 创建时间 |
| `image` | 镜像 |
| `networks` | 网络列表 |
| `ports` | 端口映射 |
| `mounts` | 挂载卷 |

#### VMware ESXi 主机（模型 `vmware_esxi` · 9 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `self_vc` | 所属 vCenter |
| `resource_id` | 云资源唯一 ID |
| `cpu_cores` | CPU 核数 |
| `vcpus` | 虚拟 CPU 数 |
| `memory` | 内存大小（GB） |
| `esxi_version` | ESXi 版本 |
| `assos` | 关联关系（自动建立的关联实例） |

#### VMware vCenter（模型 `vmware_vc` · 2 字段）

| 字段标识 | 中文含义 |
|---|---|
| `vc_version` | vCenter 版本 |
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |

#### VMware 数据存储（模型 `vmware_ds` · 6 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `self_vc` | 所属 vCenter |
| `system_type` | 系统类型 |
| `resource_id` | 云资源唯一 ID |
| `storage` | 存储 |
| `url` | URL 地址 |

#### VMware 虚拟机（模型 `vmware_vm` · 19 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `self_vc` | 所属 vCenter |
| `resource_id` | 云资源唯一 ID |
| `os_name` | 操作系统名称 |
| `vcpus` | 虚拟 CPU 数 |
| `memory` | 内存大小（GB） |
| `annotation` | 备注/注解 |
| `uptime_seconds` | 已运行时长（秒） |
| `tools_version` | VMware Tools 版本 |
| `tools_status` | VMware Tools 状态 |
| `tools_running_status` | VMware Tools 运行状态 |
| `last_boot` | 上次启动时间 |
| `creation_date` | 创建日期 |
| `last_backup` | 上次备份时间 |
| `backup_policy` | 备份策略 |
| `data_disks` | 数据盘 |
| `self_esxi` | 所属 ESXi 主机 |
| `assos` | 关联关系（自动建立的关联实例） |

### 数据库

#### DB2（模型 `db2` · 12 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `version` | 版本号 |
| `db_patch` | 数据库补丁版本 |
| `db_name` | 数据库名 |
| `db_instance_name` | 数据库实例名 |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `db_character_set` | 数据库字符集 |
| `ha_mode` | 高可用模式 |
| `replication_managerole` | 复制管理角色 |
| `replication_role` | 复制角色 |
| `data_protect_mode` | 数据保护模式 |

#### Elasticsearch（模型 `es` · 13 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `log_path` | 日志路径 |
| `data_path` | 数据目录 |
| `is_master` | 是否主节点 |
| `node_name` | 节点名称 |
| `cluster_name` | 集群名称 |
| `java_version` | Java 版本 |
| `java_path` | Java 路径 |
| `conf_path` | 配置文件路径 |
| `install_path` | 安装路径 |

#### HBase（模型 `hbase` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `log_path` | 日志路径 |
| `config_file` | 配置文件 |
| `tmp_dir` | 临时目录 |
| `cluster_distributed` | 是否分布式集群 |
| `java_path` | Java 路径 |
| `java_version` | Java 版本 |

#### MongoDB（模型 `mongodb` · 12 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `mongo_path` | MongoDB 安装路径 |
| `bin_path` | 可执行文件路径 |
| `config` | 配置文件 |
| `fork` | 是否后台 fork 运行 |
| `system_log` | 系统日志配置 |
| `db_path` | 数据库数据路径 |
| `max_incoming_conn` | 最大入站连接数 |
| `database_role` | 数据库角色（主/从） |

#### MySQL（模型 `mysql` · 16 字段）

| 字段标识 | 中文含义 |
|---|---|
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `enable_binlog` | 是否开启 binlog |
| `sync_binlog` | binlog 同步策略 |
| `max_conn` | 最大连接数 |
| `max_mem` | 最大内存 |
| `basedir` | 安装根目录 |
| `datadir` | 数据目录 |
| `socket` | 套接字文件路径 |
| `bind_address` | 绑定地址 |
| `slow_query_log` | 慢查询日志开关 |
| `slow_query_log_file` | 慢查询日志文件 |
| `log_error` | 错误日志路径 |
| `wait_timeout` | 连接等待超时 |
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |

#### Oracle（模型 `oracle` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `version` | 版本号 |
| `max_mem` | 最大内存 |
| `max_conn` | 最大连接数 |
| `db_name` | 数据库名 |
| `database_role` | 数据库角色（主/从） |
| `sid` | Oracle SID |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `service_name` | Oracle 服务名 |
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |

#### PostgreSQL（模型 `postgresql` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `config` | 配置文件 |
| `data_path` | 数据目录 |
| `max_connect` | 最大连接数 |
| `shared_buffer` | 共享缓冲区大小 |
| `log_directory` | 日志目录 |
| `conf` | 配置文件路径/内容 |
| `max_conn` | 最大连接数 |

#### Redis（模型 `redis` · 12 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `max_conn` | 最大连接数 |
| `max_mem` | 最大内存 |
| `database_role` | 数据库角色（主/从） |
| `topo_mode` | 拓扑模式（单机/集群） |
| `cluster_uuid` | 集群 UUID |
| `slaves` | 从节点列表 |
| `master` | 主节点地址 |

#### SQL Server（模型 `mssql` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `db_name` | 数据库名 |
| `max_conn` | 最大连接数 |
| `max_mem` | 最大内存 |
| `order_rule` | 排序规则 |
| `fill_factor` | 填充因子 |
| `boot_account` | 启动账户 |

#### TiDB（模型 `tidb` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `db_name` | 数据库名 |
| `install_path` | 安装路径 |
| `home_bash` | 用户家目录/启动环境 |
| `db_max_sessions` | 最大会话数 |
| `redo_log` | 重做日志配置 |
| `datafile` | 数据文件 |
| `mode` | 运行模式 |

### 中间件

#### ActiveMQ（模型 `activemq` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `conf_path` | 配置文件路径 |
| `java_path` | Java 路径 |
| `java_version` | Java 版本 |
| `xms` | JVM 初始堆内存（-Xms） |
| `xmx` | JVM 最大堆内存（-Xmx） |

#### Apache（模型 `apache` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `httpd_path` | Apache httpd 路径 |
| `httpd_conf_path` | Apache 配置路径 |
| `doc_root` | 站点根目录 |
| `error_log` | 错误日志路径 |
| `custom_Log` | 自定义日志 |
| `include` | 包含的子配置 |

#### Ceph（模型 `ceph` · 9 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `role` | 角色（如主/从、管理/工作） |
| `install_path` | 安装路径 |
| `config_file` | 配置文件 |
| `cmdline` | 启动命令行 |
| `ceph_exe` | Ceph 可执行文件 |

#### Consul（模型 `consul` · 8 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `install_path` | 安装路径 |
| `version` | 版本号 |
| `data_dir` | 数据目录 |
| `conf_path` | 配置文件路径 |
| `role` | 角色（如主/从、管理/工作） |

#### Etcd（模型 `etcd` · 8 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `data_dir` | 数据目录 |
| `conf_file_path` | 配置文件路径 |
| `peer_port` | 集群通信端口 |
| `install_path` | 安装路径 |

#### HAProxy（模型 `haproxy` · 13 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `conf_file` | 配置文件 |
| `defaults_maxconn` | 默认最大连接数 |
| `defaults_mode` | 默认工作模式 |
| `defaults_retries` | 默认重试次数 |
| `global_group_name` | 全局运行组 |
| `global_maxconn` | 全局最大连接数 |
| `global_pidfile` | PID 文件路径 |
| `global_user_name` | 全局运行用户 |

#### IIS（模型 `iis` · 14 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `webapp` | Web 应用 |
| `virdir` | 虚拟目录 |
| `configfile` | 配置文件 |
| `apppool` | 应用程序池 |
| `website` | 站点 |
| `apppool_count` | 应用程序池数量 |
| `webapp_count` | Web 应用数量 |
| `phys_path` | 物理路径 |
| `server_name` | 服务器名称 |
| `max_concur_connect` | 最大并发连接数 |

#### JBoss（模型 `jboss` · 9 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `jvm_xms` | JVM 初始堆内存 |
| `jvm_xmx` | JVM 最大堆内存 |
| `role` | 角色（如主/从、管理/工作） |
| `config_file` | 配置文件 |

#### Jetty（模型 `jetty` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `jetty_home` | Jetty 主目录 |
| `bin_path` | 可执行文件路径 |
| `monitored_dir` | 监控目录 |
| `java_path` | Java 路径 |
| `java_version` | Java 版本 |
| `conf_path` | 配置文件路径 |
| `java_vendor` | Java 厂商 |

#### Kafka（模型 `kafka` · 17 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `conf_path` | 配置文件路径 |
| `log_path` | 日志路径 |
| `java_path` | Java 路径 |
| `java_version` | Java 版本 |
| `xms` | JVM 初始堆内存（-Xms） |
| `xmx` | JVM 最大堆内存（-Xmx） |
| `broker_id` | Broker ID |
| `io_threads` | IO 线程数 |
| `network_threads` | 网络线程数 |
| `socket_receive_buffer_bytes` | Socket 接收缓冲区(字节) |
| `socket_request_max_bytes` | Socket 单请求最大字节 |
| `socket_send_buffer_bytes` | Socket 发送缓冲区(字节) |

#### Keepalived（模型 `keepalived` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `bk_obj_id` | 模型对象标识 |
| `version` | 版本号 |
| `priority` | 优先级 |
| `state` | 状态 |
| `virtual_router_id` | VRRP 虚拟路由 ID |
| `user_name` | 运行/登录用户名 |
| `install_path` | 安装路径 |
| `config_file` | 配置文件 |

#### Memcached（模型 `memcached` · 8 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `maxconn` | 最大连接数 |
| `cachesize` | 缓存大小 |
| `user_name` | 运行/登录用户名 |

#### Nginx（模型 `nginx` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `bin_path` | 可执行文件路径 |
| `version` | 版本号 |
| `log_path` | 日志路径 |
| `conf_path` | 配置文件路径 |
| `server_name` | 服务器名称 |
| `include` | 包含的子配置 |
| `ssl_version` | 支持的 SSL/TLS 版本 |
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |

#### OpenResty（模型 `openresty` · 8 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `openresty_path` | OpenResty 路径 |
| `log_path` | 日志路径 |
| `config_path` | 配置文件路径 |
| `doc_root` | 站点根目录 |

#### RabbitMQ（模型 `rabbitmq` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `allport` | 全部端口 |
| `node_name` | 节点名称 |
| `log_path` | 日志路径 |
| `conf_path` | 配置文件路径 |
| `version` | 版本号 |
| `enabled_plugin_file` | 已启用插件文件 |
| `erlang_version` | Erlang 版本 |

#### RocketMQ（模型 `rocketmq` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `configfile` | 配置文件 |
| `broker_id` | Broker ID |
| `broker_name` | Broker 名称 |
| `cluster_name` | 集群名称 |
| `namesrv_addr` | NameServer 地址 |
| `java_path` | Java 路径 |

#### Spark（模型 `spark` · 9 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `webui_port` | Web UI 端口 |
| `java_path` | Java 路径 |
| `java_version` | Java 版本 |
| `log_path` | 日志路径 |

#### Squid（模型 `squid` · 10 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `config_file_path` | 配置文件路径 |
| `cache_dir` | 缓存目录 |
| `access_log` | 访问日志路径 |
| `error_log` | 错误日志路径 |
| `visible_hostname` | 对外可见主机名 |

#### Tomcat（模型 `tomcat` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `catalina_path` | Tomcat CATALINA 路径 |
| `version` | 版本号 |
| `xms` | JVM 初始堆内存（-Xms） |
| `xmx` | JVM 最大堆内存（-Xmx） |
| `max_perm_size` | JVM 永久代最大大小 |
| `permsize` | JVM 永久代初始大小 |
| `log_path` | 日志路径 |
| `java_version` | Java 版本 |

#### TongWeb（模型 `tongweb` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `bin_path` | 可执行文件路径 |
| `log_path` | 日志路径 |
| `java_version` | Java 版本 |
| `xms` | JVM 初始堆内存（-Xms） |
| `xmx` | JVM 最大堆内存（-Xmx） |
| `metaspace_size` | 元空间初始大小 |
| `max_metaspace_size` | 元空间最大大小 |

#### Tuxedo（模型 `tuxedo` · 13 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `bin_path` | 可执行文件路径 |
| `conf_file` | 配置文件 |
| `domainid` | 域 ID |
| `ipckey` | Tuxedo IPC Key |
| `lmid` | Tuxedo 逻辑机器 ID |
| `patch_level` | 补丁级别 |
| `maxdispatchthreads` | 最大派发线程数 |
| `mindispatchthreads` | 最小派发线程数 |

#### WebLogic（模型 `weblogic` · 14 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `name` | 名称 |
| `console_context_path` | 控制台上下文路径 |
| `console_enabled` | 控制台是否启用 |
| `md_home` | 中间件主目录 |
| `root_dir` | 根目录 |
| `weblogic_home` | WebLogic 主目录 |
| `application_name` | 应用名称 |
| `admin_server_name` | 管理服务名 |
| `domain_version` | 域版本 |
| `java_version` | Java 版本 |

#### WebSphere（模型 `websphere` · 15 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `bin_path` | 可执行文件路径 |
| `java_path` | Java 路径 |
| `java_version` | Java 版本 |
| `server_name` | 服务器名称 |
| `cell` | WebSphere Cell |
| `node` | WebSphere Node/节点 |
| `initial_heap_size` | 初始堆大小 |
| `maximum_heap_size` | 最大堆大小 |
| `threadpool` | 线程池配置 |
| `jdbc` | JDBC 数据源 |
| `port_list` | 端口列表 |

#### ZooKeeper（模型 `zookeeper` · 14 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `ip_addr` | IP 地址 |
| `port` | 端口号 |
| `version` | 版本号 |
| `install_path` | 安装路径 |
| `log_path` | 日志路径 |
| `conf_path` | 配置文件路径 |
| `java_path` | Java 路径 |
| `java_version` | Java 版本 |
| `data_dir` | 数据目录 |
| `tick_time` | ZooKeeper tickTime |
| `init_limit` | ZooKeeper initLimit |
| `sync_limit` | ZooKeeper syncLimit |
| `server` | 服务器配置 |

### 云资源-阿里云

#### 阿里云 ECS 云服务器（模型 `aliyun_ecs` · 17 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `ip_addr` | IP 地址 |
| `public_ip` | 公网 IP |
| `region` | 地域 |
| `zone` | 可用区 |
| `vpc` | 所属 VPC |
| `status` | 运行状态 |
| `instance_type` | 实例类型/规格 |
| `os_name` | 操作系统名称 |
| `vcpus` | 虚拟 CPU 数 |
| `memory_mb` | 内存大小（MB） |
| `charge_type` | 计费方式 |
| `create_time` | 创建时间 |
| `expired_time` | 到期时间 |
| `assos` | 关联关系（自动建立的关联实例） |

#### 阿里云 Kafka 实例（模型 `aliyun_kafka_inst` · 17 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |
| `zone` | 可用区 |
| `vpc` | 所属 VPC |
| `status` | 运行状态 |
| `class` | 类别 |
| `storage_gb` | 存储容量（GB） |
| `storage_type` | 存储类型 |
| `msg_retain` | 消息保留策略 |
| `topoc_num` | 主题数 |
| `io_max_read` | 最大读 IOPS/带宽 |
| `io_max_write` | 最大写 IOPS/带宽 |
| `charge_type` | 计费方式 |
| `create_time` | 创建时间 |
| `assos` | 关联关系（自动建立的关联实例） |

#### 阿里云 MongoDB（模型 `aliyun_mongodb` · 17 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |
| `zone` | 可用区 |
| `zone_slave` | 从可用区 |
| `engine` | 引擎类型 |
| `version` | 版本号 |
| `type` | 类型 |
| `status` | 运行状态 |
| `class` | 类别 |
| `storage_type` | 存储类型 |
| `storage_gb` | 存储容量（GB） |
| `lock_mode` | 锁模式 |
| `charge_type` | 计费方式 |
| `expire_time` | 到期时间 |
| `assos` | 关联关系（自动建立的关联实例） |

#### 阿里云 OSS 存储桶（模型 `aliyun_bucket` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `location` | 地域/位置 |
| `extranet_endpoint` | 外网接入点 |
| `intranet_endpoint` | 内网接入点 |
| `storage_class` | 存储类别 |
| `cross_region_replication` | 跨地域复制 |
| `block_public_access` | 阻止公网访问 |
| `creation_date` | 创建日期 |
| `assos` | 关联关系（自动建立的关联实例） |

#### 阿里云 RDS MySQL（模型 `aliyun_mysql` · 21 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |
| `zone` | 可用区 |
| `zone_slave` | 从可用区 |
| `engine` | 引擎类型 |
| `version` | 版本号 |
| `type` | 类型 |
| `status` | 运行状态 |
| `class` | 类别 |
| `storage_type` | 存储类型 |
| `network_type` | 网络类型 |
| `net_type` | 网络类型 |
| `connection_mode` | 连接模式 |
| `lock_mode` | 锁模式 |
| `cpu` | CPU 规格/核数 |
| `memory_mb` | 内存大小（MB） |
| `charge_type` | 计费方式 |
| `expire_time` | 到期时间 |
| `assos` | 关联关系（自动建立的关联实例） |

#### 阿里云 RDS PostgreSQL（模型 `aliyun_pgsql` · 21 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |
| `zone` | 可用区 |
| `zone_slave` | 从可用区 |
| `engine` | 引擎类型 |
| `version` | 版本号 |
| `type` | 类型 |
| `status` | 运行状态 |
| `class` | 类别 |
| `storage_type` | 存储类型 |
| `network_type` | 网络类型 |
| `net_type` | 网络类型 |
| `connection_mode` | 连接模式 |
| `lock_mode` | 锁模式 |
| `cpu` | CPU 规格/核数 |
| `memory_mb` | 内存大小（MB） |
| `charge_type` | 计费方式 |
| `expire_time` | 到期时间 |
| `assos` | 关联关系（自动建立的关联实例） |

#### 阿里云 Redis（模型 `aliyun_redis` · 20 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |
| `zone` | 可用区 |
| `engine_version` | 引擎版本 |
| `architecture_type` | 架构类型 |
| `capacity` | 容量 |
| `network_type` | 网络类型 |
| `connection_domain` | 连接域名 |
| `port` | 端口号 |
| `bandwidth` | 带宽 |
| `qps` | 每秒查询数 |
| `shard_count` | 分片数 |
| `instance_class` | 实例规格 |
| `package_type` | 安装包类型 |
| `charge_type` | 计费方式 |
| `end_time` | 结束时间 |
| `create_time` | 创建时间 |
| `assos` | 关联关系（自动建立的关联实例） |

#### 阿里云负载均衡 CLB（模型 `aliyun_clb` · 13 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |
| `zone` | 可用区 |
| `zone_slave` | 从可用区 |
| `vpc` | 所属 VPC |
| `ip_addr` | IP 地址 |
| `status` | 运行状态 |
| `class` | 类别 |
| `charge_type` | 计费方式 |
| `create_time` | 创建时间 |
| `assos` | 关联关系（自动建立的关联实例） |

### 云资源-腾讯云

#### 腾讯云 CMQ 主题（模型 `qcloud_cmq_topic` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tag` | 标签 |
| `region` | 地域 |
| `status` | 运行状态 |
| `max_retention_s` | 最大保留时长(秒) |
| `max_message_b` | 最大消息字节数 |
| `filter_type` | 过滤类型 |
| `qps` | 每秒查询数 |

#### 腾讯云 COS 存储桶（模型 `qcloud_bucket` · 5 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |

#### 腾讯云 CVM 云服务器（模型 `qcloud_cvm` · 15 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `ip_addr` | IP 地址 |
| `public_ip` | 公网 IP |
| `region` | 地域 |
| `zone` | 可用区 |
| `vpc` | 所属 VPC |
| `status` | 运行状态 |
| `instance_type` | 实例类型/规格 |
| `os_name` | 操作系统名称 |
| `vcpus` | 虚拟 CPU 数 |
| `memory_mb` | 内存大小（MB） |
| `charge_type` | 计费方式 |

#### 腾讯云 MongoDB（模型 `qcloud_mongodb` · 23 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `ip_addr` | IP 地址 |
| `tag` | 标签 |
| `project_id` | 项目 ID |
| `vpc` | 所属 VPC |
| `region` | 地域 |
| `zone` | 可用区 |
| `port` | 端口号 |
| `status` | 运行状态 |
| `cluster_type` | 集群类型 |
| `machine_type` | 机型 |
| `version` | 版本号 |
| `cpu` | CPU 规格/核数 |
| `memory_mb` | 内存大小（MB） |
| `volume_mb` | 卷容量（MB） |
| `secondary_num` | 从节点数 |
| `mongos_cpu` | mongos CPU |
| `mongos_memory_mb` | mongos 内存(MB) |
| `mongos_node_num` | mongos 节点数 |
| `charge_type` | 计费方式 |

#### 腾讯云 MySQL（模型 `qcloud_mysql` · 11 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `ip_addr` | IP 地址 |
| `region` | 地域 |
| `zone` | 可用区 |
| `status` | 运行状态 |
| `volume` | 卷/容量 |
| `memory_mb` | 内存大小（MB） |
| `charge_type` | 计费方式 |

#### 腾讯云 PostgreSQL（模型 `qcloud_pgsql` · 19 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tag` | 标签 |
| `project_id` | 项目 ID |
| `vpc` | 所属 VPC |
| `region` | 地域 |
| `zone` | 可用区 |
| `status` | 运行状态 |
| `chartset` | 字符集 |
| `engine` | 引擎类型 |
| `mode` | 运行模式 |
| `version` | 版本号 |
| `kernel_version` | 内核版本 |
| `cpu` | CPU 规格/核数 |
| `memory_mb` | 内存大小（MB） |
| `volume_mb` | 卷容量（MB） |
| `charge_type` | 计费方式 |

#### 腾讯云 Pulsar 集群（模型 `qcloud_plusar_cluster` · 18 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tag` | 标签 |
| `project_id` | 项目 ID |
| `region` | 地域 |
| `status` | 运行状态 |
| `version` | 版本号 |
| `vpc_endpoint` | VPC 接入点 |
| `public_endpoint` | 公网接入点 |
| `max_namespace_num` | 最大命名空间数 |
| `max_topic_num` | 最大主题数 |
| `max_qps` | 最大 QPS |
| `max_retention_s` | 最大保留时长(秒) |
| `max_storage_mb` | 最大存储（MB） |
| `max_delay_s` | 最大延迟（秒） |
| `charge_type` | 计费方式 |

#### 腾讯云 Redis（模型 `qcloud_redis` · 22 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `ip_addr` | IP 地址 |
| `vpc` | 所属 VPC |
| `region` | 地域 |
| `zone` | 可用区 |
| `port` | 端口号 |
| `wan_address` | 公网地址 |
| `status` | 运行状态 |
| `sub_status` | 子状态/细分状态 |
| `engine` | 引擎类型 |
| `version` | 版本号 |
| `type` | 类型 |
| `memory_mb` | 内存大小（MB） |
| `shard_size` | 分片规格 |
| `shard_num` | 分片数 |
| `replicas_num` | 副本数 |
| `client_limit` | 客户端连接上限 |
| `net_limit` | 网络带宽上限 |
| `charge_type` | 计费方式 |

#### 腾讯云 RocketMQ（模型 `qcloud_rocketmq` · 14 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `region` | 地域 |
| `zone` | 可用区 |
| `status` | 运行状态 |
| `topic_num` | 主题数 |
| `used_topic_num` | 已用主题数 |
| `tpsper_name_space` | 单命名空间 TPS |
| `name_space_num` | 命名空间数 |
| `used_name_space_num` | 已用命名空间数 |
| `group_num` | 消费组数 |
| `used_group_num` | 已用消费组数 |

#### 腾讯云域名（模型 `qcloud_domain` · 7 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tld` | 顶级域名 |
| `status` | 运行状态 |
| `expired_time` | 到期时间 |

#### 腾讯云弹性公网 IP（模型 `qcloud_eip` · 13 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tag` | 标签 |
| `region` | 地域 |
| `status` | 运行状态 |
| `type` | 类型 |
| `ip_addr` | IP 地址 |
| `instance_type` | 实例类型/规格 |
| `instance_id` | 实例 ID |
| `isp` | 运营商 |
| `charge_type` | 计费方式 |

#### 腾讯云文件系统 CFS（模型 `qcloud_filesystem` · 12 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tag` | 标签 |
| `region` | 地域 |
| `zone` | 可用区 |
| `status` | 运行状态 |
| `protocol` | 协议类型 |
| `type` | 类型 |
| `net_limit` | 网络带宽上限 |
| `size_gib` | 容量（GiB） |

#### 腾讯云消息队列 CMQ（模型 `qcloud_cmq` · 12 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tag` | 标签 |
| `region` | 地域 |
| `status` | 运行状态 |
| `max_delay_s` | 最大延迟（秒） |
| `polling_wait_s` | 长轮询等待(秒) |
| `visibility_timeout_s` | 消息可见性超时(秒) |
| `max_message_b` | 最大消息字节数 |
| `qps` | 每秒查询数 |

#### 腾讯云负载均衡 CLB（模型 `qcloud_clb` · 17 字段）

| 字段标识 | 中文含义 |
|---|---|
| `inst_name` | 实例名称（CMDB 中的唯一展示名） |
| `assos` | 关联关系（自动建立的关联实例） |
| `resource_name` | 云资源名称 |
| `resource_id` | 云资源唯一 ID |
| `tag` | 标签 |
| `project_id` | 项目 ID |
| `security_group_id` | 安全组 ID |
| `vpc` | 所属 VPC |
| `region` | 地域 |
| `master_zone` | 主可用区 |
| `backup_zone` | 备份可用区 |
| `status` | 运行状态 |
| `domain` | 域名/域 |
| `ip_addr` | IP 地址 |
| `type` | 类型 |
| `isp` | 运营商 |
| `charge_type` | 计费方式 |
