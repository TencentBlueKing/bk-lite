# Stargazer 启动后孤儿任务标记自动清理设计

## 背景

Stargazer 使用共享 Redis 保存 ARQ 队列和应用层去重标记。异常退出可能留下 `task:running:*` 或 `task:dedupe:*`，使后续相同任务被误判为已在队列或执行中。

项目已经提供容器内人工运维 CLI，用于 dry-run、清理 pending/in-progress、备份和恢复。本变更不替代该 CLI，只增加一个风险更低的自动恢复动作：Sanic 正常启动后，在后台删除可以确定为孤儿的 marker。

生产环境存在多个 Stargazer 副本，并共享同一个 Redis。自动清理必须全局选主、并发安全、资源有界，且任何失败都不能阻碍 Sanic 或 ARQ Worker 启动。

## 目标

- Sanic 监听端口正常启动后再调度后台清理，不增加启动阻塞。
- 多容器、多 Sanic worker 共享 Redis 时，同一时刻最多一个清理器工作。
- 只删除明确孤儿的 `task:running:*` 和 `task:dedupe:*`。
- 不删除 pending、in-progress、job、retry、result 或任何其他 Redis 数据。
- 清理失败、锁竞争、超时或状态漂移时 fail-open：记录脱敏告警并结束后台任务。
- 保留现有人工 CLI、自动备份和恢复流程。

## 非目标

- 不自动清空 `arq:queue`。
- 不自动删除长时间 pending 的 job。
- 不终止或回收 in-progress job。
- 不替代人工 CLI 的 `--all-pending`、`--include-in-progress`、备份或恢复能力。
- 不新增 HTTP 清理接口。
- 不改变 Supervisor 对 Sanic 和 ARQ Worker 的现有启动顺序。

## 孤儿定义

一个 marker 只有同时满足以下条件才是明确孤儿：

1. key 匹配 `task:running:*` 或 `task:dedupe:*`；
2. marker 当前值仍等于第一次扫描记录的 job ID；
3. `ZSCORE arq:queue <job_id>` 不存在；
4. `arq:in-progress:<job_id>` 不存在。

`arq:job:*`、`arq:retry:*` 和 `arq:result:*` 不参与“活跃”判定，也不会被自动删除。自动动作只删除 marker；其余状态留给 ARQ 或人工 CLI 处理。

## 架构

### 组件边界

新增独立模块 `core/task_queue_startup_cleanup.py`，包含：

- 启动清理配置解析；
- Redis 分布式锁获取与按 token 释放；
- 有界 `SCAN`；
- 两阶段候选确认；
- 单 marker 原子判断与删除；
- 结构化统计结果。

`core/task_queue.py` 只负责生命周期集成：

- `after_server_start` 使用 `asyncio.create_task()` 创建后台任务并立即返回；
- 将 task 保存到当前 `TaskQueue` 实例，避免被垃圾回收；
- `after_server_stop` 取消并等待未完成任务，再关闭 Redis pool。

现有 `core/task_queue_cleanup.py` 和 `scripts/clear_task_queue.py` 保持人工运维语义，不复用自动清理入口，避免“人工清 pending”和“自动只清孤儿”混淆。

### 多副本选主

每个 Sanic worker 都可以创建后台任务，但任务首先以非阻塞方式竞争固定 Redis 锁：

```text
stargazer:maintenance:startup-orphan-cleanup
```

锁使用随机 token 和 60 秒 TTL。未获得锁的任务记录 `lock_not_acquired` 后立即结束。释放锁时通过 Lua 比较 token 后删除，禁止误删其他实例后来获得的锁。

自动清理的总预算为 30 秒，短于锁 TTL。即使持锁进程崩溃，TTL 也会自动解除锁定。

### 两阶段确认

后台任务按以下流程执行：

1. 使用 `SCAN` 分别扫描 running 和 dedupe marker；禁止 `KEYS`。
2. 最多检查 10,000 个 marker；达到上限后停止扫描并记录 `limit_reached`。
3. 第一次读取 marker 值，并检查 queue/in-progress；只记录疑似孤儿。
4. 所有候选统一等待 5 秒，不阻塞 Sanic 请求处理。
5. 对每个候选执行原子 Lua：再次比较 marker 值、queue 成员和 in-progress key；条件仍成立才执行 `DEL marker`。

第二阶段 Lua 的逻辑等价于：

