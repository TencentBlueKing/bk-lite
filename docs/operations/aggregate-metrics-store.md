# APM / RUM 聚合库运维规则

本文是给运维的部署与验收规则。研发锁死聚合库的用途、保留期、地址、写入方式和合格判定。
生产进程怎么编排、镜像怎么进入仓库、告警接到哪条渠道，由运维自己的流水线决定。
这和 [APM 数据面契约夹具](../../deploy/apm/README.md) 一样：契约硬，编排软。

研发不提供生产 Compose 或 Helm。运维调整自己的流水线，重新打包 APM Collector
和 RUM 网关两个产品镜像，并部署下面这套库。APM 镜像同时跑区域、系统和聚合三个进程。架构决定见
[ADR 0011](../adr/0011-apm-rum-aggregate-metrics-store.md)。调用链传输的其余决定仍以
[ADR 0006](../adr/0006-apm-regional-nats-victoriatraces-pipeline.md) 为准。

APM 聚合由独立进程承担，配置是 `deploy/apm/otel/aggregate.yaml`。系统 Collector 的
`deploy/apm/otel/system.yaml` 只写 VictoriaTraces。发行版核心版本仍是 v0.153.0，镜像标签是
`0.153.0-bklite.3`。RUM 网关的
`deploy/rum/collector/otel/rum.gateway.yaml` 已经包含浏览、JS 错误和 Web Vitals 聚合流水线。
发行版核心版本仍是 v0.154.0，镜像标签是 `0.1.0-bklite.3`。本文不表示聚合库已经在生产部署；
运维按本文重新打包镜像并部署聚合库。

## 1. 用途与边界

聚合库是一套独立的单节点 VictoriaMetrics。它只保存 APM 和 RUM 的累计计数器与累计直方图。

调用链明细仍在 VictoriaTraces。RUM 事件明细仍在 VictoriaLogs。聚合库不保存 Span 正文、
RUM 原始事件、会话或回放。会话数、错误会话、国家、设备和版本分布继续读 VictoriaLogs。

准备改读聚合库的是这些结果：APM 的入口 RED 与可用性 SLO；RUM 的浏览次数、JS 错误次数
和 Web Vitals。策略、慢请求、Apdex、延迟 SLO、下钻和拓扑仍以 VictoriaTraces 为准。
读取代码的落地范围见[聚合层变更](../../specs/changes/observability-aggregate-metrics/spec.md)。

聚合库停掉或连不上时，VictoriaTraces 和 VictoriaLogs 照常入库。读聚合层的页面显示降级
或缺数据，不把缺数据展示成 0，也不在故障时改去扫描明细库。只有查询窗口的起点早于聚合
开始时间，才回退到原来的明细查询。页面上的降级和回退随 Server 读取 ticket 落地后核对。
在那之前，运维先保证停库不影响明细入库，也不影响 Server 启动。

Monitor 和 CMDB 继续使用自己的 VictoriaMetrics。聚合序列不写入那套库。监控策略扫描
读不到 `apm_` 和 `rum_` 序列。

## 2. 部署硬约束

必须满足下面几条。用哪种进程管理、怎样打包镜像、告警规则写在哪套系统，由运维选择。

- 独立进程、独立数据目录、独立地址，并且只部署一个节点。这一期不做集群，不用
  AccountID 多租户，也不按 APM 和 RUM 拆成两个库或两套保留期。
- 整库保留期不低于 35 天。单节点常用参数是 `-retentionPeriod=35d` 或更长，以所部署
  版本的参数名为准。35 天用来盖住 30 天和自然月的可用性 SLO。
- 写入和查询只走内网。聚合库没有公网入口，查询端口也不对浏览器或租户网络开放。
- 写入地址和查询地址都使用第 3 节的变量。这些变量不读取、不复用 `VICTORIAMETRICS_HOST`。
  聚合库地址和监控库地址必须不同。
- 生产必须开启基础认证（参数见上线说明第 2 节）。聚合库、两个写入进程和 Server 使用同一组用户名和口令。
  认证不能代替内网边界。
- 用户名和口令只从环境注入。不写入 Git、镜像层、工单或日志。

调用链明细库的磁盘和保留期另见 [APM 容量说明](../../deploy/apm/CAPACITY.md)。
那份数字不包括聚合库。

