# APM / RUM 入库旁路聚合层

Status: done

来源需求：p398_930（公共组件，只交付规则）、p398_929（APM）、p398_931（RUM）。技术论断已在 2026-11-09 的两轮
概念验证中实测：RUM 网关 v0.154.0 的 `signal_to_metrics → batch → deltatocumulative → prometheusremotewrite`
链路；APM Collector v0.153.0 的 spanmetrics / count / filter / prometheusremotewrite 构建、标签、桶、溢出、
晚到、错误隔离与容量。

## 总执行顺序

三个变更目录按下面的顺序逐张执行，每张 ticket 完成并复核后再开始下一张：

1. `rum-session-end-records/01` 分析可用性只看 VictoriaLogs
2. `rum-session-end-records/02` 网关写出会话结束记录
3. `rum-session-end-records/03` 会话类查询改读会话记录
4. `apm-policy-merged-queries/01` 当前窗按目标分组
5. `apm-policy-merged-queries/02` 基线历史窗按目标分组
6. 本目录 `01` 聚合层规则与 ADR
7. 本目录 `02` APM Collector 生成聚合指标
8. 本目录 `03` Server 聚合查询客户端与 APM 首页、服务列表、服务 RED 改读
9. 本目录 `04` APM 可用性 SLO 改读
10. 本目录 `05` RUM 网关生成聚合指标
11. 本目录 `06` RUM 应用目录、概览与页面列表改读
12. 本目录 `07` RUM Web Vitals 告警改读

## Problem Statement

APM 的首页、服务列表、服务 RED、可用性 SLO，RUM 的应用概览、页面列表、Web Vitals 告警，都在打开页面或每分钟
评估时临时扫描原始数据（VictoriaTraces 的 Span、VictoriaLogs 的事件）。查询耗时随数据量线性增长，长窗口先超时，
并和用户正在看的明细查询抢同一套库。

## Solution

在已有的中心 Collector（APM）和 RUM 网关进程内做入库旁路聚合，把入口 RED 与 RUM 的浏览、JS 错误、Web Vitals
写成累计计数和累计直方图，存进一套独立的 VictoriaMetrics（聚合库）。上述页面和告警改读聚合库，查询耗时只与
序列数有关。明细仍只在 VictoriaTraces / VictoriaLogs。聚合库挂了，明细照常入库，读这层的页面降级。

聚合库本身由运维部署：研发只交付一份部署与写入规则、两个产品自有镜像（APM Collector、RUM 网关）里的组件和
配置变更，以及 Server 读取侧。

## User Stories

1. 作为运维，我打开 APM 首页、服务列表或服务详情的 1 天、7 天窗口，页面不再随 Span 数量变慢或超时。
2. 作为运维，我查看 7 天、30 天、自然月的可用性 SLO，结果秒级返回。
3. 作为运维，我打开 RUM 应用目录、应用概览和按路由的页面列表，浏览次数、JS 错误次数与 Web Vitals p75 秒级返回。
4. 作为运维，Web Vitals 告警每分钟评估不再扫描原始事件。
5. 作为运维，聚合库不可用或缺数据时，页面显示降级或缺数据，不显示成 0；调用链与 RUM 事件照常入库。
6. 作为运维，查询窗口早于聚合上线时间时，页面回退到原来的明细查询，数字连续。
7. 作为平台运维，我按一份规则文档就能部署聚合库、配置写入方和告警，并按验收清单判定是否合格。
8. 作为安全负责人，聚合库里没有用户、会话、原始 URL、SQL、`trace_id`、`span_id` 或随机实例标识。

## Implementation Decisions

### 聚合库（p398_930，只交付规则）

- 交付物是一份运维文档：独立的单节点 VictoriaMetrics，保留期不低于 35 天，只走内网；写入地址
  `AGG_VICTORIAMETRICS_WRITE_URL`（Collector / 网关），查询地址 `AGG_VICTORIAMETRICS_QUERY_URL`（Server），
  可选基础认证；不读取、不复用 `VICTORIAMETRICS_HOST`。
