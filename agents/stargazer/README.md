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

### Monitor 接口鉴权迁移

`/api/monitor/*` 支持 Bearer Token 鉴权，并通过显式模式分阶段迁移：

```bash
# 兼容期默认值：保留旧 Telegraf 请求，并记录其鉴权状态
STARGAZER_MONITOR_AUTH_MODE=legacy
STARGAZER_MONITOR_AUTH_TOKEN=<current-token>
# 轮换期可同时接受上一枚 Token
STARGAZER_MONITOR_AUTH_PREVIOUS_TOKEN=<previous-token>
```

先在 `legacy` 模式配置当前 Token，再逐个让调用方发送
`Authorization: Bearer <current-token>`。确认兼容日志中的调用均为 `valid` 后，把模式切为
`enforce`；此时缺失或错误的凭据返回 `401`，运行时不会创建采集任务。`enforce` 未配置当前或
上一枚 Token 时失败关闭并返回 `503`。Token 轮换时先把旧值移到 previous、发布新值，确认调用方
完成切换后再移除 previous。若上线后需要回滚，只需把模式恢复为 `legacy`，旧调用立即恢复，健康
检查与非 monitor 蓝图不受影响。

## 并发与超时

目标并发**只从环境变量读取**（代码默认值仅作缺省），改配置重启即可，不必改代码：

```bash
MAX_ACTIVE_RUNS=16
MAX_ACTIVE_TARGETS=160
CONFIGURATION_MAX_ACTIVE_TARGETS=100
MONITORING_MAX_ACTIVE_TARGETS=30
NETWORK_TOPOLOGY_MAX_ACTIVE_TARGETS=30
TARGET_TASK_WINDOW=160
SNMP_MAX_IN_FLIGHT=100
SNMP_ENGINE_MAX_TARGETS=2000
SNMP_ENGINE_IDLE_SECONDS=300
SYNC_SDK_MAX_IN_FLIGHT=16
REMOTE_JOB_MAX_IN_FLIGHT=20
DEFAULT_ASYNC_MAX_IN_FLIGHT=160
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
```

这些值是单 Pod、跨所有 Run 共享的容量。三类软配额必须为正整数，但不要求总和等于 160；
三类同时积压时按 `100/30/30` 调度，某类无排队目标时，其他类可借满 160。新类别到达后不抢占
在途目标，而是优先获得后续释放的槽位。`SNMP_MAX_IN_FLIGHT`、`SYNC_SDK_MAX_IN_FLIGHT`
和 `REMOTE_JOB_MAX_IN_FLIGHT` 是第二维技术资源边界；两维都有容量时才创建目标 Task。配置非法时启动失败，
不再支持用 `0` 隐式关闭边界。

`MAX_ACTIVE_RUNS` 仍保留 run 级准入；满了返回 busy/429。

SNMP 采集在每个 worker 进程内按凭据作用域共享 pysnmp `SnmpEngine`（v1/v2c 共用一个，
v3 按用户名与密钥组合各一个），不再为每个目标新建 engine：pysnmp 每个 engine 首次解析 OID
都会用 PLY 重算 SMI 语法表（连同 MIB 模块约 2 MiB、约 50 ms 纯 Python CPU），100 并发一批
就阻塞事件循环数秒；uvloop 的 sendto 地址缓存（2048 项 LRU）还会经 pysnmp 传输地址对象拖住
已关闭 engine 的整棵 MIB 树，这是大规模 SNMP 轮次内存不回落与 CPU 饱和的根因（builder 实测
800 个不可达目标：修复前 RSS 73→1747 MiB、事件循环 P99 延迟最高 7.3 s；修复后 73→115 MiB、
P99 延迟 ≤25 ms）。`SNMP_ENGINE_MAX_TARGETS` 限制单个 engine 服务过的不同目标地址数
（每个目标在 pysnmp LCD 中约占 20 KiB），达到后新目标换用新 engine、旧 engine 排空在途请求后关闭；
`SNMP_ENGINE_IDLE_SECONDS` 是 engine 空闲多久后释放 dispatcher。两者必须为正数，否则启动失败。