## 3. 环境变量

| 变量 | 使用进程 | 填写内容 |
|---|---|---|
| `AGG_VICTORIAMETRICS_WRITE_URL` | APM 聚合 Collector、RUM 网关 | 聚合库的 remote write 地址 |
| `AGG_VICTORIAMETRICS_QUERY_URL` | Server | 同一套聚合库的查询入口 |
| `AGG_VICTORIAMETRICS_USER` | APM 聚合 Collector、RUM 网关、Server，仅在启用基础认证时 | 基础认证用户名 |
| `AGG_VICTORIAMETRICS_PASSWORD` | APM 聚合 Collector、RUM 网关、Server，仅在启用基础认证时 | 基础认证口令 |
| `APM_AGG_SHARD` | 每一个 APM 聚合 Collector 写入进程 | 该进程固定的分片值 |
| `APM_AGG_NATS_ACK_WAIT` | APM 聚合消费者，可选 | ACK 等待。留空时用 `30s` |
| `APM_AGG_NATS_MAX_DELIVER` | APM 聚合消费者，可选 | 重投上限。留空时用 `3` |
| `APM_AGG_CARDINALITY_LIMIT` | APM 聚合 Collector，可选 | 每个服务资源的组合上限。留空时用 `500`。不是全局上限 |
| `APM_AGG_SERIES_EXPIRATION` | APM 聚合 Collector，可选 | 单条序列无新 Span 后从进程内存删除。留空时用 `1h` |
| `RUM_AGG_SHARD` | 每一个 RUM 网关写入进程 | 该进程固定的分片值 |
| `APM_AGG_FLUSH_INTERVAL` | APM 聚合 Collector 与 Server，可选 | 聚合指标刷出间隔。留空时用 `60s`。改这个值必须同时改采集端和 Server |
| `RUM_AGG_BATCH_TIMEOUT` | RUM 网关与 Server，可选 | 聚合指标刷出间隔。留空时用 `60s`，缩短后磁盘按比例增加。改这个值必须同时改采集端和 Server |
| `RUM_AGG_MAX_STREAMS` | RUM 网关，可选 | `deltatocumulative` 流上限。留空时用 `420000`。超出的样本记在网关指标 `otelcol_deltatocumulative_datapoints`，属性 `error=limit` |

`AGG_VICTORIAMETRICS_WRITE_URL` 填写内网 remote write 地址，路径通常是
`/api/v1/write`，主机写成实际内网名字，不要写进仓库。APM 侧只配在聚合 Collector 上。
区域 Collector 仍然只发布调用链，系统 Collector 只写 VictoriaTraces，两者都不写聚合库。

`AGG_VICTORIAMETRICS_QUERY_URL` 填写同一套库的内网查询入口，不要带 remote write 路径，
也不要填成 `VICTORIAMETRICS_HOST`。Server 读取客户端落地时如果要收紧路径，再核对这一格。
未设置查询地址表示 Server 侧聚合层不可用，进程继续启动。

两个认证变量要么一起设置，要么一起留空。留空表示不发送基础认证。写入进程、Server
和聚合库自己的认证配置使用同一组值。

`APM_AGG_CARDINALITY_LIMIT` 作用在每一个服务资源上。服务资源是 `service.namespace`、
`service.name`、`deployment.environment` 这一组，不是全部服务加在一起。同一服务的多个实例共用这一组的
500 个组合名额；不同环境各自再有 500。`APM_AGG_SERIES_EXPIRATION` 只让一条序列过期，不删除整个服务资源。
资源缓存上限写死为 1000，没有单独的开关。

`APM_AGG_FLUSH_INTERVAL` 和 `RUM_AGG_BATCH_TIMEOUT` 同时给采集端和 Server 用。采集端按它刷出，
Server 按它把查询结束时间留出一个周期。改其中一个值必须两边一起改，只改采集端时窗口末尾会少算。
Server 遇到非法或非正值时回落默认 60 秒，并记一条 WARN，不记录原始值。

