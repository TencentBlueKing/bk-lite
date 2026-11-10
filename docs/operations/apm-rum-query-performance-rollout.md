# APM / RUM 查询性能改造上线调整说明

本文是给运维的一份全量调整清单：这次上线要新部署什么、重新打包哪些镜像、改哪些配置和
环境变量、按什么顺序上线、怎么验收和回滚。细则以文中链接的规则文档为准；本文与细则冲突时，
以细则为准。

对应代码：`master` 上的合并提交 `efc28fb228` 及其之前的四个需求合并
（RUM 会话结束记录、APM 策略合并查询、可观测聚合层、遗留问题收口）。

## 1. 调整总览

| 对象 | 调整 | 必须/可选 |
|---|---|---|
| 聚合库（单节点 VictoriaMetrics） | 新部署一套，保留期 ≥ 35 天，只走内网 | 必须（读聚合前） |
| APM Collector 镜像 | `bklite/apm-otel-collector` 升到 `0.153.0-bklite.2`，区域和系统 Collector 共用 | 必须 |
| APM 系统 Collector 配置 | 下发新的 `system.yaml`，并带上 `system-traces.yaml`、`system-auth.yaml` | 必须 |
| APM 系统 Collector 环境变量 | 新增聚合写入地址、分片值 | 必须（挂 `system.yaml` 时） |
| RUM 镜像 | `bklite/rum-collector` 升到 `0.1.0-bklite.2`，网关、控制器、维护进程共用 | 必须 |
| RUM 网关环境变量 | 新增聚合写入地址、分片值 | 必须（挂 `rum.gateway.yaml` 时） |
| RUM 维护进程启动参数 | 新增会话库地址和口令文件；只能单副本 | 必须 |
| Server 环境变量 | 新增聚合库查询地址 | 可选（不配则全部读明细） |
| Server 数据库迁移 | `core/0001_aggregate_metric_origin` | 随发布自动执行 |
| Celery Beat | 新增每分钟任务 `probe_aggregate_metric_origins`，走现有 `background` 队列 | 随发布自动生效 |
| 告警 | 聚合库磁盘、活跃序列、remote write 失败；RUM 会话记录丢失 | 必须 |

不需要调整的部分：

- Redis ACL：新用到的键都在现有 `ops:rum:*` 授权内。
- NATS、JetStream Stream/Consumer、VictoriaTraces、VictoriaLogs：保持不变。
- 监控用的 VictoriaMetrics（`VICTORIAMETRICS_HOST`）：保持不变，聚合数据不写进去。
- APM 策略合并查询：只改了 Server 内部查询方式，部署上没有变化。

## 2. 新部署聚合库

规则全文见 [聚合库运维规则](aggregate-metrics-store.md)，架构决定见
[ADR 0011](../adr/0011-apm-rum-aggregate-metrics-store.md)。必须满足：

- 一套独立的单节点 VictoriaMetrics：独立进程、独立数据目录、独立地址。不做集群，不按 APM/RUM 拆库。
- 保留期不低于 35 天，例如 `-retentionPeriod=35d`。
- 地址和 `VICTORIAMETRICS_HOST` 必须不同，任何组件都不得回落到监控库。
- 只走内网。查询端口不对浏览器和租户网络开放。
- 基础认证可选。启用时，聚合库、APM 系统 Collector、RUM 网关、Server 用同一组用户名和口令，
  口令只从环境注入。

容量参考（35 天上限估算，按 60 秒样本间隔、约 1 字节/样本，实际以压测为准）：

| 产品 | 估算规模 | 序列数 | 磁盘 |
|---|---|---|---|
| APM | 200 个服务 × 50 个入口操作 × 3 个环境 | 约 162 万 | 约 76 GiB |
| RUM | 50 个应用 × 3 个环境 × 100 条路由 | 约 342 万 | 约 161 GiB |

## 3. APM Collector

APM 数据面的完整说明见 [deploy/apm/README.md](../../deploy/apm/README.md)。

### 3.1 打包镜像

