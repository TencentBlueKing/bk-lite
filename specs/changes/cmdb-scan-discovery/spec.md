# CMDB 扫描纳管（与监控 / 采集联动）

Status: ready

## Problem Statement

运维要用网段和凭据发现还没有节点的设备、主机和库，再按需推进监控和周期采集。今天只有「专业采集」能填 IP 段，但它不适合当发现层：手动执行只更新不新增；凭据池最多 3 把；创建任务会下发 Telegraf 常驻配置并走周期 Beat。扫描若做成又一张采集任务，会和第二套观测抢并发，也会把发现和常驻巡检绑死。

## Solution

在 CMDB「管理 → 自动发现」下，于「采集」之前增加「扫描」。扫描任务可保存、不配周期、人手执行。Server 按勾选的凭据族各模拟一次 Telegraf，对现有 Stargazer `collect_info` 打一枪全量采集；结果仍进 VictoriaMetrics，凭据命中走现有 NATS 凭据事件（换扫描专用 subject）。Server 再按现有 mapping 写 CI，并做扫描侧身份后处理。清单每次都留。「推送到监控」和「生成采集任务」是两个出口，开关默认关。删扫描不连带已生成的采集和监控。

## User Stories

1. As a CMDB 管理员, I want 在自动发现里用扫描任务填多网段、按族勾选不限把数的凭据并手工执行, so that 发现不必先建采集任务、也不必配周期。
2. As a CMDB 管理员, I want 执行过程看到已回传目标 / 目标总数, so that 我知道这一枪还在跑还是已经收口。
3. As a CMDB 管理员, I want 扫描写入已识别的 CI（含新增）, so that 发现层能真正进 CMDB；未知 SOID 不建成交换机。
4. As a CMDB 管理员, I want 每次执行都有结果清单, so that 自动推不会变成黑盒。
5. As a CMDB 管理员, I want 从清单分开展开「推送到监控」和「生成采集任务」, so that 观测和巡检可以不同步打开。
6. As a CMDB 管理员, I want 生成的采集任务只带已命中的那一把凭据并默认开周期, so that 常驻采集不再试错、不再占用凭据池。
7. As a CMDB 管理员, I want 删除或停止扫描时已生成的采集和监控继续跑, so that 一次性发现不能绑架常驻观测。
8. As a 平台用户, I want 同一 IP 可以同时是主机和库（或多协议命中）, so that 扫描按门留行、按房子认领 CI。

## Implementation Decisions

### 不把扫描做成 CollectModels

扫描是独立任务 + 执行记录。不调用采集创建链路（否则会下发节点 Telegraf、注册 Beat、触发首次采集、套上 3 把凭据上限和「手动只更新」）。生成采集时再走现有采集创建服务，那时才允许出现 CollectModels。

### 执行：复用 collect_info，不改 Stargazer

勾选 N 个凭据族 → N 次 HTTP `GET /api/collect/collect_info`。请求头复用现有 NodeParams `cmdb*` 契约（含 `hosts` 展开、`credential_N_*` 扁平池）。接纳以 Stargazer 当前实现为准：HTTP 202、`X-Task-Status` 为 `accepted` / `duplicate_active`、`X-Target-Count`。不落节点采集配置。不建 identity profile、不建跨族调度。

Celery 只负责触发和短收口。`CELERY_WORKER_CONCURRENCY=2`，禁止一个 worker 干等整轮扫描。全量采集与周期采集共享 Stargazer `MAX_ACTIVE_RUNS=16` / `MAX_ACTIVE_TARGETS=150`；单目标仍受插件超时（约 60s）。

### 进度与收口：沿用现有两条回流，不发明第三套运行时

Stargazer 薄租约结束后删除 Redis，不能回读 completed。进度分母来自接纳时的 `X-Target-Count`。分子来自凭据结果 NATS：**每个目标主机首次收到任意凭据事件（含 failed / unreachable）即计入进度**；清单只落库 `success`，失败类不进命中清单（大网段 × 多凭据时量级过大）。收口条件：各家族回传数达到目标数，或到达该次执行的墙钟上限。收口后再按现有方式查 VictoriaMetrics、走 mapping、写 CI，并把主机 OS / 网络 SOID·品牌·型号等基础事实回填到命中 `snapshot`。

配置采集失败目标不再发布弱 `collection_status` 指标；扫描进度始终以 NATS 凭据结果事件为准（含失败仅计进度），不依赖 VM 失败行。若验收证明某类目标完全没有凭据结果事件，再单独修复结果事件协议，不恢复失败占位指标。

### 写 CI：复用 mapping + Management，扫描只做后处理

字段口径复用现有各插件 mapping。图写入复用 `Management.controller()`（允许新增）。不沿用采集 `input_method=MANUAL` 的只更新。网络未知 / 非网络 SOID：现有采集默认 `device_type=switch` 保持不动（那是采集债务）；扫描在写入前丢掉这条建 CI，清单仍保留 SNMP 命中行。不靠 SNMP 新建物理机。物理机认领键优先序列号 / UUID，否则 BMC IP；IPMI 与日后 Redfish 共用。主机仍按已锁的（云区域, IP）。库按（模型, IP, 端口）。CI 合并不等于采集 / 监控合并。

### 两个出口

