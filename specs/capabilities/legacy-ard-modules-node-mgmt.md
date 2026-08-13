# 模块 ARD：Node Management（节点管理）

> Migrated from `spec/ARD/modules/node_mgmt.md` as legacy capability evidence.

> 路径 `server/apps/node_mgmt` ｜ API 前缀 `api/v1/node_mgmt/`

## 1. 职责【已实现/已存在】
纳管分布式基础设施：节点、控制器（controller）、采集器（collector）、云区域（cloud region）与 sidecar 配置；负责 agent 部署、健康检查、采集器生命周期与配置下发（经 NATS）。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| Node / Collector / Controller | `models/sidecar.py` | 节点、采集组件、管理 agent；Node 含 `node_type`（默认 host，支持容器节点类型）与 `install_method` 字段，二者影响安装与采集行为；同时持久化 CMDB、监控两侧的关联标识及各目标最近一次推送结果，用于后续补推和退役联动 |
| SidecarApiToken | `models/sidecar.py:162` | sidecar 鉴权令牌（`node_id` + `token`），节点激活后注册获得（对齐 PRD 云区域.md §5） |
| NodeCollectorConfiguration | `models/sidecar.py:120` | 节点与采集器配置的关联 |
| NodeCollectorInstallStatus | `models/installer.py:9` | 节点-采集器安装状态跟踪 |
| CloudRegion / SidecarEnv | `models/cloud_region.py` | 部署区域、sidecar 环境变量；CloudRegion 含 `proxy_address` 字段（migration `0027_cloudregion_proxy_address.py` 新增，`models/cloud_region.py:9`），被 NATS handler `get_cloud_region_proxy_address` 与采集器配置下发逻辑消费 |
| CloudRegionService | `models/cloud_region.py:30` | 云区域服务（stargazer/nats-executor）的部署与健康状态，为 §4 `check_all_region_services` 健康检查的存储载体 |
| PackageVersion | `models/package.py` | agent/采集器安装包（存 MinIO） |
| ControllerTask(Node) / CollectorActionTask(Node) | `models/{installer,action}.py` | 安装/升级、采集器启停动作及节点级状态 |
| NodeComponentVersion | `models/node_version.py` | 组件版本与可升级标记 |

> 证据来源：server/apps/node_mgmt/models/sidecar.py:50-52　|　同步基线：d2769559　|　【已实现】

**存储**：PostgreSQL（ORM）；MinIO（安装包，`utils/s3.py`）。

## 3. 接口【已实现/已存在】
REST 路由组：`node`/`cloud_region`/`sidecar_env`/`collector`/`controller`/`configuration`/`child_config`/`installer`/`package`；`open_api`（sidecar 可访问，`OpenSidecarViewSet`）。