```bash
cd deploy/apm/collector
make test
make build        # 产出 bklite/apm-otel-collector:0.153.0-bklite.2
make validate     # 用镜像校验 regional / system / system-traces 配置
```

核心版本仍是 OpenTelemetry Collector v0.153.0。新镜像比 `bklite.1` 多了聚合组件
（`span_metrics`、`count`、`filter`、`transform`、`deltatocumulative`、`prometheusremotewrite`、
`basicauth`），可用 `/bklite-otelcol components` 核对。tag 固定，记录 digest，禁止 `latest`。

区域 Collector 和系统 Collector 共用这个镜像，要一起升级。区域 Collector 的配置不变，也不写聚合库。

### 3.2 下发配置

镜像里不带配置。配置从 `deploy/apm/otel/` 挂载到容器内的 `/etc/bklite-apm/`，
这次要一起下发三份系统 Collector 配置：

| 文件 | 用途 |
|---|---|
| `system.yaml` | 正式配置：调用链明细 + 入口聚合 |
| `system-traces.yaml` | 只有调用链明细，不带聚合分支。聚合库未就绪或回退时用 |
| `system-auth.yaml` | 聚合库启用基础认证时，作为第二个 `--config` 追加 |

注意：不能让旧镜像（`bklite.1`）加载新的 `system.yaml`，否则会报 `unknown type: "count"`，
容器起不来。如果配置文件是直接挂载的，换配置和换镜像必须在同一次变更里完成。

### 3.3 系统 Collector 环境变量

| 变量 | 内容 |
|---|---|
| `AGG_VICTORIAMETRICS_WRITE_URL` | 聚合库的 remote write 地址，路径通常是 `/api/v1/write` |
| `APM_AGG_SHARD` | 这个进程固定的分片值。每个副本各不相同，重启不变。不要用 Pod 名或随机 ID，有状态副本序号可以 |
| `AGG_VICTORIAMETRICS_USER` / `AGG_VICTORIAMETRICS_PASSWORD` | 可选。要么都设、要么都不设；都设时追加 `system-auth.yaml` |
| `APM_AGG_FLUSH_INTERVAL` | 可选，默认 `60s`。缩短后磁盘按比例增加 |
| `APM_AGG_CARDINALITY_LIMIT` | 可选，默认 `90000` |

启动参数：

```text
# 正式
/bklite-otelcol --config=/etc/bklite-apm/system.yaml
# 启用基础认证
/bklite-otelcol --config=/etc/bklite-apm/system.yaml --config=/etc/bklite-apm/system-auth.yaml
# 聚合库未就绪，只保明细
/bklite-otelcol --config=/etc/bklite-apm/system-traces.yaml
```

**高风险：** 挂 `system.yaml` 时，只要写入地址或 `APM_AGG_SHARD` 有一个为空，整个系统 Collector
都起不来（`invalid endpoint` / `external labels configuration contains an empty key or value`），
调用链明细入库也会一起停。聚合库还没就绪时，先挂 `system-traces.yaml`。

## 4. RUM 网关、控制器、维护进程

RUM 部署全文见 [deploy/rum/OPS-DEPLOY.md](../../deploy/rum/OPS-DEPLOY.md)。

### 4.1 打包镜像

```bash
cd deploy/rum/collector
make test
make image        # 产出 bklite/rum-collector:0.1.0-bklite.2
```

构建参数、镜像内容和运行用户见 OPS-DEPLOY 第 1 节。镜像内置三份网关配置：
`/etc/bklite-rum/rum.gateway.yaml`（明细 + 聚合）、`rum.gateway.ingest.yaml`（只有明细）、
`rum.gateway.auth.yaml`（基础认证）。网关、控制器、维护进程三个进程用同一个镜像，一起升级。

### 4.2 网关

新增环境变量：

