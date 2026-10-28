# CMDB 扫描三阶段渐进发现

Status: ready

## Problem Statement

现有扫描把发现做成了专业采集打一枪：没有采集级凭据就扫不出对象，中间件要跑完整 `*_info` 才进清单，JOB 还和配置采集抢 Stargazer / Ansible 槽。管理员录入网段后，即使特征库已经知道 3306 是 MySQL、进程里能看到 `mysqld`，只要没填库账号，扫描结果里就不会出现这个对象。数据库和中间件的监控凭据又与配置采集不是一套，扫描侧假装自动推监控会填错采集。

## Solution

扫描改成三个渐进阶段，由 Stargazer 新增的扫描调度模块编排，不改现有配置采集插件，也不占用原采集任务队列。

一阶段按特征库端口指纹对网段做网络发现（与采集凭据无关）。二阶段在能 SSH / Agent 登录的主机上做进程指纹（每台主机只登录一次，匹配全部进程规则）。三阶段仅当任务里填了该对象的采集凭据时，才复用现有 `*_info` 采集逻辑把配置事实补全。任务勾选只为打开凭据池，不决定扫哪些类型；扫什么由特征库里的端口指纹和进程指纹决定。命中带回可信度，用户勾选后再写入 CMDB。数据库 / 中间件这类监控凭据不合的对象，写入 CMDB 后走现有 CMDB→监控同步任务，到监控页补采集，不在扫描里暗建 Telegraf。

## User Stories

1. As a CMDB 管理员, I want 不勾选数据库、不填 MySQL 账号也能在扫描清单里看到疑似 MySQL, so that 端口或进程已经说明这里有库，不必先准备采集凭据。
2. As a CMDB 管理员, I want 任务勾选只用来录入对应凭据, so that 我不勾中间件也能按特征库扫到 Nginx，勾了并填了 SSH 才做配置采集补全。
3. As a CMDB 管理员, I want 端口指纹和进程指纹的扫描范围由特征库决定, so that 我要扩一种对象只需在特征库加指纹，不必改扫描任务表单。
4. As a CMDB 管理员, I want 特征库预置当前配置采集能在网段主机上发现的对象的端口和进程指纹, so that 开箱就能扫 MySQL / Nginx 这类对象，而不只有三条 SQL 端口。
5. As a CMDB 管理员, I want 特征库新增进程指纹 Tab 并能自己追加规则, so that 非默认进程名也能教会扫描。
6. As a CMDB 管理员, I want 每条命中带可信度（端口低、进程中、采集登录高）, so that 我能判断哪些可以同步进 CMDB、哪些只是疑似。
7. As a CMDB 管理员, I want 扫描过程中命中回填到本次执行清单而不是等整任务同步, so that 我能边扫边看结果。
8. As a CMDB 管理员, I want 勾选疑似数据库写入 CMDB 后再生成「同步到监控」任务, so that 监控凭据在监控接入页补，扫描 SSH / 库账号不会被当成监控采集。
9. As a 平台管理员, I want 扫描调度不占用配置采集的 Stargazer 队列, so that 大网段扫描进行时，已有采集任务仍能按时跑。

## Implementation Decisions

### 三阶段与职责

- 一阶段（网络指纹）：对任务网段逐 IP，按特征库全部启用的端口指纹做 TCP 探测。不调用任何 `*_info`，不需要数据库 / 中间件 / SNMP 凭据。开放端口按 `(IP, 端口, target_type)` 落命中，可信度 `low`，证据 `port`。同一端口多类型各落一行。
- 二阶段（进程指纹）：仅当任务提供了主机登录通道（勾选主机或中间件，并具备 SSH 或 Agent 占位）时执行。对一阶段仍存活或网段内可登录的地址尝试登录；成功后在该主机上采集进程列表，用特征库全部进程指纹匹配。每台主机只登录一次，不得按类型重复 SSH。命中可信度 `medium`，证据 `process`；已有同身份端口命中则升级可信度，不另开一行。登录失败只计进度，不删一阶段命中。
- 三阶段（复用采集）：仅当任务勾选了该对象所属凭据族、且池内凭据满足对应采集插件时，才对该命中调用现有配置采集（`mysql_info`、`nginx_info` 等）。成功则补 snapshot（版本、路径等），可信度 `high`，证据 `collect`。失败不得删除一、二阶段命中。
- SNMP 网络设备仍要团体字 / v3 账号，不属于无凭据的一阶段。勾选网络并填 SNMP 后，仍走现有 SOID 识别；SOID Tab 职责不变。
- Windows WinRM 进程指纹本变更只把匹配字段写入特征库；二阶段执行器本期为 Linux SSH / Agent。

### 任务勾选与凭据

