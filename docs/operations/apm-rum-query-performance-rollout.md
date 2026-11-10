# APM / RUM 查询性能改造上线调整说明

本文是这次上线的全量执行清单：新部署什么、重新打包哪些镜像、改哪些配置和环境变量、按什么顺序上线、
怎么验收和回滚。文中每一项都是确定要求，运维按本文执行，不做取舍。链接的规则文档只解释约束的来由。

对应代码：`master` 上的以下合并：RUM 会话结束记录、APM 策略合并查询、可观测聚合层、遗留问题收口、
聚合链路上线前加固（`observability-aggregate-hardening`）、APM `0006` 迁移修复，以及本文所在的上线复查修正。
打包以包含这些合并的 `master` 为准。

## 1. 调整总览

以下全部必须执行。

| 对象 | 调整 |
|---|---|
| 聚合库（单节点 VictoriaMetrics） | 新部署一套，开启基础认证，保留期 35 天，只走内网 |
| APM Collector 镜像 | `bklite/apm-otel-collector` 升到 `0.153.0-bklite.3`，区域、系统和聚合 Collector 共用 |
| APM 系统 Collector | 换成只写 VictoriaTraces 的 `system.yaml` |
| APM 聚合 Collector | 新进程，1 个副本。配置 `aggregate.yaml` + `aggregate-auth.yaml`，消费 `BKLITE_APM_AGGREGATE` |
| NATS 消费者 | 新建 durable consumer `BKLITE_APM_AGGREGATE` |
| RUM 镜像 | `bklite/rum-collector` 升到 `0.1.0-bklite.3`，网关、控制器、维护进程共用 |
| RUM 网关 | 配置 `rum.gateway.yaml` + `rum.gateway.auth.yaml`，新增聚合写入地址、分片值和认证 |
| RUM 维护进程 | 新增会话库地址和口令文件，保持单副本 |
| Server 环境变量 | 新增聚合库查询地址、认证和两个刷出间隔 |
| Server 数据库迁移 | `core/0001_aggregate_metric_origin`，随发布执行 |
| Celery Beat | 新增每分钟任务 `probe_aggregate_metric_origins`，走现有 `background` 队列，随发布生效 |
| 告警 | 第 7 节全部 9 条 |

不变的部分：

- Redis 实例与 ACL：新用到的键都在现有 `ops:rum:*` 授权内。
- NATS Stream `APM_TRACES`、VictoriaTraces、VictoriaLogs：配置不变。
- 监控用的 VictoriaMetrics（`VICTORIAMETRICS_HOST`）：不变，聚合数据不写进去。
- APM 策略合并查询：只改了 Server 内部查询方式，部署上没有变化。

## 2. 新部署聚合库

规则见 [聚合库运维规则](aggregate-metrics-store.md)，架构决定见
[ADR 0011](../adr/0011-apm-rum-aggregate-metrics-store.md)。

- 镜像：`victoriametrics/victoria-metrics:v1.106.1`，与验证环境相同。
- 一套独立的单节点：独立进程、独立数据目录、独立地址。不做集群，不按 APM/RUM 拆库。
- 只监听内网地址。不对浏览器、租户网络和公网开放。地址必须与 `VICTORIAMETRICS_HOST` 不同。
- 数据盘不小于 500 GiB（APM 典型约 76 GiB + RUM 约 161 GiB，按 2 倍预留），70% 告警时扩容。
- 开启基础认证。用户名和口令由运维生成，只从环境注入，同一组凭据发给 APM 聚合 Collector、RUM 网关和 Server。

启动参数：

```text
-storageDataPath=<独立数据目录>
-retentionPeriod=35d
-httpListenAddr=<内网 IP>:8428
-search.latencyOffset=0s
-envflag.enable
```

认证通过环境变量注入：`httpAuth_username=<用户名>`、`httpAuth_password=<口令>`（`-envflag.enable` 使
VictoriaMetrics 从这两个变量读取 `-httpAuth.username` / `-httpAuth.password`）。口令不写进命令行和仓库。

由此得到两个地址，后文统一引用：

- 写入地址：`http://<内网 IP>:8428/api/v1/write`
- 查询地址：`http://<内网 IP>:8428`

容量依据（35 天，60 秒样本间隔，约 1 字节/样本）：