`REDIS_MAX_CONNECTIONS` 应不小于目标并发并留租约余量（推荐
`≳ MAX_ACTIVE_TARGETS`，并按实际辅助请求留出余量）。多 Pod 时还要保证
`单池峰值 × Pod 数 < Redis maxclients`。池满时会有限等待
`REDIS_POOL_TIMEOUT` 秒，而不是立刻 `MaxConnectionsError` 打崩整轮 run。

`REDIS_PROTOCOL` 默认 `2`（RESP2）。`redis-py` 8+ 默认会走 RESP3 并发送 `HELLO`；
若 Redis 过旧或不支持 `HELLO` 的代理会在启动 `ping` 时直接失败，因此显式钉在 RESP2。

`PREFLIGHT_TIMEOUT` 与 `PROBE_TIMEOUT` 分别控制协议预检和插件 AccessProbe，默认均为 15 秒。
是否执行 IP 预检不再由全局环境变量控制。每个请求仅在 `params.ip_precheck` 为 `true`、`1`、
`yes` 或 `on` 时执行协议连通性预检及插件 AccessProbe；缺失或为其他值时跳过这些探测，直接进入
正式采集。CIDR/SSRF 出站安全检查不属于可选预检，无论请求开关如何都必须执行。
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
- `/api/health/ready`：Redis、NATS subscriber，以及 metrics 专用连接、目标 Stream 和 subject 覆盖契约就绪；
- `/api/health/stats`：活动运行、并发配置和事件循环延迟；
- `/api/health/metrics`：Prometheus 格式的运行时指标。

重点观察 `active_runs`、`active_targets`、接纳拒绝、事件循环 lag、预检失败、插件超时、结果
发布失败、Redis 连接池等待/超时，以及凭据状态 Redis 错误。日志和指标只允许任务、目标、插件、凭据 ID 与稳定错误码，不得记录凭据
正文。

运行时默认每 3 分钟输出一次 `event=collection_capacity`，专门记录
`MAX_ACTIVE_TARGETS`（默认 160）全局异步目标槽位的已用、剩余、利用率和峰值，同时包含待调度
目标/Run、发布队列利用率、事件循环 lag、进程 CPU/RSS/线程/FD，以及 cgroup CPU 限额、内存
利用率和 CPU throttling 增量。可通过 `CAPACITY_LOG_INTERVAL` 调整周期；该日志用于压测后判断
是否调整 `MAX_ACTIVE_TARGETS`，不代表线程池并发。若 lag P99 持续超过 1 秒、CPU 限额利用率或
cgroup 内存利用率持续超过 80%、发布队列长期超过 80%，或 throttling 增量持续增长，不应继续
上调并发，应先定位事件循环阻塞、CPU/内存限额或发布瓶颈。健康接口中字段为 `-1` 表示当前平台
不可采集。

`collection_capacity` 保留英文 `event` 便于日志平台检索，正文按中文分为“任务、目标并发、配置、
发布队列、事件循环、进程、容器”七段，并自动给出 `空闲 / 正常 / 繁忙 / 需关注` 状态及中文提示。
不可采集的进程或 cgroup 数据显示为“不可用”，不再直接展示 `-1`。

### 配置采集日志约定

配置采集在生产 INFO 级别保留 Run 生命周期和有界失败样本，不记录凭据正文：

- `collection_run_started`：中文“任务开始”，优先记录 `instance_id`，缺失时才回退记录 `task_id`；
  同时包含 `plugin_ref`、`plugin_name`、`model_id`、目标数、凭据数和租约；
- `collection_progress`：Run 约每完成 10% 输出一条，最多约 11 条；包含插件、完成/活动/待处理数、
  最近完成目标、中文结果和最多 5 个活动目标样本；
- `target_collection_succeeded`：仅网络设备 SNMP 采集成功时，每个 IP 输出一条 INFO，包含凭据标识和
  单目标采集耗时（不记录凭据内容）；
- `collection_failure_samples`：存在失败时每个 Run 只输出一条 INFO，最多包含 3 个
  `target|failed_stage|error_code` 样本；协议无响应使用 `access_probe|protocol_no_response`，
  不伪装成插件代码异常，也不记录错误正文或凭据标识；