`APM_AGG_SHARD` 和 `RUM_AGG_SHARD` 各表示一个写入进程的身份。每个会执行 remote write
的进程取一个值，所有这类进程的值互不相同，包括同一产品的多个副本。值写在部署配置里，
进程重启后保持不变。不要用每次启动都会变的 Pod 名，也不要在进程里临时生成随机 UUID。
有状态副本的固定序号可以充当这个值。

RUM 网关还要用同一个 `RUM_AGG_SHARD` 作为自身遥测资源的 `service.instance.id`。
APM 不要用 Span 上的 `service.instance.id` 充当 `APM_AGG_SHARD`。原因见第 4 节第 2 条。

写入地址为空时，不要回落到 `VICTORIAMETRICS_HOST`。明细入库配置保持原样。
使用 `deploy/apm/otel/aggregate.yaml` 时，未设置的变量会展开成空字符串。
写入地址为空时报 `invalid endpoint`，`APM_AGG_SHARD` 为空时报 external labels 为空。
两种都只让聚合 Collector 无法启动。系统 Collector 不读这些变量，VictoriaTraces 入库继续。
区域 Collector 也不读这些变量。

聚合消费者名是 `BKLITE_APM_AGGREGATE`，过滤 `apm.traces.>`，显式 ACK，pull，`deliver new`。
首次创建不回放当时已在 Stream 里的消息，避免积压被记成晚到或把已经聚合过的历史再算一遍。
已存在的同名消费者不要删掉重建。预建命令：

```text
nats consumer add APM_TRACES BKLITE_APM_AGGREGATE \
  --filter "apm.traces.>" --pull --deliver new --ack explicit \
  --wait 30s --max-deliver 3 --max-pending 256 --replay instant --defaults
```

`APM_AGG_NATS_ACK_WAIT` 默认 30 秒，短于系统消费者的 60 秒，并且必须大于聚合配置里写死的
`downstream_timeout` 20 秒。聚合入口在内存里完成，不必盖住 VictoriaTraces 的导出重试。
`APM_AGG_NATS_MAX_DELIVER` 默认 3。聚合流水线正常不把导出失败退回接收器，重投只发生在进程崩溃
或处理卡住超过 ACK 等待。3 给在途消息再试两次，然后终止；取 1 会在每次重启时丢掉已拉取未 ACK 的消息。
`max ack pending` 仍用 `APM_NATS_MAX_ACK_PENDING`，与接收器的拉取批量对齐。

仓库内 `deploy/apm/nats/nats-server.conf` 对 consumer 使用 `APM_TRACES.*` 通配，不用改。
生产账号如果按 consumer 名授权，要给 `BKLITE_APM_AGGREGATE` 补上 info、pull 和 ACK。

同一变更里创建这个消费者、启动聚合 Collector，并把系统 Collector 换成只写 VictoriaTraces 的
`system.yaml`。不要让旧的聚合分支和新进程同时消费。

聚合进程内存按容量压测里约 236 MiB 的聚合堆取值，不另做压测。`memory_limiter` 的 `limit_mib`
默认 512，`spike_limit_mib` 默认 128，软拒绝线是 384 MiB，比测到的堆高出约 148 MiB。容器上限默认
640 MiB，等于 `limit_mib` + 128 MiB。拒收发生在计数之前，只 NAK 聚合消费者。系统 Collector 仍用
384 / 96 / 512 MiB，只服务明细。

回退聚合写入时停掉聚合 Collector。系统 Collector 继续用 `system.yaml` 写 VictoriaTraces。
不要删除 Stream 或两个 consumer。`0.153.0-bklite.2` 及更早的镜像没有 `routing` 连接器，不能加载
`aggregate.yaml`。退回那种镜像时要同时停掉聚合进程，并换回该镜像自带的系统配置。

RUM 网关同样不能按空环境变量只关掉聚合分支。使用 `deploy/rum/collector/otel/rum.gateway.yaml`
时，写入地址为空或 `RUM_AGG_SHARD` 为空都会让整个网关无法启动，VictoriaLogs 入库一起停。
要保住明细，改挂同目录的 `rum.gateway.ingest.yaml`。基础认证放在 `rum.gateway.auth.yaml`，
只在 `AGG_VICTORIAMETRICS_USER` 和 `AGG_VICTORIAMETRICS_PASSWORD` 都已设置时作为第二个
`--config` 合并。不要在口令为空时加载它：空的 basicauth 仍会发送 `Authorization`。
网关不回落到 `VICTORIAMETRICS_HOST`。remote write 关闭队列和重试，累计值靠下一次成功的刷出补上。
本地夹具可以把写入地址设成一个不可达的占位，只为让带聚合分支的配置通过校验并启动；
那不是已经接入聚合库。生产不要用占位地址代替空地址，也不要把它指到 `VICTORIAMETRICS_HOST`。

