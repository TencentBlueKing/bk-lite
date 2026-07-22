# Historical Superpowers change: 2026-06-12-job-mgmt-cancel-honest-semantics

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-12-job-mgmt-cancel-honest-semantics-design.md

- 日期：2026-06-12
- 关联 Issue：[TencentBlueKing/bk-lite#2964](https://github.com/TencentBlueKing/bk-lite/issues/2964)
- 范围：server（job_mgmt）+ web 前端展示；**不涉及** agents（nats-executor / ansible-executor）

## 1. 背景与问题

当前取消链路（`JobExecutionViewSet.cancel`，`server/apps/job_mgmt/views/execution.py`）只做两件事：

1. `current_app.control.revoke(celery_task_id)` —— 仅对队列中尚未被 worker 取走的任务有效；
2. 无条件把 `JobExecution.status` 写为 `CANCELLED`。

一旦作业已开始执行（worker 已取走、甚至已向节点下发 SSH/Sidecar/Ansible 远端执行），远端执行不会被中断，"已取消"只是数据库表象，真实副作用继续发生。运维人员会基于错误状态做后续决策（二次操作、误回滚等）。

连带缺陷：`server/apps/job_mgmt/nats_api.py` 的 `ansible_task_callback` 对终态（含 `CANCELLED`）直接返回"任务已处理"，导致取消后 Ansible 的真实执行结果被永久丢弃。

本设计对应 issue 评论中的 **方案 C（诚实化语义）**，并顺带纳入 **方案 D 的分批 submit** 改进。真正终止远端执行的跨层 cancel 协议（方案 A）作为后续立项，本设计引入的 `CANCELLING` 状态机是其地基。

## 2. 目标与非目标

**目标**

- 取消语义诚实：只有"确实没执行"的任务才标"已取消"；已在执行的标"取消中"，等真实结果回写后收敛终态。
- 取消后 Ansible 真实结果不再丢弃。
- 取消后不再向新目标下发执行（确定性行为，不依赖竞态）。
- "取消中"不会永久滞留（兜底收敛）。

**非目标**

- 不终止已下发的 SSH / Sidecar / Ansible 远端执行（方案 A 范围）。
- 不改 agents 任何代码、不新增 NATS 协议。
- 不处理 `RUNNING` 状态因 worker 崩溃而僵死的存量问题。

## 3. 状态机

`server/apps/job_mgmt/constants/choices.py` 的 `ExecutionStatus` 新增：

```python
CANCELLING = "cancelling"   # 取消中：已请求取消，远端执行未必已停止
CHOICES += ((CANCELLING, "取消中"),)
# TERMINAL_STATES 保持不变：CANCELLING 是非终态
```

状态流转：

```
PENDING  --cancel-->  CANCELLED                       （终态，未产生副作用）
RUNNING  --cancel-->  CANCELLING  --收敛-->  CANCELLED （终态，结果真实回写）
```

`CANCELLING → CANCELLED` 的收敛由三个入口之一完成（幂等，先到先得）：

1. Runner 收尾（`finalize_execution`）；
2. Ansible 回调（`ansible_task_callback`）；
3. 兜底收敛任务（超时强制收敛）。

`JobExecution.status` 为无 choices 约束的 CharField，新增状态值不需要数据库 migration。

## 4. 取消接口改造

`JobExecutionViewSet.cancel`（`server/apps/job_mgmt/views/execution.py:362`）改为 CAS（compare-and-swap）分流，消除"刚好开跑"竞态：

```
1. 若已是 TERMINAL_STATES 或 CANCELLING → 400（文案区分"已终态"与"已在取消中"）
2. revoke Celery 任务（逻辑不变，尽力而为）
3. CAS-1：QuerySet.filter(pk=pk, status=PENDING)
          .update(status=CANCELLED, finished_at=now)
   命中 → 200 {"message": "已取消执行", "status": "cancelled"}
4. CAS-2：QuerySet.filter(pk=pk, status=RUNNING)
          .update(status=CANCELLING)
   命中 → 调度兜底收敛任务（§7）
        → 200 {"message": "已请求取消，远端执行可能仍在进行，等待结果回写",
               "status": "cancelling"}
5. 两次 CAS 都未命中（状态在第 1 步检查后被并发改变）→ 重读状态按第 1 步逻辑返回 400
```

响应体新增 `status` 字段，前端据此区分两种取消语义。

## 5. Runner 侧改造

文件：`server/apps/job_mgmt/services/execution_base_service.py`、`script_execution_runner.py`、`file_distribution_runner.py`。

1. **`is_cancelled`**（`execution_base_service.py:82`）：判定条件由 `status == CANCELLED` 改为 `status in (CANCELLED, CANCELLING)`。所有现有检查点（每目标执行前、每结果返回后、每文件分发前、Ansible 轮询间隙）自动对 CANCELLING 生效。
2. **`prepare_execution`**（`execution_base_service.py:42`）：拦截条件同步改为 `(CANCELLED, CANCELLING)`，兜住 revoke 失败但状态已变更的任务。
3. **`finalize_execution`**：收尾前重读数据库状态，若为 `CANCELLING`：
   - 已完成目标保留真实结果；未执行/被跳过目标补 `CANCELLED` 结果；
   - 最终状态写 `CANCELLED`（终态收敛），`finished_at=now`；
   - 哨兵补发逻辑沿用现有 `_publish_cancelled_sentinels`。
4. **分批 submit（方案 D 项）**：`script_execution_runner.py:98` 与 `file_distribution_runner.py:55` 现在一次性向线程池 submit 全部目标，`future.cancel()` 只对尚未被线程取走的 future 有效。改为按 `MAX_WORKERS` 大小分批 submit，批与批之间检查 `is_cancelled`，命中则不再提交后续批次。已提交批次的行为不变（等待完成 + 真实结果落库）。

## 6. Ansible 回调改造

`server/apps/job_mgmt/nats_api.py` 的 `ansible_task_callback`：

- 终态拦截逻辑保持（`CANCELLED` 等终态仍直接返回"任务已处理"，防重复处理）。
- `CANCELLING` 为非终态，回调正常进入结果落库流程：per-host 真实结果写入 `execution_results`、统计 `success_count/failed_count`、发 done 哨兵。
- 落库收尾时若执行记录状态为 `CANCELLING`，最终状态写 **`CANCELLED`**（而非按结果写 SUCCESS/FAILED），保留真实结果数据。

此改动同时修复"取消后 Ansible 真实结果被丢弃"的连带缺陷。

## 7. 兜底收敛任务

`server/apps/job_mgmt/tasks.py` 新增一次性 Celery 任务 `finalize_cancelling_execution(execution_id)`，由取消接口在置 `CANCELLING` 成功后调度：

```python
finalize_cancelling_execution.apply_async(
    args=[execution.id],
    countdown=execution.timeout + CANCEL_FINALIZE_GRACE_SECONDS,  # 缓冲 60 秒
)
```

任务逻辑（幂等）：

1. CAS：`filter(pk=execution_id, status=CANCELLING).update(status=CANCELLED, finished_at=now)`；
2. CAS 未命中（runner/回调已收敛）→ 直接返回；
3. CAS 命中 → 为 `execution_results` 中没有结果的目标补记 `CANCELLED` 结果，`error_message` 为"任务已取消，远端结果未知（超时收敛）"；为这些目标补发 done 哨兵关闭 SSE 面板；刷新 `success_count/failed_count`。

选择一次性 countdown 任务而非 beat 周期巡检：兜底窗口由 `execution.timeout` 决定，一次性任务无常驻成本，且取消动作与兜底一一对应、易于测试。

## 8. 前端（web）

- 执行记录列表与详情的状态枚举新增 `cancelling` → "取消中"，使用进行中（黄色）样式。
- 详情页状态为 `cancelling` 时显示提示条："已请求取消，远端执行可能仍在进行，结果将在执行结束后回写"。
- 状态为 `cancelling` 时禁用"取消"按钮（接口侧同样会 400 拒绝）。
- 取消操作的成功提示按响应 `status` 字段区分两种文案。

## 9. 测试

按 `server/docs/testing-guide.md` 分层：

**`_views`（cancel 接口）**

- PENDING 取消 → 200，状态 CANCELLED，finished_at 已写；
- RUNNING 取消 → 200，状态 CANCELLING，兜底任务已调度（mock `apply_async` 断言 countdown）；
- 终态取消 → 400；CANCELLING 重复取消 → 400。

**`_service`（runner / 兜底）**

- `is_cancelled` 对 CANCELLING 返回 True；
- `finalize_execution` 在 CANCELLING 下收敛为 CANCELLED 且保留真实结果、补 CANCELLED 结果；
- 分批 submit：第一批执行中置 CANCELLING，断言后续批次未提交；
- 兜底任务：CANCELLING 时强制收敛并补结果/哨兵；已收敛时 CAS 不命中直接跳过（幂等）。

**`nats_api`（Ansible 回调）**

- CANCELLING 状态下回调正常落库，最终状态为 CANCELLED；
- CANCELLED 终态下回调仍返回"任务已处理"，不重复落库。

## 10. 与方案 A 的衔接

本设计引入的 `CANCELLING` 状态机、CAS 取消接口、收敛与兜底机制均为方案 A（跨层 cancel 协议）的必要组成。A 阶段在此之上增量：

1. nats-executor 新增 `local.cancel.{instanceId}` / `ssh.cancel.{instanceId}` 订阅与按 `execution_id` 的进程注册表；
2. ansible-executor 新增 `ansible.task.cancel.{instance_id}` RPC 与运行任务中断；
3. server 取消接口在置 `CANCELLING` 后向执行平面下发 cancel 指令。

旧版本 agent 不理解 cancel 指令时，行为自动退化为本设计（诚实的"取消中"），无兼容风险。
