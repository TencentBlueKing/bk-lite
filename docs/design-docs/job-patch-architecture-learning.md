# 作业平台与补丁管理：架构学习笔记

> 对照 `server/apps/job_mgmt/`、`server/apps/patch_mgmt/` 与部署事实整理。
> 图入口：[Server 后端模块架构中心](server-module-architecture-hub.html)
> 深度分析：[作业平台](job-mgmt-module-architecture-analysis.md) · [补丁管理](patch-mgmt-module-architecture-analysis.md)
>
> 图上的产品标识符保持英文原文（Sidecar、Outbox、claim、team、token、nats-executor、ansible-executor）。

本文回答四件事：两个模块各自管什么、作业怎么选执行通道、结果怎么回写、部署时哪些是容器哪些是进程。文末是本模块架构梳理作业。

---

## 1. 先立边界

`job_mgmt` 与 `patch_mgmt` 是两个 Django app，**不共用目标模型**：`job_mgmt.Target` ≠ 补丁侧目标。作业回写 `JobExecution`，补丁回写 `GovernanceTaskHost`。

| | 作业平台 JobMgmt | 补丁管理 PatchMgmt |
|---|---|---|
| 前端 | `web/src/app/job/` | `web/src/app/patch-manager/` |
| 目标来源 | `manual` / `node_mgmt` | `manual` / `node_mgmt` |
| 通道选择 | `target_source` + 目标 `driver` | `source_type` + `os_type`（无 `driver` 字段） |
| 回写表 | `JobExecution` | `GovernanceTaskHost` |
| Celery 形态 | 一条执行记录一个 runner | 父任务扇出每主机 `execute_governance_host` |

排障时先问：卡在**派发**（控制面）还是卡在**回写**（数据面）。

图：Hub → JobMgmt / PatchMgmt 的「控制面与数据面」「入参出参与存储」。

---

## 2. 作业平台：怎么选通道

### 2.1 前端参数

| UI | 代码 |
|---|---|
| 目标管理 | `target_source = manual` |
| 节点管理 | `target_source = node_mgmt` |
| 脚本库 / 临时输入 | `execute_script_task` |
| Playbook | `execute_playbook_task`（只走 Ansible） |

新建目标默认 `driver = ansible`（`web/src/app/job/(pages)/target/page.tsx`）。Linux 可改为 Sidecar；Windows 手动目标只能 Ansible / WinRM。

入口：`JobExecutionViewSet.quick_execute` → `ExecutionService.create_quick_execution` → Celery `ScriptExecutionRunner` / `PlaybookExecution`。

### 2.2 运行时三条腿

判断是否 Ansible：`ExecutionTaskBaseService._should_use_ansible`，**只看 `target_ids[0]` 的 driver**。

1. **节点管理 + Sidecar**  
   fusion-collector 里的 `nats-executor` 本机二进制，`execute_local_stream`。  
   Celery **等** NATS RPC，再 `finalize_execution` 写 `JobExecution`。

2. **目标管理 Linux + Sidecar**  
   独立 compose `nats-executor`（`NATS_INSTANCE_ID=default`），SSH 到无 Agent 主机。  
   回写同样是 Celery 等 RPC。

3. **目标管理 + Ansible**（Playbook / WinRM / `driver=ansible`）  
   云区域 `is_container=True` 节点上 fusion-collector 内的 **ansible-executor 进程**（不是独立 compose 服务）。  
   Celery **只提交** `adhoc` / `playbook` 后返回；终态靠 NATS `ansible_task_callback`。回调不到会一直「执行中」。  
   实时日志走 JetStream `job.stream.*`，和终态回调不是同一条路。

图：[Sidecar / Ansible 落点](region-host-agent-placement.architecture.html)

### 2.3 测试连接 ≠ 作业执行

Linux「添加目标 → 测试连接」**不走 Ansible**，即使驱动选了 Ansible。