## 4. 写入规则

下面五条都是硬约束。查询由 Server 生成，页面不能提交 PromQL。

1. 只写累计计数器和累计直方图。查询使用 `increase()`、`rate()` 和 `histogram_quantile()`。
   禁止按增量对齐到分钟起点、再靠同一时间戳覆盖。
   原因：2026-11-09 的验证里，spanmetrics 写出的是累计值。同一累计样本重复写入后，
   `increase()` 不变；进程重启造成的计数器重置，也只把重启后的新 Span 算进去。
   VictoriaMetrics 会留下同一序列、同一时间戳上的多个样本。开启去重时保留的是最大值，
   不是最后一次写入。按增量对齐后指望同一时间戳只留最后一次，重试会多计，多个写入方会互相吞掉。
   count 连接器输出的是 Delta，必须先变成累计值再写。一条不再增长的直方图如果先做
   `increase()` 再取分位数，结果可能为空。空结果表示这个窗口没有新样本，按无数据处理，
   不记成 0。

2. 每个写入进程在 remote write 的 `external_labels` 里带固定标签 `shard`。值来自
   `APM_AGG_SHARD` 或 `RUM_AGG_SHARD`，重启不变，不同写入进程互不相同。查询一律跨
   `shard` 求和，不能把单个分片当成全集。组件自动加上的实例标识必须排除，或者固定成
   与该进程分片值相同的配置值。
   原因：同一条序列只能有一个写入方。两个进程写同一条序列时，重复时间戳会把累计值算乱。
   分片让每个进程写自己的序列，查询再把各分片相加。随机实例标识会在重启后拆出新序列，
   基数失控，`increase()` 也无法按原序列跨过重启。验证里 spanmetrics 默认给每条序列加
   随机的 `collector.instance.id`，排除这个维度后可以没有它。`external_labels.shard`
   能够写入 VictoriaMetrics。`service.instance.id` 不能当作 APM 的分片：它替换不了
   `collector.instance.id`，留在 Span 资源上还会变成 Prometheus 的 `instance`。

3. 标签里禁止出现用户、会话、原始 URL、查询串、SQL、`trace_id`、`span_id`、随机实例标识
   和 Pod 名。
   原因：这些值要么是用户数据，要么没有上界。写进标签后，聚合库会变成另一份明细，
   磁盘和查询都随 Span、用户或 URL 增长。安全要求也是库里不能有用户、会话、原始 URL、
   SQL、`trace_id`、`span_id` 或随机实例标识。

4. APM 指标名使用前缀 `apm_`，RUM 指标名使用前缀 `rum_`。
   原因：这一期不用 AccountID 区分租户，两个产品共用一个库，只靠前缀分开。聚合起点表示
   RED 序列开始存在：APM 只探测 `apm_calls_total`，每个产品记下起点后不再重复探测。
   RUM 只探测 `rum_views_total`（`min(tfirst_over_time(rum_views_total[35d]))`），不用 `rum_` 前缀。同一条流水线还写 `rum_js_errors_total`，以及
   `rum_web_vital_lcp_milliseconds`、`rum_web_vital_inp_milliseconds`、
   `rum_web_vital_fcp_milliseconds`、`rum_web_vital_ttfb_milliseconds` 和
   `rum_web_vital_cls` 直方图。毫秒直方图带 `_milliseconds` 后缀，数值仍是毫秒，不换成秒。
   前缀不能代替独立地址。监控扫描读不到这些序列，是因为它们不在 `VICTORIAMETRICS_HOST` 那套库里。

5. Server 启动和 `batch_init` 不依赖聚合库。
   原因：聚合库是运行期可以降级的依赖。启动阶段等待它，会在库未就绪时挡住 API、Worker、
   Beat 和 Listener。未配置查询地址表示聚合层不可用，不是启动失败。停库只影响读这层的
   页面，明细入库继续。启动边界见第 9 节。