节点跨模块同步【已实现】：节点管理可将已纳管节点显式推送至 CMDB 或监控系统；详情页可按所选目标补推。推送会携带节点、云区域、组织归属及已有对端关联标识，并在节点侧记录各目标的结果；两个对端均已建立关联时会补齐双方关联标识。该能力以 [[legacy-ard-modules-cmdb.md#4. 依赖与通信【已实现/已存在】]] 和 [[legacy-ard-modules-monitor.md#3. 接口【已实现/已存在】]] 的接收契约为准。

> 证据来源：server/apps/node_mgmt/models/sidecar.py:50-52，server/apps/node_mgmt/services/module_push.py:129-193,370-400　|　同步基线：d2769559　|　【已实现】

节点退役联动【已实现】：删除节点默认只删除节点管理记录；调用方显式选择关联退役时，系统才向已关联的 CMDB、监控对象发送退役事件。对端不可用或退役失败不会阻断节点删除。

> 证据来源：server/apps/node_mgmt/views/node.py:296-307，server/apps/node_mgmt/services/module_push.py:98-126,197-249　|　同步基线：d2769559　|　【已实现】

`open_api` 安装链路【已实现/已存在】：安装令牌有效期 30 分钟、最多 5 次使用；下载令牌有效期 10 分钟、最多 3 次使用；脚本渲染会调用 webhook，Linux bootstrap 入口生成安装会话，安装会话为 sidecar 生成 NATS 下载配置并按 CPU 架构选择包（证据：`views/sidecar.py:338,395,532,564,583`、`services/install_token.py:11,103`、`services/installer_session.py:51`）。

NATS handlers（`@nats_client.register`，`nats/node.py`）：
- `install_collector(data)` / `install_managed_component(data)`：经 NATS 触发采集器 / 受管组件安装，二者复用同一安装流程（`nats/node.py:701-710`）。
- `get_cloud_region_proxy_address(cloud_region_id, organization_ids)`：返回云区域代理地址，支持按组织过滤；优先读 `CloudRegion.proxy_address`，为空时回退环境变量 `PROXY_ADDRESS`（`nats/node.py:534-569`）。

## 4. 通信机制【已实现/已存在】
- NATS：`nats/{node,permission}.py` 节点数据同步与权限。安装日志事件流走 NATS core 订阅：`installer.py` 通过 `subscribe_lines_sync` 订阅普通 subject `executor.stream.{execution_id}`，并未使用 JetStream 持久消费者（`tasks/installer.py:591-604`）。`subscribe_lines_sync` 定义在服务端顶层包 `server/nats_client/clients.py:256-285`（用 `nc.subscribe(subject, cb=...)` 即 core 订阅）；同文件另有 JetStream 原语 `ensure_stream`/`iter_jetstream_subject`（`server/nats_client/clients.py:304,332`），但 node_mgmt installer 未引用。
- 跨模块推送：节点创建/补推按用户所选 CMDB、监控目标逐一调用对端接收契约，单目标最多尝试 3 次；冲突不回填关联标识，结果以成功、冲突或跳过记录。安装请求中的推送目标仅对已存在的节点立即生效；首次 Sidecar 注册后的延迟推送尚未接线，不能表述为“安装完成即自动同步”的闭环。
- SSH：`utils/installer.py` 远程安装控制器。
- WinRM：Windows 控制器远程安装由云区域内健康的 Ansible Executor 连接目标主机，固定使用 HTTPS/5986、NTLM 和服务端证书校验；Executor 将原生 `bklite-controller-bootstrap.exe` 分发到目标主机并执行，不新增独立 WinRM 服务。
- Celery：
  - 控制器：`install/uninstall_controller`。
  - 采集器：`install_collector`（实际执行安装）；`uninstall_collector` 当前为占位任务，函数体仅 `pass`、未实现卸载逻辑（`tasks/installer.py:1148-1150`）。
  - 收敛 / 超时（两组）：控制器安装侧 `converge_controller_install_connectivity_for_node`（`tasks/installer.py:722`）/ `timeout_controller_install_task`（`tasks/installer.py:766`）；采集器动作侧 `converge_collector_action_task_for_node`（`tasks/action_task.py:153`）/ `timeout_collector_action_task`（`tasks/action_task.py:217`）。
  - 其他：`discover_node_versions`、`sync_node_properties_to_sidecar`（推送配置到 sidecar.yaml）、`check_all_region_services`（健康检查 nats-executor/stargazer）。
- 管理命令【已实现/已存在】：`node_init` 初始化内置节点数据；`collector_package_init` / `controller_package_init` 上传 collector/controller 包；`installer_init` 上传 latest 安装器对象，其中 Windows GUI 安装器使用默认 `installer` variant，Windows 远程安装产物使用 `--variant bootstrap` 上传到 `installer/windows/x86_64/bklite-controller-bootstrap.exe`；`node_token_init` / `reset_node_token` 生成或重置节点 token；`backfill_node_cpu_architecture`、`backfill_package_storage_paths`、`verify_architecture_rollout` 分别用于 CPU 架构回填、包对象路径回填与架构发布校验。

> 证据来源：server/apps/node_mgmt/services/module_push.py:129-193,370-400，server/apps/node_mgmt/views/installer.py:86-103　|　同步基线：d2769559　|　【已实现】

## 5. 风险 / 待确认
- 安装日志事件流采用 NATS core 订阅（`subscribe_lines_sync` 订阅 `executor.stream.{execution_id}`），不依赖 JetStream，订阅在超时或 `stop_event` 后即解订阅、不做持久化与重放，进程/网络中断期间的日志行可能丢失【已实现，见 `tasks/installer.py:591-604`、`server/nats_client/clients.py:256-285`】。
- SSH 凭据/私钥的存储与保护（部分存 MinIO）【待确认】。

## 2026-07-01 Code-ARD 校准
- `[node_mgmt#20260701-015]` 补录初始化、包上传、安装器 latest 对象上传、token 生成/重置、CPU 架构回填、包对象路径回填与架构发布校验命令。
- `[node_mgmt#20260701-016]` 补录 open_api 安装令牌、下载令牌和安装会话链路。

## 6. 证据来源
- `server/apps/node_mgmt/{urls.py,models/*,nats/*,tasks/*,utils/{s3,installer}.py,constants/cloudregion_service.py}`。
- 模型：`models/sidecar.py:44-49`（Node.node_type/install_method）、`models/sidecar.py:162-168`（SidecarApiToken）、`models/cloud_region.py:9`（CloudRegion.proxy_address）、`models/cloud_region.py:30-42`（CloudRegionService）。
- NATS handlers：`nats/node.py:534-569`（get_cloud_region_proxy_address）、`nats/node.py:701-710`（install_collector / install_managed_component）。
- 安装事件流（NATS core）：`tasks/installer.py:591-604`、`server/nats_client/clients.py:256-285`。
- Celery 收敛/超时与卸载：`tasks/installer.py:722,766`、采集器卸载占位任务 `tasks/installer.py:1148-1150`、`tasks/action_task.py:153,217`。
- migration：`migrations/0027_cloudregion_proxy_address.py`、`migrations/0035_backfill_container_node_cpu_architecture.py`。
- 管理命令与安装令牌：`management/commands/{node_init.py:8,collector_package_init.py:7,controller_package_init.py:7,installer_init.py:10,node_token_init.py:8,reset_node_token.py:8,backfill_node_cpu_architecture.py:11,backfill_package_storage_paths.py:12,verify_architecture_rollout.py:10}`、`views/sidecar.py:338,395,532,564,583`、`services/install_token.py:11,103`、`services/installer_session.py:51`。
