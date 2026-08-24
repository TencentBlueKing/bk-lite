# PatchMgmt 模块架构与代码结构分析

> 分析日期：2026-08-21
> 分析范围：`server/apps/patch_mgmt/`，以及直接相连的 HTTP/Beat、Celery、数据库、NodeMgmt、SystemMgmt、Ansible/Executor、SSH/WinRM、Linux Repo 与 WSUS 边界。
> 分析方式：按“补丁来源事实—基线与评估—风险投影—治理计划—逐主机执行—终态与后续动作”完整闭环分析，不按单个 tech-debt 或大文件逐项罗列。

## 1. 结论摘要

PatchMgmt 已经具备一套相当完整的治理系统，而不是简单的补丁 CRUD：

- `GovernanceTask + GovernanceTaskHost` 把父任务与逐主机执行事实分离；
- 主机任务以原子 `waiting → running` claim 和 `execution_token` 做 fencing，陈旧 worker 不能覆盖新结果；
- 安装、重启超时后进入 `reconciling`，通过只读核验判断远端真实状态，不自动重放未知副作用；
- 基线要求或绑定变化时用签名阻止旧评估结果回写；
- 周期评估通知有唯一 delivery、claim token、退避与重扫，已经形成可恢复投递闭环；
- 创建治理任务时锁定目标和基线绑定，并重新验证补丁仍属于当前基线、当前合规事实确为缺失。

这些能力应作为后续演进的可靠性内核保留。

当前最关键的问题不是某个 2,703 行文件本身，而是同一个业务闭环仍有三组不一致边界：

1. **治理终态和后续动作没有原子闭环。** 父任务终态事务提交后，才即时创建自动重启/验证任务并投 Celery；进程在两者之间退出会永久丢步骤，创建子任务后 broker 失败也没有原始意图可恢复。通知已经有 durable delivery，但治理链没有。
2. **周期评估和风险读侧以全库为容量单位。** 全局 `ScanSetting` 将所有 `PatchTarget` 放入一条任务并一次性扇出；风险 API 先计算全库主机×基线要求，再按请求目标权限过滤。团队边界只在结果阶段出现，成本和任务事实却已经跨团队混合。
3. **合规与补丁关系主要是“当前投影”。** 基线明确不做版本，`HostComplianceSnapshot` 每次评估删除重建，补丁依赖/替代又以 JSON ID 保存；当前页面可用，但历史审计、规则重放、关系完整性和规模化查询都会受限。

建议短期不拆微服务，先把 `Transition Intent/Outbox`、父任务原子 claim、周期扫描分区、同步租约和风险查询下推补齐；中期建立 `GovernancePlan + WorkItem + BudgetedScheduler`；长期再引入版本化基线、不可变评估证据和规范化补丁关系图。

## 2. 模块规模与职责边界

本次统计生产 Python 约 17,069 行（排除 migrations/tests）；测试目录有 41 个 Python 文件、至少 257 个显式测试函数。HTTP 侧注册 8 个 Router，另有 Celery/Beat、NATS 查询接口与多个远端执行适配器。

| 能力 | 当前实现 | 主要事实与外部依赖 |
|---|---|---|
| 补丁来源 | PatchSource、Repo/WSUS preview、selected ingest、来源删除快照 | Linux Repo、WSUS、HTTP/WinRM |
| 补丁目录 | Patch、Windows/Linux detail、source M2M | 依赖/替代 JSON IDs、文件/S3 |
| 基线与绑定 | PatchBaseline、BaselineRequirement、HostBaselineBinding | 当前清单，无不可变版本 |
| 合规与风险 | HostComplianceSnapshot、RiskService、三视角聚合 | 当前投影；请求时动态计算风险 |
| 治理编排 | GovernanceService、GovernanceTask、自动链路 | Celery、执行窗口、风险快照 |
| 逐主机执行 | patch_execution_service、路由与连接适配 | NodeMgmt、Executor、Ansible、SSH/WinRM |
| 收敛与通知 | Watchdog、reconcile、AssessmentNotificationDelivery | SystemMgmt、Celery broker |

