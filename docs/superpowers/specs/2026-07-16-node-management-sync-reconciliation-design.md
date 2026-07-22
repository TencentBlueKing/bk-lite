# 节点管理同步期望状态对账设计

- 日期：2026-07-16
- 状态：已批准，待实施计划
- 范围：`server/apps/cmdb`、`server/apps/node_mgmt`、`web/src/app/cmdb`
- 关联问题：projectmem #0242；`CMDB-F44`–`CMDB-F51`

## 1. 背景与结论

节点管理已有数据，但 CMDB“节点管理同步”页面长期显示两个自动开关开启、最近同步/采集时间为空且发现数为 0。调查确认存在两个可独立触发现象的断点：

1. `NodeMgmtSyncConfig` 默认开启自动同步和自动采集，首次读取只创建配置行，不创建对应的 django-celery-beat `PeriodicTask`。页面因此显示“已开启”，实际没有调度。
2. 同步调用 `NodeMgmt.node_list` 时没有传权限上下文、组织范围或 `skip_permission=True`。Node Management 当前对这种调用 fail-closed，稳定返回空列表。

现有链路还存在权限、更新事实、父子任务状态、并发、资源预算和跨系统配置交付缺陷。批准方案采用“期望状态对账”：`NodeMgmtSyncConfig` 表达期望状态，Beat 周期任务和各区域节点采集配置表达实际状态，幂等 Reconciler 负责首次初始化、开关变化、部署重启和运行态漂移的收敛。

## 2. 目标与非目标

### 2.1 目标

- 首次打开页面时，默认开关与真实周期任务一致。
- 关闭、重新开启和重复切换均幂等，后端强制 `auto_collect_enabled => auto_sync_enabled`。
- 配置开启但周期任务或区域节点配置缺失时能够检测并恢复。
- Beat 系统执行和用户手工执行使用不同、明确的授权主体。
- 同步能够真实取得 Node Management 节点，并区分合法空源与授权/调用契约错误。
- 已有 CMDB 主机按真实字段差异更新，不再把未写入误报为更新成功。
- 自动采集等待有效同步结果；子任务投递不等于采集成功。
- 页面展示期望开关和实际健康状态，异常状态可行动。
- 新行为遵循 TDD，核心状态和授权逻辑覆盖率不低于 90%。

### 2.2 非目标

- 本次不重写通用 Celery、采集或 NATS 框架。
- 本次不建设通用工作流编排平台。
- 本次不引入审批、维护窗口或复杂报表。
- 不改变 Node Management 的 fail-closed 安全默认值。

## 3. 方案选择

### 3.1 备选方案

1. **最小热修**：首次创建配置时补建 Beat 任务，并为系统 RPC 增加 `skip_permission=True`。改动小，但不能修复任务漂移、采集抢跑和错误成功。
2. **期望状态对账（采用）**：以配置为期望状态，使用幂等 Reconciler 对账周期任务和区域节点配置，并补齐主体、前置条件、状态和可观测性。
3. **完整执行架构重构**：一次性引入租约、父子 execution、delivery、deadline 和补偿状态机。可靠性最高，但超出本次可控范围。

采用方案 2，并让运行与区域状态具备未来升级为方案 3 的稳定身份和代次字段。

## 4. 核心对象与职责

### 4.1 `NodeMgmtSyncConfig`

全局唯一的期望状态源。增加数据库可证明的 singleton 业务键，禁止并发首次访问创建多行。保存：

- 自动同步、自动采集及各自周期；
- 对账状态 `healthy | reconciling | degraded`；
- 最近对账时间和稳定错误码/脱敏摘要；
- 配置版本，用于拒绝旧请求覆盖新状态。

约束：自动采集开启时自动同步必须开启。关闭自动同步时，后端强制同时关闭自动采集，不能依赖前端联动。

### 4.2 `NodeMgmtSyncReconciler`

只负责把期望状态收敛为实际状态：

- 幂等创建、更新或删除同步/采集 `PeriodicTask`；
- 校验 task path、cron、enabled 状态，而非只判断名称存在；
- 对账各云区域隐藏 `CollectModels` 和 Node Management 节点配置；
- 对失败区域保留 generation、阶段、稳定错误码和重试状态；
- 返回结构化差异与修复结果，不直接拼接面向用户的原始异常。

触发点：首次配置创建、配置 PUT、配置 GET 健康检查、同步/采集执行前置检查、服务启动初始化命令。周期任务过期但没有任何运行记录时，页面按 `2 × interval + grace` 判定 `schedule_overdue`，从而暴露 Beat/Worker 不工作。

### 4.3 `NodeMgmtSyncRun`

表达一次可观察 execution，而不只是 UI 日志。状态集合：

