# Stargazer

Stargazer 是配置采集与业务监控采集代理。运行形态为单个无状态 Sanic 服务；不再启动
ARQ Worker，也不把 Redis 当作任务队列。

完整设计见
[`specs/changes/stargazer-stateless-async-collection/spec.md`](../../specs/changes/stargazer-stateless-async-collection/spec.md)。

## 启动

```bash
uv sync
uv run python server.py
```

服务启动时建立普通异步 Redis Client 和 NATS 连接，并初始化统一
`CollectionApplication`。Docker/Kubernetes 通过增加 Pod 数量扩展不同采集运行的吞吐；首版不把
单个运行拆到多个 Pod。

## HTTP 任务约定

配置采集与 `/api/monitor/*` 的薄租约 ID 由服务端对请求做规范化指纹派生
（`METHOD` + path + 排序 query + 业务 headers），形如 `req_<sha256>`；调用方不必传
`X-Task-ID`。响应头会回传派生 ID。同一 Telegraf input / 直触发在业务 headers/query
不变时指纹稳定，用于防重叠；凭据或参数变更会换键。

相同指纹且租约仍有效时返回 `202 duplicate-active`；本 Pod 容量已满返回 `429` 和
`Retry-After`。一次多 IP 请求只创建一个顶层运行，每个 IP 是一个目标逻辑任务，目标
内部按输入顺序串行尝试凭据。

Redis 只保存运行租约、凭据 ID 亲和/冷冻和 Deferred callback 上下文，不保存密码、
Token、community 或私钥。移除持久队列后，Pod 故障丢单依赖下周期用相同请求指纹再次触发。

## 并发与超时

目标并发**只从环境变量读取**（代码默认值仅作缺省），改配置重启即可，不必改代码：

```bash
MAX_ACTIVE_RUNS=16
# 配置采集目标并发；设为 0 表示不限制（尽快打满机器、靠监控扩容）
MAX_ACTIVE_TARGETS=150
TARGET_TASK_WINDOW=150
REDIS_MAX_CONNECTIONS=2560
REDIS_POOL_TIMEOUT=2
# 默认 RESP2，兼容不支持 HELLO 的旧 Redis / 代理；仅在确认服务端支持 RESP3 时设为 3
REDIS_PROTOCOL=2
PREFLIGHT_TIMEOUT=15
PROBE_TIMEOUT=15
COLLECTION_TIMEOUT=60
PUBLISH_QUEUE_TIMEOUT=60
PUBLISH_DELIVERY_TIMEOUT=30
PUBLISH_TOTAL_TIMEOUT=120
RUN_LEASE_TTL=600
RUN_LEASE_HEARTBEAT=30
COLLECTION_SHUTDOWN_GRACE=30
EVENT_LOOP_LAG_INTERVAL=1
CAPACITY_LOG_INTERVAL=180
OUTBOUND_ALLOWED_CIDRS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7
OUTBOUND_ALLOWED_DOMAINS=
# 默认 off：跳过 TCP/TLS 端口短探，CIDR 出站与 Job remote 通道检查仍保留；设为 on 恢复探活
PREFLIGHT_REACHABILITY=off
```

这些值都是部署参数。未设置时默认 `MAX_ACTIVE_TARGETS=150`、
`TARGET_TASK_WINDOW=150`。二者是单 Pod、跨所有运行共享的配置采集目标并发与任务窗口；
全局调度器在 Run 之间 round-robin，单个大 Run 不再预占 worker。需要临时去掉目标并发上限时：

```bash
MAX_ACTIVE_TARGETS=0
TARGET_TASK_WINDOW=0
```

`MAX_ACTIVE_RUNS` 仍保留 run 级准入；满了返回 busy/429。

`REDIS_MAX_CONNECTIONS` 应不小于目标并发并留租约余量（推荐
`≳ MAX_ACTIVE_TARGETS`；目标不限制时按机器与 Redis `maxclients` 自行抬高）。多 Pod 时还要保证
`单池峰值 × Pod 数 < Redis maxclients`。池满时会有限等待
`REDIS_POOL_TIMEOUT` 秒，而不是立刻 `MaxConnectionsError` 打崩整轮 run。

`REDIS_PROTOCOL` 默认 `2`（RESP2）。`redis-py` 8+ 默认会走 RESP3 并发送 `HELLO`；
若 Redis 过旧或不支持 `HELLO` 的代理会在启动 `ping` 时直接失败，因此显式钉在 RESP2。