- `collection_run_summary`：中文“任务汇总”，包含总目标、采集成功/失败、不可达、延后处理、跳过、
  发布统计、总耗时、Top 8 聚合失败类型（其余合并为 `other`），以及最多 3 个脱敏失败样本；
- `plugin_exception`：插件执行、协议预检或插件内部捕获到的每个异常均记录，包含 `task_id`、
  `plugin_ref`、`model_id`、`plugin_name`、`target`、`error_type`、脱敏且有长度上限的
  `error_message`，以及有界 `call_chain` / `source_context`；不记录局部变量、请求头或凭据；
- `snmp_facts_collection_started`：SNMP 插件每次正式采集输出当前目标 IP 和任务、插件上下文；执行器
  不再重复输出通用的目标开始日志；
- `collection_run_terminal`：中文“任务结束”，包含中文终态和总耗时，同时保留稳定英文 `status`；
- `collection_capacity`：每 3 分钟输出中文容量快照，明确区分采集任务和目标任务，并展示目标的
  等待执行、正在执行、本轮已完成和容器启动后累计已完成数量，以及进程和容器资源；
- `result_publish_failed`：每个 Run 最多 3 个发布失败样本，只保留发布阶段、稳定原因和重试次数；
  完整发布错误计数与样本合并到 `collection_run_summary` 的中文“发布失败类型”、
  “发布失败样本”字段；
- `nats_metrics_publish_succeeded`：每个 NATS 指标发布分块成功后输出一条 INFO，包含任务、主题、
  成功行数、总行数和取消前跳过的行数；
- NATS、Redis、租约、发布终态等 WARNING/ERROR：保留单次失败诊断字段。

日志统一写 stdout，由日志平台按 `event`、`task_id`、`plugin_ref`、`model_id`、`target` 建立字段和
视图；不再创建 SNMP 专用日志文件。

常用本地检索：

```bash
rg 'task_id=<task-id>' stargazer.log
rg 'event=collection_run_(started|summary|terminal)' stargazer.log
rg 'event=collection_progress|event=collection_failure_samples' stargazer.log
rg 'event=plugin_exception' stargazer.log
rg 'event=snmp_facts_collection_started|target=<ip>' stargazer.log
rg 'event=collection_capacity' stargazer.log
```

## Host Remote

Host Remote 提交返回 `Deferred`。每个目标使用独立 callback ID；可信上下文包含父任务 ID、
目标、owner、fencing token、真实 `attempt_id`、Executor caller 和一次性 v2 token。回调先匹配
完整身份，再用单个 Lua 快照核对 Redis generation、latest-run tombstone 与可选 active run 的
fence、attempt 和 owner；该指针在 run 返回 `Deferred` 并完成薄租约后继续存在，latest-run 又在
每次 acquire 时原子推进，因此新 run 即使在创建首个 context 前结束也会让旧 generation 失败关闭。
首次保存 callback payload 时会再次原子核对三层身份，并移除 raw payload 中已消费的 token。
token 由独立环境密钥和不可变执行身份确定性 HMAC 派生，Redis 只存摘要。失败时不会 claim、
清 running 或启动处理。创建 callback context 的 Lua 同时核验当前 run 并保留首次身份，让同 task 重投幂等；失败
重投不删除共享 context，而由 1 小时 TTL / 300 秒 pre-accept sweeper 有界收敛。处理任务直接注册
在 Sanic 本地生命周期中，不再进入 ARQ。

滚动升级时 `HOST_REMOTE_CALLBACK_V2_ENABLED` 默认关闭；先升级并排空旧 Executor/context/retry，
再设置至少 32 字符的 `HOST_REMOTE_CALLBACK_TOKEN_SECRET` 并启用。旧 `remote-` callback 仅在
context TTL/deadline 内兼容，排空后可把 `HOST_REMOTE_CALLBACK_LEGACY_MAX_AGE_SECONDS` 设为 0。
回滚前先关闭 v2 新签发并排空 v2 context、执行任务及 Executor retry；无法排空时保留 v2 handler。

该 token 只阻断无法读取任务请求的盲伪造；共享 NATS 管理员仍能观察 token。最终信任根需用
独立服务身份和最小 subject ACL，或 Executor 独立签名完成，相关治理完成前 Issue #4280 保持开放。

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