| 动作 | 真正出口 |
|---|---|
| 容器里手动 `ssh` | 系统 OpenSSH |
| UI 测试连接 | `ssh.execute.{容器节点ID}` → nats-executor 的 **Go SSH**；`connection_test=True` 先 TCP 探测（最多约 5s），再 `echo success`，stdout 必须含 `success` |
| 作业执行（默认 Ansible） | ansible-executor |

文案区别：

- **连接测试失败: …**：已经拿到执行器结果（认证失败、TCP 不通等）。
- **连接测试异常，请查看后端日志**：`execute_ssh` 抛异常，常见是 NATS RPC 超时，还没结构化 SSH 结果。搜 `[test_connection]`。

代码：`server/apps/job_mgmt/views/target.py`、`agents/nats-executor/ssh/executor.go`。

---

## 3. 作业平台：结果怎么回来

| 通道 | 等待方式 | 写库 |
|---|---|---|
| Sidecar | Celery 同步等 RPC | `finalize_execution` → `JobExecution` → `send_callback` |
| Ansible | fire-and-forget | `ansible_task_callback` → 同一行 `JobExecution` → `send_callback` |

两边都可以往 JetStream 打 SSE。**日志流到了 UI，不等于状态已终态。**

---

## 4. 补丁管理：怎么选通道、怎么回写

补丁没有 Job 的 `driver` 字段。路由在 `resolve_target_execution_route(source_type, os_type)`：

| 目标 | 通道 |
|---|---|
| 节点管理 | `NODE_EXECUTOR`，`instance_id = node_id` |
| 目标管理 Linux | `NATS_SSH`，区域 nats-executor |
| 目标管理 Windows | `ANSIBLE_WINRM`，`AnsibleExecutorResolver` |

Celery：`execute_governance_task` 按主机扇出 `execute_governance_host`（或 `run_governance_host`）。结果写 `GovernanceTaskHost`，带 token / 心跳。Windows 探测/装包常 `task_query` 轮询；部分 adhoc 只拿到 `accepted`，和作业的 callback 终态不一样。

图：[补丁入参、服务与回写](patch-mgmt-params-services-writeback.architecture.html)

---

## 5. 部署：哪些是容器，哪些是进程

没有独立 Job 容器。`job_mgmt` 在 `server` 里，和 uvicorn / Celery / `nats_listener` 同 Supervisord。

作业实际用到的：

- compose：`web`、`server`、`postgres`、`redis`、`nats`、`minio`（桶 `job-mgmt-private`）、独立 `nats-executor`、`fusion-collector`
- fusion 容器内进程：本机 `nats-executor`、`ansible-executor`（`DEFAULT_CONTAINER_COLLECTOR_CONFIGS` 含 `Ansible-Executor`）

作业链路**不经过**：stargazer、telegraf、Victoria*。

图：[作业涉及的容器](job-mgmt-deploy-containers.architecture.html)

| 名字 | 用途 |
|---|---|
| fusion-collector | 托管主机上的采集+执行容器 |
| 独立 nats-executor | 默认云区域 SSH 跳板，打无 Agent 的 Linux |
| ansible-executor | 容器节点上的 Ansible 进程 |
| stargazer | 云区域无 Agent 采集；作业不走它 |
| Celery | 在 server 内，不是独立容器 |

---

## 6. 关键代码索引

路径相对仓库根。

