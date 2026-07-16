# Task 6 实施报告

## 状态

完成。同步与采集共用数据库唯一键 `node_mgmt_sync` 实现全局单活；阻塞运行保留独立历史记录。运行具备 30 分钟截止时间、分页/区域循环心跳、统一终态收敛和陈旧运行条件恢复。

## 关键实现

- `acquire_run()` 依赖 `active_scope` 唯一约束裁决；持锁 INSERT 使用内层 `transaction.atomic()` savepoint，`IntegrityError` 后可安全创建 `blocked/RUN_ALREADY_ACTIVE` 历史。
- `finish_run()` 以 `pk + generation + 当前状态` 条件更新终态，原子清空 `active_scope`；`partial_success/timeout/failed/blocked` 不被后续异常覆盖。
- `heartbeat_run()` 在 deadline 到期时稳定写入 `timeout/RUN_TIMEOUT` 并释放锁；`recover_stale_runs()` 仅回收持锁、超时、非终态运行，并用 generation 与原 scope 防止旧 Worker 清除新锁。
- 非容器节点与接入点分页、同步区域循环和采集任务循环均刷新心跳并检查截止时间。
- Celery 入口先恢复陈旧运行，再调用既有 trigger；同步返回 dict、采集返回 `None` 的外部合同保持不变；异常日志只记录稳定异常类型。

## TDD 与验证

- RED：execution 首轮 7 项均因缺少 acquire/finish/recover/heartbeat API 失败；Celery 编排入口及接入点分页心跳分别确认缺失。
- GREEN：`test_node_mgmt_sync_execution.py` 17 passed。
- Task 2–6 组合回归：122 passed（models/reconciler/views/helpers/resilience/persistence/execution）。
- 覆盖补测：84 passed；coverage XML + 零上下文 diff 等价计算新增生产可执行行 `97/97 = 100%`。
- `git diff --check` 通过；新增文件 black/isort/flake8 通过。service 与两个旧测试整文件仍有历史 black 基线，flake8 仅保留既有 `service:922 E125`、旧 resilience 长行 `E501`，未扩大格式污染。

## 关注项

- Task 8 的 submitted 父子运行聚合未提前实现。
- `diff-cover` 未安装，覆盖率使用 coverage XML 与 git diff 等价计算。

## Critical / Important 审查修复

- 统一租约守卫现以 `pk + generation + active_scope=node_mgmt_sync + 非终态 + deadline_at>now` 原子校验并刷新心跳；节点 RPC、区域载荷、每条主机 create/update、区域采集任务写入/参数推送、关联调度及每个 collect submit 均在副作用前后复验。
- 单次已发出的外部调用无法中途取消；调用返回后立即复验，失租或超时 Worker 抛出稳定 `RUN_TIMEOUT` / `RUN_NOT_ACTIVE`，不会进入下一副作用。已完成的外部调用不宣称回滚。
- `success/partial_success` 终态使用同 generation、仍持全局锁且 deadline 未过期的原子 CAS；stale 回收或过期后，旧 Worker 不能覆盖 `timeout`。
- `recover_stale_runs()` 收敛为包含 `active_scope + status + deadline_at__lte` 的单条条件 UPDATE，不再先物化候选后以缺少 deadline 的条件更新。
- 未额外加入 heartbeat stale 回收条件；本轮严格保持 Task 6 的硬 deadline 语义，活跃长 RPC 依靠返回后栅栏停止后续副作用。

## 审查修复验证

- TDD RED：首条主机写后过期仍继续、最后一次 collect submit 跨 deadline 仍成功、stale 最终 UPDATE 缺 deadline 条件均稳定失败；旧 Worker 覆盖保护测试同时固化。
- GREEN：execution `24 passed`；persistence/resilience `13 passed`；Task 2–6 全回归 `136 passed`。
- 新增生产可执行行覆盖率：`65/70 = 92.86%`（coverage JSON + 零上下文 diff 等价计算）。
- 静态门禁：两个触及测试通过 black/isort/flake8，service 通过 isort，`git diff --check` 通过；service 整文件仅保留未触及历史 `E125`（原 922 行，因增量行位移现为 962 行）。
