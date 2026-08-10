# 模块 ARD：Job Management（作业平台）

> Migrated from `spec/ARD/modules/job_mgmt.md` as legacy capability evidence.

> 路径 `server/apps/job_mgmt` ｜ API 前缀 `api/v1/job_mgmt/`

## 1. 职责【已实现/已存在】
在目标主机上执行脚本、playbook 与文件分发；通过两类驱动路由执行：**nats-executor**（sidecar 节点）与 **ansible-executor**（手动/外部目标），完成回调经 NATS。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| JobExecution | `models/execution.py` | 作业记录（类型/状态/目标/结果/celery_task_id/team）；内部 `terminal_source` 区分 Ansible 真实回调与取消超时兜底，`cancel_finalize_at` 是 Beat 可恢复的取消收敛截止时间，`playbook_temp_file_key` 固定本次执行上传到 NATS OS 的精确清理目标；`callback_attempt_id` 与 `callback_token_hash` 绑定当前 Ansible 提交 attempt，数据库只保存随机令牌摘要；另含对外/审计字段：`callback_url`、`callback_type`、`callback_subject`（支持 web/nats/both 回调通道）、`trigger_source`（manual/api/scheduled）、`playbook_version`（执行时版本快照）、`executor_user`（执行用户快照）、`overwrite_strategy` 等 |
| JobCompletionOutbox | `models/completion_outbox.py` | Ansible 回调与取消兜底终态的副作用投递意图；按目标/通道拆分，保存稳定幂等键、尝试次数、重试时间及带 token 的投递租约 |
| Script | `models/script.py` | 脚本模板（SHELL/PYTHON/POWERSHELL/BATCH，Jinja2） |
| Playbook | `models/playbook.py` | Ansible playbook ZIP（存 MinIO `job-mgmt-private`） |
| Target | `models/target.py` | 手动目标（driver=ANSIBLE/NATS_EXECUTOR，SSH/WinRM 凭据）；SSH 密钥文件经 `ssh_key_file` 存于 MinIO 桶 `job-mgmt-private`（与 Playbook 同桶），即该桶承载 Playbook ZIP 与 SSH 密钥两类文件 |
| DistributionFile | `models/distribution_file.py` | 临时分发文件（file_key + 过期清理）；文件实际上传到 NATS JetStream Object Store（前缀 `job-files/`，经 node_mgmt `upload_file_to_s3`），而非 MinIO；`is_permanent` 字段已在 migration 0009 删除，现已无「永久保存」选项，仅 `expire_at` 过期清理 |
| ScheduledTask | `models/scheduled_task.py` | 定时任务（并发策略） |
| DangerousRule / DangerousPath | `models/*.py` | 危险命令/路径黑名单 |

## 3. 接口【已实现/已存在】
DRF 路由前缀均带 `api/` 段；结合 app 注册前缀 `api/v1/job_mgmt/`，对外完整路径为 `api/v1/job_mgmt/api/<resource>/`：`api/target`、`api/script`、`api/playbook`、`api/execution`、`api/scheduled_task`、`api/dashboard`、`api/distribution_file`、`api/dangerous_rule`、`api/dangerous_path`。开放端点 `api/open/upload_file`、`api/open/delete_file`（同样带 `api/` 前缀）。当前 `urls.py` 未注册 `callback_test/` 回调测试端点。