- `families` 的含义改为「本任务为这些族提供了采集凭据」，不再是「只扫这些类型」。
- 不勾任何族、凭据全空：仍跑一阶段；二、三阶段都不跑。
- 勾选主机（空池=Agent，填写=SSH）：打开二阶段登录通道。列进程与配置采集主机任务相同：已纳管节点优先 Agent `local.execute`，未纳管再走接入点 `ssh.execute`；三阶段可对主机跑 `host_info`。
- 勾选中间件且未勾主机：中间件 SSH / Agent 池同时作为二阶段登录通道（与现网主机/中间件共用 SSH 一致）。
- 勾选数据库 / InfluxDB / 网络：只打开对应协议凭据，供三阶段使用，不限制一、二阶段是否报告这些类型。
- 云区域：二阶段走 Agent 时仍必填，按 IP + 云区域匹配已纳管节点。

### 特征库

- 现有 Tab：网络设备 SOID、端口指纹。新增第三 Tab：进程指纹。权限对齐特征库新增/删除，不经 OpenAPI 网关对外暴露。
- 端口指纹不再设「扫描数据库白名单」。特征库里有的 TCP 指纹，一阶段都探；用户删除不了内置行，可停用（内置增加 `enabled`，默认开；用户行可删可停用）。停用的指纹本轮不探、不匹配。
- 进程指纹实体：`target_type`（CMDB 模型 ID）、`linux_process`（进程名或命令行正则）、`windows_image`（可选，映像名/服务名）、`built_in`、`enabled`。唯一约束 `(target_type, linux_process, windows_image)`。
- 端口与进程的 `target_type` 下拉使用配置采集对象树里「可网段主机发现」的模型，不出现云账号、K8s、vCenter、存储阵列管理 API。
- 内置同步幂等：已有用户行占用同一 `(port, target_type)` 或进程键时跳过，不覆盖。

### 内置端口指纹（可网段发现，不含 22/443 管理口）

社区配置采集对象先按下列监听口初始化；企业版对象树里同类数据库 / 中间件若有公认监听口，同一套同步逻辑一并写入，不把 HTTPS 管理口、SSH、IPMI、Redfish、云 API 写进端口指纹。

| target_type | 端口 |
|---|---|
| mysql | 3306 |
| postgresql | 5432 |
| mssql | 1433 |
| oracle | 1521 |
| influxdb | 8086 |
| redis | 6379 |
| mongodb | 27017 |
| es | 9200 |
| nginx | 80, 443 |
| apache | 80 |
| openresty | 80, 443 |
| tomcat | 8080 |
| kafka | 9092 |
| zookeeper | 2181 |
| rabbitmq | 5672, 15672 |
| consul | 8500 |
| etcd | 2379 |
| memcached | 11211 |
| minio | 9000 |
| haproxy | 80 |
| iis | 80 |
| activemq | 61616 |
| rocketmq | 9876 |
| squid | 3128 |
| nacos | 8848 |

同一端口多种类型合法（80→nginx/apache/iis/openresty/haproxy；5432→postgresql 及企业版同源库）。进程指纹负责消歧。

### 内置进程指纹

为上表对象初始化 Linux 进程规则（Windows 映像名能确定的一并写入，本期二阶段可不匹配）。规则用进程名 / 命令行正则，不写死在扫描器里。示例：`mysqld|mariadbd`→mysql，`postgres`→postgresql，`redis-server`→redis，`mongod`→mongodb，`nginx`→nginx，`org.apache.catalina`→tomcat，`kafka.Kafka`→kafka。Java 类中间件优先匹配命令行中的主类，避免所有 Java 进程都认成同一种。

### Stargazer 扫描调度

- 新增扫描调度模块，独立于现有 `collect_info` 配置采集入口。现有采集插件、凭据池、Telegraf 下发、Ansible 采集槽位行为不变。
- 扫描有自己的并发配额和优先级；配置采集满载时扫描降速，禁止反向抢占。一阶段 TCP 探测走该配额，不进 Ansible。二阶段登录可复用现有 SSH/Agent 执行能力，但必须走扫描配额，不得把整段 IP 一次打进原 JOB 队列。
- 三阶段需要跑 `*_info` 时，调度模块调用现有插件实现，仍受扫描配额约束，并按命中过滤目标，禁止对全网段再打 7 种中间件脚本。
- Server 触发改为把网段、指纹快照、可选凭据交给扫描调度，不再为每个模型各 `admit` 一枪全量 `collect_info`。指纹快照在触发时从特征库读取，本轮执行内不变；特征库改动只影响下次执行。
- 命中仍经现有扫描凭据/结果 subject 回填 `ScanHit`。一、二阶段没有采集凭据时也要回传，使用稳定的阶段结果事件（成功发现 / 不可达），不得要求 `credential_id` 非空才写清单。
- 现有 Server 侧 JOB 切批工作队列（8 IP、协议先打）不再作为中间件发现本体；扫描内调度改由 Stargazer 扫描模块负责。SNMP 成功地址仍可从二阶段登录目标中剔除。

### 清单、可信度与出口

