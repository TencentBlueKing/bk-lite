# 模块 ARD：分布式 Agents

> Migrated from `spec/ARD/modules/agents.md` as legacy capability evidence.

> 路径 `agents/*`

## stargazer —— 协议采集 agent【已实现/已存在】
- 运行时与职责【已实现/已存在】：Python + Sanic（`server.py`，:8083）在自身生命周期内装配统一配置采集运行时；该运行时以 Redis 保存运行及凭据状态，以 NATS 发布采集结果，并统一受理配置采集请求。原先文档所述独立 ARQ Worker、`core/worker.py`、`core/task_queue.py` 与 `start_worker.py` 已不在当前实现中，不能再作为运行架构或任务链路的一部分。
- 通信：NATS pub/sub（`core/nats.py:NATSSanic`，`service/nats_server.py`）。
- 注册处理函数（经 `@register_handler()`，主题由其派生）：`list_regions`、`test_connection`、`health_check`、`debug_snmp`、`debug_ipmi`、`handle_host_remote_callback`（证据：`agents/stargazer/service/nats_server.py:46-97`）。
- IP 发现扫描相关 Python 文件位于 `plugins/inputs/ip/`（`__init__.py`、`ip_discovery_scanner.py`、`scan_targets.py`、`plugin.yml`），是否经 NATS `ip_scan` handler 对外暴露【待确认】。
- HTTP REST 接口面【已实现/已存在】：除 NATS 外，通过 Sanic Blueprint 暴露 HTTP 路由，统一挂载到 `/api` 前缀（`api/__init__.py:22`）。各蓝图：
  - health（`/health`）：`/`、`/ready`、`/stats`、`/metrics`（证据：`agents/stargazer/api/health.py:13,16,33,75,107`）。
  - collect（`/collect`）：`/credential_results`、`/collect_info`（证据：`agents/stargazer/api/collect.py:21,253,300`）。
  - monitor（`/monitor`）：`/vmware/metrics`、`/qcloud/metrics`、`/oceanstor/metrics`、`/windows/wmi/metrics`、`/host/metrics`（证据：`agents/stargazer/api/monitor.py:9,26,153,276,353,423`）。
- enterprise 扩展机制【已实现/已存在】：`api/__init__.py` 在导入时尝试 `from enterprise.api import ENTERPRISE_BLUEPRINTS`，存在则分组挂载到 `/api/enterprise` 前缀；`server.py` 同时导入 `api` 与 `enterprise_api` 两组蓝图（证据：`agents/stargazer/api/__init__.py:12,15-17,24-25`；`agents/stargazer/server.py:2`）。
- 统一调度与容量边界【已实现/已存在】：应用运行时按 `MAX_ACTIVE_RUNS`、`MAX_ACTIVE_RUN_TARGETS`、`MAX_ACTIVE_TARGETS`、`TARGET_TASK_WINDOW` 构造全局容量边界；`MAX_ACTIVE_RUN_TARGETS` 限制全部已接纳 Run 的目标总数，避免仅按 Run 数接纳多个超大任务；跨 `CollectionRun` 的目标由 round-robin 调度器在同一 in-flight 窗口内公平派发，新 Run 优先获得下一空闲槽位，避免大 Run 长时间占用。运行统计暴露活动 Run/目标、准入目标预算、排队目标与峰值，作为容量观测契约。
- 结果发布背压【已实现/已存在】：采集执行器将每个目标结果交给有界 `BufferedResultPublisher`；队列容量随目标任务窗口/目标上限确定，队列接纳与最终投递确认分离。发布阶段在统一截止时间内有限重试，投递状态区分 succeeded、failed 与 unknown，运行关闭时按宽限期排空或终止。这一队列是 NATS 结果发布链路的本地有界背压点。
- 执行计划与阶段超时【已实现/已存在】：每次采集从环境变量与插件 YAML 解析为不可变 `ExecutionPlan`，统一约束预检、可达性/访问探测、插件采集和结果发布四个阶段的超时，并标记 `sync`、`async`、`remote` 执行模式及 `snmp`、`sync_sdk`、`remote_job`、`default` 容量组。YAML 缺失时回退默认计划；插件具体配置到真实连接的全链路重校验【待确认】。
- 预检与出站安全【已实现/已存在】：目标在协议采集前由异步预检处理，预检结果区分通过、不可达及超时等状态；预检路径会在连接前校验出站地址或受信云端点声明。部署策略与插件真实连接是否逐项复用该校验【待确认】。
- 指标与健康【已实现/已存在】：Sanic 生命周期启动/停止统一运行时及事件循环滞后观测；`/health/ready` 以运行时和 Redis 状态决定就绪性，`/health/stats` 返回容量、发布队列、线程、文件描述符及运行指标，`/health/metrics` 以 Prometheus 文本输出阶段耗时、超时、调度等待、发布和执行模式/容量组指标。
- 原生异步与线程隔离矩阵【已实现/已存在】：插件矩阵将网络 I/O 明确分为原生异步（直接 `await`）、同步隔离（同步 SDK 在线程中执行）和远程异步（通过 NATS 等待独立执行端）；当前 protocol executor 统计为 15 个原生异步、6 个同步隔离，同步隔离仍受全局目标容量边界约束。矩阵中的插件适用范围及其与生产真实连接的逐项全链路一致性【待确认】。
- 能力：协议采集（SNMP/IPMI/SSH/HTTP/WMI 等）、凭据状态管理、YAML 驱动采集（`service/collection_service.py`）、远程命令运行时。
- 配置采集插件矩阵【已实现/已存在】：`plugins/inputs/` 下 `*_info.py` 以当前仓库枚举为准（约 30 个，含 highgo/iris/nacos/oceanbase/sap_hana 等新增采集对象）。另有 `keepalived`、`minio` 以非 `*_info.py` 形态存在；IP 发现位于 `plugins/inputs/ip/`。历史“19 个 *_info.py、仅 x86 采集器”口径作废。
- 多租户与安全收敛【已实现/已存在】：配置采集查询节点信息时优先携带 `organization_id` 缩小查询范围，未提供组织上下文时才回退 `skip_permission=True`；HTTP 监控接口对凭证/实例标识做 Prometheus label 转义与日志脱敏，避免泄露原始凭据（`service/collection_service.py:347-363`、`api/collect.py:355-521`、`api/monitor.py:12-17,247,270,429`）。

