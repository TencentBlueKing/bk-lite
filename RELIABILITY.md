# RELIABILITY.md

> 可靠性与韧性约定:故障模式、回滚、Runbook 入口。运行细节见 [AGENTS.md](AGENTS.md)。

## 1. 依赖拓扑(谁挂了影响谁)

| 依赖 | 服务于 | 失效表现 | 兜底 |
|------|--------|---------|------|
| PostgreSQL(或 `DB_ENGINE` 指定库) | server 全部 | 接口 500 / 启动失败 | 多库适配,迁移可回退 |
| NATS | 采集(Stargazer/Collector)、SSO、分布式消息 | 无数据上报 / 登录同步停 | Worker 先于 Server 起 |
| Celery + Beat | 告警检测、定时任务 | 告警/定时不触发 | 见下方告警闭环 |
| Redis | Stargazer、缓存 | 任务不被消费 | Server/Worker Redis 必须一致 |
| MinIO | 对象存储 | 附件/模型读写失败 | — |
| MLflow | mlops ↔ algorithms | 训练追踪丢失 | — |

## 2. 关键韧性设计:告警生命周期闭环

`alerts` 的通知采用**三层闭环**(见近期提交 `d97feca85`):
1. 重试(应用层)
2. DB 追踪(状态可查、可补偿)
3. Celery 补偿(漏发兜底)

> 改动 `alerts` 通知链时,三层缺一不可;`destroy()` 中的 `AlertLifecycleNotifier.notify_alerts` 调用属于闭环一环,不可随手删(曾回归,见 `3c44d1243`)。

## 2.5 下发安全:插件/作业不得伤害目标主机(红线)

部分服务会向**目标服务器下发插件 / 执行作业**(node_mgmt sidecar、job_mgmt、nats-executor/ansible-executor、stargazer 采集)。这类操作直接作用于客户机器,**第一原则:绝不能致目标主机崩溃、死机或数据丢失**。

约束:
- **资源边界**:下发/执行有 CPU/内存/磁盘/超时上界,杜绝打满目标机或无上界拉取(参见技术债中多处「无上界 OOM/DoS」)。
- **幂等可回滚**:重复下发不产生副作用;安装/变更失败可回退,不留半成品。
- **不可逆操作显式确认**:删除、覆盖、重启目标服务等高危动作,先 **dry-run / 预检**,再受控执行。
- **凭据与传输**:下发链路校验 TLS/host key(勿 `skip-tls` / `AutoAddPolicy`);凭据不落明文(参见 [SECURITY.md](SECURITY.md))。
- **必有测试**:下发路径的资源边界、失败回滚、越权拒绝必须有自动化测试(单测/集成),不可只手验。

> 改动任何「下发/执行到目标机」的代码,本节即红线;测试要求见 [QUALITY_SCORE.md §4](QUALITY_SCORE.md)。

## 3. 回滚标准动作

| 层 | 动作 |
|----|------|
| 代码 | `git revert <commit>` |
| 数据库 | `python manage.py migrate <app> <target_migration>` 回退 |
| 运行 | 回滚到上一个可用镜像 tag 重新部署 |
| 前端产物 | `pnpm clean && pnpm install && pnpm build` 或回退镜像 tag |
| npm 包(webchat) | 按 npm 版本策略撤回/升补 |

## 4. Runbook(完整版在 AGENTS.md §Runbook)

高频项摘录:
- `make dev` 启动失败 → 核对 `.env` 的 DB/NATS/Redis。
- `make test` 因迁移失败 → 先 `make migrate`,再查 `server/scripts/check_migrate/`。
- Stargazer 无任务消费 → Redis/NATS 与 Server/Worker 一致,**先起 Worker 再起 Server**。
- K8s 采集器无数据 → 检查 `secret.env` 的 `CLUSTER_NAME/NATS_*` 与 `ca.crt`。

## 5. 变更的可靠性自检

- [ ] 触及异步任务?已确认重试/幂等
- [ ] 触及迁移?已验证可回退(`sqlmigrate` / 逆向迁移)
- [ ] 触及外部依赖调用?失败路径有日志且不吞异常
- [ ] 触及告警/通知?三层闭环完整
- [ ] 触及插件/作业下发?资源有边界、失败可回滚、不可逆操作有预检,且有测试(见 §2.5)
- [ ] 触及数据库查询?走 ORM,无原生 SQL(跨 `DB_ENGINE` 方言)

> TODO: 补充各服务的健康检查端点与超时/重试默认值清单(确认位置:`*/support-files/release/`、`server/config/components/`)。