- 命中增加 `confidence`（`low` / `medium` / `high`）和 `evidence`（`port` / `process` / `collect`，可多值）。身份键仍是 `(模型, IP, 端口)`；进程命中若解析到监听口则写入端口，解析不到则端口为空、同一主机同一模型一行。
- 清单边扫边回填，不把扫描结果同步成 `CollectModels`，不在任务级做一次总拷贝。
- 收口不因三阶段空结果或 VM 空指标删除低/中可信命中。
- 写入 CMDB：用户勾选后才写；低/中/高可信均可由用户确认写入。只信当时 snapshot。只扫出中间件/库时仍不因此新建主机；`run host` 仅当图上已有同 IP 主机。
- 生成配置采集：仅高可信、或用户勾选且任务里确有该模型采集凭据的行。无凭据的疑似行拒绝生成采集，提示去补凭据或只写入 CMDB。
- 推监控：网络 SNMP / 主机 SSH 且凭据与监控插件契合的，可继续走现有带凭据推送。数据库、中间件、以及扫描凭据与监控凭据不一致的行：必须先有 CI，再创建 CMDB→监控同步任务（`module_link`），到监控页选模板补凭据；扫描侧不调用 `push_with_credential`，不猜 stub_status / Exporter URL。

## Testing Decisions

只测外部行为：特征库种子与 Tab、任务勾选不限制一/二阶段类型、无库账号仍出疑似 MySQL、进程命中升级可信度、三阶段失败保留前序命中、扫描与采集队列隔离、数据库走同步任务而不是带凭据推监控。不测真实大网段墙钟、不测 Windows WinRM、不把扫描器内部 `ps` 解析当验收。

测试缝沿用现有扫描与特征库测试，并给 Stargazer 扫描调度加隔离缝：

- 端口 / 进程指纹：内置同步幂等、用户行不覆盖、停用后本轮不探；进程 Tab CRUD 权限对齐特征库。
- 扫描触发：不勾数据库仍按特征库探 3306；不勾中间件仍按特征库探 80 并在有主机登录时匹配 nginx 进程；勾选数据库才对命中调用 `mysql_info`。
- 凭据回传：无 `credential_id` 的端口/进程发现仍写 `ScanHit`；三阶段失败不删该行。
- 清单序列化：`confidence` / `evidence` 出现在命中详情。
- 写 CI：用户勾选的低可信 MySQL 可写入；未勾选不写。
- 生成采集：无库凭据的疑似行拒绝。
- 推监控：中间件 / 数据库行进入 `module_link` 任务路径（mock），不走 `CmdbToMonitorPushService.push_with_credential`。
- Stargazer：扫描调度与 `collect_info` 使用不同队列/配额；模拟采集槽已满时扫描仍能进入扫描队列、采集槽计数不增加。
- 前端：特征库三 Tab、任务勾选文案（勾选=凭据）、清单可信度列；类型检查覆盖，不强制 Playwright。

Prior art：`test_scan_trigger_service.py`、`test_scan_credential_event_nats.py`、`test_scan_finalize_service.py`、`test_scan_write_ci_service.py`、`test_scan_push_monitor.py`、`test_port_fingerprint.py`、特征库 `surfaceHierarchy.contract.test.ts`、`test_monitor_link_batch.py`。

## Out of Scope

- 改专业采集插件、`sync_collect_task`、Telegraf 常驻下发。
- 用端口指纹或进程指纹自动建监控采集 / 猜测监控 URL。
- 把云账号、K8s、vCenter、存储阵列管理 API 纳入网段指纹。
- 把 Agent 扫描改成只扫已纳管节点列表、不再填网段。
- Windows WinRM 二阶段执行器（特征库可先有 Windows 字段）。
- 取消扫描任务的族勾选改为纯凭据袋（勾选仍用于展开凭据表单）。
- 重写 SOID 网络设备发现。
- OpenAPI 暴露指纹或扫描新动作。

## Further Notes

- 本规格替代「扫描=对现有 collect_info 打一枪」作为发现本体，见 `cmdb-scan-discovery`。中间件不再以 7 个 JOB 脚本为发现手段，见 `cmdb-scan-middleware`。端口指纹不再仅服务 mysql/postgresql/mssql 三枪白名单，见 `cmdb-scan-port-fingerprint`。Server 侧 JOB 切批队列不再承担发现调度，见 `cmdb-scan-work-queue`。
- 清单驱动写 CI、不自动落库，仍遵守 `cmdb-scan-manual-ci-actions`。命中抽屉已匹配/未匹配顶层结构仍遵守 `cmdb-scan-hit-interaction`；本变更在已匹配表增加可信度，低可信疑似对象进已匹配（带标记），不再把「没采集成功」一律打进未匹配。
- 数据库 / 中间件进监控的产品路径是 `cmdb-monitor-link-task`，不是扫描带密创建。
- 产品记忆：`docs/design/product-decisions/cmdb-scan-progressive.md`。
- 实现计划：`specs/changes/cmdb-scan-progressive-discovery/plan.md`。