## 5. 标签禁区

库里不得出现 Span 正文和 RUM 原始事件。标签和指标名里不得出现：

- 用户、会话、原始 URL、查询串、SQL（包括 SQL 原文）
- `trace_id`、`span_id`
- 随机实例标识、Pod 名、每次重启都会变的写入实例名
- APM 序列上的 `collector.instance.id`、`span.kind`、Prometheus `instance`
- scope 信息（例如 `otel_scope_name`）和 `target_info` 指标

验收时不要把下面几项当成违规：

- APM 上去不掉的 `job`，以及规则要求的 `shard`
- RUM 上 `signal_to_metrics` 的实例标识，但该值必须等于这个进程的 `RUM_AGG_SHARD`

APM 和 RUM 各自允许的业务维度由 02、05 ticket 锁定。那些白名单也不能突破本节的禁区。

## 6. 告警

告警接到运维自己的渠道。研发不提供生产告警编排。至少配置下面几类。

- 聚合库数据目录所在文件系统：使用率达到 70% 时告警，达到 85% 时定为严重。
- 活跃序列数相对本环境最近的稳定基线异常上涨。短时间内明显偏离基线，且没有对应的
  上线或维度变更，就要告警。第 7 节的典型值不是告警阈值，最坏值也不是该环境的预期用量。
  规模更小的环境应在远低于这些数字时告警。活跃序列取 VictoriaMetrics 单节点自身的
  序列统计，具体指标名以所部署版本为准。
- 出现溢出序列。在聚合库执行 `count(apm_calls_total{otel_metric_overflow="true"}) > 0`。
  条件成立表示某个服务资源的入口组合已经超过 `APM_AGG_CARDINALITY_LIMIT`。溢出序列没有
  `service_name` 和 `deployment_environment`，`job` 仍是「命名空间/服务名」，用它定位是哪一个资源打满。
  处理办法是修 Span 命名，去掉原始路径和 ID；或者只调高这个环境的每服务资源上限。调高会让该资源的
  内存和活跃序列按新上限增长。不要改 Server 查询去按 `job` 统计 RED，溢出不应当算进某个服务的请求数。
- remote write 失败或丢弃。写入进程上，发送失败或被丢弃的样本出现后就要告警。
  常见指标名是 `otelcol_exporter_send_failed_metric_points`。RUM 和 APM 的聚合
  remote write 都关闭了队列，不要把 `otelcol_exporter_enqueue_failed_metric_points`
  当成这条流水线的丢弃信号。RUM 流上限丢弃看网关自身的
  `otelcol_deltatocumulative_datapoints`，属性 `error=limit`。
- APM 聚合消费者积压。聚合 Collector 健康检查失败，或 `BKLITE_APM_AGGREGATE` 的待投递消息数
  （`num_pending`）持续增长，就要告警。Server 的健康探针只看系统消费者，不反映这个消费者。
  积压超过 5 分钟的 Span 恢复后记成晚到，`apm_aggregate_late_spans_total` 会突增，这段时间的请求数偏少。

收到 remote write 告警时，先恢复聚合库或网络。不要为了清告警把导出失败退回给
JetStream 或 RUM 接收接口。那样做会让调用链重复入库，或让 RUM 接收接口失败。

## 7. 容量参考

下面是 35 天的容量估算，不是远程 VictoriaMetrics 上量到的磁盘占用。系数是约
1 字节每个样本，样本间隔按 60 秒，即 APM、RUM 的默认刷出间隔。刷出更快时，磁盘按比例增加，例如 RUM 改成 10 秒时最坏约为表中的 6 倍。实际容量以压测为准。

| 项 | APM | RUM |
|---|---|---|
| 规模 | 按服务资源计算，见下方公式 | 1 个租户，50 个应用，3 个环境，100 条路由，4 种流量类型，共 60,000 个组合 |
| 每个组合的序列 | 1 条计数，加上 1 条直方图。直方图含 15 个桶（14 个显式桶和 `+Inf`），再加 `_count` 与 `_sum`，合计 18 条 | 2 条计数，加上 5 条直方图。夹具里每条直方图是 8 个边界，含 `+Inf` 为 9 个桶，再加 `_count` 与 `_sum`，合计 57 条 |
| 序列总数 | 典型 1,620,000；最坏 9,000,000 | 3,420,000 |
| 35 天的样本数 | 50,400 | 50,400 |
| 磁盘估算 | 典型约 76 GiB；最坏约 422 GiB | 3,420,000 × 50,400 × 1 字节，约 161 GiB |