- 磁盘 70% / 85% 告警，活跃序列数异常上涨告警，remote write 失败与丢弃告警；容量上限估算（APM 约 76 GiB、
  RUM 约 161 GiB，35 天）作为参考，实际以压测为准。
- 不提供生产编排（Compose / Helm）。运维自行调整流水线、重新打包两个产品镜像并部署聚合库。
- 写入规则：
  1. 只写累计计数器和累计直方图；查询用 `increase()`、`rate()`、`histogram_quantile()`；禁止按增量覆盖写。
  2. 每个写入进程用 remote write 的 `external_labels` 带一个固定分片标签 `shard`，值由部署配置注入、重启不变、
     不同写入进程互不相同；查询一律跨 `shard` 求和。组件自动加的实例标识必须排除或固定为同一配置值。
  3. 标签禁止：用户、会话、原始 URL、查询串、SQL、`trace_id`、`span_id`、随机实例标识、Pod 名。
  4. 指标名前缀：APM `apm_`，RUM `rum_`。
  5. Server 启动与 `batch_init` 不依赖聚合库。
- 文档同时列出两个镜像需要的组件、版本与稳定性等级（alpha/beta，升级 Collector 时回归），以及每个进程新增的环境变量。

### 架构决定

- 新 ADR 部分替代 ADR 0006：APM 与 RUM 允许把有界维度的累计计数和直方图写入独立聚合库；VictoriaTraces 仍是调用链
  明细、告警策略、慢请求/Apdex、延迟 SLO、下钻与拓扑的唯一来源；Monitor 的 VictoriaMetrics 不受影响；聚合层不去重，
  重投期间按重投比例偏高。ADR 0006 的其余决定不变。
- 长期规范同步：APM 架构与功能清单、`deploy/apm` 的验收清单/README、产品决策文档中“APM 不使用 VictoriaMetrics、
  不生成 Span Metrics”的表述改为本决定；基础设施清单增加聚合库一行。

### APM 聚合（p398_929）

- 中心 Collector 的同一个 JetStream 接收器同时挂多条流水线：写 VictoriaTraces（不变）、入口聚合、晚到计数。
  不新增 JetStream 消费者。
- builder 加入 v0.153.0 的 spanmetrics、count 连接器，filter、deltatocumulative 处理器，prometheusremotewrite
  导出器；资源属性收窄需要的处理器（推荐 transform 的 `keep_keys`）一并加入并说明稳定性。
- 聚合分支（prototype 验证过的形状，节选）：

  ```yaml
  traces/aggregate: [nats_jetstream] → filter/entry(kind ∈ SERVER, CONSUMER) → filter/drop_late → 资源属性收窄 → span_metrics
  traces/late:      [nats_jetstream] → filter/entry → filter/only_late → count/late
  metrics/apm_agg:  [span_metrics] → prometheusremotewrite/agg
  metrics/apm_late: [count/late] → batch → deltatocumulative → prometheusremotewrite/agg
  # late 条件: span.end_time_unix_nano < UnixNano(Now()) - 300000000000（300e9 无法解析）
  # span_metrics: namespace apm, exclude_dimensions [span.kind, collector.instance.id],
  #   exemplars.enabled false, histogram explicit buckets 5ms…10s（必须带单位）,
  #   aggregation_cardinality_limit（溢出带 otel.metric.overflow=true）
  # prometheusremotewrite: external_labels.shard=${env:APM_AGG_SHARD}, target_info 关闭, scope 关闭
  ```

- 聚合分支上不得放任何会把错误返回给接收器的组件（包括 memory_limiter），否则会触发 NAK、VictoriaTraces 重复写入；
  内存由序列上限约束。spanmetrics 不回传导出错误（已验证）；count 分支必须先经 batch（已验证）。
- **必验项（验证时未覆盖）**：APM 探针要求每个实例带 `service.instance.id`。聚合分支必须在 spanmetrics 之前把资源属性
  收窄到服务命名空间、服务名、环境，并让 spanmetrics 的资源分组键与之相同；验证同一服务多个实例的 Span 只产生一组序列、
  没有 `instance` 标签、数值等于各实例之和。
