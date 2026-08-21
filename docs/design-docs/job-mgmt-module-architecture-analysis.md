# JobMgmt 模块架构与代码结构分析

> 分析日期：2026-08-21
> 分析范围：`server/apps/job_mgmt/`，以及直接相连的 HTTP/OpenAPI/NATS、Celery/Beat、数据库、JetStream、MinIO、NodeMgmt、Ansible 和远端目标边界。
> 分析方式：沿“可信执行命令—计划与派发—远端执行—逐目标结果—终态裁决—完成副作用”完整闭环分析，不按单个 tech-debt 或大文件逐项罗列。

## 1. 结论摘要

JobMgmt 已经具备作业平台的关键骨架，而不只是“Celery 调一个远端接口”：

- `JobExecution` 作为执行聚合，脚本、文件分发、Playbook 和定时任务共用主状态；
- worker 使用数据库行锁 claim `PENDING → RUNNING`，避免重复消费同时执行；
- 取消采用 `CANCELLING` 过渡态、终态行锁和超时兜底；
- Ansible 回调具有一次性 attempt/token，陈旧回调不能覆盖当前执行；
- `JobCompletionOutbox` 已具备唯一幂等键、短 lease、失败退避和 Beat 重扫；
- `TargetTeamMembership` 是可查询的团队投影，并能阻止并发旧对象覆盖新团队。

这些是应该保留并扩展的“深模块”能力。

但当前核心生命周期没有收敛：Sidecar 与 Ansible 是两套终态系统。Sidecar 正常完成、危险命令早退、Ansible 提交失败和部分 Playbook 失败直接改 `JobExecution`，然后即时发 JetStream sentinel 或投 Celery callback；Ansible 真实回调与取消才在数据库事务中写 Completion Outbox。因此同一个“作业完成”在不同路径下具有不同的崩溃恢复、重试和幂等语义。

同时存在三个会直接限制维护、扩展和容量的结构性边界：

1. legacy NATS 执行入口把消息体中的 `team` 当授权事实，远程脚本和文件分发缺少可信 caller boundary；
2. worker claim 后没有 heartbeat/lease/reaper，进程退出会留下长期 `RUNNING`，并持续阻塞 scheduled `skip/queue`；
3. 全部目标和 stdout/stderr 结果聚合到 `JobExecution.execution_results` 单个 JSON 行，且每个 execution 自建线程池，没有团队、区域和执行器级全局预算。

建议短期先统一信任和终态，不做服务拆分；中期建立 `ExecutionPlan + TargetWorkItem + ExecutionAttempt`，将执行分区、容量预算和恢复协议持久化；长期再依据独立 SLO、吞吐和安全隔离需求决定是否拆远端执行服务。

## 2. 模块规模与当前职责

本次只统计生产 Python（排除 migrations/tests），约 11,370 行；测试目录有 69 个 Python 文件、约 927 个测试函数。HTTP 侧有 9 个 Router 和一组开放 API，NATS 侧注册 11 个 handler。

当前职责可归为六组：

| 能力 | 当前实现 | 主要事实/外部依赖 |
|---|---|---|
| 作业资源目录 | Script、Playbook、Target、DistributionFile、ScheduledTask | Django DB、MinIO |
| 执行接入 | ViewSet、OpenAPI、`nats_api.py` | 登录用户、JWT/NATS、调用方消息体 |
| 执行编排 | `ExecutionService`、scheduled task、Celery dispatch | Celery broker、Beat |
| 远端运行 | Script/File Runner、PlaybookExecution、Ansible Executor | Node sidecar、SSH、WinRM、Ansible |
| 状态与取消 | `prepare_execution`、CancellationService、AnsibleCallbackService | `JobExecution` 行锁 |
| 完成投递 | JetStream log/sentinel、callback tasks、Completion Outbox | NATS、Webhook、Object Store |

生产代码还直接依赖 NodeMgmt 的 `Node`、`CloudRegion`、S3 helper，以及 SystemMgmt 的 token、GroupUtils 和 operation log helper。这些依赖目前多为实现导入，不是稳定 Port，因此 NodeMgmt/SystemMgmt 的内部模型或工具变化会直接传播到 JobMgmt。