| 产品 | 规模 | 序列数 | 磁盘 |
|---|---|---|---|
| APM | 每服务资源上限 500，资源缓存 1000。典型是 200 个服务 × 3 个环境 × 50 个入口操作 × 3 种状态 | 典型约 162 万；理论最坏 900 万 | 典型约 76 GiB；理论最坏约 422 GiB |
| RUM | 50 个应用 × 3 个环境 × 100 条路由 | 约 342 万 | 约 161 GiB |

理论最坏值 = 500 × 1000 × 18，只在所有服务都打满组合上限时出现；第 7 节的溢出告警会在接近前发出。

## 3. APM Collector

完整说明见 [deploy/apm/README.md](../../deploy/apm/README.md)。

### 3.1 打包镜像

```bash
cd deploy/apm/collector
make test
make build        # 产出 bklite/apm-otel-collector:0.153.0-bklite.3
make validate     # 用镜像校验 regional / system / aggregate（含认证）配置
```

核心版本是 OpenTelemetry Collector v0.153.0。`bklite.3` 比 `bklite.2` 多了 `routing` 组件，用
`/bklite-otelcol components` 核对。tag 固定，记录 digest，禁止 `latest`。部署用的 `.env` 和编排文件里
`APM_COLLECTOR_IMAGE` 必须指向 `bklite.3`。

区域、系统、聚合三种 Collector 共用这个镜像，一起升级。区域 Collector 配置不变，不写聚合库。

### 3.2 下发配置

镜像里不带配置，从 `deploy/apm/otel/` 挂载到容器内的 `/etc/bklite-apm/`。

| 文件 | 进程 | 用途 |
|---|---|---|
| `system.yaml` | 系统 Collector | 只写 VictoriaTraces |
| `aggregate.yaml` | 聚合 Collector | 入口聚合 |
| `aggregate-auth.yaml` | 聚合 Collector | 聚合库基础认证，作为第二个 `--config` 加载 |

启动参数：

```text
# 系统 Collector
/bklite-otelcol --config=/etc/bklite-apm/system.yaml
# 聚合 Collector
/bklite-otelcol --config=/etc/bklite-apm/aggregate.yaml --config=/etc/bklite-apm/aggregate-auth.yaml
```

切换严格按下面的顺序，在同一次变更里完成：

1. 新建消费者 `BKLITE_APM_AGGREGATE`（3.3）。聚合从这一刻开始计数。
2. 系统 Collector 换成 `bklite.3` 和新的 `system.yaml`。此后只有聚合 Collector 写聚合库。
3. 第 1 步之后 5 分钟内启动聚合 Collector。它从第 1 步的位置开始消费。

先换系统 Collector、后建消费者，中间这段调用链永远进不了聚合；第 3 步晚于 5 分钟，积压的 Span 会记成晚到，
不进请求数和错误率。

### 3.3 NATS 消费者

在聚合 Collector 启动前用下面的命令新建。已存在时不改写、不删除重建。

```text
nats consumer add APM_TRACES BKLITE_APM_AGGREGATE \
  --filter "apm.traces.>" --pull --deliver new --ack explicit \
  --wait 30s --max-deliver 3 --max-pending 256 --replay instant --defaults
```

| 参数 | 取值 | 原因 |
|---|---|---|
| `--deliver new` | 固定 | 不回放已有积压，否则积压会记成晚到 |
| `--wait` | `30s` | 聚合在内存里完成，30 秒足够；必须大于配置里的 `downstream_timeout` 20 秒 |
| `--max-deliver` | `3` | 只给进程崩溃时未 ACK 的消息重试两次 |

聚合 Collector 使用系统 Collector 的 NATS 账号。生产 NATS 中这个账号的权限必须与仓库
`deploy/apm/nats/nats-server.conf` 一致（对 `APM_TRACES.*` 通配授权）。新建后用该账号执行
`nats consumer info APM_TRACES BKLITE_APM_AGGREGATE`，必须成功。

Server 的健康探针只看 `BKLITE_APM_SYSTEM`，聚合消费者的积压由第 7 节的告警覆盖。

### 3.4 聚合 Collector 部署参数

1 个副本，容器内存上限 `640m`，CPU `1` 核。以下环境变量全部设置为表中的值：

