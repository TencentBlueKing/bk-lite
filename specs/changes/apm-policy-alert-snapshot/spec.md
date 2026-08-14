# APM 策略、告警与事件快照

Status: accepted

## 目标与范围

本变更只实现 APM 自有的策略执行、告警生命周期、事件快照和可靠通知。Monitor 与 Log 的生产实现是机制参考，APM Storybook 是只读交互参考；生产页面只读取 APM 接口和 VictoriaTraces，不导入 Storybook Mock，也不让 APM 依赖 Monitor/Log 的策略、对象、日志组、告警或快照表。

APM 继续遵循 ADR 0004：APM Alert 是告警生命周期事实来源；告警中心只接收事件副本，不回写 APM。VictoriaTraces 继续遵循 ADR 0006，作为策略评估与指标预览的唯一遥测事实源。

不在本变更中处理服务目录、拓扑、探索、接入和数据链路优化。

## 统一领域语言与状态机

- **Alert** 是一次生命周期聚合，状态只有 `active / recovered / closed`。同一策略目标在活动期间只存在一个 Alert。
- **Event** 是生命周期内不可变的状态变化，动作只有 `triggered / escalated / recovered / closed`。`triggered` 创建 Alert；更高级阈值首次连续满足产生 `escalated`；自动恢复产生 `recovered`；用户关闭产生 `closed`。
- **Event Snapshot** 与 Event 一一对应，以 `event_id` 去重；通知投递是独立可变记录，不属于快照。
- API、数据库新增数据和页面统一使用上述词汇；旧 `firing/new/created/recovery` 仅在迁移兼容层读取，响应不再扩散旧口径。
- 无数据是明确的评估状态。策略可关闭无数据告警，或配置无数据持续周期与级别；查询失败是 `unavailable`，不得当成无数据、触发或恢复。

## 策略模型与执行语义

策略只作用于一个 APM Service，`environment` 必填；`endpoints` 可为空或多选，空表示服务聚合；`version_mode` 为 `all/specific/grouped`，`specific` 必须提供版本，`grouped` 按 VictoriaTraces 对账形成的 APM Service Instance 版本目录分别维护评估目标。生产 Adapter 的查询 DTO 必须携带版本。

指标固定为 `error_rate / p95 / p99 / throughput / no_traffic`。不接受 MonitorObject、采集插件、任意表达式、LogSQL 或日志组。每条策略包含：

- `evaluation_interval`：1–60 分钟；Beat 每分钟扫描到期策略，任务按策略独立投递。
- `metric_window`：1–1440 分钟；每次从 VictoriaTraces 查询该窗口。
- `aggregation`：`avg / max / min / last`；只对 APM 定义的指标序列聚合。
- 1–3 条不同级别阈值；阈值比较符一致，数值有限且按严重度保持单调，避免同一值产生歧义。
- `trigger_after` 与 `recover_after`：分别表示连续满足和连续不满足的评估次数。
- `no_data_after` 与 `no_data_severity`：两者同时为空表示关闭；启用后连续无数据达到次数才触发，并在数据恢复且连续健康后自动恢复。

评估锁内重读策略、目标状态与当前活动 Alert。评估游标为 `policy + target identity + scheduled_at`，重复或乱序执行不产生重复 Event。策略修改会重置未来评估计数，但不修改既有 Alert/Event/Snapshot；删除策略使用 `SET_NULL` 保留历史。

## 深模块 seam 与测试面

### `DjangoApmPolicyService.evaluate(policy_id, evaluated_at)`

隐藏 VictoriaTraces 查询、窗口聚合、多级阈值、连续命中、无数据、恢复、并发仲裁和生命周期写入。调用方只需提供策略与调度时间；测试用内存 TelemetryStore Adapter，生产用 VictoriaTraces Adapter。

### `ApmEventSnapshotStore.stage/persist/serialize`

隐藏 schema 校验、`event_id` 去重、DB 身份索引、压缩对象存储、失败状态、重试和保留期。一个 Event 对应一条索引，Alert 通过集合关系取得完整生命周期快照。

### `ApmNotificationOutbox.deliver_pending()`

沿用现有 APM outbox 的幂等键、claim TTL、有界指数退避、终止失败与人工重投。快照与投递记录完全独立；通知失败不改 Event/Snapshot。

### DRF 与页面 seam

- `/api/v1/apm/policies/`：CRUD、列表启停、真实预览。
- `/api/v1/apm/alerts/`：活跃/历史、筛选、时间范围、分布；活动告警可人工关闭。
- `/api/v1/apm/alerts/{id}/`：Alert 聚合与事件时间线。
- `/api/v1/apm/alerts/{id}/snapshots/`：按事件返回持久化快照；对象载荷过期或暂不可用时仍返回 DB 语义快照和明确状态。

