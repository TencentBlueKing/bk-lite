# APM / RUM 聚合链路上线前加固

Status: done

来源：`observability-aggregate-metrics` 合入 master 后，对采集端和读取端的数据链路复核（2026-11-10）。
本变更只处理复核中的 P0 / P1；P2 见 Out of Scope。

## Problem Statement

聚合层写入量本身不大，但复核发现两处会让聚合数字出错，另有三处在故障或配置变化时会拖累明细入库、或让运维误判：

1. **明细写失败时，APM 聚合重复计数（P0）。** 系统 Collector 的 JetStream 接收器把同一批调用链扇出给明细、聚合、晚到三条流水线。
   OpenTelemetry 扇出先把克隆交给会改数据的聚合与晚到流水线，最后才交给明细流水线，所有错误合并后返回接收器。
   VictoriaTraces 不可用或明细流水线的 `memory_limiter` 拒收时，接收器 NAK，消息重投，聚合分支把同一批 Span 再算一次。
   `APM_NATS_MAX_DELIVER=8` 时，同一条消息最多算 8 次：5 分钟内的重投进入请求数和错误率，之后进入晚到计数。
   契约测试只覆盖了反方向（聚合库写失败时明细不重复）。
2. **APM 序列数实际上没有全局上限（P0）。** `aggregation_cardinality_limit: 90000` 在 spanmetrics 里按每个服务资源生效，
   不是全局；没有配置序列过期，消失的接口和服务一直留在内存并每分钟重写；资源缓存默认 1000。容量文档按“全局 9 万组合”估算。
   某个服务的 Span 名带原始路径时，这个服务单独就能涨到 9 万组合，内存和聚合库活跃序列一起上涨。
3. **聚合状态挤占明细入库的内存（P1）。** `memory_limiter` 看整个进程的内存。聚合状态和每分钟刷出的尖峰与明细共用一个进程，
   夹具默认上限 384 MiB，容量压测里聚合部分增加约 236 MiB 堆内存。超限后明细流水线拒收并 NAK，又叠加第 1 条。
4. **RUM 路由准入在 Redis 故障时拖慢收数（P1）。** `rumroutecap` 在收数请求里同步执行，每条新路由调用一次 Redis（超时 200ms）。
   调用失败不写负缓存，并且每条记录打一条 WARN；超出 100 条上限的路由放在本地溢出缓存里，只在同一路由再次出现时才清掉，内容站的 slug 路由会让它持续增长。
5. **刷出间隔可以单边修改（P1）。** `APM_AGG_FLUSH_INTERVAL`、`RUM_AGG_BATCH_TIMEOUT` 是采集端的运维开关，
   Server 用于对齐查询结束时间的刷出间隔却是常量（APM 60 秒、RUM 10 秒）。只改采集端时，窗口末尾会少算。

## Solution

- APM 聚合改由独立的 JetStream durable consumer 和独立的 Collector 进程承担，与明细各自 ACK、各自限内存。
  系统 Collector 回到只写 VictoriaTraces。
- 聚合进程只有一条入口流水线，`memory_limiter` 在任何计数之前；拒收只会让消息重投，不会出现“已计数又重投”。
- spanmetrics 改为按服务设置合理上限，并开启序列过期；容量文档按“每服务上限 × 服务资源数”重写，溢出序列有告警。
- `rumroutecap` 在 Redis 失败后短时间内直接记为「其他」，日志按时间窗汇总；溢出缓存有上限并定期清理。
- Server 读取与采集端同名的刷出间隔变量，默认值与采集端一致；文档写明两边必须一致。

## Implementation Decisions

### APM 聚合独立消费（01）

- Stream `APM_TRACES` 已是 `limits` 保留策略，新增 durable consumer `BKLITE_APM_AGGREGATE`，过滤 `apm.traces.>`，
  显式 ACK，`deliver new`（首次上线不回放积压，否则积压会全部记成晚到）。
- 聚合流水线本身不返回错误，所以这个消费者只会在进程崩溃或卡住超过 ACK 等待时重投。接受“崩溃时极少量重复”，
  不选“最多一次”：后者每次正常重启都会丢掉已拉取未处理的消息。重投次数上限取小值，具体值在 ticket 里定并写进部署文档。
- 新进程 `apm-aggregate-collector`，复用 APM Collector 镜像，配置 `deploy/apm/otel/aggregate.yaml`；基础认证改为
  `aggregate-auth.yaml` 追加。系统 Collector 的 `system.yaml` 回到只有 VictoriaTraces 流水线，`system-traces.yaml` 不再需要，删除；
  聚合的写入地址、分片值和认证变量只配在聚合进程上。系统 Collector 不再因为聚合变量为空而起不来。