| 变量 | 取值 |
|---|---|
| `APM_NATS_URL`、`APM_NATS_STREAM`、`APM_NATS_CREDENTIALS_FILE`、`APM_NATS_CA_FILE`、`APM_NATS_CERT_FILE`、`APM_NATS_KEY_FILE`、`APM_NATS_TLS_SERVER_NAME` | 与系统 Collector 完全相同 |
| `APM_NATS_CONSUMER` | `BKLITE_APM_AGGREGATE` |
| `APM_NATS_MAX_ACK_PENDING` | `256` |
| `AGG_VICTORIAMETRICS_WRITE_URL` | 第 2 节的写入地址 |
| `AGG_VICTORIAMETRICS_USER` / `AGG_VICTORIAMETRICS_PASSWORD` | 第 2 节的认证凭据，从环境注入 |
| `APM_AGG_SHARD` | `apm-agg-0` |
| `APM_AGG_FLUSH_INTERVAL` | `60s` |
| `APM_AGG_CARDINALITY_LIMIT` | `500`（每个服务资源，即命名空间 + 服务名 + 环境） |
| `APM_AGG_SERIES_EXPIRATION` | `1h` |
| `APM_COLLECTOR_MEMORY_LIMIT_MIB` | `512` |
| `APM_COLLECTOR_MEMORY_SPIKE_MIB` | `128` |

内存依据容量压测里约 236 MiB 的聚合堆；软拒绝线 384 MiB。系统 Collector 保持原来的 384 / 96 MiB 与 512 MiB 容器上限。

聚合相关变量只配在聚合 Collector 上。写入地址或分片值为空时，聚合 Collector 启动失败
（`invalid endpoint` / `external labels configuration contains an empty key or value`），不影响明细入库。
不得把写入地址填成 `VICTORIAMETRICS_HOST` 或占位地址。

## 4. RUM 网关、控制器、维护进程

RUM 部署全文见 [deploy/rum/OPS-DEPLOY.md](../../deploy/rum/OPS-DEPLOY.md)。

### 4.1 打包镜像

```bash
cd deploy/rum/collector
make test
make image        # 产出 bklite/rum-collector:0.1.0-bklite.3
```

构建参数、镜像内容和运行用户见 OPS-DEPLOY 第 1 节。网关、控制器、维护进程共用这个镜像，一起升级。
tag 固定，记录 digest。

### 4.2 网关

启动参数：

```text
/usr/local/bin/bklite-rum-gateway \
  --config=/etc/bklite-rum/rum.gateway.yaml \
  --config=/etc/bklite-rum/rum.gateway.auth.yaml
```

新增环境变量，全部设置为表中的值：

| 变量 | 取值 |
|---|---|
| `AGG_VICTORIAMETRICS_WRITE_URL` | 第 2 节的写入地址 |
| `AGG_VICTORIAMETRICS_USER` / `AGG_VICTORIAMETRICS_PASSWORD` | 第 2 节的认证凭据，从环境注入 |
| `RUM_AGG_SHARD` | `rum-gw-<副本序号>`，从 0 起。每个副本不同，重启不变；不用 Pod 名或随机 ID |
| `RUM_AGG_BATCH_TIMEOUT` | `60s` |
| `RUM_AGG_MAX_STREAMS` | `420000` |

写入地址或 `RUM_AGG_SHARD` 为空时，整个网关起不来，VictoriaLogs 入库也一起停。所以网关升级前，
第 2 节的聚合库必须已经就绪，变量必须已经注入。

聚合路由准入复用会话 Redis，不需要新的 Redis 或 ACL：

- 每个应用最多 100 条路由，其余记为「其他」。
- Redis 调用失败后熔断 5 秒，期间未缓存的路由记为「其他」，不再访问 Redis。
- 第一次失败立即打一条 WARN；同一 5 秒内的其余失败，在窗口结束后的下一次路由处理或进程关闭时汇总成一条。
- 本地溢出缓存最多 1024 条，请求经过时清掉过期项。

### 4.3 维护进程（会话结束记录）

启动参数新增两项。会话库地址与网关的 `RUM_SESSION_REDIS_URL` 完全相同；口令文件使用维护进程已有的
`rum_maintainer_redis_password`，不新建文件：

```text
-session-redis-url=redis://<redis>:6379/1
-session-redis-password-file=/run/secrets/rum_maintainer_redis_password
```

