# 日志系统 · 功能清单

> Migrated from `spec/fuctionlist/04-日志系统-功能清单.md` as legacy capability evidence.

**文档版本：** V1.0
**发布日期：** 2026-06-02
**适用范围：** BK-Lite 日志系统模块（`/log`）
**编制依据：** 日志系统 PRD v1.6（2026-05-28）与 `server/apps/log`、`web/src/app/log` 源代码核对

---

## 一、模块定位

日志系统是平台统一承载日志接入、检索、分析与告警处置的能力域，围绕"日志采集集成、日志检索与实时观察、内置日志分析、策略告警与事件追溯"四类场景，面向运维、研发与平台管理角色提供可配置、可追溯、可治理的日志闭环。日志检索基于统一搜索上下文（查询表达式 + 日志分组），策略按周期扫描产生告警并保留原始日志快照以支撑追溯。所有关键查询与管理操作受组织权限与实例权限约束。本清单仅列已实现能力。

## 二、功能清单

### 1. 日志搜索

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 条件检索 | 按日志分组、时间范围与查询表达式搜索，查看命中趋势直方图与日志明细列表 | 查询表达式与日志分组共同构成统一搜索上下文 | GA |
| 字段候选 | 查询字段名与字段值候选，用于构建检索表达式 | — | GA |
| 字段 Top 值分布 | 按字段查看 Top 值分布、命中数量与占比 | 基于当前搜索上下文计算；可从分布项直接追加查询条件 | GA |
| 结果回填 | 从搜索结果将字段和值追加回查询表达式 | — | GA |
| 展示字段与明细 | 选择结果展示字段并展开查看完整日志明细 | — | GA |
| 实时 tail | tail 实时日志流查询 | 实时查询与当前查询表达式、日志分组保持一致 | GA |
| 搜索条件保存 | 搜索条件的保存、加载、更新与删除 | 记录创建人；按当前组织隔离与复用，不随"包含子组织"设置扩展 | GA |

### 2. 日志分析

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 内置分析仪表盘 | 提供日志分析页面入口与内置分析仪表盘查看 | 覆盖数据库、中间件、网络、容器等典型采集源，按场景预置图表与表格 | GA |
| 查看控制 | 按日志分组、时间范围与刷新频率查看预置图表和表格 | 以内置仪表盘查看为主，不含用户自定义持久化配置 | GA |

### 3. 事件中心 - 策略管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 策略操作 | 策略的创建、编辑、删除、查询与启用、停用 | 策略名与采集方式联合唯一；停用后不再产生新扫描结果；删除为单事务原子操作（先清绑定的 `PeriodicTask` 再删策略），避免产生周期性漏扫的孤儿策略 | GA |
| 告警类型 | 策略告警类型 | `keyword` 关键字告警 / `aggregate` 聚合告警 | GA |
| 策略定义 | 含组织范围、日志分组、查询条件、执行频率、检测周期、告警等级与通知配置 | `schedule` 执行周期、`period` 数据周期 | GA |
| 关键字告警 | 关键字告警支持展示字段配置 | — | GA |
| 聚合告警 | 聚合告警支持聚合维度与多条件规则组合 | — | GA |
| 告警等级 | 告警级别取值 | `info` / `warning` / `error` / `critical` | GA |
| 数据补偿与延迟 | 任务执行时对历史周期补偿，并设日志查询安全延迟 | 单次最多补偿 10 个周期，最大补偿范围 24 小时；查询安全延迟默认 60 秒 | GA |
| 通知配置 | 读取通知渠道列表与可用用户信息进行通知配置 | 通知渠道来源于系统管理；通知对象录入方式随渠道类型变化 | GA |

### 4. 事件中心 - 告警与追溯

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 告警列表 | 活跃告警与历史告警的列表查询、分页展示与筛选 | 告警状态：`new` 活跃 / `closed` 关闭 | GA |
| 告警统计 | 提供告警统计用于态势观察 | — | GA |
| 告警详情 | 查看告警详情、最近原始日志 | — | GA |
| 事件时间线 | 查看事件时间线与单事件原始日志 | 告警须可追溯到关联事件与原始日志 | GA |
| 原始日志快照 | 告警生命周期内累积存储事件原始数据快照 | 快照存于对象存储（S3/MinIO），自动压缩 | GA |
| 告警关闭 | 人工关闭告警并记录关闭操作人 | 列表与详情可查看关闭操作人 | GA |

