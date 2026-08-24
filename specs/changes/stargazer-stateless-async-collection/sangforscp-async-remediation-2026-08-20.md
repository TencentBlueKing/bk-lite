# SangforSCP 原生异步与完整快照修复

Status: Implemented（2026-08-20）

## 背景与根因

SangforSCP 配置采集器原先暴露同步 `list_all_resources()`，内部使用无明确超时的
`requests.Session`。统一运行时会对插件入口执行 `await`，因此旧实现既违反异步契约，也会在
大量 HTTPS 分页等待时阻塞 Sanic 事件循环。结果发布器虽有独立有界队列，但 writer 同样依赖
该事件循环调度；事件循环长期被同步 HTTP 占用后，结果会在触达 NATS transport 前耗尽
120 秒总发布预算并出现 `publish_total_timeout_before_delivery`。

## 锁定决定

- 全局容量保持 `MAX_ACTIVE_RUNS=16`、`MAX_ACTIVE_TARGETS=150`、
  `TARGET_TASK_WINDOW=150`，不以降并发掩盖阻塞。
- NATS 保持单 writer、批量发布及现有 30/60/120 秒发布超时，本次不增加 writer。
- Sangfor 配置采集使用 `httpx.AsyncClient` 原生异步 I/O；RSA 加密作为短 CPU 工作放入
  `asyncio.to_thread()`。
- 旧设备 TLS 1.0/1.1 继续使用既有 legacy SSL context；禁止自动重定向。目标由统一
  TargetPolicy 解析和校验一次，正式 HTTP 连接固定使用该 IP，并保留原始 Host，避免校验后
  DNS 再解析。当前 legacy context 同时关闭证书校验，这是已有兼容模式而非安全默认；部署侧
  应限制可信管理网访问，后续以受控 CA/证书指纹配置替换，不能在未验证设备兼容性前直接切换。
- Sangfor executor 的正式采集总超时为 300 秒。插件内部所有登录、重试、分页共用同一个
  绝对预算，不能每一页重新获得 300 秒；内部最多预留 100ms 给框架转换并发布稳定的
  `collection_timeout`，目标从进入插件到退出仍不超过框架的 300 秒边界。
- YAML `collector.options` 是受信任配置，由 `PluginExecutor` 以保留字段
  `_collector_options` 注入并覆盖请求中的同名字段，外部任务不能抬高资源上界。

## YAML 默认边界

| 边界 | 默认值 | 达到后的行为 |
| --- | ---: | --- |
| 完整采集总预算 | 300 秒 | 整个目标失败，错误码 `collection_timeout` |
| connect/read/write/pool | 10/60/15/10 秒 | 有限重试后整个目标失败 |
| GET 最大尝试 | 3 | 仅 transport、429、502/503/504 重试 |
| 登录 POST 最大尝试 | 2 | 仅 transport 失败可重试；业务认证失败不重试 |
| page size / 最大非空页 | 100 / 1000 | 超过最大非空页则完整快照失败 |
| 最大对象数 | 100000 | 完整快照失败，不截断为成功 |
| 单响应 / 全快照响应字节 | 10 MiB / 48 MiB | 完整快照失败 |

分页以 Janus 明确返回空页作为完成信号。插件同时检查缺失稳定 ID、跨页重复 ID、相邻重复页、
对象数和响应字节；任何不完整或不前进状态都停止本轮。`max_pages` 允许在达到最大非空页后再
读取一个空结束页，但不允许第 `max_pages + 1` 个非空页。

## 完整性与错误语义

物理主机、虚拟机和可用区先写入目标内临时结构。只有登录及三类分页全部完成后，才构造并
返回成功快照。认证、TLS、网络、HTTP、非法 JSON、分页停滞、资源上界或总预算任一失败时：

1. 丢弃本轮已收集的所有临时对象；
2. 返回 `success=false` 与稳定 `cmdb_collect_error`；
3. 统一运行时只发布一条目标失败结果；
4. Server/CMDB 不得把失败快照中的“未看到”解释为删除，保留上一轮完整成功数据。

只有所有 API 均成功并明确返回空集合时，空清单才是合法的完整成功快照。

## 结果发布可观测性

发布架构未改变。本次在 receipt 与周期容量日志中补充：

- `delivery_started`：是否已触达 transport；
- `queue_depth_at_enqueue`：结果入队时的队列深度；
- `queue_wait_ms`：等待有界队列接纳的时间；
- `queue_age_ms`：终态时该结果从入队起的年龄；
- `publish_queue_residence_p99_ms`：最近样本入队至 transport 的 p99；
- `publish_batch_age_ms`：当前 writer 正在处理批次的持续时间。

`collection_capacity` 仍每 180 秒输出一次。若
`publish_total_timeout_before_delivery` 再出现，先结合事件循环 p99、队列驻留 p99 与当前批次年龄
区分“事件循环阻塞”“队列积压”和“NATS transport 慢”，再决定是否单独调整 NATS；不得直接
放大超时或增加 writer。

## 验收与回滚

自动化覆盖公开插件入口的原生 await、事件循环 heartbeat、16 路并发推进、出站策略拒绝与固定
连接 IP、认证失败、分页完整成功、分页重复、中间失败不发布半截数据、对象/响应体上界、总预算
和临时 503 重试。发布器覆盖 receipt 遥测、取消前未投递、批量部分失败和总发布预算。

上线先对单台真实 Sangfor 比对主机/虚机/AZ 数量，再在 `16/150/150` 下执行 Sangfor 与
网络/Job 混合压测。验收要求：无静默截断，`publish_total_timeout_before_delivery=0`，发布队列不
持续超过 80%，事件循环 p99 不持续超过 200ms。

回滚为两个独立动作：回退企业版 Sangfor commit；主仓回退企业子模块指针及通用 YAML options/
发布观测 commit。无数据库或消息 schema 迁移。