- **只运行一个副本。** 会话扫描没有选主，第二个副本会把同一条会话重复写一遍。
- 维护进程每分钟把空闲满 15 分钟、或开始满 4 小时的会话写成一条 `session_end` 记录，写进 RUM 的 VictoriaLogs。
- 网关和维护进程在同一次变更里一起升级。

## 5. Server

### 5.1 环境变量

以下变量必须在 Server 的部署环境中添加（它们不在 Server 的环境变量模板里），全部设置为表中的值：

| 变量 | 取值 |
|---|---|
| `AGG_VICTORIAMETRICS_QUERY_URL` | 第 2 节的查询地址。不带 `/api/v1/write`，不得填 `VICTORIAMETRICS_HOST` |
| `AGG_VICTORIAMETRICS_USER` / `AGG_VICTORIAMETRICS_PASSWORD` | 第 2 节的认证凭据，从环境注入 |
| `APM_AGG_FLUSH_INTERVAL` | `60s`，与 APM 聚合 Collector 相同 |
| `RUM_AGG_BATCH_TIMEOUT` | `60s`，与 RUM 网关相同 |

两个刷出间隔必须与采集端一致。Server 按它们把查询结束时间留出一个刷出周期，不一致时窗口末尾会少算。

`AGG_VICTORIAMETRICS_QUERY_URL` 在第 6 节第 5 步才配置。Server 启动和 `batch_init` 都不连接聚合库，
聚合库故障不影响 Server 启动。

### 5.2 随发布生效

- 数据库迁移 `core/0001_aggregate_metric_origin`：在现有 `migrate` 流程里执行，只新增一张表。
- Celery Beat 任务 `apps.core.tasks.aggregate_origin.probe_aggregate_metric_origins`：每分钟一次，
  走现有 `background` 队列，不新增 Worker。它记下 APM 和 RUM 聚合数据最早出现的时刻（聚合起点），
  记下后不再探测。

### 5.3 上线后的读取行为

- 查询窗口在聚合起点之后：APM 首页与服务 RED、可用性 SLO，RUM 目录、概览、页面列表、
  Web Vitals 告警读聚合库。
- 窗口早于聚合起点：继续读 VictoriaTraces / VictoriaLogs 明细，上线前后的数字连续。
- 聚合库故障：对应区块显示「—」或「加载失败」，不显示 0，也不改去扫明细库；页面其他部分正常。
- 会话列表和会话数：第一条会话结束记录出现之前的窗口，仍按原始事件统计，不做历史回补，也没有空档。
- 聚合数据比实时晚 60 到 120 秒（一个刷出周期加对齐到整分钟）。

## 6. 上线顺序

1. 部署聚合库（第 2 节），配好第 7 节的告警。
2. 发布 Server（自动执行迁移和新 Beat 任务）。配好第 5.1 节除 `AGG_VICTORIAMETRICS_QUERY_URL` 以外的变量，
   此时页面行为与原来一致。
3. 升级 RUM 网关、控制器、维护进程到 `bklite.3`（第 4 节）。
4. 升级 APM 区域、系统和聚合 Collector 到 `bklite.3`，严格按 3.2 的顺序：新建 `BKLITE_APM_AGGREGATE`，
   切换系统 Collector，5 分钟内启动聚合 Collector。
5. 在聚合库查到 `apm_calls_total` 和 `rum_views_total` 序列后，给 Server 配上 `AGG_VICTORIAMETRICS_QUERY_URL`
   并重启。约一分钟后聚合起点记录下来，此后的窗口开始读聚合库。

## 7. 告警

以下 9 条全部配置。

