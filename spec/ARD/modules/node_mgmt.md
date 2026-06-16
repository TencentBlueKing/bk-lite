# 模块 ARD：Node Management（节点管理）

> 路径 `server/apps/node_mgmt` ｜ API 前缀 `api/v1/node_mgmt/`

## 1. 职责【已实现/已存在】
纳管分布式基础设施：节点、控制器（controller）、采集器（collector）、云区域（cloud region）与 sidecar 配置；负责 agent 部署、健康检查、采集器生命周期与配置下发（经 NATS）。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| Node / Collector / Controller | `models/sidecar.py` | 节点、采集组件、管理 agent |
| NodeCollectorConfiguration | `models/sidecar.py:120` | 节点与采集器配置的关联 |
| NodeCollectorInstallStatus | `models/installer.py:9` | 节点-采集器安装状态跟踪 |
| CloudRegion / SidecarEnv | `models/cloud_region.py` | 部署区域、sidecar 环境变量 |
| PackageVersion | `models/package.py` | agent/采集器安装包（存 MinIO） |
| ControllerTask(Node) / CollectorActionTask(Node) | `models/{installer,action}.py` | 安装/升级、采集器启停动作及节点级状态 |
| NodeComponentVersion | `models/node_version.py` | 组件版本与可升级标记 |

**存储**：PostgreSQL（ORM）；MinIO（安装包，`utils/s3.py`）。

## 3. 接口【已实现/已存在】
`node`/`cloud_region`/`sidecar_env`/`collector`/`controller`/`configuration`/`child_config`/`installer`/`package`；`open_api`（sidecar 可访问，`OpenSidecarViewSet`）。

## 4. 通信机制【已实现/已存在】
- NATS：`nats/{node,permission}.py` 节点数据同步与权限；JetStream 订阅安装事件流（`tasks/installer.py`）。
- SSH：`utils/installer.py` 远程安装控制器。
- Celery：`install/uninstall_controller`、`install_collector`、`converge_*`/`timeout_*`（收敛/超时）、`discover_node_versions`、`sync_node_properties_to_sidecar`（推送配置到 sidecar.yaml）、`check_all_region_services`（健康检查 nats-executor/stargazer）。

## 5. 风险 / 待确认
- JetStream 默认关闭，但安装事件流依赖 JetStream，生产需确认启用【已实现风险，见总体 §11】。
- SSH 凭据/私钥的存储与保护（部分存 MinIO）【待确认】。

## 6. 证据来源
`server/apps/node_mgmt/{urls.py,models/*,nats/*,tasks/*,utils/{s3,installer}.py,constants/cloudregion_service.py}`。
