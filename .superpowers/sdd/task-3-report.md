# Task 3：真实 Redis 竞态、Runbook 与最终门禁

## 改动

- 将真实 Redis fixture 拆为共享 Unix socket：同步/异步 Redis 客户端均使用
  DB 15，每项测试前后 `FLUSHDB`；服务关闭持久化，fixture finally 中关闭
  客户端、终止 `redis-server`、等待退出并删除随机 `/tmp` socket。
- 用真实 Redis 覆盖 Lua 原子删除边界、两副本共享锁、marker 值替换、确认
  窗口内进入 queue/in-progress/waiting callback、非 owner token 释放、
  WRONGTYPE 隔离，以及 callback context 损坏时 Lua 的保守保留。
- 修复首检 callback context 为损坏 JSON、数组或非法 `status` 时中止整轮的
  缺陷：仅保留该 running marker、累计 `marker_errors`，并继续处理其他 marker；
  Lua 对同类不完整结构也拒绝删除。
- README 增加自动启动清理的默认开启、5 秒二阶段确认、10000/30 秒边界、
  Redis 分布式锁、fail-open、环境变量、脱敏日志和人工 CLI 边界说明。
- 审查修复：以 Host Remote 实际写入的 `waiting_callback`、
  `execution_finished`、`callback_timeout` 为唯一 execution 白名单；未知、
  非字符串和结构损坏均按单 marker `marker_errors` 保留。Lua 用独立 `-1`
  结果码表示二检损坏，Python 仅将 `eval == 1` 视为删除成功。
- fixture 在启动失败时记录最后连接异常、socket 和进程状态；客户端初始
  `FLUSHDB` 失败仍关闭，停止时 `communicate(timeout=5)`，超时后 kill 并
  有界 wait，最外层 finally 删除 socket。

## TDD 证据

- 首检损坏 JSON/数组结构的参数化单测先 RED：分别稳定抛出
  `JSONDecodeError` 与 `AttributeError`，证明会中止整轮；最小修复后
  `2 passed`。
- Runbook 合同先 RED：缺少启动开关及安全边界说明；补充 README 后 `1 passed`。
- 真实 Redis RED：sandbox 外首次运行新覆盖为 `12 passed, 2 failed`，两项
  损坏 callback context 同样分别复现 `JSONDecodeError` / `AttributeError`；
  最小修复后先复跑为 `14 passed in 2.28s`，补充 Lua 确认窗口损坏 context
  回归后最终复跑为 `16 passed in 2.50s`。
- 审查 RED：首检未知 execution 会得到 `success`；Lua 二检坏 context 的
  `-1` 被 Python truthiness 误记为删除。分别以 7 项状态矩阵和 `-1` fake
  Redis 合同复现，最小修复后定向 `8 passed`，最终真实 Redis `31 passed in
  3.45s`。

## 验证

- 相关非 Redis 回归：`157 passed`。
- 依赖合同（排除 sandbox 内缺少 `uv` 的离线同步用例）：`6 passed, 1 deselected`。
- `py_compile` 和 `git diff --check` 通过。
- 当前 sandbox 不能连接临时 Unix socket：`redis-server v6.2.4` 可执行但每个
  fixture 的 100 次 ping 均失败；真实 Redis 已使用提升权限的 sandbox 外命令
  验证。精确命令：

  ```bash
  cd agents/stargazer && ./.venv/bin/pytest \
    tests/test_task_queue_cleanup_redis_integration.py \
    tests/test_dependency_lock_contract.py::test_docker_context_and_runbook_expose_task_queue_cleanup_cli \
    -q
  ```

## 环境顾虑

- task worktree 不含 `server/.venv`，故使用主仓受控虚拟环境；Black、isort、
  flake8 已对全部触及 Python 文件通过。此前 8 个同功能文件 E501 均已机械
  拆行或缩短测试名收口。
- `test_locked_sync_rejects_stale_lockfile_offline` 在本 sandbox 因子进程找不到
  `uv` 而失败，不是业务断言失败；需在具有 `uv` 的 sandbox 外环境复跑。

## 提交

本报告与实现一并提交；最终提交 hash 以本任务完成时的 Git 记录为准。

## 最终审查收口

- 锁释放 Redis 异常不再静默成功：核心返回 `warning/redis_error`；后台核心
  抛出 `RedisError` 同样记录脱敏 `reason=redis_error`，非 Redis 异常仍为
  `cleanup_failed`。RED 为 3 项失败，GREEN 为 7 项通过。
- 批准计划的五个 Python 文件已在 `agents/stargazer` cwd 用主仓
  `server/.venv` 实际格式化并通过 Black、isort、flake8（均退出 0）。
- 正式 `make lint` 仍是既有环境基线失败：`pre-commit run --all-files` 后报
  `make: pre-commit: No such file or directory`，本次未扩大范围安装依赖。
- 最终在 sandbox 外复跑真实 Redis 集成与运行手册合同：`31 passed in 3.59s`。

### 覆盖率

```bash
PYTHONPATH=/Users/windyzhao/Documents/Canway/weops_X/cmdb/bk-lite/server/.venv/lib/python3.12/site-packages \
COVERAGE_FILE=/tmp/stargazer-task3-coverage \
./.venv/bin/python -m coverage run \
  --source=core.task_queue_startup_cleanup,core.task_queue \
  -m pytest tests/test_task_queue_startup_cleanup.py \
  tests/test_task_queue_cleanup.py tests/test_task_queue_cleanup_cli.py \
  tests/test_collect_multicred.py \
  tests/test_host_collector.py::TestWorkerRunningFlag \
  tests/test_host_collector.py::TestHostRemoteRuntime -q
```

该命令及后续 `coverage report -m` 的结果为：启动清理核心
`core/task_queue_startup_cleanup.py` 90%，满足 75% 门槛；生命周期相关的
历史大模块 `core/task_queue.py` 57%，其未覆盖部分主要是 enqueue、状态查询
和 host remote processing 的既有路径。上述 159 项相关回归仍覆盖本次启动
生命周期、结果映射和 Redis 异常改动；两文件合计 70%，不将其误报为整体 75%。

以任务基线 `b727334ef` 的零上下文 diff 为准，使用 `coverage json` 的
`executed_lines ∪ missing_lines` 仅统计新增的可执行行，差异行覆盖率为
`290/338 (85.80%)`：`core/task_queue.py` 为 `97/124 (78.23%)`，
`core/task_queue_startup_cleanup.py` 为 `193/214 (90.19%)`。未覆盖的新增
可执行行如下，均为未触发的防御或异常分支；不影响该任务已覆盖的 Redis
错误与启动清理主流程：

- `core/task_queue.py`: 59、158、211、241-242、248-249、263-266、357-358、
  414、484、493、515、560、564、569、613、627、631、675、703、717、734。
- `core/task_queue_startup_cleanup.py`: 91、93、97、99、103、109、111、169、
  197-198、208-209、276、281-282、376、391-392、399-401。
