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

## TDD 证据

- 首检损坏 JSON/数组结构的参数化单测先 RED：分别稳定抛出
  `JSONDecodeError` 与 `AttributeError`，证明会中止整轮；最小修复后
  `2 passed`。
- Runbook 合同先 RED：缺少启动开关及安全边界说明；补充 README 后 `1 passed`。
- 真实 Redis RED：sandbox 外首次运行新覆盖为 `12 passed, 2 failed`，两项
  损坏 callback context 同样分别复现 `JSONDecodeError` / `AttributeError`；
  最小修复后先复跑为 `14 passed in 2.28s`，补充 Lua 确认窗口损坏 context
  回归后最终复跑为 `16 passed in 2.50s`。

## 验证

- 相关非 Redis 回归：`149 passed`。
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

- 当前 sandbox 的 `PATH` 与 `.venv` 均没有 `black`、`isort`、`flake8`；对应
  原始静态门禁无法执行，未将其误报为通过。
- `test_locked_sync_rejects_stale_lockfile_offline` 在本 sandbox 因子进程找不到
  `uv` 而失败，不是业务断言失败；需在具有 `uv` 的 sandbox 外环境复跑。

## 提交

本报告与实现一并提交；最终提交 hash 以本任务完成时的 Git 记录为准。
