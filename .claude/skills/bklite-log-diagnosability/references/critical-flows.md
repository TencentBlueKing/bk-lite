# Server ↔ Stargazer 关键链路导航

代码会演进；这些是审计入口，不是永久调用图。每次都用 `rg` 和调用方阅读验证。

先分别确认开发 HTTP 服务、生产 HTTP 服务和 worker 的启动入口。当前入口包括
`agents/stargazer/Makefile`、`support-files/supervisor/service.conf`、
`support-files/supervisor/worker.conf` 和 `start_worker.py`；日志等级与 handler 不能
从其中一个入口外推到全部运行形态。

## 默认优先级

1. 采集任务派发、执行、回调和结果持久化。
2. NATS 连接、请求、订阅和 handler 执行。
3. CMDB 采集工具调试（SNMP/IPMI 等）。
4. 节点远程执行与回调。
5. ARQ worker 启动、任务领取、超时和停止。

## 采集主链

| Stage | 常见入口 | 重点标识 | 典型失败 |
|---|---|---|---|
| Server 创建/派发 | `server/apps/cmdb/tasks/`、`server/apps/cmdb/services/`、相关 `nats_api.py` | collect_task_id、task_id、model_id、instance_id | 校验、任务状态、派发失败 |
| NATS 传输 | Server/Stargazer 的 `nats.py`、`nats_api.py`、`nats_utils.py` | subject、request/operation ID | DNS、TLS、超时、断连、序列化 |
| Stargazer handler | `agents/stargazer/service/nats_server.py`、`api/collect.py`、`api/monitor.py` | task_id、batch_id、host、model_id | payload 无效、排队失败、冷却跳过 |
| 采集编排 | `agents/stargazer/service/collection_service.py` | model_id、plugin_name、executor_type、host | 插件解析、节点信息、执行、格式转换 |
| 插件/执行器 | `agents/stargazer/core/plugin_executor.py`、`plugins/`、`common/monitor_plugins/` | plugin/source、target、attempt | 凭据、连接、第三方响应、解析、脚本执行 |
| 回调 | Stargazer callback handler/service 与 Server 接收方 | task_id、instance_id、subject | 回调丢失、重复、状态清理失败 |
| Server 落库 | 对应 result/callback service | task_id、status、counts | 状态错配、部分写入、补偿失败 |

审计时画出真实路径，并确定哪一层拥有最终 `outcome`。不要把每一层都设成 ERROR 所有者。
当业务失败被编码进指标或回调时，分别追踪 `execution_outcome` 和
`delivery_outcome`；传输成功不能覆盖业务失败。

动态插件不要求穷举全部实现。至少选择一个可能携带凭据/配置内容的插件和一个
高频插件，验证共享编排、返回结构和日志边界；在报告中列明未检查的插件家族。

## 调试链路

从 `server/apps/cmdb/services/collect_tool_service.py` 和相关 Celery/NATS 调用开始，追踪到：

- `agents/stargazer/service/nats_server.py` 的 debug handler；
- `agents/stargazer/service/debug/protocol_debug_service.py`；
- 协议执行器；
- Server 标准化响应。

至少验证 `debug_id/request_id`、protocol、action、target、stage、duration_ms 和 outcome 能贯穿。credential 与 raw_log 不得进入普通生产日志。

## 节点远程执行链路

从 Server 的 node/job 管理派发点追踪到 Stargazer/sidecar 执行和 callback。该链路受 `RELIABILITY.md` 的目标主机安全红线约束。

必须能区分：

- 未派发、派发失败、已接收、执行中；
- 超时、取消、失败、部分成功、回调失败；
- 自动重试、人工重试和重复回调；
- 执行失败与“清理 running flag 失败”。

高危执行缺少终态证据可升为 P0；不要在日志中记录完整命令、凭据或远程输出。

## NATS/ARQ 基础设施

检查：

- 初始化成功是否只有一条有用摘要；
- 连接失败是否只输出一个终态 ERROR，而不是多行推测；
- retry/reconnect 是否限频并包含 attempt/max_attempts；
- handler 错误是否保留 subject 和业务 ID；
- worker 启停日志是否包含 service/queue/concurrency，而不是装饰分隔线；
- 健康检查等高频成功请求是否依赖统一访问日志，不重复输出业务 INFO。

## 常用发现命令

```bash
rg -n 'register_handler|publish\(|request\(|subscribe|\.delay\(|enqueue_job' server agents/stargazer
rg -n 'callback_subject|collect_task_id|task_id|debug_id|execution_id|batch_id' server agents/stargazer
rg -n 'except|logger\.(warning|error|exception)|raise' <selected-flow-files>
```

把搜索命中当导航，不当结论。第三方 SDK、副本代码和测试 fixture 必须单独标注，避免把不可控代码列入项目修复范围。