> 证据来源：agents/stargazer/core/collection/scheduler.py:30-142；agents/stargazer/core/collection/application.py:48-147；agents/stargazer/core/collection/execution_plan.py:29；agents/stargazer/core/collection/executor.py:465,808；agents/stargazer/core/collection/result_publisher.py:68；agents/stargazer/core/collection/preflight.py:24；agents/stargazer/core/infra/outbound_policy.py:16；agents/stargazer/api/health.py:100；agents/stargazer/docs/configuration-plugin-async-matrix.md:46　|　同步基线：b98b782a7　|　【已实现/推断/待确认】

## nats-executor —— 命令执行 agent【已实现/已存在】
- 运行时：Go（`main.go` v3.0.0）。
- 通信：NATS JetStream（KV 状态 + pub/sub 任务）。
- 订阅（instance 维度，主题模式为 `{action}.{location}.{id}`）：`local.execute.{id}`、`download.local.{id}`、`unzip.local.{id}`、`health.check.{id}`、`ssh.execute.{id}`、`download.remote.{id}`、`upload.remote.{id}`（证据：`agents/nats-executor/{local/executor.go:858,880,896,912,ssh/executor.go:1125,1142,1159}`，与 `apps/rpc/executor.py` 命名空间一致）。
- 能力：本地/SSH 执行、文件下载上传、解压、健康检查；YAML 配置 + TLS。

## ansible-executor —— playbook 执行【已实现/已存在】
- 运行时：Python + 内嵌 Ansible（`main.py`）。
- 通信：NATS（`AnsibleNATSService`，request/response）。
- 能力：adhoc / playbook 执行，结果经 NATS 回调 job_mgmt。Server 下发的 callback context（固定 caller、execution、attempt、随机 token）由 Executor 原样附加到完成回调及可恢复重试；JetStream 任务/重试消息、查询态 SQLite 与最终 DLQ 只保留脱敏 token，执行所需明文仅短暂存在于进程内存与本地独立加密的 callback secret，回调成功或进入最终 DLQ 后清除。

## fusion-collector —— sidecar 统一采集器【已实现/已存在】
- 形态：配置 + 容器（`agent/sidecar.yml`、`agent/Dockerfile`、`telegraf/telegraf.conf`）。
- 内含组件：collector-sidecar(Go)、telegraf、vector、filebeat/packetbeat/auditbeat、snmptrapd、nats-executor、ansible-executor。
- 能力：多协议指标/日志/SNMP trap 采集，并可执行远程作业。

