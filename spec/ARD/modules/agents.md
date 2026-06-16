# 模块 ARD：分布式 Agents

> 路径 `agents/*`

## stargazer —— 协议采集 agent【已实现/已存在】
- 运行时：Python + Sanic（`server.py`，:8083）。
- 通信：NATS pub/sub（`core/nats.py:NATSSanic`，`service/nats_server.py`）。
- 注册处理函数（经 `@register_handler()`，主题由其派生）：`list_regions`、`test_connection`、`health_check`、`debug_snmp`、`debug_ipmi`、`handle_host_remote_callback`（证据：`agents/stargazer/service/nats_server.py:46-97`）。
- 能力：协议采集（SNMP/IPMI/SSH/HTTP/WMI 等）、凭据状态管理、YAML 驱动采集（`service/collection_service.py`）、远程命令运行时。

## nats-executor —— 命令执行 agent【已实现/已存在】
- 运行时：Go（`main.go` v3.0.0）。
- 通信：NATS JetStream（KV 状态 + pub/sub 任务）。
- 订阅（instance 维度，主题模式为 `{action}.{location}.{id}`）：`local.execute.{id}`、`download.local.{id}`、`unzip.local.{id}`、`health.check.{id}`、`ssh.execute.{id}`、`download.remote.{id}`、`upload.remote.{id}`（证据：`agents/nats-executor/{local/executor.go:858,880,896,912,ssh/executor.go:1125,1142,1159}`，与 `apps/rpc/executor.py` 命名空间一致）。
- 能力：本地/SSH 执行、文件下载上传、解压、健康检查；YAML 配置 + TLS。

## ansible-executor —— playbook 执行【已实现/已存在】
- 运行时：Python + 内嵌 Ansible（`main.py`）。
- 通信：NATS（`AnsibleNATSService`，request/response）。
- 能力：adhoc / playbook 执行，结果经 NATS 回调 job_mgmt。

## fusion-collector —— sidecar 统一采集器【已实现/已存在】
- 形态：配置 + 容器（`agent/sidecar.yml`、`agent/Dockerfile`、`telegraf/telegraf.conf`）。
- 内含组件：collector-sidecar(Go)、telegraf、vector、filebeat/packetbeat/auditbeat、snmptrapd、nats-executor、ansible-executor。
- 能力：多协议指标/日志/SNMP trap 采集，并可执行远程作业。

## sidecar-installer —— agent 安装【已实现/已存在】
- 运行时：Go（`setup-worker.go`）。
- 通信：NATS JetStream Object Store（大文件传输）+ HTTP 回调。
- 能力：下载/校验/安装/升级 sidecar 包，事件流上报进度。

## webhookd —— webhook 接入【已实现/已存在】
- 形态：配置模板（K8s 清单 `bk-lite-{log,metric}-collector.yaml`）。
- 能力：接收外部 webhook/告警的 HTTP 端点。

## 风险 / 待确认
- 各 agent 与后端的 NATS 主题命名约定的完整清单【推断，部分已知】。
- fusion-collector 各内嵌组件的启停与健康聚合【待确认】。
- nats-executor 主代码以 pub/sub + KV 形态使用 NATS；JetStream 高级 API（Object Store）主要见于 sidecar-installer/job 日志路径【推断，需确认 KV 用法范围】。

## 证据来源
`agents/stargazer/{server.py,core/nats.py,service/*}`、`agents/nats-executor/main.go`、`agents/ansible-executor/main.py`、`agents/fusion-collector/*`、`agents/sidecar-installer/setup-worker.go`、`agents/webhookd/*`。