| 变量 | 内容 |
|---|---|
| `AGG_VICTORIAMETRICS_WRITE_URL` | 聚合库的 remote write 地址 |
| `RUM_AGG_SHARD` | 这个网关进程固定的分片值：1 到 64 位，只含字母、数字和 `.` `_` `:` `-`。每个副本各不相同，重启不变 |
| `RUM_AGG_BATCH_TIMEOUT` | 可选，默认 `10s` |
| `RUM_AGG_MAX_STREAMS` | 可选，默认 `420000` |
| `AGG_VICTORIAMETRICS_USER` / `AGG_VICTORIAMETRICS_PASSWORD` | 可选。都设时才追加 `--config=/etc/bklite-rum/rum.gateway.auth.yaml`；口令为空时不要加载 |

**高风险：** 挂 `rum.gateway.yaml` 时，写入地址或 `RUM_AGG_SHARD` 为空，整个网关起不来，
VictoriaLogs 入库也会一起停。聚合库还没就绪时，改挂 `rum.gateway.ingest.yaml`。

聚合路由准入复用会话 Redis：每个应用最多 100 条路由，其余记为「其他」。不需要新的 Redis 或 ACL。

### 4.3 维护进程（会话结束记录）

启动参数新增两项，指向会话库（和网关 `RUM_SESSION_REDIS_URL` 同一个 DB，默认 1）：

```text
-session-redis-url=redis://<redis>:6379/1
-session-redis-password-file=/run/secrets/rum_maintainer_redis_password
```

口令文件可以和维护进程原有的那份共用。

- **只运行一个副本。** 会话扫描没有选主，第二个副本会把同一条会话重复写一遍。
- 维护进程每分钟把空闲满 15 分钟、或开始满 4 小时的会话写成一条 `session_end` 记录，
  写进 RUM 的 VictoriaLogs。
- 新指标 `core_rum_session_end_records_lost_total` 正常为 0，增长说明有会话记录丢失，需要告警。
- 网关和维护进程要在同一次变更里一起升级。

## 5. Server

### 5.1 环境变量（可选）

| 变量 | 内容 |
|---|---|
| `AGG_VICTORIAMETRICS_QUERY_URL` | 同一套聚合库的内网查询入口。不要带 `/api/v1/write`，不要填成 `VICTORIAMETRICS_HOST` |
| `AGG_VICTORIAMETRICS_USER` / `AGG_VICTORIAMETRICS_PASSWORD` | 启用基础认证时设置 |

这几个变量目前不在 Server 的环境变量模板里，要在 Server 的部署环境中手动添加。

不配查询地址时，Server 照常启动，页面全部按原来的方式读明细。Server 启动和 `batch_init`
都不连接聚合库，聚合库故障也不影响 Server 启动。

### 5.2 随发布自动生效

- 数据库迁移 `core/0001_aggregate_metric_origin`：在现有 `migrate` 流程里执行。
- Celery Beat 任务 `apps.core.tasks.aggregate_origin.probe_aggregate_metric_origins`：每分钟一次，
  走现有 `background` 队列，不需要新增 Worker。它记下 APM 和 RUM 聚合数据最早出现的时刻
  （聚合起点），记下后不再重复探测。

### 5.3 上线后的读取行为

- 查询窗口在聚合起点之后：APM 首页与服务 RED、可用性 SLO，RUM 目录、概览、页面列表、
  Web Vitals 告警读聚合库。
- 窗口早于聚合起点：继续读 VictoriaTraces / VictoriaLogs 明细，上线前后的数字连续。
- 聚合库故障：对应区块显示「—」或「加载失败」，不显示 0，也不改去扫明细库；页面其他部分正常。
- 会话列表和会话数：第一条会话结束记录出现之前的窗口，仍按原始事件统计，不做历史回补，也没有空档。

## 6. 上线顺序

1. 部署聚合库，配好保留期、内网访问和第 7 节的告警。
2. 发布 Server（自动执行迁移和新 Beat 任务）。先不配 `AGG_VICTORIAMETRICS_QUERY_URL`，行为与原来一致。
3. 升级 RUM 网关、控制器、维护进程到 `bklite.2`：网关配写入地址和分片值，维护进程加会话库参数。
4. 升级 APM 区域和系统 Collector 到 `bklite.2`，同时下发新配置；系统 Collector 配写入地址和分片值。
5. 确认聚合库里已有 `apm_calls_total` 和 `rum_views_total` 序列后，给 Server 配上
   `AGG_VICTORIAMETRICS_QUERY_URL` 并重启。约一分钟后聚合起点记录下来，此后的窗口开始读聚合库。