## sidecar-installer —— agent 安装【已实现/已存在】
- 运行时：Go（`setup-worker.go`）。
- 通信：NATS JetStream Object Store（大文件传输）+ HTTP 回调。
- 能力：下载/校验/安装/升级 sidecar 包，事件流上报进度。
- 升级停服：Linux 在覆盖解压前停止 `bk-sidecar.service`；Windows 在暂存包校验完成、激活新目录前停止 `sidecar` 服务。两端统一上报 `stop_service` 安装步骤；首次安装未发现服务时按幂等成功处理。

### Windows 事务式安装与升级【已实现】
- GUI 安装器将共享 worker 解压至 NSIS 插件目录后运行，与目标安装目录隔离；该边界允许 worker 在不占用目标目录的前提下完成目录切换与激活。
- 空的目标目录按首次安装处理；已有安装则按事务方式暂存新包、激活并在中断或新服务启动失败时恢复上一版本。运行时目录（缓存、日志和生成文件）在升级中保留。
- 升级会保留既有卸载入口与图标；若新包已提供同名文件，则以新包为准。远程 bootstrap 直接运行 worker，首次安装不会生成 NSIS 卸载器；GUI 首次激活完成后再由 NSIS 写入卸载器、图标及系统卸载登记。

> 证据来源：agents/sidecar-installer/setup.nsi:3-5,187-203,224-238；agents/sidecar-installer/setup-worker.go:1297-1303,1568-1572,1712-1766；agents/sidecar-installer/setup-worker_test.go:747-850　|　同步基线：d2769559　|　【已实现】

## webhookd —— webhook 接入【已实现/已存在】
- 形态：配置模板（K8s 清单 `bk-lite-{log,metric,resource}-collector.yaml`）。
- 能力：接收外部 webhook/告警的 HTTP 端点；`bk-lite-resource-collector.yaml` 部署 kube-state-metrics 相关资源采集能力。

## ops-analysis-transform-runner —— 运营分析脚本变换【已实现/已存在】
- 独立薄 Runner：接收 `{script,rows,params,org_id}`，执行 `transform(rows, params) -> list[dict]`；不持有数据库凭据或用户 Token。
- 契约：`POST /v1/transform`，服务间 Token；单副本单 worker；行数上限 10000；默认超时 5s。
- 不参与 `batch_init`；不可用时脚本 REST 失败，不拖垮 Server 启动。

> 证据来源：agents/ops-analysis-transform-runner/README.md:1-36　|　同步基线：61bace9f　|　【已实现】

## 2026-07-01 Code-ARD 校准
- `[agents#20260701-031]` 移除 Stargazer `ip_scan` NATS handler 已落地结论：当前 `service/nats_server.py` 注册列表与 `plugins/inputs/ip_discovery/` 目录均不匹配（grep `ip_scan` 无命中），`plugins/inputs/ip/` 下的 IP 发现扫描文件是否经 NATS handler 暴露尚待确认。
- `[agents#20260701-032]` 配置采集插件矩阵更新为 19 个 `*_info.py`，并修正华为云、VMware 等插件路径为当前 `hwcloud`、`vmware_vc` 目录。
- `[agents#20260701-033]` 将 webhookd 资源采集 Kubernetes 清单纳入形态说明。
- `[agents#20260810-034]` ansible-executor 完成回调透传 Server 签发的 execution/attempt/token 身份，并在本地查询态与最终 DLQ 脱敏 token。

## 风险 / 待确认
- 各 agent 与后端的 NATS 主题命名约定的完整清单【推断，部分已知】。
- fusion-collector 各内嵌组件的启停与健康聚合【待确认】。
- nats-executor 主代码以 pub/sub + KV 形态使用 NATS；JetStream 高级 API（Object Store）主要见于 sidecar-installer/job 日志路径【推断，需确认 KV 用法范围】。

## 证据来源
`agents/stargazer/{server.py,core/nats.py,service/*,service/nats_server.py:46-97,plugins/inputs/ip/{__init__.py,ip_discovery_scanner.py,scan_targets.py,plugin.yml},plugins/inputs/{hwcloud/huaweicloud_info.py,vmware_vc/vmware_info.py,config_file/config_file_info.py,vastbase/vastbase_info.py}}`、`agents/nats-executor/main.go`、`agents/ansible-executor/main.py`、`agents/fusion-collector/*`、`agents/sidecar-installer/setup-worker.go`、`agents/webhookd/{bk-lite-log-collector.yaml,bk-lite-metric-collector.yaml,bk-lite-resource-collector.yaml}`。