- 业务维度只有：服务命名空间、服务名、环境、入口操作（Span name）、状态；另允许 `job`（去不掉）和 `shard`。
  环境取 Server 现有 RED 查询使用的同一资源字段。
- 桶固定为 5、10、25、50、100、200、300、500、800、1000、2000、3000、5000、10000 毫秒，发布后不变。

### RUM 聚合（p398_931）

- 网关进程内旁路：`logs/rum` 的导出端增加 `forward` 连接器，进入专用的 `logs/rum_agg` 流水线：路由上限处理器 →
  `signal_to_metrics`；`metrics/rum_agg`：`batch → deltatocumulative → prometheusremotewrite`。聚合专用的路由字段不写入
  VictoriaLogs。`logs/rum_agg` 上的组件都不得返回错误（否则会让网关接收接口失败），`batch` 隔离 remote write 错误（已验证）。
- 指标（容器契约已锁定写入名）：`rum_views_total`、`rum_js_errors_total`、
  `rum_web_vital_lcp_milliseconds`、`rum_web_vital_inp_milliseconds`、`rum_web_vital_fcp_milliseconds`、
  `rum_web_vital_ttfb_milliseconds` 与 `rum_web_vital_cls`。毫秒直方图带 `_milliseconds` 后缀，数值仍是毫秒。
  桶按需求：LCP 100、250、500、1000、2500、4000、8000、16000；INP 50、100、200、500、1000、2500；
  CLS 0.01、0.05、0.1、0.25、0.5、1；FCP 100、250、500、1000、1800、3000、6000、12000；TTFB 50、100、200、400、800、1800、4000。
  浏览、JS 错误、各 vital 的判定条件与 Server 现有 LogsQL 完全一致。
- 标签只有：租户、流量类型、应用、环境、聚合路由、`shard`（以及固定为同一分片值的 `signal_to_metrics` 实例标识）。
  资源属性按白名单带出；关闭 `target_info` 与 scope。
- 路由上限：每个应用最多 100 条聚合路由，其余记为「其他」。准入表放在网关已依赖的 Redis 中、多副本共享（进程内缓存已准入
  路由），保证同一路由在所有副本上的归属一致；Redis 暂不可用时未知路由记为「其他」并计数。键是
  `ops:rum:v2:aggregate:routes:` 加租户和应用的 sha256，TTL 35 天，每次命中刷新；长期不活跃的应用会按之后的到达顺序重建。
  溢出路由在进程内负缓存 1 分钟，Redis 失败不进这层缓存。`deltatocumulative.max_streams`
  只作兜底，丢弃有指标告警。
- **不做晚到过滤**：网关已把偏离接收时间超过 5 分钟的事件时间改写为接收时间（`rum.timestamp.clamped`），VictoriaLogs 也按
  改写后的时间存储；聚合层按处理时间计数即与之一致。p398_931 中 `rum_aggregate_late_events_total` 不实现。
- 写入身份：`shard` 与网关遥测资源的 `service.instance.id` 用同一个部署注入值（如 `RUM_AGG_SHARD`），不得随机。

### Server 读取侧

- 新增一个聚合库 PromQL 查询客户端（instant / range），APM 与 RUM 共用，放在两个 app 都能依赖的公共位置，不依赖 monitor app，
  配置只来自 `AGG_VICTORIAMETRICS_*`。未配置 = 聚合层不可用。
- PromQL 只由 Server 生成：标签值来自 Server 已做权限校验的对象（APM 的命名空间+服务，RUM 的租户+应用），统一转义；
  请求参数不能拼接任意表达式。
- 聚合起点：运行期周期任务探测各产品首次出现序列的时间（按分钟对齐），持久化；未记录 = 视为没有聚合数据。
  APM 只探测 `apm_calls_total`，RUM 只探测 `rum_views_total`。
  查询窗口起点早于起点时走原明细查询；30 天 SLO 与自然月 SLO 在起点覆盖整个窗口前继续走 VictoriaTraces。
