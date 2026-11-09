# RUM 会话结束记录与分析可用性解耦

Status: done

来源需求：p398_955。技术论断已在 2026-11-09 的聚合层验证中实测（Lua 快照、`assign()` 返回值、
`/insert/jsonline` 写入、删除字段、合并规则、调用面清单）。

## Problem Statement

运维打开 RUM 会话列表、会话摘要，或看会话数、错误会话率时，Server 要把窗口内全部原始事件按
`rum.session.key` 分组。事件越多、窗口越长越慢，流量上涨后先出现超时和空数。

另外，Server 判断 RUM 分析是否可用时同时探活 VictoriaLogs 和 VictoriaTraces。分析查询只读
VictoriaLogs，但 VictoriaTraces 不通时，会话、错误、页面、概览整页被标成不可用。

## Solution

会话结束时由网关侧写一条「一个会话一行」的会话记录到 RUM 的 VictoriaLogs。已结束的会话读会话
记录；还在进行中的会话（最长 4 小时）仍从原始事件分组，但扫描范围收窄到最近 4 小时。RUM 分析
是否可用只看 VictoriaLogs，VictoriaTraces 的健康单独展示。

## User Stories

1. 作为运维，我打开 7 天、30 天窗口的会话列表和会话摘要，页面不再随事件量线性变慢。
2. 作为运维，我在会话列表里仍能看到正在进行中的会话，以及它们的回放标记。
3. 作为运维，同一个会话在列表里只出现一行，计数不因会话记录与原始事件重叠而翻倍。
4. 作为隐私负责人，我按用户或会话删除数据时，会话记录一并删除。
5. 作为运维，VictoriaTraces 故障时，我仍能正常使用会话、错误、页面和概览；VictoriaTraces
   的异常在接入健康里单独可见。
6. 作为运维，会话记录因故写不进去而过期丢失时，我能看到丢失计数并收到告警。

## Implementation Decisions

### 会话状态与快照（网关 rumsession 处理器）

- 现有 Redis 会话 hash（`key`、`first`、`last`、`traffic`）扩展为同时累计事件数、浏览数、错误数，
  并记录第一个非空的入口路由、版本、用户（伪名化后的值）、环境，以及原始事件上的
  `rum.erasure.user_key`、`rum.erasure.session_key`。
- 会话切换必须在同一次 Lua 执行中完成：先把上一场写成独立快照 key（`ops:rum:v2:ended:{session_key}`
  形态），再清零当前状态。只在现有 hash 上累加会把旧计数带进新会话、后写的路由覆盖第一个路由（已验证）。
- 增加一个按最后活动时间检索的 ZSET 索引：member 为会话键，score 为 `last_seen`。稳态每条事件多一次
  `ZADD`。不全量扫描 Redis。
- Lua 返回值增多；`assign()` 及其返回结构同步扩展（现在只接受 3 个返回值）。
- 15 分钟空闲、4 小时上限、5 小时 TTL 保持不变（配置校验已冻结前两者）。
- 浏览数、错误数的判定与 Server 现有口径一致：浏览 = `rum.event.type` 为 view；错误 = `rum.event.type`
  为 error。

### 维护进程写会话记录（maintainer）

- maintainer 定期从 ZSET 取出空闲满 15 分钟、或开始满 4 小时的会话，向 RUM 的 VictoriaLogs 写一条
  `rum.event.type=session_end` 记录，写成功后再移出索引并删除快照。
- 新增 VictoriaLogs 写入客户端，走 `/insert/jsonline`（已验证）。现有 `victoria.go` 只有删除，不改删除路径。
- 记录字段：会话键、应用、租户、环境、开始时间、结束时间、时长、事件数、浏览数、错误数、入口路由、版本、
  用户、流量类型、`rum.erasure.user_key`、`rum.erasure.session_key`。`_time` 取会话结束时间。
- 写失败重试；重试窗口就是快照 key 的 TTL（约 4 小时 45 分钟）。快照已过期、索引成员还在的会话：计入丢失
  计数（Prometheus 指标）、移出索引、日志 WARNING 一次（有界汇总，不逐条刷屏）。
- 先写后移出索引之间崩溃会多写一条；不在存储层去重，由查询按会话键合并。
- maintainer 只跑一个副本（扫描任务没有选主），写进 `deploy/rum` 的验收清单与部署说明。
- 日志遵守仓库生产日志规则：不记录用户、会话键、事件正文。

### 会话类查询改读（Server）

- 已结束的会话：会话列表、会话摘要、会话数趋势、错误会话数与错误会话率，读会话记录。应用目录和概览 KPI
  的会话数、错误会话率同样读合并结果；浏览、错误条数、Web Vitals、国家、设备和环境分布仍读原始事件。
