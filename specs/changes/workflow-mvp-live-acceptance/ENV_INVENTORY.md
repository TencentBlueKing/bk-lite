# 本地真实验证环境假设与进程清单

Date: 2026-10-13（已拉起并冒烟）  
约定：控制面本机 + OrbStack Docker 中间件 + Windows `job-web3` + Orb Linux 目标。

## 1. 环境假设

| 角色 | 落点 |
|---|---|
| 控制面 | Mac：API `:8011`、Web `:3000` |
| 中间件 | OrbStack Docker：Conductor / Postgres / Redis / NATS(本地容器) / MinIO |
| 作业消息面 | Server `.env` 的 `NATS_SERVERS`（当前指向可达的共享 NATS `192.168.97.2`）；ansible-executor 已对齐该主机 |
| Windows 目标 | `job-web3` / `10.10.90.120` / Target id=`5` / 云区域 `5` |
| Linux 目标 | Orb 机器 `bklite-linux-target` / `192.168.139.176` / Target id=`33` |
| 本地 RPC | `server/.env` 已设 `IS_LOCAL_RPC=1`（NodeMgmt 等同进程） |

## 2. 当前进程（开测时需保持）

| 组件 | 状态 | 备注 |
|---|---|---|
| Conductor / PG / Redis / MinIO / 本地 NATS 容器 | OK | compose / 既有容器 |
| uvicorn `:8011` | OK | 需带 `IS_LOCAL_RPC=1` |
| next `:3000` | OK | |
| `run_workflow_worker` | OK | `CONDUCTOR_BASE_URL=http://127.0.0.1:8091/api` |
| Celery worker | OK | broker=`redis://127.0.0.1:6379/0` |
| `nats_listener` | OK | 作业回调必需 |
| ansible-executor (`local-ansible-executor`) | OK | 需 `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`（macOS fork）+ 与 Server 同 NATS 凭据；`ansible.windows` collection 已装到 `agents/ansible-executor/collections` |
| Mailpit（SMTP 1025） | OK | 演示邮件渠道指向 `127.0.0.1:1025`；UI `http://127.0.0.1:8025` |

## 3. 冒烟证据（2026-10-13）

| 检查 | 结果 |
|---|---|
| Windows 作业 `job-web3` | JobExecution `223` → `success` |
| Linux 作业 Orb | JobExecution `224` → `success`（stdout `bklite-linux-ok`） |
| live acceptance | **passed=9 failed=0**（报告 `/tmp/wo-live-report.json`；`--timeout 180`） |
| A5 终止→Job | 执行 `3d5797d7-64ad-4b66-a84b-87d80f7d8ce6` → `TERMINATING`；Job `227` → `cancelling`；`termination_job_cancels.ok=true` |

### live acceptance 分项

- PASSED（9/9）: `engine_switch`, `document_docx`, `document_xlsx`, `http_request`, `notification`（email channel_id=2→Mailpit）, `approval`, `job_execute_probe`, `health_docx_chain`, `health_xlsx_chain`

## 4. 拉起命令备忘（进程挂了可重跑）

```bash
# API（若未在跑）
cd server && IS_LOCAL_RPC=1 uv run uvicorn asgi:application --host 0.0.0.0 --port 8011 --reload --workers 1

cd server && IS_LOCAL_RPC=1 CONDUCTOR_BASE_URL=http://127.0.0.1:8091/api \
  uv run python -u manage.py run_workflow_worker

cd server && IS_LOCAL_RPC=1 uv run celery -A apps.core.celery worker -l info -c 1

cd server && IS_LOCAL_RPC=1 uv run python manage.py nats_listener

# 演示邮件渠道 SMTP（channel id=2 → 127.0.0.1:1025）
docker run -d --name mailpit-bklite -p 1025:1025 -p 8025:8025 axllent/mailpit

cd agents/ansible-executor
# 从 server/.env 解析 NATS_USERNAME/PASSWORD 后：
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES NATS_INSTANCE_ID=local-ansible-executor \
  uv run python main.py --config ./config.yml
```

## 5. 明确未宣称

- B/C 硬点与共识项见 [validation.md](./validation.md)；未实验项须写外部阻塞原因  
- 预发对照尚未做