`PREFLIGHT_TIMEOUT` 与 `PROBE_TIMEOUT` 分别控制协议预检和插件 AccessProbe，默认均为 15 秒。
`PREFLIGHT_REACHABILITY` 默认 `off`：保留 CIDR/SSRF 出站安全检查，但跳过 TCP/TLS、SNMP、
remote/job 及其他所有采集前探测，直接进入正式采集；设为 `on` 时才执行预检和插件 probe。
`COLLECTION_TIMEOUT` 是正式采集缺省值 60 秒，插件 YAML executor 的 `timeout` 优先；
发布阶段拆为三层：`PUBLISH_QUEUE_TIMEOUT` 默认 60 秒，控制等待有界发布队列接纳结果；
`PUBLISH_DELIVERY_TIMEOUT` 默认 30 秒，控制实际 NATS publish/flush；`PUBLISH_TOTAL_TIMEOUT`
默认 120 秒，控制单目标发布全生命周期。兼容期未配置 `PUBLISH_DELIVERY_TIMEOUT` 时回退读取
`PUBLISH_TIMEOUT`。ICMP 不作为硬过滤条件。

发布总超时发生在 NATS transport 触达前时会安全撤销队列项，不会在后台晚发，也不会误记为
`delivery_unknown`；周期任务的结果幂等 ID 包含本轮 `attempt_id`。
直接 IP 与域名解析后的每个可用地址都必须落在 `OUTBOUND_ALLOWED_CIDRS`；配置
`OUTBOUND_ALLOWED_DOMAINS` 后，域名还必须同时命中该名单，域名名单不能绕过 CIDR 边界。
生产环境应按实际采集边界收窄这两项。

所有注册插件必须暴露异步入口。原生异步实现直接 `await`；同步 SDK 由插件自身在异步入口中
显式调用 `asyncio.to_thread(self._sync_collect)`，并必须给 SDK 配置真实连接/读取超时。
运行时没有同步插件 Adapter 和专用线程池。

各配置采集插件的真实 I/O 模型、异步依赖与兼容路径见
[`docs/configuration-plugin-async-matrix.md`](docs/configuration-plugin-async-matrix.md)。

## 健康与观测

- `/api/health/`：进程存活；
- `/api/health/ready`：Redis 与统一运行时就绪；
- `/api/health/stats`：活动运行、并发配置和事件循环延迟；
- `/api/health/metrics`：Prometheus 格式的运行时指标。

重点观察 `active_runs`、`active_targets`、接纳拒绝、事件循环 lag、预检失败、插件超时、结果
发布失败、Redis 连接池等待/超时，以及凭据状态 Redis 错误。日志和指标只允许任务、目标、插件、凭据 ID 与稳定错误码，不得记录凭据
正文。

运行时默认每 3 分钟输出一次 `event=collection_capacity`，专门记录
`MAX_ACTIVE_TARGETS`（默认 150）全局异步目标槽位的已用、剩余、利用率和峰值，同时包含待调度
目标/Run、发布队列利用率及事件循环 lag。可通过 `CAPACITY_LOG_INTERVAL` 调整周期；该日志用于
压测后判断是否调整 `MAX_ACTIVE_TARGETS`，不代表线程池并发。

## Host Remote

Host Remote 提交返回 `Deferred`。每个目标使用独立 callback ID；可信上下文包含父任务 ID、
目标、owner 和 fencing token。回调必须同时匹配父任务、目标和 fencing，处理任务直接注册在
Sanic 本地生命周期中，不再进入 ARQ。Redis 中的 callback 上下文继续提供重复回调和发布重试
所需的短期状态。

## 网络拓扑发现契约

- `topology_protocols` 支持 `lldp`、`cdp`、`fdb`、`arp`；
- `topology_fallback_strategy` 由上游 CMDB 消费，Stargazer 不解释；
- 原始 `network_topo` 始终保留，同时输出 `network_topology_facts`；
- 下游优先用事实建边，无法解析时再回退原始结果。

## 验证

```bash
uv run pytest -q -o addopts='' \
  tests/test_collection_runtime.py \
  tests/test_target_collection_executor.py \
  tests/test_redis_collection_state.py \
  tests/test_async_plugin_contract.py \
  tests/test_collection_load.py
```

负载测试覆盖 `255 IP × 5 凭据 × 200 目标并发`，验证并发上界、不可达目标过滤、事件循环
响应和 Task 清理。
`MAX_TARGETS_PER_RUN` 限制单次请求目标数（默认 10000）；`RUN_DEADLINE` 设置整个运行的硬超时秒数，`0` 表示不额外限制，仍受连接和插件超时保护。