## 4. 执行机制【已实现/已存在】
- 脚本：危险命令校验 → Ansible（Windows 手动目标）或 nats-executor（sidecar）；日志发布到 JetStream。
- playbook：上传 ZIP 到 MinIO → 在上传 NATS OS 前按 execution 预留延迟清理 outbox → 提交 `apps.rpc.ansible.AnsibleExecutor` → 异步回调；正常终态刷新并立即投递同一幂等清理意图，worker 硬退出或即时删除失败则由 Beat 重扫。
- 文件分发：上传 NATS JetStream Object Store（前缀 `job-files/`，经 `node_mgmt.upload_file_to_s3`，非 MinIO）→ nats-executor 或 Ansible 推送。
- 回调：Server 每次提交 Ansible 前签发新的 `execution_id + attempt_id + token` 上下文，Executor 原样附加到完成回调；`ansible_task_callback` 在执行行锁内校验固定 caller、执行 ID、当前 attempt 和令牌摘要，缺失、伪造或旧 attempt 均不得写终态。回调、`tasks.py:finalize_cancelling_execution` 与 outbox claim 统一按 JobExecution → outbox 顺序加锁，终态和每个 SSE done、Playbook 精确临时文件清理、web/nats 完成通知的 outbox 意图在同一事务写入。取消兜底先提交时，副作用至少暂缓一个协调窗口；所有可变副作用都仍为从未尝试的 PENDING 时，唯一真实回调可纠正占位结果并刷新同一 outbox；任一记录已 claim 或有过投递尝试后，即使本地收到失败也可能是远端已收到、响应丢失，因此保留已可能对外可见的数据库终态。HTTP/NATS 发布调用允许以稳定 `delivery_id` 重放，web 签名覆盖该增量字段；Core NATS 保留既有 fire-and-forget publish 契约，不承诺离线消费者补发，也不要求存量消费者回复。`callback_type=both` 的两个通道使用独立记录，单通道失败不阻塞另一通道。
- Celery：`execute_script_task`/`execute_playbook_task`/`distribute_files_task`/`execute_scheduled_task`；另有 `cleanup_expired_distribution_files_task`（每天 00:00 由 celery-beat 清理过期分发文件）、`deliver_job_completion_outbox` 与每分钟执行的 `dispatch_pending_job_completion_outbox`。完成 outbox 的即时入队失败不影响已提交意图；取消入口会先持久化 `cancel_finalize_at`，再尝试即时入队。Beat 重扫到期取消、pending、冷却到期 failed 和租约过期 delivering，失败周期会自动冷却并重启，不依赖人工复位。旧入口 `do_callback_task`/`do_nats_callback_task` 仍服务其余回调路径。
- 取消：REST 与 NATS 共用 `execution_cancellation_service` 的执行行锁状态机。PENDING→CANCELLED 与完成 outbox 在同一事务落库；RUNNING→CANCELLING 先持久化兜底截止时间，revoke 与即时 Celery 入队只在事务提交后尽力执行。NATS `job_task_terminate` 必须携带有效 `caller_token`，团队范围由 Server 解码登录身份取得，不接受请求体自报 `caller_team`。
- NATS handler：除 `ansible_task_callback` 外，`nats_api.py` 还注册了数据权限类 `get_job_mgmt_module_list`/`get_job_mgmt_module_data`，以及供第三方 App（如补丁管理）经 NATS 调用的开放接口 `job_script_execute`（脚本执行）/`job_file_distribute`（文件分发）/`job_status_batch_query`（批量状态查询）/`job_detail_query`（作业详情）/`job_target_list`（目标列表）/`job_script_detail`（脚本详情读取）/`job_task_terminate`（作业取消/终止）。
- 依赖 `apps.rpc.{executor,ansible,node_mgmt}`。

## 5. 风险 / 待确认
- 危险命令黑名单覆盖度与绕过风险【待确认】。
- JetStream 日志流依赖（默认关闭）【已实现风险】。
- 水平越权防护【已实现/已存在】：`utils/team_authz.py` 提供团队归属授权校验（BL-NEW-002 修复），视图层按 ID 加载 Script/Playbook/Target/DistributionFile 后，用 `is_team_authorized` 校验对象 `team` 是否落在「当前用户授权团队」内；开放删除按 `(file_id, file_key, team)` 限定文件，NATS 文件分发按请求声明的团队范围限定 `file_key`。跨团队和无团队归属文件一律 fail-closed，防止 Team A 的文件被 Team B 删除或用于自己的作业。

## 2026-07-01 Code-ARD 校准
- `[job_mgmt#20260701-017]` 移除 `callback_test/` 回调测试端点的强结论，当前 `urls.py` 未注册该路由。
- `[job_mgmt#20260701-018]` 补录 `job_script_detail` 与 `job_task_terminate` NATS handler，分别用于脚本详情读取和作业取消/终止。
- `[job_mgmt#20260701-019]` 补录 `JobExecution.callback_type` / `callback_subject`、web/nats/both 双通道分发、`do_nats_callback_task` 与 `CallbackService`。