- `waiting_sync`
- `running`
- `submitted`
- `success`
- `partial_success`
- `blocked`
- `failed`
- `timeout`

保存稳定 reason code、脱敏摘要、开始/投递/完成时间。`last_sync_at` 和 `last_collect_at` 只在定义明确的最终完成状态推进。

### 4.4 区域运行/交付状态

新增独立的 `NodeMgmtSyncRegionState`，让每个父运行按云区域保存稳定子 execution 身份、generation、接入点、实例数量、投递状态和实际终态；不得仅依赖可被并发覆盖的聚合 JSON 判断完成。节点配置 delete→push 同样按区域和 generation 持久化阶段，使 push 失败后可以从 `PUSH_PENDING/DEGRADED` 重试，旧 generation 不得覆盖新配置。

## 5. 开关与调度状态机

| 用户操作 | 期望同步 | 期望采集 | Reconciler 结果 |
|---|---:|---:|---|
| 首次打开 | 开 | 开 | 创建唯一配置和两个唯一周期任务；采集等待首次同步 |
| 关闭自动采集 | 开 | 关 | 保留同步任务，删除采集任务，停用区域采集配置 |
| 关闭自动同步 | 关 | 强制关 | 删除两个周期任务，停用区域采集配置 |
| 重新开启自动同步 | 开 | 仍为关 | 只恢复同步任务 |
| 再开启自动采集 | 开 | 开 | 恢复采集任务；无有效快照时先同步 |
| 配置开但周期任务丢失 | 按配置 | 按配置 | 标记漂移并幂等恢复 |
| 重复打开或重复切换 | 不变 | 不变 | 不产生重复配置、任务或节点下发 |

配置和 django-celery-beat 位于同一关系库时，在同一事务中完成期望状态及周期任务变更。Node Management 属于外部副作用，只能在数据库提交后按持久化 generation 交付和补偿，不能用数据库回滚假装撤销远端 delete/push。

## 6. 同步数据流

```text
Beat 系统主体 / 平台管理员手工主体
  -> NodeMgmt.node_list(明确授权上下文)
  -> 有界分页、去重与 deadline
  -> 非容器节点按云区域分组
  -> 查询各区域容器接入点
  -> CMDB host before/after 差异
  -> create / update / unchanged / failed
  -> 区域隐藏采集任务与节点配置期望状态
  -> NodeMgmtSyncRun 最终状态与 last_sync_at
```

### 6.1 主体与权限

- Beat 自动同步是可信系统作业，RPC 显式传 `skip_permission=True`。
- HTTP 手工全局同步/采集仅允许平台管理员，不得把普通用户提升为 `system`。
- 普通组织用户的展示数据按组织裁剪；不能读取其他组织 IP、运行明细或错误。
- 配置 GET 使用 View 权限；配置 PUT 使用配置管理权限，至少为 `auto_collection-Execute`。拒绝路径在进入 Service 前终止，确保零副作用。

### 6.2 节点与资产事实

- Node Management 合法返回 0 条时记录 `source_empty`。
- 权限上下文缺失、RPC 协议错误或调用失败不得归类为空源。
- 已有 host 必须比较 organization、OS、名称、node_id、cloud_name 等受模型约束字段。
- 无变化计 `unchanged`；有变化且统一实例更新链路成功才计 `updated`。
- 单节点失败不中断整批，但整次运行至少为 `partial_success`，并保存稳定节点级错误码。

### 6.3 资源边界

分页必须具备 max pages、max nodes、去重进度和整次 deadline。达到上限时 fail-closed，停止后续图写与节点配置下发。已有 host 查询按区域/IP 定向或一次有界加载，禁止每个区域重复全量扫描全部 host。

## 7. 采集数据流与状态真实性

采集前置条件：

- 最近同步存在有效最终状态；
- 至少存在一个区域隐藏采集任务；
- 区域任务存在实例和可用容器接入点。

处理规则：

- 缺同步结果：创建采集 run=`waiting_sync`，触发/等待同步。
- 同步失败：采集 run=`blocked`，reason=`sync_failed`。
- 无容器接入点：区域 reason=`no_access_point`，父运行按区域结果聚合。
- 同步和采集同一分钟触发：采集等待当前同步 generation，不能读取旧/空快照抢跑。
- `CollectModelService.exec_task` 成功投递只把区域和父运行推进到 `submitted`。
- 所有区域实际进入 SUCCESS/PARTIAL/ERROR/TIMEOUT 后，父运行才聚合成最终状态。
- `last_collect_at` 只在实际完成时更新；投递时间使用独立 `submitted_at`。

## 8. API 与页面契约

配置/展示响应除现有字段外包含：

