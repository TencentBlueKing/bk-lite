# 模块 ARD：Job Management（作业平台）

> 路径 `server/apps/job_mgmt` ｜ API 前缀 `api/v1/job_mgmt/`

## 1. 职责【已实现/已存在】
在目标主机上执行脚本、playbook 与文件分发；通过两类驱动路由执行：**nats-executor**（sidecar 节点）与 **ansible-executor**（手动/外部目标），完成回调经 NATS。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| JobExecution | `models/execution.py` | 作业记录（类型/状态/目标/结果/celery_task_id/team） |
| Script | `models/script.py` | 脚本模板（SHELL/PYTHON/POWERSHELL/BATCH，Jinja2） |
| Playbook | `models/playbook.py` | Ansible playbook ZIP（存 MinIO `job-mgmt-private`） |
| Target | `models/target.py` | 手动目标（driver=ANSIBLE/NATS_EXECUTOR，SSH/WinRM 凭据） |
| DistributionFile | `models/distribution_file.py` | 临时分发文件（S3 key + 过期清理） |
| ScheduledTask | `models/scheduled_task.py` | 定时任务（并发策略） |
| DangerousRule / DangerousPath | `models/*.py` | 危险命令/路径黑名单 |

## 3. 接口【已实现/已存在】
`target`/`script`/`playbook`/`execution`/`scheduled_task`/`dashboard`/`distribution_file`/`dangerous_rule`/`dangerous_path`；开放端点 `open/upload_file`、`open/delete_file`。

## 4. 执行机制【已实现/已存在】
- 脚本：危险命令校验 → Ansible（Windows 手动目标）或 nats-executor（sidecar）；日志发布到 JetStream。
- playbook：上传 ZIP 到 MinIO → 提交 `apps.rpc.ansible.AnsibleExecutor` → 异步回调。
- 文件分发：上传 MinIO → nats-executor 或 Ansible 推送。
- 回调：`nats_api.py:ansible_task_callback` 接收结果、更新 JobExecution、清理临时文件、推送 SSE 结束哨兵。
- Celery：`execute_script_task`/`execute_playbook_task`/`distribute_files_task`/`execute_scheduled_task`。
- 依赖 `apps.rpc.{executor,ansible,node_mgmt}`。

## 5. 风险 / 待确认
- 危险命令黑名单覆盖度与绕过风险【待确认】。
- JetStream 日志流依赖（默认关闭）【已实现风险】。

## 6. 证据来源
`server/apps/job_mgmt/{urls.py,models/*,tasks.py,nats_api.py,services/*}`、`apps/rpc/{executor,ansible,node_mgmt}.py`。