- 查询结束时间对齐到最近一个完整分钟，并留出一个刷出周期；缺样本返回“无数据”，不当 0；聚合库错误时该区块降级，
  不自动回退去扫明细（避免故障时把负载压回明细库）。
- APM 改读：首页（KPI、健康、Top 列表）、服务列表批量 RED、服务 RED（整窗、趋势、Top 操作）、可用性 SLO。吞吐/错误率用
  `increase()`，平均耗时 = 总和/次数，分位数用 `histogram_quantile`；最大耗时不再提供（返回空，前端显示“—”）。
  慢请求、Apdex、延迟 SLO、版本、实例、依赖、告警策略和试算继续读 VictoriaTraces。
- RUM 改读：应用目录与应用概览中的浏览次数、JS 错误次数、LCP/INP p75 与浏览趋势；页面列表（按路由、未按版本筛选或分组时）
  的浏览次数、错误次数、Web Vitals p75；Web Vitals 告警及其告警详情趋势。每个页面保持现有流量口径（目录与概览为全部流量，
  页面列表与告警默认访客且可选）。会话数、错误会话、国家/设备/环境/版本分布、按版本的页面列表继续读 VictoriaLogs。

## Testing Decisions

- 只测外部行为：Collector / 网关配置能 `validate`、写入聚合库后的序列名与标签集合、数值；Server 接口返回值与降级状态。
- Collector / 网关：Go 进程内测试 + 临时容器（VictoriaMetrics、NATS、VictoriaTraces / VictoriaLogs，端口避开本机正在用的
  8428、9428、10428），覆盖标签集合、多实例合并、桶、溢出、错误隔离（remote write 不可达时不 NAK / 接收接口不失败、
  明细不重复）、重启后 `increase()` 正确。先例：`/tmp/aggverify` 验证代码（已归档到 agent store）、`deploy/apm` 的
  `make contract`、`deploy/rum` 的 `make test`。
- 数据面配置契约：更新 `test_data_plane_config.py`，锁住聚合分支形状、没有 memory_limiter、`exclude_dimensions`、带单位的桶、
  shard 来自环境变量、不出现 `VICTORIAMETRICS_HOST`。
- Server：用伪造的 PromQL 客户端覆盖每个读取面的数值映射、起点回退、缺数据、聚合库错误降级、标签转义与租户收窄；
  对少量关键 PromQL 断言表达式形状。先例：APM `test_victoriatraces_adapter.py` 的 session mock、RUM `test_logsql_pushdown.py`
  的 `FakeVictoria`。
- 验证命令：`make -C deploy/apm test validate`（容器契约按需 `contract`）、`make -C deploy/rum test validate`；Server 用
  sqlite 跑相关 `apps/apm/tests`、`apps/rum/tests`；改了前端类型时 `cd web && pnpm lint && pnpm type-check`。

## Out of Scope

- 部署聚合库、生产编排、镜像流水线（运维负责）。
- 告警策略改读聚合层；慢请求、Apdex、延迟 SLO 走聚合层（需要固定延迟阈值，另立需求）。
- 按 `span_id` 去重、每分钟最大耗时、历史回补、定时回扫明细做离线聚合。
- Client Span、SQL、推断下游进聚合层；尾采样或改采样位置。
- RUM 会话类指标（见 `rum-session-end-records`）、热力图、长任务、移动端、SLO、ClickHouse。
- 用聚合层数字重画已经固化的告警证据。
- AccountID 多租户、多节点集群、按产品分别设置保留期。

## Further Notes

- 验证报告与验证代码归档在 agent store 的 `aggregation-verification-2026-11-09/`。
- 现有缺口（不在本变更范围）：VictoriaTraces 保留期不足 35 天时，30 天 SLO 仍会被标为可用。

## Completion evidence

### APM 可用性 SLO（04）