- 聚合进程的入口流水线：`memory_limiter` → 入口 Span 过滤 → 资源收窄 → 按晚到条件分流到 `span_metrics` 与 `count/late`。
  分流组件优先用 `routing` connector；镜像里没有时加入构建并把镜像升到 `0.153.0-bklite.3`。
  不再让两条流水线各自克隆整批数据、各跑一遍入口过滤。
- NATS 账号权限已按 `APM_TRACES.*` 放开 consumer，不改 ACL；生产 ACL 若按 consumer 名收紧，部署文档提醒运维补授权。
- 区域 Collector、Stream、明细写入保持不变。

### APM 序列上限与过期（02）

- 每服务上限默认 500 个组合（约 166 个入口操作 × 3 种状态），仍可用 `APM_AGG_CARDINALITY_LIMIT` 调整，文档写明是“每服务”。
- 开启按序列过期（spanmetrics 的序列过期字段，以 v0.153 实际字段为准），默认 1 小时；不活跃的接口释放名额。
  过期后再出现的序列从 0 开始，`increase()` 按计数器重置处理，结果正确。
- 显式设置服务资源缓存上限，取值与容量文档一致。
- 溢出序列丢失服务名和环境标签，Server 不改为按 `job` 查询；溢出作为运维信号，告警清单增加“出现溢出序列”。
- 容量文档按“每服务上限 × 服务资源数 × 每组合序列数”给出最坏值和典型值，删掉“全局 9 万”的说法。

### RUM 路由准入（03）

- Redis 调用失败后进入短暂熔断（量级为数秒）：熔断期间未缓存的路由直接记为「其他」，不再调用 Redis。
- 失败日志在窗口内第一次失败时立即打一条 WARN；同窗口后续失败在窗口结束后的下一次路由处理或关闭时再汇总一条，只含尚未输出的次数，字段仍是 `failed_stage`、`error_type`、`failure_count`。失败计数指标照常累加。
- 本地溢出缓存设条目上限并定期清理过期项；准入缓存保持现状。
- 改了网关代码，RUM 镜像升到 `0.1.0-bklite.3`。

### 刷出间隔对齐（04）

- Server 读取 `APM_AGG_FLUSH_INTERVAL`（默认 60s）和 `RUM_AGG_BATCH_TIMEOUT`（默认 10s），解析失败按默认值并记一条 WARN。
- 部署文档与上线说明写明：改这两个值必须同时改采集端和 Server。

## Testing Decisions

- 01：APM 容器契约（独立 Compose project、随机端口）新增：停掉 VictoriaTraces 期间写入一批 Span，恢复后聚合计数等于实际 Span 数；
  保留原有“聚合库不可达时明细不重复”“重启后 `increase()` 正确”。数据面配置契约锁住：系统配置没有聚合分支，聚合配置单条入口流水线且
  `memory_limiter` 在计数之前、没有 `VICTORIAMETRICS_HOST`。`make -C deploy/apm test validate`，契约按需 `contract`。
- 02：契约覆盖超过每服务上限时并入溢出序列、序列过期后重新出现时 `increase()` 正确（夹具用短过期时间）。
- 03：Go 单测覆盖 Redis 失败后熔断期间不再调用 Redis、第一次失败立即打出 WARN、窗口到期后一次成功调用刷出其余次数、溢出缓存不超过上限且过期项被清理；`make -C deploy/rum test`。
- 04：Server 单测覆盖默认值、自定义值、非法值；sqlite 跑 `apps/apm/tests`、`apps/rum/tests`、`apps/core/tests`，对照 master 基线不新增失败。
- 不连接用户本机的 8428、9428、10428，不操作用户正在运行的 `bk-lite-apm-*`、`bklite-dev-*` 容器。

## Out of Scope

- P2：Server 按服务批量查询聚合库（去掉首页 40 个目标的限制）、RUM 样本密度与聚合库去重、APM 页面口径类优化。
- 页面状态与空态口径（APM 静默与健康度、RUM「窗口内无数据」、页面列表依赖控制面）。
- 聚合库的生产部署与流水线编排（运维负责，按更新后的文档执行）。

## Further Notes

- 依赖 `observability-aggregate-metrics`（已完成并合入 master）。
- 执行顺序：01 → 02 → 03 → 04。01、02、04 都改 APM 聚合配置或其文档，必须顺序执行。
- 每张 ticket 同步更新 `docs/operations/aggregate-metrics-store.md`、`docs/operations/apm-rum-query-performance-rollout.md`
  及 `deploy/apm`、`deploy/rum` 下受影响的 README / 验收文档。