### 5. 集成管理 - 采集接入

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 采集类型浏览 | 采集类型按分类浏览并支持关键字搜索 | 分类：通用、Kubernetes、数据库、中间件、网络、容器、安全 | GA |
| 统计展示 | 采集类型可显示策略数与实例数统计 | — | GA |
| 接入配置/说明 | 进入接入配置页与接入说明页 | 通用接入支持批量录入实例参数，部分接入类型提供专用接入指引 | GA |
| Kubernetes 接入 | 支持云区域选择、安装命令生成与采集状态检查 | — | GA |
| 采集插件 | 内置采集插件 | Filebeat、Auditbeat、Packetbeat、Winlogbeat、Snmptrapd、Vector | GA |

### 6. 集成管理 - 实例与分组

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 日志接收实例 | 已接入实例列表查看、实例编辑、批量删除、配置更新、查看日志、组织范围绑定 | 实例创建、配置更新与删除需与节点侧配置保持一致 | GA |
| 采集配置 | 读取实例基础配置与子配置，并更新采集配置用于后续日志接入与采集 | — | GA |
| 日志分组管理 | 日志分组的创建、查询、更新、删除 | 规则支持 AND 与 OR 组合 | GA |
| 默认日志分组 | 系统提供默认日志分组用于全量日志场景 | 选择默认分组时按全量日志口径查询；默认分组与其他分组同时选择时以默认分组优先，其他分组条件不参与查询拼装 | GA |
| 节点信息查询 | 在接入场景查询节点信息，辅助实例接入与专用接入指引展示 | — | GA |

## 三、能力边界与约束

本模块不覆盖非日志数据域（指标、链路、资产等）的统一分析与治理，不提供第三方日志平台的深度双向编排能力。日志分析页仅提供内置仪表盘查看，不承诺用户自定义仪表盘的保存与编排。策略编排能力以关键字告警与聚合告警两类为限，不承诺通用规则引擎。告警处置状态以活跃（`new`）与关闭（`closed`）为主，关闭通过人工操作完成并记录操作人。搜索条件按当前组织隔离，不随"包含子组织"设置扩展。日志查询设安全延迟（默认 60 秒），数据补偿单次上限 10 个周期、最大 24 小时。日志模块进入后默认跳转到首个可用菜单项。所有关键查询与管理操作受组织权限与实例权限约束，非授权范围内数据不可见、不可改。

## 四、平台协同

日志系统从节点管理获取节点信息并保持采集实例与节点侧配置一致；通知渠道与可用用户信息来源于系统管理统一配置；组织隔离与权限控制依赖系统管理 RBAC；日志策略产生的告警可作为标准化事件源向告警中心 `/alarm` 输送（告警源类型含"日志"），由告警中心完成跨源聚合与处置协同；原始日志快照存于对象存储（S3/MinIO）。

## 五、支持的采集类型与采集器范围

平台随包预置 **18 种**内置采集类型，按 `display_category` 归入 **7 大分类**，由 **6 种**采集器（`collector`）承载，开箱即用、无需手动定义。下表按分类列出采集类型，括号内为该采集类型预置的解析字段数（基于内置 `support-files/plugins/*/collect_type.json` 的 `attrs` 统计），合计预置约 **328 个**解析字段。

### 5.1 内置采集类型（按分类）

| 分类（display_category） | 采集类型（预置字段数） | 采集器 |
|---|---|---|
| 通用（general，3 种） | file 文件（9）、syslog（16）、snmp_trap（8） | Vector / Vector / Snmptrapd |
| Kubernetes（k8s，1 种） | kubernetes（10） | Vector |
| 数据库（database，5 种） | mysql（17）、postgresql（18）、redis（15）、mongodb（11）、elasticsearch（24） | Filebeat |
| 中间件（middleware，4 种） | apache（22）、nginx（22）、kafka（14）、rabbitmq（10） | Filebeat |
| 网络（network，2 种） | flows 网络流（13）、http（9） | Packetbeat |
| 容器（container，1 种） | docker（13） | Vector |
| 安全（security，2 种） | file_integrity 文件完整性（59）、winlogbeat Windows 事件日志（38） | Auditbeat / Winlogbeat |

### 5.2 采集器支持矩阵