可用性 SLI 在聚合库已配置、已记录 APM 起点、且窗口起点不早于该起点时，用
`sum(increase(apm_calls_total{服务、环境、已有入口操作}[窗口秒]))` 计算总数，坏数是同一选择器加上
`status_code="STATUS_CODE_ERROR"`。查询结束对齐到最近完整分钟，再留一个 60 秒刷出周期。起点未覆盖、未记录或未配置时仍走
VictoriaTraces 按天切片。延迟 SLO 不变。聚合库错误不回退扫描，达成率不显示为 0：列表保留该 SLO 且达成率为空；首页若没有任何可展示达成率，SLO 区块标为失败。

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 900 uv run pytest apps/apm/tests --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
  结果：`11 failed, 866 passed, 2 skipped`。11 项失败都在既有 sqlite 基线内（topology_api 8 项、deployments backfill 1 项、cross_database_guard 1 项、owned_alert_lifecycle 1 项）。新增 17 项通过，覆盖 7 天、30 天、自然月、起点回退、延迟 SLO、降级、标签收窄与转义，以及首页和列表/详情同一达成率。
- 功能清单已改为：可用性 SLO 在起点覆盖窗口后读聚合库，延迟 SLO 仍读 VictoriaTraces。未改前端。

### RUM 目录、概览与页面列表（06）

聚合可用、已记录 RUM 起点、且窗口起点不早于该起点时，应用目录和概览的浏览次数、JS 错误次数、LCP/INP p75、浏览趋势改读聚合库；按路由且未按版本筛选的页面列表，浏览次数、错误次数、LCP/INP/CLS p75 改读聚合库。会话、错误会话、国家/环境/版本/设备、加载耗时和按版本的页面列表仍读 VictoriaLogs。目录与概览不加流量过滤；页面列表默认访客，`traffic` 与现有 LogsQL 一致。查询结束对齐到最近完整分钟，再留出 RUM 默认 10 秒刷出周期。p75 是直方图分位数，单位仍是毫秒（CLS 无单位）。缺序列不是 0；聚合库错误只把这些数字降为无数据。起点探测改为 `min(tfirst_over_time(rum_views_total[35d]))`。`specs/capabilities` 里没有 RUM 功能清单可改。

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 900 uv run pytest apps/rum/tests apps/core/tests/test_aggregate_origin_probe.py --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
  结果：`241 passed`。其中 `apps/rum/tests` 233 项（基线 215，新增 18），起点探测 8 项。覆盖数值映射、流量口径、版本模式回退、起点回退、降级、`其他` 行、标签收窄与转义。
- 共用对齐函数后 `apps/apm/tests`：`11 failed, 866 passed, 2 skipped`，11 项失败与既有 sqlite 基线相同。
- 前端：改动文件 eslint 通过；相关 vitest 24 项通过；`pnpm type-check` 通过。未起浏览器，页面点击未做人工走查。

### RUM Web Vitals 告警（07）

策略只有应用，没有环境、路由或版本。聚合可用、已记录 RUM 起点、且对齐后的 increase 窗口不早于该起点时，LCP、INP、FCP、TTFB、CLS 的 p75 评估改为
`histogram_quantile(0.75, sum by (le) (increase(<vital>_bucket{租户、应用、流量}[5/15/60 分钟])))`。结束时间对齐到最近完整分钟，再留出 RUM 默认 10 秒刷出周期。默认访客，`traffic` 与页面列表一致。环境、路由和分片被 `sum by (le)` 并回应用级，口径与原来不带这些条件的 LogsQL 相同。无样本是无数据，不是 0。起点未覆盖、未记录或未配置时仍走 VictoriaLogs，读取失败和无数据仍走原来的状态机。聚合查询失败不扫明细，也不触发或恢复。告警详情里这些指标的趋势读聚合库；失败只清空曲线。已经写入的告警值和事件不重画。会话数和错误会话率仍读 VictoriaLogs。`specs/capabilities` 里没有 RUM 告警功能清单可改。

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 900 uv run pytest apps/rum/tests --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
  结果：`256 passed`。基线 234，新增 22。覆盖五个 vital、三个窗口、无样本与 0、读取失败不改状态、起点与未配置回退、标签转义与流量收窄、会话类告警、趋势分桶和已固化事件。未改前端。