- `schedule_status`: `healthy | reconciling | degraded`
- `sync_task_exists`
- `collect_task_exists`
- `collect_prerequisite_status`: `ready | waiting_sync | no_access_point`
- `last_reconciled_at`
- `reconcile_error`: 稳定错误码和脱敏摘要

页面同时展示期望开关与实际健康状态。`degraded`、`waiting_sync`、`blocked` 必须说明下一步动作。刷新按钮只刷新状态；若保留手工执行，使用独立按钮和平台管理员权限。页面不得把“任务已投递”展示为“采集成功”。

## 9. 错误与恢复

- Beat 对账失败：期望配置保留，健康状态为 `degraded`，后续启动、GET、PUT 或执行前检查继续重试。
- NodeMgmt RPC 失败：本次同步失败，不生成空快照，不推进成功时间。
- 单节点失败：记录脱敏错误并继续其他节点。
- 节点配置 delete 成功、push 失败：停留在可重试阶段，下一次 Reconciler 继续 push。
- 旧 generation 晚到：条件更新失败，不覆盖新状态。
- 错误只保存稳定错误码和脱敏摘要；禁止把 RPC 原始响应、连接串、凭据写入日志、数据库或 API。

## 10. TDD 与验收矩阵

### 10.1 首次打开

- 空数据库首次 GET 只创建一条 singleton 配置。
- 默认两个开关开启时创建两个正确且启用的 PeriodicTask。
- 连续 GET 和并发首次 GET 不产生重复配置或任务。
- Beat 创建失败时响应为 `degraded`，不能只显示开启。
- 首次采集先于同步时进入 `waiting_sync`。
- 系统 RPC 明确携带 `skip_permission=True` 并能取得真实 NodeService 测试数据。

### 10.2 关闭与重新开启

- 关闭采集只删除采集任务并保留同步任务。
- 关闭同步由后端强制关闭采集并删除两个任务。
- 直接提交“同步关、采集开”被拒绝或归一化为均关闭。
- 重复关闭无重复远端副作用。
- 重新开启同步只恢复同步任务；采集保持关闭。
- 再开启采集恢复采集任务和区域节点配置。
- 无同步快照时等待同步；同步失败时 `blocked(sync_failed)`。
- 配置为开启但 PeriodicTask 被删除时能够检测并恢复。
- delete/push 任一阶段失败后能按区域幂等重试。

### 10.3 数据、权限与状态

- 无权限上下文的 NodeService 保持 fail-closed；系统主体和用户主体分别验证。
- 平台管理员全局路径、普通组织裁剪路径和越权零写入均有测试。
- 新主机创建、已有主机真实更新、无变化 unchanged、单节点部分失败、重复同步幂等均验证最终数据库/图事实。
- 子任务拒绝不进入 executed；成功投递为 submitted；实际 SUCCESS/ERROR/TIMEOUT 聚合父状态。
- `last_collect_at` 仅在实际终态更新。
- 同步/采集竞跑、重复 callback、旧 generation 晚到均保持状态正确。

### 10.4 测试纪律与门禁

- 每个新增行为先运行旧实现并确认测试按预期 RED，再写最小实现。
- 使用真实 ORM 和 django-celery-beat 模型；只 Mock NodeMgmt、broker、图存储等不可控边界。
- 断言最终配置、PeriodicTask、运行状态和资产事实，不以“Mock 被调用”代替行为证明。
- Reconciler、状态转换、权限和 RPC 契约覆盖率不低于 90%；本次涉及模块总体不低于 75%。
- 定向测试通过后运行 CMDB 回归和 Server 模块门禁；Web 运行 `pnpm lint && pnpm type-check`。

## 11. 实施分层

1. **阻断修复**：首次调度一致性、开关后端约束、NodeMgmt 系统查询契约、配置权限、真实 host 更新。
2. **状态闭环**：采集前置同步、submitted/blocked/timeout、区域子 execution 和真实父终态。
3. **恢复与规模**：singleton/generation、启动和运行态 Reconciler、节点配置交付补偿、分页与 deadline 预算。
4. **页面闭环**：实际健康状态、可行动错误、组织裁剪和独立手工执行入口。

每一层独立完成 RED/GREEN、回归和覆盖率门禁后再进入下一层，避免把多个根因揉成一次不可验证的大改。

## 12. 已批准决策与待确认项

已批准：

- 采用期望状态对账，而不是只补首次创建或一次性完整重构。
- 首次打开、关闭、重新开启、重复操作和运行态漂移均属于必测契约。
- Beat 与用户主体分离；采集等待同步；submitted 不等于 success。
- 合法空源、权限/协议错误、无接入点、同步失败必须分别表达。
- 核心状态、授权和失败恢复采用真实行为测试与 TDD。

待确认项：无。