| 采集器（collector） | 承载采集类型数 | 适用对象 |
|---|---|---|
| Vector | 4 | file、syslog、kubernetes、docker |
| Filebeat | 9 | mysql、postgresql、redis、mongodb、elasticsearch、apache、nginx、kafka、rabbitmq |
| Packetbeat | 2 | flows、http |
| Auditbeat | 1 | file_integrity |
| Winlogbeat | 1 | winlogbeat |
| Snmptrapd | 1 | snmp_trap |

> 说明：18 种采集类型与 7 大分类口径与 PRD 一致；分类排序按代码 `DISPLAY_CATEGORY_ORDER`（general → k8s → database → middleware → network → container → security）。括号内字段数为各采集类型 `collect_type.json` 中 `attrs` 预置字段条目数，反映该类型默认抽取/规范化的日志字段，实际入库字段可随解析规则扩展。源码中内置采集类型与采集器均未标注 Beta，全部为 GA；除内置类型外，日志支持基于 Vector / Filebeat 等采集器自定义采集配置扩展自定义日志源。


## 六、采集类型字段明细（逐项）

> 本节逐项列出各日志采集类型的预置字段，源自各采集类型 `collect_type.json` 的 `attrs` 定义。共 18 种采集类型、328 个字段。

### 容器

#### docker（采集器 Vector · 13 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `container_created_at` | 容器创建时间 |
| `container_id` | 容器ID |
| `container_name` | 容器名称 |
| `host` | 采集主机标识 |
| `image` | 容器镜像名称 |
| `label` | 容器标签信息 |
| `message` | 原始日志消息内容 |
| `source_type` | 数据来源类型 |
| `stream` | 输出流类型(stdout/stderr) |
| `timestamp` | 日志时间戳 |

### 数据库

#### elasticsearch（采集器 Filebeat · 24 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `elasticsearch.server.message` | 服务端日志消息 |
| `elasticsearch.server.level` | 服务端日志级别 |
| `elasticsearch.server.component` | 产生日志的组件名 |
| `elasticsearch.server.node.name` | ES节点名称 |
| `elasticsearch.server.cluster.name` | ES集群名称 |
| `elasticsearch.audit.event_type` | 审计事件类型 |
| `elasticsearch.audit.origin.type` | 审计请求来源类型 |
| `elasticsearch.audit.user.name` | 审计操作用户名 |
| `elasticsearch.audit.request.name` | 审计请求操作名称 |
| `elasticsearch.slowlog.type` | 慢日志类型(查询/取回) |
| `elasticsearch.slowlog.source` | 慢查询请求体内容 |
| `elasticsearch.slowlog.took` | 慢查询执行耗时 |
| `elasticsearch.slowlog.index` | 慢查询涉及的索引名 |
| `elasticsearch.deprecation.message` | 弃用功能告警信息 |
| `elasticsearch.deprecation.level` | 弃用日志级别 |
| `elasticsearch.gc.heap.size_kb` | GC后堆内存大小(KB) |
| `elasticsearch.gc.young.pause_time.ms` | 年轻代GC停顿时长(ms) |
| `elasticsearch.gc.old.pause_time.ms` | 老年代GC停顿时长(ms) |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

#### mongodb（采集器 Filebeat · 11 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `mongodb.log.message` | MongoDB日志消息内容 |
| `mongodb.log.severity` | MongoDB日志严重级别 |
| `mongodb.log.component` | 产生日志的MongoDB组件 |
| `mongodb.log.context` | 日志上下文(连接/线程) |
| `mongodb.log.id` | MongoDB日志条目ID |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

#### mysql（采集器 Filebeat · 17 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `mysql.error.message` | MySQL错误日志信息 |
| `mysql.error.level` | MySQL错误日志级别 |
| `mysql.error.thread_id` | 出错的MySQL线程ID |
| `mysql.slowlog.query` | 执行的慢查询SQL语句 |
| `mysql.slowlog.query_time.sec` | 慢查询执行耗时(秒) |
| `mysql.slowlog.lock_time.sec` | 慢查询锁等待时长(秒) |
| `mysql.slowlog.rows_sent` | 慢查询返回行数 |
| `mysql.slowlog.rows_examined` | 慢查询扫描行数 |
| `mysql.slowlog.user` | 执行慢查询的用户 |
| `mysql.slowlog.host` | 执行慢查询的来源主机 |
| `mysql.slowlog.id` | 慢查询连接ID |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