| 对象 | 条件 | 处理 |
|---|---|---|
| 聚合库数据盘 | 使用率 70% 告警，85% 严重 | 扩容数据盘 |
| 聚合库活跃序列 | 相对本环境上线后一周的稳定基线上涨 50%，且没有对应上线或维度变更 | 查是哪个服务或应用的序列在涨 |
| APM 溢出序列 | `count(apm_calls_total{otel_metric_overflow="true"}) > 0` | 用 `job`（命名空间/服务名）定位服务，让该服务修正 Span 命名，去掉原始路径和 ID。不改 Server 查询 |
| 聚合写入失败 | APM 聚合 Collector、RUM 网关的 `otelcol_exporter_send_failed_metric_points` 增长 | 恢复聚合库或网络。聚合写入没有队列，不看 `enqueue_failed` |
| APM 聚合 Collector | 健康检查失败 | 拉起进程；超过 5 分钟的积压会记成晚到 |
| APM 聚合消费者积压 | `BKLITE_APM_AGGREGATE` 的待投递消息数（`num_pending`）连续 5 分钟增长 | 查聚合 Collector 是否卡住或资源不足 |
| APM 晚到计数 | `increase(apm_aggregate_late_spans_total[5m])` 超过上线后一周基线的 3 倍 | 聚合 Collector 停过或消费跟不上，按上两条处理 |
| RUM 流上限 | 网关 `otelcol_deltatocumulative_datapoints{error="limit"}` 增长 | 查应用和路由数量是否超出容量规模 |
| RUM 会话记录丢失 | 维护进程 `core_rum_session_end_records_lost_total` 增长 | 查维护进程日志和 VictoriaLogs 写入 |

处理 remote write 告警时，不得把导出失败退回 JetStream 或 RUM 接收接口，那样会造成明细重复入库或接收失败。

## 8. 验收

逐条见 [聚合库运维规则第 10 节](aggregate-metrics-store.md#10-验收清单)。上线后必须核对：

1. 聚合库地址与 `VICTORIAMETRICS_HOST` 不同；监控策略扫描读不到 `apm_`、`rum_` 序列。
2. 不带认证访问聚合库返回 401。
3. 聚合库里有 `apm_calls_total`、`apm_duration_milliseconds_*`、`rum_views_total`、
   `rum_js_errors_total`、`rum_web_vital_*` 序列，带 `shard` 标签，取值为 `apm-agg-0` 和 `rum-gw-*`。
4. 序列标签里没有用户、会话、原始 URL、查询串、SQL、`trace_id`、`span_id`、Pod 名或随机实例标识；
   APM 序列上没有 `collector.instance.id` 和 `instance`。
5. `nats consumer info APM_TRACES BKLITE_APM_AGGREGATE` 的待投递消息数稳定在低位，不持续增长。
6. 停掉聚合库：调用链仍进入 VictoriaTraces，RUM 事件仍进入 VictoriaLogs；Server 正常启动；
   读聚合的区块显示降级，不显示 0。恢复后数据自动续上。
7. Server 的 `AggregateMetricOrigin` 表里有 apm、rum 两条起点记录。
8. RUM 的 VictoriaLogs 中出现 `rum.event.type:session_end` 记录，
   `core_rum_session_end_records_lost_total` 为 0。

## 9. 回滚

按下表分层回退，明细入库始终不受影响：

| 回退对象 | 做法 |
|---|---|
| Server 读聚合 | 去掉 `AGG_VICTORIAMETRICS_QUERY_URL` 后重启，页面全部回到读明细 |
| APM 聚合写入 | 停掉聚合 Collector。系统 Collector 继续用 `system.yaml` 写 VictoriaTraces |
| RUM 聚合写入 | 网关改为只加载 `--config=/etc/bklite-rum/rum.gateway.ingest.yaml` 后重启 |
| 镜像 | 回到上一个已验收的 digest，同时停掉聚合 Collector，换回该版本的系统 Collector 配置 |

迁移 `core/0001_aggregate_metric_origin` 只新增一张表，回滚 Server 版本时不回退迁移。

## 10. 常见问题

- **聚合 Collector 起不来，日志 `unknown type: "routing"`：** 镜像不是 `bklite.3`。检查部署用的 `.env`
  和编排文件里的 `APM_COLLECTOR_IMAGE`。
- **聚合 Collector 或 RUM 网关起不来，报 `invalid endpoint` 或 external labels 为空：**
  写入地址或分片值没注入。补在聚合 Collector 或网关上。系统 Collector 不需要这两个变量。
- **聚合写入报 401：** 写入端的 `AGG_VICTORIAMETRICS_USER` / `AGG_VICTORIAMETRICS_PASSWORD` 与聚合库不一致，
  或聚合 Collector 没有加载 `aggregate-auth.yaml`、网关没有加载 `rum.gateway.auth.yaml`。
- **页面数字是「—」：** 窗口内聚合库没有样本，或聚合库不可用。先看聚合库和聚合写入失败告警。
- **会话被重复统计：** 维护进程跑了多个副本，缩回 1 个。
