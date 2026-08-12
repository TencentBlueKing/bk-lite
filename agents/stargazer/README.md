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

```bash
MAX_ACTIVE_RUNS=16
MAX_ACTIVE_TARGETS=2000
TARGET_TASK_WINDOW=2000
REDIS_MAX_CONNECTIONS=2560
REDIS_POOL_TIMEOUT=2
CONNECT_TIMEOUT=5
PLUGIN_TIMEOUT=60
RUN_LEASE_TTL=600
RUN_LEASE_HEARTBEAT=30
COLLECTION_SHUTDOWN_GRACE=30
EVENT_LOOP_LAG_INTERVAL=1
OUTBOUND_ALLOWED_CIDRS=10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7
OUTBOUND_ALLOWED_DOMAINS=
```

这些值都是部署参数；`2000` 不是固定容量。`MAX_ACTIVE_TARGETS` /
`TARGET_TASK_WINDOW` 是单 Pod、跨所有运行共享的配置采集目标并发窗口，默认偏大是为了
不把压力藏在软上限后面，便于通过 CPU / 事件循环 lag / 错误率判断扩容。`MAX_ACTIVE_RUNS`
仍保留 run 级准入；满了返回 busy/429。

`REDIS_MAX_CONNECTIONS` 应不小于目标并发并留租约余量（推荐
`≳ MAX_ACTIVE_TARGETS`）。多 Pod 时还要保证
`单池峰值 × Pod 数 < Redis maxclients`。池满时会有限等待
`REDIS_POOL_TIMEOUT` 秒，而不是立刻 `MaxConnectionsError` 打崩整轮 run。

协议预检默认 5 秒：TCP 协议先连接实际端口，SNMP/UDP 返回“不确定”并进入
凭据感知采集，云账号检查逻辑端点；ICMP 不作为硬过滤条件。
直接 IP 与域名解析后的每个可用地址都必须落在 `OUTBOUND_ALLOWED_CIDRS`；配置
`OUTBOUND_ALLOWED_DOMAINS` 后，域名还必须同时命中该名单，域名名单不能绕过 CIDR 边界。
生产环境应按实际采集边界收窄这两项。

所有注册插件必须暴露异步入口。原生异步实现直接 `await`；同步 SDK 由插件自身在异步入口中
显式调用 `asyncio.to_thread(self._sync_collect)`，并必须给 SDK 配置真实连接/读取超时。
运行时没有同步插件 Adapter 和专用线程池。

## 健康与观测

- `/api/health/`：进程存活；
- `/api/health/ready`：Redis 与统一运行时就绪；
- `/api/health/stats`：活动运行、并发配置和事件循环延迟；
- `/api/health/metrics`：Prometheus 格式的运行时指标。

重点观察 `active_runs`、`active_targets`、接纳拒绝、事件循环 lag、预检失败、插件超时、结果
发布失败、Redis 连接池等待/超时，以及凭据状态 Redis 错误。日志和指标只允许任务、目标、插件、凭据 ID 与稳定错误码，不得记录凭据
正文。

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