#### postgresql（采集器 Filebeat · 18 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `postgresql.log.message` | PostgreSQL日志消息 |
| `postgresql.log.level` | PostgreSQL日志级别 |
| `postgresql.log.database` | 操作所在数据库名 |
| `postgresql.log.user` | 执行操作的用户名 |
| `postgresql.log.query` | 执行的SQL语句 |
| `postgresql.log.duration` | SQL执行耗时 |
| `postgresql.log.client_addr` | 客户端连接IP地址 |
| `postgresql.log.session_id` | 数据库会话ID |
| `postgresql.log.session_line_num` | 会话内日志行号 |
| `postgresql.log.command_tag` | 执行的命令类型标签 |
| `postgresql.log.virtual_transaction_id` | 虚拟事务ID |
| `postgresql.log.transaction_id` | 事务ID |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

#### redis（采集器 Filebeat · 15 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `redis.log.message` | Redis日志消息内容 |
| `redis.log.level` | Redis日志级别 |
| `redis.log.pid` | Redis进程PID |
| `redis.log.role` | Redis实例角色(主/从) |
| `redis.slowlog.cmd` | 慢日志执行的命令 |
| `redis.slowlog.duration.us` | 慢命令执行耗时(微秒) |
| `redis.slowlog.id` | 慢日志条目ID |
| `redis.slowlog.key` | 慢命令操作的键名 |
| `redis.slowlog.args` | 慢命令的参数列表 |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

### 通用

#### file（采集器 Vector · 9 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `file` | 日志文件路径 |
| `host` | 采集主机标识 |
| `message` | 原始日志消息内容 |
| `source_type` | 数据来源类型 |
| `timestamp` | 日志时间戳 |
| `instance_id` | 采集实例ID |

#### snmp_trap（采集器 Snmptrapd · 8 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `event_type` | 事件类型标识 |
| `node_ip` | 发送Trap的设备IP |
| `timestamp` | 日志时间戳 |
| `received_at` | Trap接收时间 |
| `trap_message` | SNMP Trap消息内容 |
| `raw_message` | 原始Trap报文 |

#### syslog（采集器 Vector · 16 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `appname` | 产生日志的应用名 |
| `client_metadata` | 客户端连接元数据 |
| `facility` | Syslog设施类别 |
| `host` | 采集主机标识 |
| `hostname` | 来源主机名 |
| `message` | 原始日志消息内容 |
| `msgid` | Syslog消息ID |
| `procid` | 进程ID |
| `severity` | Syslog严重级别 |
| `source_ip` | 来源IP地址 |
| `source_type` | 数据来源类型 |
| `timestamp` | 日志时间戳 |
| `version` | Syslog协议版本 |

### Kubernetes

#### kubernetes（采集器 Vector · 10 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `k8s_namespace` | Kubernetes命名空间 |
| `k8s_pod_name` | Pod名称 |
| `k8s_container_name` | 容器名称 |
| `k8s_node_name` | 所在节点名称 |
| `message` | 原始日志消息内容 |
| `log_message` | 解析后的日志正文 |
| `timestamp` | 日志时间戳 |

### 中间件

#### apache（采集器 Filebeat · 22 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `apache.access.remote_ip` | 客户端来源IP地址 |
| `apache.access.user_name` | 认证访问用户名 |
| `apache.access.method` | HTTP请求方法 |
| `apache.access.url` | 请求的URL路径 |
| `apache.access.http_version` | HTTP协议版本 |
| `apache.access.response_code` | HTTP响应状态码 |
| `apache.access.body_sent.bytes` | 响应体发送字节数 |
| `apache.access.referrer` | 请求来源页面地址 |
| `apache.access.agent` | 客户端User-Agent信息 |
| `apache.access.geoip.country_name` | 来源IP所属国家 |
| `apache.access.geoip.city_name` | 来源IP所属城市 |
| `apache.error.level` | 错误日志级别 |
| `apache.error.message` | 错误日志详细信息 |
| `apache.error.pid` | 工作进程PID |
| `apache.error.tid` | 工作线程ID |
| `apache.error.client` | 触发错误的客户端地址 |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

#### kafka（采集器 Filebeat · 14 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `kafka.log.timestamp` | Kafka日志时间戳 |
| `kafka.log.level` | Kafka日志级别 |
| `kafka.log.component` | 产生日志的Kafka组件 |
| `kafka.log.class` | 记录日志的Java类名 |
| `kafka.log.message` | Kafka日志消息内容 |
| `kafka.log.trace.class` | 异常堆栈所属类名 |
| `kafka.log.trace.message` | 异常堆栈消息 |
| `kafka.log.trace.full` | 完整异常堆栈信息 |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