- 会话记录按结束时间存储。查询 `_time` 取 `[from, to + 4h15m]`，再保留 `started_at_ms <= to` 且结束时间
  `>= from` 的记录，也就是会话区间与窗口重叠。计数是整段会话，不是窗口内截断后的片段。
- 合并规则：已结束会话在 VictoriaLogs 里按会话键分组（计数字段取 `max(...)`，不用日志行数），过滤、排序、
  总数、错误数和中位时长都在那里完成。列表只取回排序后的前 `offset + limit` 行，再与进行中的小集合归并后切出
  当前页。同一会话键有会话记录时，不再加它的原始事件。
- 进行中部分只扫 `max(窗口起点, now-4h)` 到窗口终点，并且最后活动时间不早于 `now - 30m`。结束超过 30 分钟的
  会话由会话记录覆盖；维护进程积压时它们会暂时不出现。分组仍受 50000 行上限保护。去重只对这批候选键发
  `rum.session.key:in(...)`，不带列表过滤条件；键太多时分批。
- 总数和错误数是已结束统计与进行中数量相加。中位时长在没有进行中会话时用记录的 `quantile`；两边都有时按数量
  对两个中位数加权，这是近似值。
- 会话数趋势每个会话只计一次，计入它开始时间所在的桶。已结束会话在 LogsQL 里按 `rum.session.started_at_ms`
  分桶。这和旧的「一个会话在每个有事件的桶里都计一次」不同。开始时间早于窗口的会话不进任何桶。
- 国家在已结束会话上不命中。路由、用户、`hasError`、流量类型直接下推到记录字段；路由只比入口
  `rum.view.name`，用户只比记录上的第一个用户。进行中会话仍按原始事件筛选。
- 应用目录和概览 KPI 的会话数、错误率走上面的统计查询，不再把会话行拉回 Server。
- 记录起点：第一次会话查询时用 `min(_time)` 探测，结果放 Django cache（10 分钟）。探测失败不写入 cache。
  没有记录、探测失败，或窗口起点早于记录起点时，整段按现状扫原始事件。不在启动期探测，也不建表。
- 列表的回放标记仍按当前页查回放索引；不把“是否有回放”写进会话记录。
- 会话数、错误会话率告警本次不改（需要进行中的会话）。旅程、回放、漏斗仍读原始事件。
- 流量类型过滤沿用现有默认（访客）与参数，会话记录上带流量类型以便过滤。

### 分析可用性只看 VictoriaLogs

- 分析客户端的探活只探 VictoriaLogs；`VictoriaAnalytics.open()` 不再要求 VictoriaTraces 地址；
  `_build_analytics()` 只在 VictoriaLogs 地址为空时返回不可用。
- `probe_pipeline_health` 的 `analytics_configured` 只看 VictoriaLogs；VictoriaTraces 健康作为独立字段
  出现在接入健康里。
- 现有把 VictoriaTraces 地址设为空的测试夹具随之调整（清单见验证报告 V2.5）。

## Testing Decisions

- 好测试只验外部行为：Redis 里的会话/快照/索引状态、写到 VictoriaLogs 的记录内容、Server 接口返回的行与
  计数，不断言内部函数调用次数。
- 网关：在 miniredis/真实 Lua 上覆盖空闲切换、4 小时切换、切换后计数清零、第一路由保留、ZSET 成员与 score。
  先例：`redis_acl_test.go` 的真实 Lua 测试、`processor_test.go` 的切换测试。
- maintainer：用本地 HTTP 桩验证 `/insert/jsonline` 请求体、重试、写成功后移出索引、快照过期计入丢失。
  先例：`victoria_test.go`。
- 删除：用临时 VictoriaLogs 或桩验证带 `rum.erasure.*` 的会话记录能被现有删除过滤器命中。
- Server：沿用 `FakeVictoria` / 本地 HTTP 桩两种夹具，覆盖合并去重、`max(event_count)`、窗口早于记录起点
  的回退、进行中会话出现在列表；可用性覆盖“logs 有、traces 空”为可用。先例：`test_logsql_pushdown.py`、
  `test_victoria_analytics.py`、`test_sessions_service.py`、`test_health_flags.py`。
- 验证命令：`make -C deploy/rum test`、`make -C deploy/rum validate`；Server 用 sqlite 跑 `server/apps/rum/tests`。

## Out of Scope

- Server 直接读网关 Redis。
- 会话数、错误会话率告警改读会话记录。
- 把“是否有回放”写进会话记录。
- 历史会话回补。
- 依赖 VictoriaMetrics 聚合层。

## Further Notes

- 执行顺序见 `specs/changes/observability-aggregate-metrics/spec.md` 的「总执行顺序」。
- 本变更不依赖新组件，可与 `apm-policy-merged-queries` 并行，但同一工作区内按顺序执行。