## 2026-07-28 Code-ARD 校准
- `[job_mgmt#20260728-020]` Ansible 回调与取消兜底统一为“执行行锁 + 同事务完成 outbox”；补录取消兜底协调窗口、稳定 `delivery_id`、web/nats 独立投递、NATS publish 兼容、租约 token fencing 及 Beat 自动恢复语义。
- `[job_mgmt#20260810-021]` Ansible 完成回调绑定 caller/execution/attempt/token 可信身份；REST/NATS 取消合并为单一锁内状态机，NATS 取消改为校验登录 token 并由服务端解析团队范围。

### 升级与回滚
- 升级是停流排空切换，不允许新旧 `nats_listener` 混合承接 `job.ansible_task_callback`：先暂停新作业、取消请求和 Ansible 回调入口，等待所有 PENDING/RUNNING/CANCELLING 执行与 Executor 回调重试队列排空；再停止全部旧 `nats_listener`/worker/beat，应用 migrations through 0015，启动且确认全部新版本 Server 与 Executor 进程后才恢复入口。该边界避免旧 listener 先写终态而新 listener 无法补建 outbox。
- migration 0014/0015 的新增内部字段允许 `NULL`，保留维护窗口中的旧 ORM INSERT 与紧急回滚兼容，但不代表允许旧 listener 或旧 Executor 在恢复流量后继续处理回调。0014 会为可识别的非终态 Playbook 执行回填精确 NATS 临时文件 Key；0015 引入回调 attempt/token 摘要，新 Server 与新 Executor 必须在排空后同时启用。新执行在外部上传前持久化 Key 并预留延迟清理意图。无精确 Key 时不扫描共享 Object Store，由停流排空边界保证不产生这类新的在途资源。
- `delivery_id` 仅为回调 payload 的增量字段；旧 web/NATS 消费者可忽略，`callback_subject` 继续使用 publish，无新增 reply 要求。
- 回滚进入维护窗口后同时暂停新作业/取消请求与 Ansible 完成回调入口，并停止 beat；分别运行 `celery -A apps.core.celery inspect active`、`celery -A apps.core.celery inspect scheduled`、`celery -A apps.core.celery inspect reserved` 查出 `finalize_cancelling_execution`，必要时执行 `celery -A apps.core.celery control revoke <task-id>`，避免 drain 期间继续产生 outbox。
- 保留一个新版本 worker，用 `python manage.py shell -c "from apps.job_mgmt.tasks import dispatch_pending_job_completion_outbox as d; print(d())"` 重扫；再用 `python manage.py shell -c "from apps.job_mgmt.models import JobCompletionOutbox as O; print(O.objects.exclude(status=O.Status.DELIVERED).count())"` 查零。随后再次检查 Celery 三类队列和 outbox 均为空，才停止 worker、回退代码并迁回 0013（Django 先逆向 0015，再逆向 0014）。任一检查非空时继续保留新 worker；直接逆向迁移会丢弃未投递意图，禁止执行。

## 6. 证据来源
- 接口：`server/apps/job_mgmt/urls.py:48-50`（路由前缀 `api/`、`api/open/*`，当前无 `callback_test/`）。
- 数据模型：`models/execution.py`、`models/completion_outbox.py`、`models/distribution_file.py`、`models/target.py`、`models/playbook.py`、`migrations/0009_distributionfile_expire_at.py`、`migrations/0014_jobcompletionoutbox.py`。
- 执行机制：`nats_api.py:ansible_task_callback`、`tasks.py:finalize_cancelling_execution`、`tasks.py:deliver_job_completion_outbox`、`tasks.py:dispatch_pending_job_completion_outbox`、`services/completion_outbox_service.py`、`services/callback_service.py`、`config.py:CELERY_BEAT_SCHEDULE`、`views/distribution_file.py` 与 `views/open_api.py`。
- 越权防护：`utils/team_authz.py:1-63`。
- 其它：`server/apps/job_mgmt/{services/*}`、`apps/rpc/{executor,ansible,node_mgmt}.py`。