#### nginx（采集器 Filebeat · 22 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `nginx.access.remote_ip` | 客户端来源IP地址 |
| `nginx.access.user_name` | 认证访问用户名 |
| `nginx.access.method` | HTTP请求方法 |
| `nginx.access.url` | 请求的URL路径 |
| `nginx.access.http_version` | HTTP协议版本 |
| `nginx.access.response_code` | HTTP响应状态码 |
| `nginx.access.body_sent.bytes` | 响应体发送字节数 |
| `nginx.access.referrer` | 请求来源页面地址 |
| `nginx.access.agent` | 客户端User-Agent信息 |
| `nginx.access.geoip.country_name` | 来源IP所属国家 |
| `nginx.access.geoip.city_name` | 来源IP所属城市 |
| `nginx.error.level` | 错误日志级别 |
| `nginx.error.message` | 错误日志详细信息 |
| `nginx.error.pid` | 工作进程PID |
| `nginx.error.tid` | 工作线程ID |
| `nginx.error.connection_id` | 客户端连接ID |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

#### rabbitmq（采集器 Filebeat · 10 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `rabbitmq.log.timestamp` | RabbitMQ日志时间戳 |
| `rabbitmq.log.level` | RabbitMQ日志级别 |
| `rabbitmq.log.pid` | Erlang进程标识 |
| `rabbitmq.log.message` | RabbitMQ日志消息内容 |
| `event.dataset` | 事件数据集名称 |
| `event.module` | 事件所属采集模块 |
| `fileset.name` | 日志文件集名称 |

### 网络

#### flows（采集器 Packetbeat · 13 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `flow.final` | 流是否已结束标识 |
| `flow.id` | 网络流唯一标识 |
| `flow.vlan` | 网络流VLAN编号 |
| `flow_id` | 网络流ID(兼容字段) |
| `final` | 流结束标识(兼容字段) |
| `vlan` | VLAN编号(兼容字段) |
| `source.stats.net_bytes_total` | 源端发送总字节数 |
| `source.stats.net_packets_total` | 源端发送总包数 |
| `dest.stats.net_bytes_total` | 目的端接收总字节数 |
| `dest.stats.net_packets_total` | 目的端接收总包数 |

#### http（采集器 Packetbeat · 9 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `http.request.headers` | HTTP请求头信息 |
| `http.request.params` | HTTP请求参数 |
| `http.response.status_phrase` | HTTP响应状态短语 |
| `http.response.headers` | HTTP响应头信息 |
| `http.response.code` | HTTP响应状态码 |
| `http.response.phrase` | HTTP响应状态描述 |

### 安全