模块直接导入 NodeMgmt 的 `Node`、`CloudRegion`、RegionService、Ansible resolver 与 S3 helper；直接调用 RPC Executor/Ansible/SystemMgmt，也直接使用 SystemMgmt operation log。它们目前多是实现级依赖，而非 PatchMgmt 稳定 Port。

PatchTarget 与 JobMgmt Target 有重叠，但二者领域语义并不完全相同：PatchTarget 持有补丁 OS、包管理与治理约束。短期不建议直接合表；应共享“目标目录查询、执行能力解析、远端命令执行、凭据引用”接口，PatchMgmt 保留自己的治理投影和策略。

## 3. 现状架构图

- [PatchMgmt 现状架构（Archify HTML）](patch-mgmt-current.architecture.html)
- [PatchMgmt 现状架构源文件](patch-mgmt-current.architecture.json)
- [PatchMgmt 现状架构静态图](patch-mgmt-current.architecture.light.png)

现状可以概括为三条相互连接但演进程度不一致的路径：

```text
来源同步 → Patch Catalog → 当前基线 → 当前合规投影
                                     ↓
HTTP / Beat → GovernanceTask → Celery 父任务扇出 → GovernanceTaskHost
                                                     ↓
                                              远端副作用与结果
                                                     ↓
                                    Watchdog / terminal follow-ups
```

目录和基线负责“应该是什么”，评估投影负责“现在是什么”，治理任务负责“如何从当前状态走到目标状态”。当前边界问题集中在这三类事实的版本、团队范围和终态事务没有采用同一套协议。

## 4. 应保留并扩展的架构基础

### 4.1 逐主机 WorkItem 已经存在雏形

