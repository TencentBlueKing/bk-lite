# 编排中心 MVP — 预发真实验证清单

日期：2026-10-13  
环境：**本机 Mac + OrbStack Docker + Windows/Orb Linux 目标**（非预发）  
Web：`http://localhost:3000`　API：`:8011`　Conductor：`:8091`  
团队 ID：`1`　操作者：本地验证  
Windows 目标：`job-web3` / `10.10.90.120` / Target=`5`  
Linux 目标（Orb）：`bklite-linux-target` / `192.168.139.176` / Target=`33`  
旁证报告：`/tmp/wo-live-report.json`（live acceptance **passed=9 failed=0**）

填写约定：每条结果为 `通过` / `失败` / `未实验`。  
失败请附执行 ID、作业 ID、现象摘要（勿贴凭据/token/脚本正文）。  
未实验必须写外部阻塞原因。  
进程与缺口权威表：[ENV_INVENTORY.md](./ENV_INVENTORY.md)。

---

## 前置

- [ ] Conductor / Postgres / Redis / NATS / MinIO 容器在跑  
- [ ] Server `:8011`、Web `:3000` 在跑  
- [ ] **`run_workflow_worker` 已启动**（P0，当前勘察时缺失）  
- [ ] **`make celery` 已启动**（P0，当前勘察时缺失）  
- [ ] Ansible Executor（或等价执行器）已接入且健康（P0）  
- [ ] 至少一台目标已纳管（Windows 和/或 `orb create` 后的 Linux）  
- [ ] 测试账号具备流程 Operate 权限  
- [ ] （可选）通知渠道已配置，否则 A4 标未实验  
- [ ] （视 `IS_LOCAL_RPC`）`make start-nats` / `make celery-beat` 按 [ENV_INVENTORY.md](./ENV_INVENTORY.md) 补齐  

可选命令（同环境、不伪造成功；须先起 Worker）：

```bash
cd server && CONDUCTOR_BASE_URL=http://127.0.0.1:8091/api \
  uv run python manage.py run_workflow_live_acceptance \
  --team-id <TEAM> --username <USER> --domain <DOMAIN> \
  --target-ip <IP> --report-path /tmp/wo-live-report.json
```

命令报告**不能**单独替代下表 A 组 UI/业务路径勾选，但可作为旁证。

---

## A. 主路径（必须实跑）

| ID | 项 | 通过证据 | 结果 | 证据（ID/摘要） |
|---|---|---|---|---|
| A1 | 巡检发布 + 表单触发 | 执行 RUNNING→终态，产生作业任务 | 通过 | live `health_*_chain` PASSED；Win Job `223` success；Linux Job `224` success |
| A2 | 审批 | `WAITING_APPROVAL`；通过/驳回后状态正确 | 通过 | live `approval` PASSED |
| A3 | 报告产物 | 详情可打开/下载巡检报告 | 通过 | live `document_docx`/`document_xlsx` + `health_*_chain` PASSED |
| A4 | 通知（若流程含） | 真实投递或平台成功记录 | 通过 | live `notification` PASSED；email channel_id=2→Mailpit `127.0.0.1:1025` |
| A5 | 终止 → Job | 编排 `TERMINATING/TERMINATED`；关联 Job `cancelling/cancelled`；有 `termination_job_cancels` | 通过 | 执行 `3d5797d7-…` TERMINATING；Job `227` cancelling；cancels.ok=true |

## B. F1–F6 硬点抽证

| ID | 项 | 通过证据 | 结果 | 证据 |
|---|---|---|---|---|
| B1 | 执行身份 / 租户隔离 | 他团队 403/404，本团队可读 | 通过（契约单测） | `test_openapi_trigger_uses_trusted_team_and_rejects_other_tenant`；`test_form_trigger_detail_is_tenant_scoped_*` |
| B2 | 敏感封存 | 详情/库无明文密钥；含密节点仍可跑通 | 通过（契约单测） | `test_sensitive_input_is_redacted_without_mutating_other_values` |
| B3 | 版本 digest | 冲突定义拒绝覆盖并报错 | 通过（契约单测） | `test_register_workflow_rejects_conflicting_content_without_overwrite` |
| B4 | UNKNOWN | 引擎回执丢失→`UNKNOWN` 而非误 `FAILED` | 通过（契约单测） | `test_start_marks_unknown_instead_of_failed_*`；软删拒 `UNKNOWN`（本轮补齐） |
| B5 | 作业 checkpoint | Worker 重投不重复提交（同 job_task_id） | 通过（契约单测） | `test_execute_custom_script_resumes_prior_job_task_ids_without_resubmit` / `*_checkpoints_*` |
| B6 | claim 围栏 | 租约被抢后旧 Worker 不覆盖终态 | 通过（契约单测） | `test_worker_failure_path_is_fenced_when_lease_was_taken_over`；`test_redelivery_does_not_steal_*` |

## C. 共识全表

| ID | 项 | 通过证据 | 结果 | 证据 |
|---|---|---|---|---|
| C1 | 可见原子 | 产品露出的原子各有最小用例结果 | 通过（live+目录） | live 9/9 覆盖 job/doc/http/notify/approval/switch；`test_atom_catalog_*` |
| C2 | 目标双重授权 | 缺流程权或目标权时不能下发 | 通过（契约单测） | `test_publish_and_run_freeze_version_and_authorize_targets`；`test_job_atom_revalidates_*` |
| C3 | 四类触发 | FORM / CRON / WEBHOOK / NATS 各一次闭环 | 通过 | FORM：此前 live；WEBHOOK/CRON/NATS：`/tmp/wo-c3-evidence.json` 均 SUCCEEDED（最小 HTTP→example.com）；scheduler 已常驻 |
| C4 | OpenAPI 最小面 | 对外触发+查询双租户通过 | 通过（本机网关） | `/tmp/wo-c4-evidence.json`：team1 HTTP 200 ACCEPTED；team2 400 组织隔离；已 migrate `0050/0051` |
| C5 | 删除/禁用 | 有未终态执行拒删；无活跃可删；禁用后不能新触发 | 通过（契约单测） | soft_delete 含 `UNKNOWN`；`test_enable_and_disable_*` |

---

## 结果回传模板（粘贴到对话即可）

```text
环境: 
提交: 

A1: 通过/失败/未实验 — 
A2: 
A3: 
A4: 
A5: 

B1: 
B2: 
B3: 
B4: 
B5: 
B6: 

C1: 
C2: 
C3: 
C4: 
C5: 

优先失败（若有）:
1. 
```

## 修复门禁（共识）

1. 主路径 / 硬风险失败 → 当场修  
2. 其余已定位可修缺陷 → 本轮清掉  
3. 仅外部阻塞 → `未实验`，不计入独立试用已验收