所有对象读取先按 `ApmServiceOrganization` 或事件固化的 `organizations` fail-closed 过滤。列表最多 100 条；详情 ID 不可跨组织枚举。

## 快照 Schema 与持久化

快照 `schema_version=1`。PostgreSQL 永久保存足以解释事件的不可变语义索引：

- Alert/Event 身份、动作、发生时间、保留截止时间、组织快照；
- 策略快照：ID、名称、指标、窗口、聚合、阈值集合、连续触发/恢复、无数据配置；
- 对象快照：Service UUID、namespace/name、端点集合或当前端点、环境、版本；
- 评估快照：值、单位、比较符、命中阈值/级别、数据状态；
- Trace 检索上下文：受控的服务、端点、环境、版本、时间范围，不含任意查询表达式。

指标序列以 `S3JSONField(bucket=apm-alert-snapshots, compressed=true)` 保存为独立 payload。payload 只追加一次且不覆盖；DB 行先以 `pending` 创建，同时保存最多 240 点的有界 staging。上传成功变为 `available` 并立即清空 staging；失败变为 `unavailable`，保留 staging、错误码和重试计数。领域 Event 不因对象存储失败回滚；分钟级补偿任务最多重试 8 次。读取时若对象已按保留期删除，返回 `expired`，不得重新查询当前策略或 VictoriaTraces 冒充历史。

默认保留：Alert/Event/DB 语义快照不由 payload 清理任务删除，随业务审计数据保留；对象指标序列 90 天。清理任务只删除已到期 payload 并把状态置为 `expired`，不删除 DB 身份索引；若对象删除失败则保留对象索引并继续有界补偿，不能把遗留对象伪装成已清理。清理按不可变主键 keyset、有界批次执行，失败可重试。

## 页面设计

策略列表保留搜索、列表内启停和明确的目标范围。新建/编辑使用独立路由，左侧四步垂直 Steps：基本信息、指标定义、告警条件、通知配置；表单不显示启停。右侧显示变量表和来自策略 preview 接口的真实指标趋势、阈值线与数据状态。

告警页使用活跃/历史 Tab、级别/服务/指标/动作筛选、时间范围、分布图和数据表。详情使用 880px Drawer，包含“告警”和“事件快照”两个 Tab。用户选择事件后，趋势只读取对应 Event Snapshot，绘制当时阈值线和事件点；`unavailable/expired` 显示可解释状态，不回退到实时查询。

所有新增组件保持 APM app-local，复用 Ant Design、`ApmRouteShell`、`ApmSurface`、`ApmDataTable`、`CatalogState` 和现有趋势图，不新增 shared 抽象，不修改 Storybook。

## 迁移、发布与回滚

1. 先增量创建策略条件、策略目标字段、Alert/Event 新状态字段、Snapshot 索引/payload 与必要索引；旧列暂时保留以支持滚动发布。
2. 数据迁移把旧单阈值转换为一条阈值条件；`duration_window` 同时映射到 `metric_window` 和 `trigger_after` 的兼容默认值，`recovery_window` 映射到 `recover_after`；旧 Alert `firing` 映射 `active`，旧 Event `created/recovery` 映射 `triggered/recovered`。
3. 旧事件没有可靠的历史 VictoriaTraces 序列，不伪造快照。为其创建 `schema_version=1` 的 DB 语义快照索引，payload 状态为 `unavailable`、原因 `legacy_snapshot_unavailable`。
4. 部署顺序为迁移 → Server/Worker/Beat → Web。迁移本身不访问 VictoriaTraces、MinIO 或通知服务，不扩大启动依赖。
5. 回滚代码前先保留新增表和兼容列；Django 迁移可逆回旧枚举/单阈值，但会丢弃新增多级条件、端点/版本和 payload 索引，因此生产回退以 `git revert` + 保留 schema 为首选，不在紧急回滚中逆向删表。

## 验收矩阵

- 校验：环境必填、端点多选、版本语义、指标白名单、有限阈值、严重度单调、周期上界、无数据成对配置。
- 评估：窗口聚合、执行周期、各比较符、多级触发/升级、连续触发、自动恢复、无数据、查询失败不推进状态、重复/乱序不重复事件。
- 生命周期：Alert 聚合多个 Event，人工关闭，策略修改/删除不改变历史，统一状态和动作。
- 快照：每个 Event 一条、并发 `event_id` 去重、策略/对象/阈值固化、事件点与序列、无数据快照、上传失败和补偿、过期仍可读 DB 语义。
- 权限：跨组织列表、详情、关闭、快照均拒绝且不可枚举。
- 通知：事务后 outbox、渠道隔离、有界重试、终止失败、人工重投、告警中心副本不回写。
- 页面：四步表单无启停、真实预览、活跃/历史筛选、分布、880px Drawer、两个 Tab、事件切换对应快照、loading/empty/error/expired。