第 3、4 步如果聚合库还没就绪，可以先分别挂 `rum.gateway.ingest.yaml`、`system-traces.yaml`，
等聚合库就绪后再切到正式配置。

## 7. 告警

| 对象 | 条件 |
|---|---|
| 聚合库数据盘 | 使用率 70% 告警，85% 严重 |
| 聚合库活跃序列 | 相对本环境稳定基线异常上涨，且没有对应上线或维度变更 |
| APM 系统 Collector、RUM 网关 | `otelcol_exporter_send_failed_metric_points` 出现即告警。聚合写入关闭了队列，不要看 `enqueue_failed` |
| RUM 网关 | `otelcol_deltatocumulative_datapoints{error="limit"}` 增长，说明超出流上限 |
| RUM 维护进程 | `core_rum_session_end_records_lost_total` 增长 |

remote write 告警的处理方式是恢复聚合库或网络。不要为了清告警，把导出失败退回 JetStream
或 RUM 接收接口，那样会造成明细重复入库或接收失败。

## 8. 验收

逐条见 [聚合库运维规则第 10 节](aggregate-metrics-store.md#10-验收清单)。上线后至少核对：

1. 聚合库地址与 `VICTORIAMETRICS_HOST` 不同；监控策略扫描读不到 `apm_`、`rum_` 序列。
2. 聚合库里有 `apm_calls_total`、`apm_duration_milliseconds_*`、`rum_views_total`、
   `rum_js_errors_total`、`rum_web_vital_*` 序列，带 `shard` 标签。
3. 序列标签里没有用户、会话、原始 URL、查询串、SQL、`trace_id`、`span_id`、Pod 名或随机实例标识；
   APM 序列上没有 `collector.instance.id` 和 `instance`。
4. 停掉聚合库：调用链仍进入 VictoriaTraces，RUM 事件仍进入 VictoriaLogs；Server 正常启动；
   读聚合的区块显示降级，不显示 0。恢复后数据自动续上。
5. Server 的 `AggregateMetricOrigin` 表里有 apm、rum 两条起点记录。
6. RUM 的 VictoriaLogs 中出现 `rum.event.type:session_end` 记录，
   `core_rum_session_end_records_lost_total` 为 0。

## 9. 回滚

可以分层回退，明细入库始终不受影响：

| 要回退的部分 | 做法 |
|---|---|
| Server 读聚合 | 去掉 `AGG_VICTORIAMETRICS_QUERY_URL` 后重启，页面全部回到读明细 |
| APM 聚合写入 | 系统 Collector 改挂 `system-traces.yaml` 后重启 |
| RUM 聚合写入 | 网关改挂 `rum.gateway.ingest.yaml` 后重启 |
| 镜像 | 回到上一个已验收的 digest。回退到 `bklite.1` 时，APM 配置也要同时换回旧版 `system.yaml` |

迁移 `core/0001_aggregate_metric_origin` 只新增一张表，回滚 Server 版本时不用回退迁移。

## 10. 常见问题

- **系统 Collector 健康检查失败，日志 `unknown type: "count"`：** 镜像还是 `bklite.1`，
  配置已经是新的 `system.yaml`。把镜像换成 `bklite.2`。检查部署用的 `.env` 有没有把
  `APM_COLLECTOR_IMAGE` 固定在旧 tag。
- **系统 Collector 或 RUM 网关起不来，报 `invalid endpoint` 或 external labels 为空：**
  写入地址或分片值没注入。补上，或者先改挂只有明细的配置。
- **页面数字是「—」：** 窗口内聚合库没有样本，或聚合库不可用。先看聚合库和写入端的 remote write 告警。
- **会话被重复统计：** 检查维护进程是不是跑了多个副本。