APM 的序列数按服务资源算，不是把所有服务收成一个全局上限：

```text
最坏序列数 = 每服务资源上限 × 服务资源缓存 × 每组合序列数
         = 500 × 1000 × 18
         = 9,000,000
```

500 是 `APM_AGG_CARDINALITY_LIMIT` 的默认值，约 166 个入口操作 × 3 种状态，只约束一个服务资源内部的组合。
服务资源是命名空间、服务名和环境。1000 是配置里写死的 `resource_metrics_cache_size`，与 spanmetrics v0.153
未配置时的默认值相同，这里显式写出。缓存满时，最久没见到的服务资源在当次刷出后丢掉，它的计数器下次从 0 开始。
打满 9,000,000 条时，9,000,000 × 50,400 字节约等于 422 GiB。每个已经溢出的服务资源还会多一个溢出组合，
相对这个最坏值可以忽略。

典型用量不是把上限乘满：200 个服务 × 3 个环境 = 600 个服务资源，每个资源 50 个入口操作 × 3 种状态 = 150 个组合。
600 × 150 × 18 = 1,620,000，1,620,000 × 50,400 字节约等于 76 GiB。150 小于 500，600 小于 1000。

一条序列默认 1 小时没有新 Span 后从聚合进程内存删除，组合名额还给这个服务资源，之后也不再每分钟重写。
聚合库里已经写入的样本留到保留期。过期后再出现的序列从 0 计，`increase()` 按计数器重置处理：窗口里过期前的
增量和过期后的新 Span 都算进去，不会把重置前的累计值再叠一次。空闲服务资源本身仍占缓存名额，直到被换出。不开启按资源过期。

换算使用 1024 的三次方。81,648,000,000 字节约等于 76 GiB，453,600,000,000 字节约等于
422 GiB，172,368,000,000 字节约等于 161 GiB。同一轮验证的进程堆增量大约是 APM 236 MiB、
RUM 331 MiB，里面包含连接器状态和最后一次刷出。这是当时那次压测的内存增量，不能当成
500 上限和 1000 资源缓存打满后的内存，也不能当成 35 天磁盘。

RUM 的 161 GiB 使用的是容量夹具：5 条直方图都按 8 个边界计算，不是产品里 Web Vitals
的桶。产品桶数不同时，磁盘随桶数线性变化。本文不另给一个未经这轮验证的数字。
APM 的典型 76 GiB 和最坏 422 GiB 都只算入口 Span 的计数加直方图，不包含晚到计数。压测时把晚到序列一并计入。

## 8. 镜像变更

本节列出两个产品镜像里的聚合组件。流水线形状以仓库配置为准，稳定性以镜像
`components` 输出为准。升级 Collector 时要回归聚合流水线，至少覆盖标签集合、重复累计样本的
`increase()`，以及 remote write 不可达时明细仍入库且不重复。

APM Collector 保持核心版本 v0.153.0，镜像标签 `0.153.0-bklite.3`。区域、系统和聚合三个进程共用这个镜像。
下面是这个镜像 `components` 里和聚合有关的条目。`deltatocumulative` 和 `transform`
已经出现在输出里。输出没有单独列出旧名 `spanmetrics`，配置使用 `span_metrics`。