- 推监控：扫描清单显式推送走 CMDB 模块 IoC 入口 `CmdbToMonitorPushService.push_with_credential` → `Monitor().ingest_from_source`（NATS `monitor_ingest_from_source`），禁止扫描侧直连 `MonitorModuleIngestService`。凭据只进 `raw.credential`，并由该入口置 `allow_credential_create=True`；公开资产页 `push_instance` 信封仍不带密钥。监控内部仍走接入页同一条 `create_monitor_instance_by_node_mgmt`。按插件**名**查询（Host Remote / Switch SNMP General / Router SNMP General / Firewall SNMP General / Loadbalance SNMP General / Hardware Server IPMI / Mysql / Postgres / MSSQL / InfluxDB），禁止写死数字 ID。命中凭据从扫描任务 `decrypt_credentials` 按 `credential_id` 取出。套模板失败则该行失败，禁止回退建没有采集配置的空壳。实例 ID 以监控接入页 identity adapter 为准（网络设备为 `build_safe_instance_id(cloud, ip)`），扫描侧不另编一套。成功后监控实例写入 `cmdb_id`（CMDB `inst_uuid`），并回写 CI `monitor_id`（监控实例主键）。未知 SOID / 图上找不到 CI 不推。
- 生成采集：一把已命中凭据 → 一张普通 CollectModels。网络 / 主机 / 物理机 / MySQL / PostgreSQL / MSSQL 对齐手建 IP 段任务（`instances=[]`，`ip_range` 用扫描任务上的起止段 `begin-end`，命中落在哪段就用哪段；`model_id` 为任务族如 `network`）。禁止把网络 CI 类型（`switch`）挂进 instances，否则旧 `format_params` 会用 `snmp+switch` 查插件失败。不要把命中 IP 写成逗号列表。**InfluxDB 例外**：采集 serializer 禁止 `ip_range`、要求恰好一个实例；每个命中端点一张任务，挂该 CI，`ip_range` 为空。主机生成必须把扫描任务的 `cloud_region` 写成采集 `params.cloud` / `params.cloud_name`（与 `CollectModelService.enrich_host_cloud_snapshot_payload` 字段名对齐）。`input_method=AUTO`（与手建网段任务一致，可新增可改）；默认开周期，间隔用该类现有默认值；凭据池不再试错。生成后必须把命中 CI 的图属性 `collect_task` 改成本 `CollectModels.id`（扫描落库时写的是 `ScanFamilyRun.id`）；不认领则自动模式会把已有 CI 当成新增，撞 `inst_name` 唯一约束。覆盖判断只用于「要不要再建采集任务」：已作为实例挂在某张**其他**采集任务上，或某张**其他**任务对该凭据已命中成功，则跳过。本扫描生成的任务已挂该实例或已命中成功时仍要认领，不得跳过。只是落在旧任务 `ip_range` 里从未采到，算未覆盖。IP 段族：本扫描已为这把凭据建过任务则复用，并把新命中所在的扫描段并进 `ip_range`。InfluxDB：本扫描已为这把凭据 + 该端点建过任务则复用，不把多个端点并进同一张任务。已生成但还是手动或旧逗号 IP 列表的任务，再次生成时改成自动并写成扫描起止段。

### 本章对象

网络 SNMP、主机 SSH、物理机 IPMI、MySQL、PostgreSQL、MSSQL（Beta）、InfluxDB（Beta）。Redfish 不进本章扫描族。中间件 JOB、云、K8s、IPAM 不进。凭据中心不前置。

## Testing Decisions

只测外部行为，不测 Stargazer 内部调度。优先服务层 / NATS handler / API，不启真实 Stargazer。

必测：

- 创建扫描不产生 CollectModels、不调用节点下发、不注册 Beat。
- 触发只打 HTTP collect_info；接纳 202 + `X-Target-Count`；Celery 任务在接纳后结束。
- 凭据事件进扫描清单，不写入 `CollectTaskCredentialHit`。
- 未知 SOID 有命中行、不建网络 CI、不可推监控；精确命中四类网络则 upsert。
- 同 IP 主机 + MySQL 两行 CI；host 与 physcial_server 不合并。
- 生成采集：一把钥匙一张任务、默认周期、自动录入；删扫描后任务仍在。InfluxDB 每个端点一张任务；主机任务带上扫描云区域。
- 开关默认关；显式推监控不把密钥放进公开信封。
- 并发执行同一扫描：旧执行不得覆盖新执行结果（执行令牌 / 状态机）。

Prior art：`test_first_collection_task.py`、`test_collect_credential_event_nats.py`、`test_push_to_monitor.py`、`test_module_ingest.py`、`test_collect_service_methods.py`。

## Out of Scope

- 改 Stargazer 调度、容量、identity profile；配置失败指标删除由
  `stargazer-stateless-async-collection/configuration-failure-delivery-and-logging-plan-2026-08-28.md`
  独立负责。
- 改采集「未知当 switch」、3 把上限、IP/实例互斥、手动只更新语义。
- 把扫描存成 CollectModels 或生成 Telegraf 常驻配置。
- Celery 干等整轮扫描。
- 扫描常驻周期、凭据中心、Redfish 扫描族、中间件 / 云 / K8s / IPAM。
- 删扫描级联停采集 / 监控。
- 打开带凭据创建后仍只适配 host。

## Further Notes

讨论稿见 grilling 画布；实现以本文和 `plan.md` 为准。入口不要占用 `featureLibrary/scanFeature`（那是空的特征库页）。权限本章复用 `auto_collection-*`，避免先改系统管理权限种子；菜单仍把扫描做成采集的兄妹项。
