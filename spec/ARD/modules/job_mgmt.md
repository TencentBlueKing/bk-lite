# 模块 ARD：Job Management（作业平台）

> 路径 `server/apps/job_mgmt` ｜ API 前缀 `api/v1/job_mgmt/`

## 1. 职责【已实现/已存在】
在目标主机上执行脚本、playbook 与文件分发；通过两类驱动路由执行：**nats-executor**（sidecar 节点）与 **ansible-executor**（手动/外部目标），完成回调经 NATS。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| JobExecution | `models/execution.py` | 作业记录（类型/状态/目标/结果/celery_task_id/team）；另含对外/审计字段：`callback_url`（第三方回调地址）、`trigger_source`（manual/api/scheduled）、`playbook_version`（执行时版本快照）、`executor_user`（执行用户快照）、`overwrite_strategy` 等 |
| Script | `models/script.py` | 脚本模板（SHELL/PYTHON/POWERSHELL/BATCH，Jinja2） |
| Playbook | `models/playbook.py` | Ansible playbook ZIP（存 MinIO `job-mgmt-private`） |
| Target | `models/target.py` | 手动目标（driver=ANSIBLE/NATS_EXECUTOR，SSH/WinRM 凭据）；SSH 密钥文件经 `ssh_key_file` 存于 MinIO 桶 `job-mgmt-private`（与 Playbook 同桶），即该桶承载 Playbook ZIP 与 SSH 密钥两类文件 |
| DistributionFile | `models/distribution_file.py` | 临时分发文件（file_key + 过期清理）；文件实际上传到 NATS JetStream Object Store（前缀 `job-files/`，经 node_mgmt `upload_file_to_s3`），而非 MinIO；`is_permanent` 字段已在 migration 0009 删除，现已无「永久保存」选项，仅 `expire_at` 过期清理 |
| ScheduledTask | `models/scheduled_task.py` | 定时任务（并发策略） |
| DangerousRule / DangerousPath | `models/*.py` | 危险命令/路径黑名单 |

## 3. 接口【已实现/已存在】
DRF 路由前缀均带 `api/` 段；结合 app 注册前缀 `api/v1/job_mgmt/`，对外完整路径为 `api/v1/job_mgmt/api/<resource>/`：`api/target`、`api/script`、`api/playbook`、`api/execution`、`api/scheduled_task`、`api/dashboard`、`api/distribution_file`、`api/dangerous_rule`、`api/dangerous_path`。开放端点 `api/open/upload_file`、`api/open/delete_file`（同样带 `api/` 前缀）。另有回调测试端点 `callback_test/`（`path('callback_test/', api_views.callback_test)`，不带 `api/` 前缀）。

## 4. 执行机制【已实现/已存在】
- 脚本：危险命令校验 → Ansible（Windows 手动目标）或 nats-executor（sidecar）；日志发布到 JetStream。
- playbook：上传 ZIP 到 MinIO → 提交 `apps.rpc.ansible.AnsibleExecutor` → 异步回调。
- 文件分发：上传 NATS JetStream Object Store（前缀 `job-files/`，经 `node_mgmt.upload_file_to_s3`，非 MinIO）→ nats-executor 或 Ansible 推送。
- 回调：`nats_api.py:ansible_task_callback` 接收结果、更新 JobExecution、清理临时文件、推送 SSE 结束哨兵。
- Celery：`execute_script_task`/`execute_playbook_task`/`distribute_files_task`/`execute_scheduled_task`；另有 `cleanup_expired_distribution_files_task`（每天 00:00 由 celery-beat 清理过期分发文件，schedule 见 `config.py`）与 `do_callback_task`（带 HMAC 签名 + SSRF 二次校验、指数退避重试最多 5 次的回调任务）。
- NATS handler：除 `ansible_task_callback` 外，`nats_api.py` 还注册了数据权限类 `get_job_mgmt_module_list`/`get_job_mgmt_module_data`，以及供第三方 App（如补丁管理）经 NATS 调用的开放接口 `job_script_execute`（脚本执行）/`job_file_distribute`（文件分发）/`job_status_batch_query`（批量状态查询）/`job_detail_query`（作业详情）/`job_target_list`（目标列表）。
- 依赖 `apps.rpc.{executor,ansible,node_mgmt}`。

## 5. 风险 / 待确认
- 危险命令黑名单覆盖度与绕过风险【待确认】。
- JetStream 日志流依赖（默认关闭）【已实现风险】。
- 水平越权防护【已实现/已存在】：`utils/team_authz.py` 提供团队归属授权校验（BL-NEW-002 修复），视图层按 ID 加载 Script/Playbook/Target/DistributionFile 后，用 `is_team_authorized` 校验对象 `team` 是否落在「当前用户授权团队」内，防止 Team A 用户引用 Team B 的对象越权执行；无团队归属的对象对非超管一律拒绝。

## 6. 证据来源
- 接口：`server/apps/job_mgmt/urls.py:20-53`（路由前缀 `api/`、`api/open/*`、`callback_test/`）。
- 数据模型：`models/execution.py:22,28,55,70,73`、`models/distribution_file.py:6-28`、`models/target.py:11,58-64`、`models/playbook.py:10`、`migrations/0009_distributionfile_expire_at.py:36-39`、`views/open_api.py:175-179`。
- 执行机制：`tasks.py:156-178`（清理任务）、`tasks.py:198-250`（`do_callback_task`）、`config.py:4-9`（beat schedule）、`nats_api.py:20,40,78,275,365,460,497,538`（NATS handler）、`views/distribution_file.py:64-67` 与 `views/open_api.py:175-179`（文件分发上传 NATS JetStream OS `job-files/`，非 MinIO）。
- 越权防护：`utils/team_authz.py:1-63`。
- 其它：`server/apps/job_mgmt/{services/*}`、`apps/rpc/{executor,ansible,node_mgmt}.py`。