| 组件 | `components` 名称 | 稳定性 | 作用 |
|---|---|---|---|
| Routing 连接器 | `routing` | Alpha（`traces_to_traces`；同一次输出里 metrics、logs 也是 Alpha） | 按 Span 把晚到调用链移到晚到流水线，其余进入 `span_metrics` |
| Span Metrics 连接器 | `span_metrics` | Alpha（`traces_to_metrics`） | 把入口 Span 变成累计计数和累计直方图 |
| Count 连接器 | `count` | Alpha（`traces_to_metrics`；同一次输出里 `logs_to_metrics`、`metrics_to_metrics` 也是 Alpha） | 统计晚到 Span。输出是 Delta |
| Filter 处理器 | `filter` | Alpha（traces、metrics、logs） | 在分流前只保留入口 Span |
| Delta to Cumulative 处理器 | `deltatocumulative` | Alpha（metrics）。logs、traces 在输出里是 Undefined | 把 Delta 累加成累计值后再写 |
| Transform 处理器 | `transform` | Beta（traces、metrics、logs） | 用 `keep_keys` 收窄资源属性；晚到指标上把样本时间改成处理时刻 |
| Memory Limiter 处理器 | `memory_limiter` | Beta（traces、metrics、logs） | 放在聚合入口、任何计数之前。拒收只重投聚合消费者 |
| Prometheus Remote Write 导出器 | `prometheusremotewrite` | Beta（metrics） | 写到 `AGG_VICTORIAMETRICS_WRITE_URL` |
| Basic Auth 扩展 | `basicauth` | Beta（extension） | 可选。只在聚合进程追加 `aggregate-auth.yaml` 时启用，留空时不加载 |
| Batch 处理器 | `batch` | Beta（metrics；traces、logs 也是 Beta） | 晚到指标上挡住导出错误，避免已经计入的 Span 随 NAK 再算一次。这个处理器原来就在镜像里 |

上游 metadata 仍给 `transform` 标了 Unsound Transformations 等警告，给 `filter` 标了
Orphaned Telemetry，给 `deltatocumulative` 标了 Statefulness。资源属性收窄放在
`span_metrics` 之前，资源分组键与留下的三个属性相同。同一服务的多个实例因此只产生一组序列。

晚到计数使用 `batch`，把样本时间改成处理时刻，再进入 `deltatocumulative`。
count 默认把时间打在 Span 结束时间上；晚到 Span 已经超过 5 分钟，不改的话即时查询看不到。
`span_metrics` 不把 remote write 失败交回 traces。`batch` 吃掉晚到导出的错误，使 `routing`
不会把这个错误返回接收器。入口上的 `memory_limiter` 在计数之前，拒收只会让聚合消费者重投。
remote write 不可达时，聚合 Collector 不对 JetStream NAK，VictoriaTraces 不因此把同一条 Span 写两次。
VictoriaTraces 不可用时，只有系统消费者 NAK；聚合消费者已经 ACK 的 Span 不会再计一次。

RUM 网关保持 v0.154.0，镜像标签 `0.1.0-bklite.3`。下面是这个镜像
`bklite-rum-gateway components` 里和聚合有关的条目。配置里的导出器类型使用
`prometheus_remote_write`；`prometheusremotewrite` 仍是别名，会打弃用警告。

| 组件 | `components` 名称 | 稳定性 | 作用 |
|---|---|---|---|
| Signal to Metrics 连接器 | `signal_to_metrics` | Alpha（`logs_to_metrics`；同一次输出里 `metrics_to_metrics`、`traces_to_metrics` 也是 Alpha） | 把浏览、JS 错误和 Web Vitals 变成 Delta 计数和直方图 |
| Forward 连接器 | `forward` | Beta（`logs_to_logs`；同一次输出里 `metrics_to_metrics`、`traces_to_traces` 也是 Beta） | 从写入 VictoriaLogs 的日志流水线旁路复制一份 |
| 路由上限处理器 | `rumroutecap` | Alpha（logs） | 每个应用最多 100 条聚合路由，其余记为「其他」 |
| Delta to Cumulative 处理器 | `deltatocumulative` | Alpha（metrics）。logs、traces 在输出里是 Undefined | 把 Delta 累加成累计值后再写 |
| Prometheus Remote Write 导出器 | `prometheus_remote_write` | Beta（metrics） | 写到 `AGG_VICTORIAMETRICS_WRITE_URL` |
| Basic Auth 扩展 | `basicauth` | Beta（extension） | 可选。只在追加 `rum.gateway.auth.yaml` 时启用，留空时不加载 |
| Batch 处理器 | `batch` | Beta（metrics；traces、logs 也是 Beta） | 聚合指标流水线上合并刷出。这个处理器原来就在镜像里 |