```text
if GET(marker) == expected_job_id
   and ZSCORE(arq:queue, expected_job_id) is nil
   and EXISTS(arq:in-progress:<expected_job_id>) == 0
then
   DEL(marker)
else
   preserve(marker)
end
```

这避免了扫描、Worker 领取任务、重新入队和 marker 被新任务覆盖之间的检查后删除竞态。

## 配置

默认配置如下：

| 环境变量 | 默认值 | 含义 |
| --- | ---: | --- |
| `TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED` | `true` | 是否启用启动后后台清理 |
| `TASK_QUEUE_STARTUP_ORPHAN_CONFIRM_DELAY_SECONDS` | `5` | 两次确认之间的等待时间 |
| `TASK_QUEUE_STARTUP_ORPHAN_MAX_MARKERS` | `10000` | 单次最多扫描的 marker 数 |
| `TASK_QUEUE_STARTUP_ORPHAN_TIMEOUT_SECONDS` | `30` | 单次后台任务总时间预算 |

锁 TTL 固定为 60 秒。配置解析失败时不执行清理，记录配置告警并继续服务；不会用不确定配置扩大扫描或删除范围。

紧急回滚只需设置：

```text
TASK_QUEUE_STARTUP_ORPHAN_CLEANUP_ENABLED=false
```

无需回滚镜像，也不影响人工 CLI。

## 失败处理与日志

自动清理是辅助恢复能力，统一 fail-open：

- Redis 连接失败：记录 `redis_error`，结束后台任务；
- 未获得锁：记录 `lock_not_acquired`，正常结束；
- 配置非法：记录 `invalid_config`，不执行扫描；
- 达到扫描上限：保留未处理 marker，记录 `limit_reached`；
- 超时：取消剩余工作，记录 `timeout`；
- 单 marker 类型错误或 Lua 错误：保留该 marker、增加 error 计数，继续处理其他候选；
- 服务停止：取消任务并安全释放自身持有的锁。

日志仅输出事件、状态、原因和计数，不输出 Redis 密码、任务参数、marker 值、job payload 或原始异常文本。示例：

```text
event=task_queue_startup_cleanup status=skipped reason=lock_not_acquired
event=task_queue_startup_cleanup status=success scanned=120 candidates=8 deleted=7 preserved=1 errors=0
event=task_queue_startup_cleanup status=warning reason=limit_reached scanned=10000
event=task_queue_startup_cleanup status=warning reason=redis_error
```

## 数据安全与回滚

自动模式只删除可由后续入队重新创建的临时 marker，并经过 5 秒二次确认和 Lua 原子复核，因此不生成 DUMP 备份，避免每次启动产生包含敏感任务数据的临时文件。

人工 CLI 的 dry-run、`--apply`、`--all-pending`、in-progress 安全门、DUMP 备份及 `--restore-backup` 全部保留。需要处理 pending 或恢复数据时仍使用人工 CLI。

## 测试设计

### 核心行为

- running/dedupe 明确孤儿会被删除；
- queued、in-progress、marker 值变化和刚创建的 marker 会被保留；
- 自动模式只产生 marker `DEL`，不修改任何 ARQ job、queue、retry、result 或其他 key；
- 非 string marker fail-closed，保留并计入错误。

### 并发与真实 Redis

- 多个清理器同时启动时只有一个获得分布式锁；
- 第一次扫描后 job 重新入队或进入 in-progress，第二阶段必须保留 marker；
- marker 被新 job ID 覆盖后，旧候选不能删除新值；
- 真实 Redis 验证 Lua 的原子判断、按 token 解锁和删除边界。

### Sanic 生命周期

- `after_server_start` 只创建任务，不等待清理完成；
- Redis 故障或清理异常不影响 Sanic 启动；
- 多 worker 均注册时，分布式锁保证只有一个实际执行；
- `after_server_stop` 取消并等待后台任务。

### 资源与日志

- 达到最大 marker 数后停止并报告截断；
- 超过时间预算后安全取消；
- 锁竞争立即跳过；
- 结构化日志不包含 Redis 密码、任务参数、job ID 或原始异常内容。

## 验收标准

- 多副本共享 Redis 时，同一时刻最多一个后台清理器执行。
- Sanic API 可用不等待清理结束。
- 明确孤儿 marker 在二次确认后被删除。
- queued、in-progress 和其他 Redis 数据零修改。
- Redis 故障、超时、配置错误和状态变化都不会阻碍服务启动。
- 设置 feature flag 为 false 后不创建清理任务。
- 原有人工 CLI 的行为和测试保持通过。