#### file_integrity（采集器 Auditbeat · 59 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `file.elf.go_imports` | ELF文件Go语言导入符号 |
| `file.elf.go_imports_names_entropy` | ELF的Go导入名熵值 |
| `file.elf.go_imports_names_var_entropy` | ELF的Go导入名方差熵 |
| `file.elf.import_hash` | ELF文件导入哈希指纹 |
| `file.elf.go_stripped` | ELF是否剥离Go符号信息 |
| `file.elf.imports_names_entropy` | ELF导入函数名熵值 |
| `file.elf.imports_names_var_entropy` | ELF导入名方差熵 |
| `file.elf.import_hash` | ELF文件导入哈希指纹 |
| `file.elf.sections.var_entropy` | ELF节区数据方差熵 |
| `file.macho.go_imports` | Mach-O文件Go导入符号 |
| `file.macho.go_imports_names_entropy` | Mach-O的Go导入名熵值 |
| `file.macho.go_imports_names_var_entropy` | Mach-O的Go导入名方差熵 |
| `file.macho.go_import_hash` | Mach-O的Go导入哈希 |
| `file.macho.go_stripped` | Mach-O是否剥离Go符号 |
| `file.macho.imports` | Mach-O文件导入符号列表 |
| `file.macho.imports_names_entropy` | Mach-O导入名熵值 |
| `file.macho.imports_names_var_entropy` | Mach-O导入名方差熵 |
| `file.macho.import_hash` | Mach-O导入哈希指纹 |
| `file.macho.sections` | Mach-O节区列表 |
| `file.macho.sections.entropy` | Mach-O节区数据熵值 |
| `file.macho.sections.var_entropy` | Mach-O节区方差熵 |
| `file.macho.sections.name` | Mach-O节区名称 |
| `file.macho.sections.physical_size` | Mach-O节区文件大小 |
| `file.macho.sections.virtual_size` | Mach-O节区内存大小 |
| `file.macho.symhash` | Mach-O符号表哈希 |
| `file.pe.go_imports` | PE文件Go导入符号 |
| `file.pe.go_imports_names_entropy` | PE的Go导入名熵值 |
| `file.pe.go_imports_names_var_entropy` | PE的Go导入名方差熵 |
| `file.pe.go_import_hash` | PE的Go导入哈希 |
| `file.pe.go_stripped` | PE是否剥离Go符号 |
| `file.pe.imports` | PE文件导入符号列表 |
| `file.pe.imports_names_entropy` | PE导入名熵值 |
| `file.pe.imports_names_var_entropy` | PE导入名方差熵 |
| `file.pe.import_hash` | PE导入哈希指纹 |
| `file.pe.sections` | PE节区列表 |
| `file.pe.sections.entropy` | PE节区数据熵值 |
| `file.pe.sections.var_entropy` | PE节区方差熵 |
| `file.pe.sections.name` | PE节区名称 |
| `file.pe.sections.physical_size` | PE节区文件大小 |
| `file.pe.sections.virtual_size` | PE节区内存大小 |
| `hash.blake2b_256` | 文件BLAKE2b-256哈希值 |
| `hash.blake2b_384` | 文件BLAKE2b-384哈希值 |
| `hash.blake2b_512` | 文件BLAKE2b-512哈希值 |
| `hash.md5` | 文件MD5哈希值 |
| `hash.sha1` | 文件SHA1哈希值 |
| `hash.sha224` | 文件SHA224哈希值 |
| `hash.sha256` | 文件SHA256哈希值 |
| `hash.sha384` | 文件SHA384哈希值 |
| `hash.sha3_224` | 文件SHA3-224哈希值 |
| `hash.sha3_256` | 文件SHA3-256哈希值 |
| `hash.sha3_384` | 文件SHA3-384哈希值 |
| `hash.sha3_512` | 文件SHA3-512哈希值 |
| `hash.sha512` | 文件SHA512哈希值 |
| `hash.sha512_224` | 文件SHA512-224哈希值 |
| `hash.sha512_256` | 文件SHA512-256哈希值 |
| `hash.xxh64` | 文件xxHash64快速校验值 |

#### winlogbeat（采集器 Winlogbeat · 38 字段）

| 字段 | 中文含义 |
|---|---|
| `collect_type` | 采集类型标识 |
| `collector` | 采集器名称 |
| `instance_id` | 采集实例ID |
| `channel` | Windows事件日志通道 |
| `event_id` | Windows事件ID |
| `provider_name` | 事件提供程序名称 |
| `computer_name` | 计算机名 |
| `record_id` | 事件记录序号 |
| `user_name` | 关联用户名 |
| `user_domain` | 用户所属域 |
| `user_type` | 用户账户类型 |
| `winlog.api` | 事件采集API类型 |
| `winlog.channel` | Windows事件通道 |
| `winlog.computer_name` | 记录事件的计算机名 |
| `winlog.event_id` | Windows事件ID |
| `winlog.keywords` | 事件关键字分类 |
| `winlog.opcode` | 事件操作码 |
| `winlog.provider_guid` | 事件提供程序GUID |
| `winlog.provider_name` | 事件提供程序名称 |
| `winlog.record_id` | 事件记录序号 |
| `winlog.task` | 事件任务类别 |
| `winlog.version` | 事件架构版本 |
| `winlog.event_data` | 事件自定义数据 |
| `winlog.user.name` | 关联账户名 |
| `winlog.user.domain` | 账户所属域 |
| `winlog.user.identifier` | 账户安全标识符SID |
| `winlog.user.type` | 账户类型 |
| `winlog.process.pid` | 产生事件的进程PID |
| `winlog.process.thread.id` | 产生事件的线程ID |
| `log.level` | 日志级别 |
| `message` | 原始日志消息内容 |
| `host.name` | 主机名 |
| `host.ip` | 主机IP地址 |
| `geoip.continent_name` | IP所属大洲 |
| `geoip.country_iso_code` | IP所属国家代码 |
| `geoip.city_name` | IP所属城市 |
| `geoip.region_name` | IP所属地区 |
| `geoip.location` | IP经纬度位置 |
