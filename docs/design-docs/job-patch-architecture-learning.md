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
| Ansible 提交与 callback | `execution_base_service._execute_script_via_ansible`、`nats_api.ansible_task_callback` |
| 测试连接 | `views/target.py` `_perform_connection_test` |
| 补丁路由 | `patch_mgmt/services/target_execution_route.py` |
| 补丁执行与回写 | `patch_mgmt/services/patch_execution_service.py` |
| Ansible CLI adhoc | `agents/ansible-executor/service/ansible_runner.py` `build_adhoc_command` |
| Go SSH + TCP 探测 | `agents/nats-executor/ssh/executor.go` |

---

## 7. 本模块架构梳理作业

每题自己画一张（Archify 或手绘），边上标 **文件 + 函数名**；英文标识符保持原样。对照 Hub 已有图，标「图对了 / 图漏了 / 图画成容器了」。

**作业 1 — 一次「快速执行」端到端（作业平台）**  
选一种真实组合（例如：目标管理 + Linux + Ansible + 临时脚本）。从 `web/.../home/page.tsx` 画到 `JobExecution` 落库。必须标出：Celery 是「等 RPC」还是「提交后返回」；结果从哪条 NATS subject 回来。

**作业 2 — Sidecar vs Ansible 回写对照**  
只画回写。对比 `ScriptExecutionRunner.run` → `finalize_execution` 与 `ansible_task_callback`。问：SSE / `job.stream.*` 通了，为什么状态还能一直「执行中」？

**作业 3 — 补丁三条通道**  
读 `target_execution_route.py` + `patch_execution_service.py`。按「前端 source_type / os_type → 服务 → 写哪张表」画一张。写出 Job 有、Patch 没有的两处（`driver`、回写模型）。

**作业 4 — 容器 vs 进程**  
对着 compose 与 [作业涉及的容器](job-mgmt-deploy-containers.architecture.html) 列表：每个框是 compose 服务还是 fusion 内进程。禁止把 Celery、`JobExecution`、ansible-executor 画成独立容器。

**作业 5 — 测试连接与执行通道（排障题）**  
从 `test_connection` 画到 nats-executor；再从同一目标的作业执行画到 ansible-executor。三列对比：容器里手动 ssh、UI 测试连接、作业执行。解释「连接测试异常」和「连接测试失败」的差别。

建议顺序：1 → 4 → 2，补丁做 3；5 当综合题。