`GovernanceTaskHost` 具有唯一 `(task, target_id)`、阶段、deadline、heartbeat、reconcile deadline、boot marker 和 execution token，见 [governance.py:112](../../server/apps/patch_mgmt/models/governance.py#L112)。它已经比将所有目标结果塞入父任务 JSON 更适合作为并发和恢复单位。

后续无需重建第二套执行记录；应把它演进为显式 WorkItem/Attempt：

```text
WorkItem(task, target, phase, partition, desired_state)
Attempt(work_item, token, lease, heartbeat, executor, started_at, outcome)
```

父任务继续保存摘要与用户命令快照，逐主机行保存可查询状态，较大日志/证据独立存储。

### 4.2 execution_token 是正确的陈旧写回防线

主机 worker 通过条件更新领取等待任务并生成新 token，见 [patch_execution_service.py:984](../../server/apps/patch_mgmt/services/patch_execution_service.py#L984)；结果更新同时匹配当前阶段与 token，失败时记录“忽略过期执行结果”，见 [patch_execution_service.py:1005](../../server/apps/patch_mgmt/services/patch_execution_service.py#L1005)。

后续拆分协议 Adapter 或增加重试时，不得只依赖 Celery task ID。所有远端回调、补偿核验和手工确认都应携带 attempt identity，并由数据库当前版本裁决。

### 4.3 未知副作用进入核验，而不是盲目重试

安装/重启发生 timeout 时，系统不会自动再执行一次危险命令，而是将主机进入 `reconciling`，由定时任务通过包状态或 boot marker 做只读判断；超过核验期限仍无法确认时进入 `pending_confirmation`。这是补丁系统必须保留的安全语义。

未来即使接入新的 Agent、Ansible 或云厂商通道，也要明确区分：

- transport failure：可以安全重投消息；
- command not started：可以重新领取；
- side effect outcome unknown：只能核验或人工确认；
- business precondition changed：计划失效，不得继续执行。

### 4.4 基线签名阻止陈旧评估覆盖当前事实

评估任务冻结 baseline、requirements 和 bindings signature；写回前重新计算并比较，变化时忽略旧结果，见 [patch_execution_service.py:1246](../../server/apps/patch_mgmt/services/patch_execution_service.py#L1246)。基线编辑也会取消仍在等待的评估任务并重置当前投影，见 [baseline.py:193](../../server/apps/patch_mgmt/views/baseline.py#L193)。

这套 invalidation 思路正确。长期引入 `BaselineVersion` 后，可以用不可变 version ID 替代字符串签名，但不能删除“结果只能写入它所评估版本”的约束。

### 4.5 通知投递已经给出了通用恢复模式

周期评估通知使用任务快照、`notification_reconciled_at`、每任务/渠道唯一 delivery、claim token、attempt 和退避，并由 Beat 扫描未对账和过期发送。这不是通知专属能力，而是治理链后续动作应复用的模式。

## 5. 治理与恢复数据流

- [PatchMgmt 治理与恢复数据流（Archify HTML）](patch-mgmt-governance.dataflow.html)
- [PatchMgmt 治理与恢复数据流源文件](patch-mgmt-governance.dataflow.json)
- [PatchMgmt 治理与恢复数据流静态图](patch-mgmt-governance.dataflow.light.png)

### 5.1 评估流：签名正确，但当前事实会覆盖历史

评估任务冻结基线签名，逐主机采集已安装包/KB，解析每条 requirement，并对缺失 Linux 补丁逐项执行 dry-run 收集安装影响。完成后先删除 binding 下全部 `HostComplianceSnapshot`，再 bulk create 当前结果，见 [patch_execution_service.py:1336](../../server/apps/patch_mgmt/services/patch_execution_service.py#L1336)。模型注释也明确“每次新的 assess 成功后替换全部快照”，见 [baseline.py:113](../../server/apps/patch_mgmt/models/baseline.py#L113)。

这适合作为 CurrentCompliance 读模型，不适合作为唯一审计事实。基线后续变化后，系统无法直接回答：

- 某主机在某一历史基线版本下为何被判定为合规；
- 当时使用了哪一组补丁来源与替代关系；
- 某次治理验证改变了哪些 requirement facts；
- 同一主机连续两次评估之间发生了什么变化。

建议保留当前表作为快速读模型，新增不可变 `AssessmentRun + AssessmentEvidence`；投影更新与证据写入同一事务完成。

### 5.2 治理创建流：前置条件保护较完整

创建 remediation 时会在事务内：

1. 从 request 取得可信 current team；
2. 锁定 PatchTarget 并收敛陈旧任务；
3. 检查主机是否忙；
4. 锁定 HostBaselineBinding，防止基线切换 TOCTOU；
5. 验证补丁仍属于主机当前基线；
6. 验证当前 HostComplianceSnapshot 状态仍为 missing；
7. 冻结风险快照并创建逐主机等待记录。

运行阶段又会重新计算当前可治理补丁集合，避免窗口任务在等待期间继续执行已经满足或已移除的要求。这是正确的“command acceptance 与 execution precondition 分离”。

### 5.3 父任务派发流：非原子 claim 与全量扇出

`execute_governance_task` 先普通读取 PENDING，再直接保存 RUNNING，未用行锁或 compare-and-set，见 [tasks.py:341](../../server/apps/patch_mgmt/tasks.py#L341)。重复 Celery delivery 可能同时通过 PENDING 检查，并各自遍历全部目标投递子任务。

逐主机原子 claim 会阻止同一远端副作用被重复执行，因此当前更常见的后果是 broker 消息放大、日志噪声和 host 创建竞态，而不是必然重复安装。但父任务仍应成为明确原子裁决点：

```text
UPDATE governance_task
SET status='running', dispatch_token=?, started_at=?
WHERE id=? AND status='pending'
```

claim 成功者才能创建/投递批次；失败者直接退出。

父任务随后逐个 target 立即 `apply_async`，无 chunk、queue quota、团队/区域/协议并发预算。实际峰值由“活动父任务数 × 每任务目标数 × Celery worker 并发”共同放大，增加 worker 也会同步放大 SSH、WinRM、Ansible、源仓库与目标主机压力。

### 5.4 终态流：通知可恢复，自动链路不可恢复

父任务汇总在事务中锁定 GovernanceTask，只有首次进入终态返回 true，见 [patch_execution_service.py:2307](../../server/apps/patch_mgmt/services/patch_execution_service.py#L2307)。但事务提交后才调用 `_run_terminal_followups`：

- install + auto_reboot：创建 reboot child task，再 `execute_governance_task.delay`；
- install：为无需重启的成功主机创建 verify child task，再投 broker；
- periodic assess：生成 notification delivery intent。

自动重启和验证的 child 创建与 broker 投递见 [patch_execution_service.py:2388](../../server/apps/patch_mgmt/services/patch_execution_service.py#L2388) 和 [patch_execution_service.py:2458](../../server/apps/patch_mgmt/services/patch_execution_service.py#L2458)。没有 `(parent_task, transition_kind, target/phase)` 唯一约束，也没有持久化 transition intent。

故障窗口是结构性的：

```text
terminal commit ── crash ──X── create child       → 后续步骤永久缺失
create child ── broker failure ──X── run child    → 留下 PENDING 记录但原始意图不重放
retry follow-up ── duplicate create                → 缺少唯一业务键
```

Watchdog 能把长时间 waiting 的 host 收敛为失败，但不能恢复“这个 install 本应触发哪一个后续步骤”。短期应新增：

```text
GovernanceTransitionIntent(
  parent_task, kind, target_set_digest,
  status, attempt, next_retry_at, lease_token, lease_expires_at,
  UNIQUE(parent_task, kind, target_set_digest)
)
```

父任务终态、链路 intent 和通知 intent 在同一事务生成；worker 领取 intent 后幂等创建 child/work items 并投递，Beat 重扫 broker 失败和过期 lease。

## 6. 不合理设计要素与影响

### P0：全局周期扫描跨团队聚合

`ScanSetting` 明确是 pk=1 的全系统单例，见 [scan_setting.py:9](../../server/apps/patch_mgmt/models/scan_setting.py#L9)。周期任务读取 `PatchTarget.objects` 全部 ID，创建一条 team 为空的 GovernanceTask，再一次性派发，见 [tasks.py:72](../../server/apps/patch_mgmt/tasks.py#L72)。

影响：

- 不同团队目标共享同一个任务、deadline、结果摘要和通知快照；
- 任务数据本身缺乏单一团队归属，后续权限投影和审计更难解释；
- 一次扫描规模等于全系统目标数，JSON target_list、父任务循环和 broker burst 同步增长；
- 通知规则虽然冻结了创建者团队的 channel/receiver 信息，任务结果却可能是全局统计，存在跨团队汇总语义风险。

短期至少按 `PatchTarget.team` 的规范化查询结果分区，每个团队创建独立 ScanRun，并为每批设置目标上限与 cursor。长期 ScanPolicy 应是显式 scope，而不是 UI 用户最后一次保存的全局单例配置。

### P0：治理链缺少 durable transition intent

这是最优先的可靠性问题。它影响自动重启、安装后验证和未来任何自动步骤；不能通过给 `.delay()` 加 try/except 解决，因为缺口位于数据库事务提交和 broker/子任务创建之间。

验收标准应是：任意位置 kill worker 后，系统最终只能产生一个语义相同的后续步骤，且不会永久丢失；恢复过程不自动重放结果未知的远端副作用。

### P1：风险 API 先计算全库，再做权限过滤

RiskViewSet `_scoped_items` 先调用无参数 `compute_risk_items()`，之后才保留用户可见 target，见 [risk.py:75](../../server/apps/patch_mgmt/views/risk.py#L75)。`compute_risk_items` 读取所有 binding、requirements 和 snapshots，在主机×要求循环内继续调用 `_compute_remediation`，后者针对每个风险项查询多类 GovernanceTask 与 Host 记录，见 [risk_service.py:258](../../server/apps/patch_mgmt/services/risk_service.py#L258)。

影响不仅是 O(H×R)：

- 未授权团队的数据仍参与 Python 内存计算；
- 分页发生在聚合之后，page_size 不降低数据库和 CPU 成本；
- 每个风险项的活跃 install/reboot/verify/failed 状态继续触发查询，形成规模化 N+1；
- 三种视角重复使用同一高成本全量结果，无法利用数据库索引和增量投影。

短期把 `visible_target_ids` 作为 query boundary 传入 service，并批量预取所有相关 task/host 状态。中期将 RiskItem 建为受事件更新的读模型，按 `(team, target, patch, baseline_version)` 可索引查询；API 只做过滤、聚合和分页。

### P1：补丁源同步是无租约布尔锁

接口使用条件更新将 `sync_in_progress=False → True`，同步完成 finally 重置，见 [patch_source.py:47](../../server/apps/patch_mgmt/views/patch_source.py#L47)。WSUS 异步任务如果成功启动也会在 finally 清理，见 [tasks.py:653](../../server/apps/patch_mgmt/tasks.py#L653)。

但若进程在设置布尔值后、任务执行前退出，或 broker 接受消息后长期丢失，该 source 会永久保持 syncing，删除和再次同步都被阻塞。字段没有 owner、started_at、heartbeat、deadline，也无法区分真正运行和陈旧状态。

应替换为 `PatchSourceSyncRun`：source、mode、requested_by、status、lease token/expiry、cursor、counts、failure reason；Source 只保留 last_success/last_failure/current_run 投影。对同步数据量大的源按页/游标入库，避免请求线程同步拉全量公告。

### P1：基线和评估事实缺少版本

模型注释明确“基线只有当前清单，无历史版本快照”，见 [baseline.py:10](../../server/apps/patch_mgmt/models/baseline.py#L10)。运行签名可以防止旧结果误写当前状态，却不能恢复历史定义。

这会限制：审计报告、变更影响分析、基线灰度发布、回滚、按时间比较、监管证据导出。应新增不可变 `BaselineVersion`，编辑动作创建新版本而不是原位变更 requirements；HostBinding 指向 effective version，治理计划冻结 version ID。

### P1：执行内核承载过多变化轴

`patch_execution_service.py` 同时包含：

- Linux/Windows 命令构造；
- SSH/WinRM/Ansible/Executor 路由；
- 安装影响 dry-run 与输出解析；
- 主机 claim、heartbeat、结果写回；
- assessment persistence；
- timeout/reconcile；
- 父任务 terminal reducer；
- 自动 reboot/verify 编排。

2,703 行只是症状。真正问题是协议、OS、命令、解析、状态机和链路编排六条独立变化轴交叉。建议在同一 Django app 内形成深模块接口：

```text
PatchExecutionPort.plan(target, requirements, phase) -> CommandPlan
RemoteExecutor.execute(attempt, command_plan) -> TransportOutcome
PatchResultInterpreter.interpret(target_facts, outcome) -> DomainEvidence
GovernanceReducer.apply(work_item, evidence) -> StateTransition + Intents
```

先拆内部 seam 和测试，不要以文件大小为理由直接拆服务。

### P1：日志在单行 TextField 上反复全量追加

`GovernanceTaskHost.log` 是 TextField，`_append_host_log` 使用 `host.log = old + entry` 后保存，见 [governance.py:136](../../server/apps/patch_mgmt/models/governance.py#L136) 和 [patch_execution_service.py:1058](../../server/apps/patch_mgmt/services/patch_execution_service.py#L1058)。命令多、输出大时，每次追加都会重写整行，累计写放大接近 O(total_log²)，并扩大主机详情查询与数据库备份。

短期设置单命令与单主机日志字节上限、截断标志和摘要；中期将结构化 command attempt/result 与大文本对象存储分离，数据库只存引用、大小、digest 和预览。

### P2：补丁依赖/替代使用 JSON ID

依赖和 replacement IDs 缺少 FK、唯一、环检测、来源/version 约束。当前规模下读取方便，但源删除、同名 Linux advisory 合并、WSUS supersedence 更新和跨源关系会逐渐形成无法由数据库保护的悬空或冲突边。

中长期改为 `PatchRelation(from_patch, to_patch, relation_type, source_identity, valid_from/to)`，写入时做环与 OS/package-family 校验。迁移阶段可保留 JSON 作为读缓存，但不能继续作为唯一事实。

### P2：PatchTarget 与跨模块执行能力耦合

PatchMgmt 直接导入 Node/CloudRegion、Ansible resolver、S3 helper 和 SystemMgmt 工具。短期可运行，但 NodeMgmt 模型、凭据或区域策略变化会直接穿透 PatchMgmt，测试也需大量 mock 内部实现。

应建立仓内 Port，不必先拆服务：

- `TargetDirectoryPort.resolve(refs, actor)`；
- `ExecutionCapabilityPort.resolve(targets)`；
- `RemoteCommandPort.submit/probe/cancel`；
- `ArtifactStorePort.put/get/delete`；
- `NotificationPort.resolve_authorized_channels/send`。

## 7. 目标架构

- [PatchMgmt 目标架构（Archify HTML）](patch-mgmt-target.architecture.html)
- [PatchMgmt 目标架构源文件](patch-mgmt-target.architecture.json)
- [PatchMgmt 目标架构静态图](patch-mgmt-target.architecture.light.png)

目标结构不是“把一个 app 拆成多个服务”，而是把变化和一致性边界显式化：

```text
Adapter
  → trusted PatchCommand
  → GovernancePlanner（验证、冻结、按 team/region/protocol 分区）
  → BudgetedScheduler（共享预算、分片、lease）
  → GovernanceWorkItem / Attempt
  → ExecutionKernel + protocol adapters
  → TerminalReducer
      ├─ 更新 WorkItem / aggregate
      └─ 同事务写 TransitionOutbox
            → child phases / notification / broker delivery
```

目录侧同时演进为：

```text
SourceSyncRun → Canonical Patch Graph
                         ↓
                  BaselineVersion
                         ↓
                  AssessmentEvidence
                         ↓
                  CurrentCompliance projection
```

核心不变量：

1. 一个 WorkItem 同一时刻只有一个有效 attempt token；
2. 一个 parent + transition kind + target-set 只能生成一个链路 intent；
3. 未知副作用只能核验/确认，不能自动重复执行；
4. 每条治理命令只属于一个可信 team scope；
5. 计划必须冻结 baseline version、patch source identity 与 executor partition；
6. 当前合规只是读模型，不覆盖不可变证据；
7. scheduler 必须有 global/team/region/protocol/target 预算和 lease 回收。

## 8. 优化路线与优先级

| 阶段 | 优先级 | 优化项 | 预期收益 | 验证重点 |
|---|---|---|---|---|
| 0–4 周 | P0 | 父任务 CAS claim；终态同事务写 GovernanceTransitionIntent；唯一键、lease、Beat 重扫 | 消除自动重启/验证永久丢失与重复链路 | 在 terminal commit、child create、broker publish 各位置 kill worker，最终仅有一个后续步骤 |
| 0–4 周 | P0 | 周期扫描按可信团队分区，设置 batch/cursor 和单任务 target 上限 | 消除跨团队任务聚合，控制 broker burst | 两团队隔离、十万目标分片、重复 Beat tick 幂等 |
| 0–6 周 | P1 | 风险 service 接受 scope，批量加载 task/host；权限过滤在查询入口完成 | 降低全库 CPU/内存和 N+1 | 查询数随 page/批次稳定，不随全库团队数线性增加 |
| 0–6 周 | P1 | PatchSourceSyncRun lease/heartbeat/expiry；陈旧同步自动恢复 | 消除永久 syncing | 设置锁后、投递前、执行中 kill worker 的恢复测试 |
| 1–2 月 | P1 | 日志字节预算、结构化 command result、大输出对象存储 | 降低 DB 行写放大与详情载荷 | 最大输出、Unicode、截断、对象缺失和权限测试 |
| 1–3 月 | P1 | 拆分 Planner / Executor Port / Interpreter / Reducer 内部 seam | 降低多协议和状态机改动互相传播 | 按行为 contract 测试每条 seam，不 mock 私有函数链 |
| 2–4 月 | P1 | GovernancePlan、Partition、WorkItem Attempt、共享 Scheduler budget | 可控并发、公平性、故障恢复 | 多 worker 抢占、lease 过期、团队/区域配额、目标互斥 |
| 3–6 月 | P1 | BaselineVersion、AssessmentRun/Evidence、CurrentCompliance 投影 | 可审计、可比较、可回放 | 版本生效、历史重放、投影重建一致性 |
| 3–6 月 | P2 | PatchSourceIdentity 与 PatchRelation 规范化 | 去重与依赖/替代关系可验证 | 多源同公告、源删除、替代环、跨生态冲突 |
| 持续 | P2 | NodeMgmt/SystemMgmt/Executor 依赖经 Port 收口 | 降低跨模块改动传播和测试脆弱性 | contract tests + adapter integration tests |

## 9. 后续设计提醒

### 给开发同学的硬约束

- 不要把 Celery `max_retries` 当成补丁副作用重试策略；先证明命令未开始，结果未知必须核验。
- 不要在终态事务提交后直接追加新的业务步骤；先持久化唯一 intent，再异步投递。
- 不要让 API 的分页参数只裁剪 Python list；权限、过滤和分页必须尽可能下推到查询/读模型。
- 不要把 team 只放在 JSON 快照中作为长期授权事实；command、task、scan run、work item 都要有单一可信 scope。
- 不要用全局 Celery worker 数表达容量；团队、区域、协议和目标互斥是不同预算维度。
- 不要把 `pending_confirmation` 自动解释为 failed 或 retryable；它表示远端事实仍未知。
- 不要把 CurrentCompliance 当历史证据；投影可以重建，证据必须不可变。
- 不要继续向 `patch_execution_service.py` 添加新协议分支；新执行通道先实现 RemoteExecutor contract。
- 不要直接合并 PatchTarget 和 JobMgmt Target；先抽共享能力 Port，再用真实重复度决定数据模型归属。
- 所有批量入口都必须给出最大目标数、分片策略、deadline、输出预算、幂等键和取消语义。

### 新增执行通道前必须回答

1. 如何解析可信 actor/team，调用方能否覆盖？
2. 目标能力如何分区，混合 OS/区域/协议是拒绝还是拆分？
3. WorkItem/Attempt 的唯一键、claim、lease、heartbeat 是什么？
4. broker 重复投递时是否会重复远端副作用？
5. worker 在命令提交前、提交后、结果写回前退出时如何恢复？
6. 如何证明远端命令未开始，何时必须进入核验/人工确认？
7. stdout/stderr、包列表、dry-run evidence 的最大字节数和保留期是什么？
8. 终态与后续步骤/通知是否在同一事务形成 durable intent？
9. 取消是“停止派发”“请求远端终止”还是“已证明终止”？状态是否区分？
10. 历史基线版本、补丁来源身份和评估证据能否重放当时判定？

## 10. 本轮不建议做的事

- 不因单文件较大立即拆 PatchMgmt 微服务；先收敛事务边界和内部深接口。
- 不删除现有 GovernanceTaskHost、execution token、reconcile 和通知 delivery 机制；它们是可复用基础。
- 不用缓存掩盖 `compute_risk_items()` 的全库计算；先让 scope 成为 service 输入并消除逐项查询。
- 不把自动链路失败简单标记成父任务失败；父任务事实和后续 transition delivery 是两个独立、可恢复的状态。
- 不以“最终 Watchdog 会失败”替代可靠投递；失败收敛不能恢复缺失的业务意图。

## 11. 验证说明

三份 Archify 交付物均通过 showcase 验证：9/9 检查、0 composition errors、0 warnings。HTML 还通过 1440×900、1600×1000、1920×1080、2048×1320 的 light containment 检查，并人工检查了最小 light 与最大 dark 截图；未发现节点遮挡、路线歧义、卡片溢出或不可读文本。