`logs/rum` 先把原事件交给 VictoriaLogs，再经 `forward/rum_agg` 进入 `logs/rum_agg`。
这条分支只有 `rumroutecap`，导出到 `signal_to_metrics/rum`。`metrics/rum_agg` 依次是
`batch/rum_agg`、`deltatocumulative/rum`、`prometheus_remote_write/rum_agg`。
聚合分支上没有 `memory_limiter`。`rumroutecap` 吞掉下游错误，remote write 关闭队列和重试。
Redis 调用失败后，`rumroutecap` 熔断 5 秒：熔断期间未缓存路由记为「其他」，不再访问 Redis。第一次失败立即打一条 WARN；同一 5 秒内的其余失败，在窗口结束后的下一次路由处理（不论成败）或进程关闭时再汇总成一条。本地溢出缓存最多 1024 条，请求经过时清掉过期项；已缓存的溢出路由保留，满了就不再写入新的溢出项。
remote write 不可达时，接收接口仍成功，VictoriaLogs 不因此把同一条事件写两次。
聚合专用的 `rum.aggregate.route` 只打在旁路副本上，不进入 VictoriaLogs。
`deltatocumulative.max_streams` 默认 420000。超出后网关自身指标
`otelcol_deltatocumulative_datapoints` 带 `error=limit`。不做晚到过滤，也没有
`rum_aggregate_late_events_total`。

## 9. 启动约束

Server 启动和 `batch_init` 都不依赖聚合库。启动阶段不连接它，不等待它的健康检查，
也不因为查询地址为空或端口拒绝而让 `startup.sh` 失败。

API、Worker、Beat 和 Listener 在聚合库缺失时仍然启动。未配置
`AGG_VICTORIAMETRICS_QUERY_URL` 只表示聚合层不可用。停掉聚合库不影响 VictoriaTraces
和 VictoriaLogs 的写入。

这条边界与 [Server 启动顺序与服务依赖边界](server-startup-dependencies.md) 一致：
非关键、可降级的外部资源失败不得阻断服务启动。不要用延长超时或在 `batch_init` 里
重试来等待聚合库。

## 10. 验收清单

下面七条对应聚合库规则的验收。镜像内的契约测试随 02、05 ticket 落地后另行核对。
本文交付的是规则和这份清单。

1. 新库地址与 `VICTORIAMETRICS_HOST` 不同。`AGG_VICTORIAMETRICS_WRITE_URL` 和
   `AGG_VICTORIAMETRICS_QUERY_URL` 都不回落到监控库。监控策略扫描读不到 `apm_`、
   `rum_` 序列。
2. 停掉聚合库后，APM 调用链仍进入 VictoriaTraces，RUM 事件仍进入 VictoriaLogs。
   Server 正常启动，`batch_init` 不因聚合库失败而退出。读聚合层的页面在读取代码
   落地后应显示降级或缺数据，不显示成 0。
3. 保留期不低于 35 天。数据盘 70% 有告警，85% 定为严重。活跃序列数异常上涨有告警。
   `count(apm_calls_total{otel_metric_overflow="true"}) > 0` 有告警。remote write 失败或丢弃有告警。
4. 聚合库没有公网入口。页面不能直接提交 PromQL。查询只由 Server 按已经授权的对象
   生成：APM 收窄到命名空间和服务，RUM 收窄到租户和应用。跨租户查询拿不到其他租户
   的数据。单节点 VictoriaMetrics 不用 AccountID 做租户隔离，网络封闭和 Server
   收窄是隔离手段。Server 的 PromQL 生成随读取 ticket 落地后核对；在那之前，先确认
   查询端口不对浏览器和租户开放。
5. 库中没有 Span 正文、RUM 原始事件，也没有用户、会话、原始 URL、查询串、SQL、
   `trace_id`、`span_id`、随机实例标识或 Pod 名。APM 序列上没有
   `collector.instance.id` 和 Prometheus `instance`。
6. 同一批累计样本重复写入（模拟重试）后，`increase()` 的结果不变。写入进程落地后
   做这次检查。规则本身在第 4 节第 1 条。
7. 本文件已经写明部署硬约束、环境变量、写入规则、标签禁区、告警、容量参考、镜像组件
   和本清单。运维可以按本文部署聚合库、配置两个写入进程、接上告警，并用本清单判定
   是否合格。