| 主题 | 位置 |
|---|---|
| 快速执行 | `server/apps/job_mgmt/views/execution.py`、`services/execution_service.py` |
| 脚本 runner / 选路 | `services/script_execution_runner.py`、`execution_base_service.py` |
| 文件分发 | `execution_service.create_file_distribution`、`tasks.distribute_files_task`、`file_distribution_runner.py` |
| 定时任务 | `views/scheduled_task.py`、`tasks.execute_scheduled_task` |
| 取消与收敛 | `views/execution.py` `cancel`、`tasks.finalize_cancelling_execution` |
| NATS / 告警入口 | `nats_api.job_script_execute`；告警 `apps/alerts/action/handlers/job.py` |
| 完成回调 | `callback_service.send_callback`（web HMAC / nats subject） |
| Ansible 提交与 callback | `execution_base_service._execute_script_via_ansible`、`nats_api.ansible_task_callback` |
| 测试连接 | `views/target.py` `_perform_connection_test` |
| 补丁源同步 | `patch_mgmt/tasks.check_patch_source_connectivity`、`source_sync_service.py` |
| 补丁评估与风险 | `views/baseline.py` `assess`、`assess_parsers.py`、`risk_service.compute_risk_items` |
| 补丁路由 | `patch_mgmt/services/target_execution_route.py` |
| 补丁执行与回写 | `patch_mgmt/services/patch_execution_service.py` |
| Ansible CLI adhoc | `agents/ansible-executor/service/ansible_runner.py` `build_adhoc_command` |
| Go SSH + TCP 探测 | `agents/nats-executor/ssh/executor.go` |

---

## 7. 本模块架构梳理作业

不要画图。笔记第 2–5 节已经写过通道选择、测试连接、Sidecar/Ansible 回写、补丁三条路由和容器 vs 进程，**不要再复述那些**。

每题用文字把**另一条关键链路**梳清楚，固定四段：

1. **入口**：哪个 ViewSet action / NATS handler / Beat 任务  
2. **调用链**：文件 + 函数名（保持英文标识符）  
3. **落点**：写了哪张表、MinIO/S3、还是只发消息  
4. **失败/并发**：超时、重复投递、取消撞上回调时会发生什么（一两句）

**作业 1 — 文件分发（JobType.FILE_DISTRIBUTION）**  
从 `ExecutionService.create_file_distribution` 跟到 `distribute_files_task` → `FileDistributionRunner`。对照脚本执行，写出至少两处不同：高危检查对象（路径 vs 命令）、文件从哪来（`DistributionFile` / 对象存储）、目标路径与 overwrite。过期文件谁清：`cleanup_expired_files`。

**作业 2 — 定时任务**  
从 `ScheduledTaskViewSet` 的启用/crontab，跟到 Beat 触发的 `execute_scheduled_task`。必须写清：锁前预读、`DangerousChecker`、`ConcurrencyPolicy` / skip、`run_count` 自增、最后落到哪条 runner（脚本 / 文件 / Playbook）。问：任务已禁用，Beat 仍触发时函数在哪一层 return。

**作业 3 — 取消与超时收敛**  
从 `JobExecutionViewSet.cancel` 跟到 `CANCELLING`，再跟 `finalize_cancelling_execution`（缺结果的目标补「远端结果未知」+ `publish_done_sentinel` + `send_callback`）。对照 `prepare_execution` 的 claim。问两句：Sidecar 还在等 RPC 时取消，远端命令停不停？Ansible 已 fire-and-forget，取消后 `ansible_task_callback` 还来，会不会覆盖终态？

**作业 4 — NATS/告警入口与完成回调**  
读 `nats_api.job_script_execute`：`team = data.get("team")` 是不是授权事实。对照 HTTP `quick_execute` 的登录用户。告警侧入口：`JobActionHandler` → RPC `job_script_execute`。终态后 `send_callback` 怎么分 `callback_type`（web HMAC / nats subject / both）。问：这条回调和 UI 的 SSE / `job.stream.*` 是不是同一条路。

**作业 5 — 补丁：源同步 → 评估快照 → 风险（不是执行通道）**  
从补丁源连通性 `check_patch_source_connectivity` / `SourceSyncService`（WSUS、Linux repo）写到 `Patch`。再从基线 `bind_hosts`、`assess`、`assess_parsers` 写到 `HostComplianceSnapshot`。风险页读的是 `compute_risk_items` 还是实时扫主机。`retry-host` 重试的是哪一层（任务还是单机 `GovernanceTaskHost`）。

建议顺序：1 → 2 → 3，4 看接入信任，5 做补丁治理闭环。