## 3. 现状架构图

- [JobMgmt 现状架构（Archify HTML）](job-mgmt-current.architecture.html)
- [JobMgmt 现状架构源文件](job-mgmt-current.architecture.json)
- [JobMgmt 现状架构静态图](job-mgmt-current.architecture.light.png)

现状图表达的是一个模块内的三条边界：

```text
HTTP / OpenAPI / NATS / Schedule
  → ExecutionService 或 nats_api 内的第二套应用逻辑
  → JobExecution(PENDING) + Celery
  → Sidecar Runner ───────────────┐
  → Ansible Async + Callback ─────┼→ JobExecution terminal
                                  └→ completion effects
```

关键不是 Runner 文件数量，而是同一个终态在图中分成了 `direct finalize` 和 `transactional outbox` 两条路径。

## 4. 应保留的架构基础

### 4.1 执行 claim 是正确的并发裁决点

worker 在 `prepare_execution` 中锁定执行行，仅允许 `PENDING` 转为 `RUNNING`。重复 Celery delivery、撤销与 worker 并发不会同时启动同一个 execution。这一约束应成为后续 `ExecutionAttempt` 的基础，而不是退回进程内标志。

### 4.2 取消是明确的状态协议

取消服务在行锁内重新校验团队范围：未开始任务直接进入 `CANCELLED`；运行中任务进入 `CANCELLING` 并记录兜底时间。Beat 重扫到期记录，再由 `finalize_cancelling_execution` 在行锁内补齐“远端结果未知”并写终态，见 [tasks.py:53](../../server/apps/job_mgmt/tasks.py#L53)。

这个模型正确地区分了“已收到取消意图”和“远端执行已经停止”。后续扩展时不要把 `CANCELLING` 直接解释成远端无副作用，也不要把 Celery revoke 当成强终止证明。

### 4.3 Ansible callback identity 与终态锁值得复用

Ansible 提交前签发 callback attempt 和 token hash；回调在写终态前重新验证并锁定 execution。旧 attempt、重复终态和取消超时后的迟到回调都有显式裁决规则。这个协议比只校验 `task_id` 或 NATS subject 安全，应推广到所有异步 Executor Adapter。

### 4.4 Completion Outbox 已经是可用的可靠性内核

`JobCompletionOutbox` 的 `idempotency_key` 唯一，并持有状态、attempt、next retry、lease token 和 expiry，见 [completion_outbox.py:8](../../server/apps/job_mgmt/models/completion_outbox.py#L8)。Beat 定期重扫 broker 入队失败和过期 lease，见 [tasks.py:118](../../server/apps/job_mgmt/tasks.py#L118)。

目标架构无需再造一套 MQ 可靠投递框架；应把所有终态路径接入这套 Outbox，并在 payload schema 上做版本化。

### 4.5 Target 团队投影是正确的查询 seam

`Target.team` JSON 仍是历史表示，但 `TargetTeamMembership` 已提供规范化、可索引投影和并发保存保护。短期应通过 Target Query/Command Port 使用该投影；后续再决定是否把它升级为唯一事实。不要让调用方重新使用 JSON contains 作为长期授权接口。

## 5. 核心执行与数据流

- [JobMgmt 执行生命周期（Archify HTML）](job-mgmt-execution-lifecycle.dataflow.html)
- [JobMgmt 执行生命周期源文件](job-mgmt-execution-lifecycle.dataflow.json)
- [JobMgmt 执行生命周期静态图](job-mgmt-execution-lifecycle.dataflow.light.png)

### 5.1 接入与信任流

可信 OpenAPI 文件分发已经限制目标最多 500 个，并由网关注入用户/团队；但 legacy `job_script_execute` 直接读取 `data.team`，随后用同一值做危险规则检查并落入 execution，见 [nats_api.py:201](../../server/apps/job_mgmt/nats_api.py#L201)。`job_file_distribute` 的 legacy 入口默认开启，只有新包装层传入 `trusted_actor`，见 [nats_api.py:297](../../server/apps/job_mgmt/nats_api.py#L297)。

这不是“少一个 if”的问题，而是 Command Contract 不同：

```text
新 OpenAPI：Transport-verified actor → server-resolved team → scoped resources
legacy NATS：message body team → same team treated as authorization claim
```

脚本执行和文件分发具有远端副作用，不能只依赖 NATS ACL 的正确配置。目标接口必须只接受服务端构造的：

```text
ActorContext(principal, tenant, current_team, audience, auth_version)
ExecutionCommand(command_id, job_spec_ref|inline_spec, target_refs, deadline, callback_ref)
```

调用方不得通过普通 payload 覆盖 principal/team/audience。

状态和资产查询同样存在范围不一致：`job_status_batch_query` 可按任意 ID 批量读取执行状态，见 [nats_api.py:504](../../server/apps/job_mgmt/nats_api.py#L504)；`job_target_list` 使用 `Target.objects.all()`，且 `page_size=-1` 返回全部目标，见 [nats_api.py:647](../../server/apps/job_mgmt/nats_api.py#L647)。这些接口应与执行命令一起迁移到 NATS v2，而不是只单独补分页。

### 5.2 计划、选路与区域分区

当前 `_should_use_ansible` 只查询第一个手动目标并根据其 driver 选择整个 execution 的路径，见 [execution_base_service.py:157](../../server/apps/job_mgmt/services/execution_base_service.py#L157)。进入 Ansible 后虽按 `cloud_region_id` 分组，却在多区域时只记录 warning 并执行第一组，见 [execution_base_service.py:248](../../server/apps/job_mgmt/services/execution_base_service.py#L248)；Playbook 路径相同行为见 [playbook_execution.py:107](../../server/apps/job_mgmt/services/playbook_execution.py#L107)。

Serializer 只验证手动目标是否存在，不验证 driver/region 同质，见 [validators.py:106](../../server/apps/job_mgmt/serializers/validators.py#L106)。因此“混合目标”会被接收，随后部分目标从未提交。缺失结果最终可能被 callback normalization 标记失败，但这不能替代正确计划。

目标设计应在创建 execution 前生成不可变 `ExecutionPlan`：

```text
TargetRef resolution
  → capability(driver, os, credential mode)
  → partition by team + driver + cloud_region
  → validate executor availability
  → estimate target_count / files / timeout / output budget
  → create TargetWorkItems
```

不支持混合分区时应 fail-closed；支持时，每个 partition 单独 dispatch、claim、retry 和聚合，不能再用第一条目标隐式决定全部行为。

### 5.3 Sidecar 并发与容量

Sidecar Runner 每批创建 `ThreadPoolExecutor(max_workers=len(batch))`，单 execution 默认最多 10 个线程，见 [script_execution_runner.py:97](../../server/apps/job_mgmt/services/script_execution_runner.py#L97)；默认值来自 `JOB_EXECUTION_MAX_WORKERS=10`。这个限制只约束单个 execution：

```text
实际远端并发上限
≈ Celery worker 并发 × 同时活跃 execution × JOB_EXECUTION_MAX_WORKERS
```

不同团队、云区域、Executor 和目标网络共享同一隐式资源池。任务高峰时，增加 Celery worker 会同时放大 NATS RPC、SSH/WinRM 连接、目标 CPU 和网络，而应用层没有 backpressure 或公平性。

应建立持久化/共享的预算维度：

- `global_active_targets`：平台总保护；
- `team_active_targets`：租户公平；
- `region_active_targets`：云区域/代理容量；
- `executor_active_targets`：Sidecar、SSH、Ansible 独立舱壁；
- `target_mutex`：同一主机是否允许并发高风险作业，由策略显式决定。

预算领取必须有 lease 与 expiry；不能只用进程内 semaphore，否则 worker 退出后容量永久丢失，多个 worker 也无法共享上限。

### 5.4 逐目标结果与大输出

`JobExecution` 同时保存 `target_list` 和 `execution_results` JSON，后者包含每个目标的 stdout/stderr/file_results，见 [execution.py:79](../../server/apps/job_mgmt/models/execution.py#L79)。Sidecar 先把所有结果保存在 Python list，全部完成后一次性写入；计数又在行锁内重读并扫描整个 JSON，见 [execution_base_service.py:113](../../server/apps/job_mgmt/services/execution_base_service.py#L113)。完成回调还会复制整份结果。

其成本不是单一 O(n) 循环，而是一组互相放大的容量问题：

```text
worker memory        O(targets × output)
DB row rewrite       O(all results payload)
terminal lock time   O(target count)
detail response      O(all results payload)
NATS callback        O(all results payload)
crash recovery       0 durable partial results for sidecar
```

目标事实应拆为：

```text
JobExecution(id, command, aggregate_status, counts, deadline, terminal_version)
ExecutionAttempt(id, execution_id, partition, lease, heartbeat, status)
TargetWorkItem(id, execution_id, target_ref, partition, status, attempt, timestamps)
TargetResult(work_item_id, exit_code, error_code, output_ref, summary, checksum)
```

短 stdout/stderr 可保留摘要；长输出写 JetStream/Object Store，数据库只保存 immutable `output_ref + checksum + size + retention`。查询按 cursor 分页，完成 callback 默认只发聚合与结果查询链接；确有需要时再提供有大小上限的分页明细。

### 5.5 终态分叉与不可恢复 RUNNING

Sidecar 正常完成由 `finalize_execution` 先写 results、再计数、再写终态，最后调用 `send_callback`，见 [execution_base_service.py:133](../../server/apps/job_mgmt/services/execution_base_service.py#L133)。`send_callback` 只是向 Celery 投递 HTTP/NATS callback task，见 [callback_service.py:42](../../server/apps/job_mgmt/services/callback_service.py#L42)，它不与终态事务绑定。

危险命令早退还会直接写 FAILED 并即时逐目标发布 done sentinel，见 [script_execution_runner.py:51](../../server/apps/job_mgmt/services/script_execution_runner.py#L51)。Playbook 不存在或提交失败也直接写 FAILED，部分路径甚至没有统一 callback，见 [playbook_execution.py:21](../../server/apps/job_mgmt/services/playbook_execution.py#L21)。

相比之下，Ansible callback 与取消在同一事务内调用 `enqueue_terminal_effects`。因此当前存在如下故障窗口：

```text
Sidecar：DB terminal committed → worker exits before Celery callback publish → completion lost
Sidecar：partial targets finished → worker exits before results JSON save → durable facts lost
Any runner：PENDING claimed as RUNNING → worker hard exits → no heartbeat/reaper → RUNNING forever
Scheduled skip/queue：stale RUNNING counted as active → future schedule keeps skip/requeue
```

应建立唯一 `TerminalReducer.complete(execution_id, expected_version, outcome)`：

1. 锁 execution 与对应 active attempt；
2. 校验允许的状态迁移和 callback/lease fencing token；
3. 从 TargetWorkItem 聚合 counts，不接收任意全量结果覆盖；
4. 在同一事务写 terminal state、terminal source/version；
5. 在同一事务生成 done sentinel、callback、cleanup Outbox；
6. 事务提交后只负责调度 outbox delivery，发布失败由 Beat 重扫。

所有正常完成、同步拒绝、提交失败、超时、取消和迟到回调都必须经过这个 reducer。

## 6. 结构性不合理设计与影响

| 优先级 | 架构主题 | 现状 | 维护/扩展影响 | 并发/性能/安全影响 |
|---|---|---|---|---|
| P0 | 远程执行缺少统一可信主体 | legacy `job_script_execute/job_file_distribute` 信任消息体 team；旧文件分发默认开启 | 每个入口重复身份、团队和目标校验，新功能容易落在较弱路径 | 总线 ACL 失配时可跨团队执行脚本/分发文件；危险规则也基于伪造 team |
| P0 | 终态与完成副作用双轨 | Sidecar/同步失败直接终态 + best-effort callback；Ansible/取消走 Outbox | 新 Runner 必须自行选择终态写法，语义继续分叉 | 崩溃窗口导致 callback/sentinel 丢失或重复，无法统一审计和补偿 |
| P0 | RUNNING 无执行租约 | claim 后只有状态，没有 heartbeat/lease/reaper | 无法回答“任务还活着还是 worker 已死”，人工处理成为正常流程 | stale RUNNING 永久占用 scheduled skip/queue；远端结果与本地状态漂移 |
| P1 | 第一个目标决定执行路径 | driver 只看首目标，多区域只执行第一组 | 增加 driver/region 组合会形成更多条件分支和隐式约束 | 合法请求只执行部分目标；回调补失败不能恢复遗漏的远端操作 |
| P1 | 单行结果聚合 | 全目标、stdout/stderr、文件明细写一个 JSON 行 | 字段 shape 变化影响模型、serializer、callback、stream fallback | 内存/行锁/DB/响应/消息载荷随目标和输出乘法增长；不能增量恢复 |
| P1 | 并发仅局部受控 | 每 execution ≤10 线程，无平台/团队/区域/执行器预算 | 扩 worker 或新增 Runner 会改变全局压力，没有稳定容量契约 | 高峰可压垮 NATS/SSH/Ansible/目标网络；团队间互相抢占 |
| P1 | NATS handler 是第二应用层 | 701 行 `nats_api.py` 内含校验、ORM、危险检查、派发、查询和兼容逻辑 | HTTP 与 NATS 的同一用例行为漂移，测试矩阵翻倍 | page/target/timeout/scope 限制不一致；回调和派发语义难统一 |
| P1 | 敏感查询无 scope/上限 | target list 全表且支持 `-1`；status batch 无身份和数量限制 | 每个消费者依赖内部 DTO，后续字段收紧形成兼容压力 | 资产枚举、任务状态探测和大查询放大 |
| P1 | 定时团队边界仍受 rollout flag 控制 | 新写入校验已收紧，但执行复核由默认 false 的开关决定 | 新旧 ScheduledTask 具有不同安全语义，迁移状态难推断 | 历史跨团队快照可能继续执行，直到显式 audit/apply/cutover |
| P2 | 派发语义不统一 | 普通入口 `.delay()` 后保存 task id；scheduled 先持久化 id 再 `send_task` | broker 不确定结果处理和测试需维护两套 | 发布成功但客户端报错、保存失败等边界行为不一致 |
| P2 | 跨模块实现直引 | 直接导入 Node/CloudRegion/S3、System token/GroupUtils/log helper | 上游模型变化传播到 JobMgmt，难用 contract tests 隔离 | 调用方可能绕过 Node/System 的统一 scope、审计和容量入口 |

危险命令/路径 blacklist 是必要的治理提示，但不是远端执行 sandbox。脚本可通过编码、间接调用或运行时下载绕过字符串匹配；高风险命令的真实控制必须依靠可信主体、目标 capability、审批/策略和最小权限凭据，不能把 `DangerousChecker.can_execute` 解释为“命令安全”。

## 7. 目标模块架构

- [JobMgmt 目标架构（Archify HTML）](job-mgmt-target.architecture.html)
- [JobMgmt 目标架构源文件](job-mgmt-target.architecture.json)
- [JobMgmt 目标架构静态图](job-mgmt-target.architecture.light.png)

目标仍可留在 Django 模块化单体中：

```text
HTTP / OpenAPI / NATS v2 / Schedule
  → Job Application
      → Job Catalog
      → Execution Policy Gate
      → Execution Planner
      → Budgeted Scheduler
      → Execution Kernel
      → Terminal Reducer

Execution Fact Store
  = JobExecution + ExecutionAttempt + TargetWorkItem + TargetResult

Event & Completion Store
  = log pointer + Completion Outbox + Delivery Receipt + Dead Letter

Executor Ports
  → Sidecar / SSH / WinRM / Ansible
```

### 7.1 深模块边界

- `JobApplication`：隐藏 HTTP/NATS/Schedule 的输入差异，只暴露 Execute、Cancel、Query、Retry；
- `ExecutionPolicyGate`：隐藏可信 ActorContext、团队范围、目标能力、高危策略和审批；
- `ExecutionPlanner`：隐藏资源快照、driver/region 分区、凭据 capability 和成本估算；
- `BudgetedScheduler`：隐藏队列、公平、全局预算、partition lease 和 backpressure；
- `ExecutionKernel`：隐藏 attempt claim、heartbeat、deadline、cancel、retry 和 executor protocol；
- `TerminalReducer`：隐藏唯一状态机、聚合计数、终态 fencing 和事务 Outbox；
- `ExecutionQuery`：隐藏分页结果、输出引用、敏感字段脱敏和团队范围。

目录划分只有在隐藏上述不变量时才有价值。单纯把 700 行 `nats_api.py` 拆成多个 handler 文件，不会解决双应用层和信任边界问题。

### 7.2 状态机最低约束

```text
PENDING → DISPATCHED → RUNNING → {SUCCEEDED, FAILED, TIMED_OUT}
                    ↘ CANCELLING → CANCELLED

Attempt: READY → LEASED → RUNNING → {DONE, RETRYABLE, LOST}
WorkItem: READY → RUNNING → {SUCCESS, FAILED, CANCELLED, UNKNOWN}
```

约束：

- 状态迁移必须带 expected version 或 lease/callback fencing token；
- terminal state 只允许 TerminalReducer 写；
- `LOST` 表示执行控制面已失联，不等同于远端没有副作用；
- retry 必须产生新 attempt，不覆盖旧 attempt 的证据；
- cancel timeout 可以把未确认目标标为 `UNKNOWN/CANCELLED`，但要保留迟到结果的 reconcile policy；
- 任何 terminal state 都必须存在 completion outbox intents。

## 8. 优化路线、优先级与验收

### 8.1 P0：1—2 个迭代

#### A. 关闭无可信身份的远程执行入口

1. 新建 NATS/OpenAPI v2 ExecutionCommand，只接受 transport-injected ActorContext；
2. 脚本执行、文件分发、目标列表、状态和详情统一走 scoped application service；
3. legacy `job_script_execute/job_file_distribute/job_target_list/job_status_batch_query` 增加拒绝计量和明确截止日期；
4. 先把 legacy 文件分发默认开关改为关闭，再移除 subject 注册；
5. 所有列表设置 hard limit、cursor 和字段白名单。

验收：伪造 payload team 不能改变服务端 principal/team；无身份请求失败关闭；跨团队目标在 execution 创建前拒绝；旧 subject 调用量为零后删除。

#### B. 统一所有终态到 Completion Outbox

1. 提取 `TerminalReducer`，先保持现有 `JobExecution` schema；
2. Sidecar finalize、危险规则早退、dispatch/Ansible/Playbook 提交失败全部改走 reducer；
3. `send_callback` 仅保留为 Outbox delivery adapter，Runner 不再直接调用；
4. done sentinel、Web callback、NATS callback、Playbook cleanup 全部由同事务 outbox intent 表达；
5. 给每种 terminal source 建 contract test 和 crash-window test。

验收：任一路径 terminal 后都能查询到预期 outbox records；模拟事务提交后 worker 退出，Beat 能完成投递；重复 complete 不生成重复副作用。

#### C. 增加执行 lease、heartbeat 与 stale reaper

1. 在不引入 WorkItem 前，先给 JobExecution 增加 `attempt_id/lease_expires_at/heartbeat_at`；
2. Runner 在每批目标之间、Ansible 提交前后刷新 heartbeat；
3. Beat 将过期 RUNNING 标记为 `LOST` 或进入 reconcile，而不是直接假设 FAILED；
4. Ansible 结合 callback attempt 决定等待、查询或失败；Sidecar 对已落日志/结果做最大程度恢复；
5. scheduled concurrency 判断不把已过 lease 的 RUNNING 永久视为 active。

验收：kill worker 后在明确窗口内收敛；stale execution 不永久阻塞 schedule；迟到 callback 受 fencing 控制且不覆盖新 attempt。

### 8.2 P1：2—4 个迭代

#### D. 建立 ExecutionPlan 与分区校验

1. 解析 target ref 时校验 team、存在性、driver、OS、credential capability 和 region；
2. 生成 `(team, driver, cloud_region)` partitions；
3. 暂不支持多分区的 job type 在接入时 fail-closed；
4. 支持后每分区生成 attempt，聚合器等待全部分区终态；
5. `credential` 模式未实现时整组明确拒绝，禁止静默跳过目标。

#### E. 引入共享并发预算

1. 从数据库 lease 或可证明原子的共享存储开始，不使用 worker 内全局变量；
2. 先设 global/executor/region 三层，采集 queue wait、active、timeout、reject 指标；
3. 再加入 team fairness 和 target mutex；
4. scheduler 只发放可执行 WorkItem，Celery worker 数量不再直接等于远端并发倍增器；
5. 预算配置有 hard maximum，避免错误配置把目标主机打满。

#### F. 迁移逐目标事实

1. 双写 `TargetWorkItem/TargetResult`，`execution_results` 保留读取投影；
2. Runner 每目标完成即幂等 upsert，使用 `(execution, target_key, attempt)` 唯一约束；
3. 聚合计数用数据库增量或查询投影，不再锁住主行扫描大 JSON；
4. 输出超过阈值自动转 Object Store/JetStream，只保留摘要与 ref；
5. 详情与 callback 改为 cursor/summary contract，最后停止写大 JSON。

### 8.3 P2：4 个迭代以后

- 将普通执行和 scheduled 的 Celery dispatch 收敛为同一持久化派发协议；
- 用 `TargetDirectoryPort`、`IdentityScopePort`、`ObjectStorePort` 替代跨模块模型/helper 直引；
- 为脚本、文件、Playbook 建声明式 JobSpec schema/version，避免 execution 模型继续加类型专属字段；
- 将 scheduled migration flag 收敛为完成态：audit → apply → enforce by default → remove flag；
- 为 callback/output/target DTO 加 schema version、payload size 和 retention contract。

## 9. 后续设计提醒

1. 不要声称远端执行 exactly-once。系统最多证明命令唯一接收、attempt 有 fencing、结果可恢复；worker 或网络失联时远端副作用可能已发生。
2. 不要用 Celery task state 作为业务真相。业务 lease、attempt 和 terminal version 必须在数据库中可查询。
3. 不要让新的 Executor 自己写 `JobExecution.status`。所有终态都经 TerminalReducer。
4. 不要再接受可变目标字典作为长期契约。保存规范 TargetRef 与执行时 capability snapshot。
5. 不要用第一目标推断整批能力。所有目标先解析、分区和预算，再 dispatch。
6. 不要把“危险规则未命中”等同于安全。高危操作需要可信身份、目标范围、审批/策略和最小权限凭据。
7. 不要把完整 stdout/stderr 放入主表、列表接口或默认 callback。输出必须有大小、保留期和访问范围。
8. 不要把线程池大小当平台容量。容量是跨 worker、团队、区域和执行器的共享协议。
9. 不要在取消时声称远端已经停止。保留 `CANCELLING/UNKNOWN` 语义和迟到结果 reconcile。
10. 不要删除现有 Outbox lease、callback token、取消锁和 TargetTeamMembership 并发保护；它们应被纳入新内核，而不是重写成更浅的 helper。
11. 不使用 raw SQL；逐目标事实、预算和 lease 必须用 Django ORM 与数据库唯一约束/行锁实现，保持多数据库兼容。
12. 每个可靠性改动都要测试崩溃窗口：broker publish 不确定、事务提交后退出、lease 过期、重复 callback、取消与完成竞态、迟到结果和大目标集。

## 10. 完成标准

JobMgmt 的架构优化不是“文件更小”，而是下列问题可以由代码和数据直接回答：

- 谁以哪个可信身份发起了什么命令，允许操作哪些目标？
- 每个目标为什么由哪个 executor/region 执行，当前由谁持有 lease？
- worker 消失后，系统何时、按什么 fencing token 恢复？
- 每个目标的最新结果和历史 attempt 是否可独立查询？
- 哪个唯一 reducer 写入了终态，哪些完成副作用已经投递或待补偿？
- 当前团队、区域和执行器分别使用了多少预算，为什么发生排队或拒绝？

当这些答案不再依赖 worker 日志、消息体自报 team、第一目标推断和一个不断膨胀的 JSON 行时，该模块才真正具备可维护、可扩展、可恢复的作业平台边界。
