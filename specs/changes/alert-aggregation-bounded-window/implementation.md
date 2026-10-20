# 告警聚合低内存优化实施流程

Status: implemented

对应方案：[spec.md](spec.md)。本文件只记录实施顺序、改动边界和测试入口。

完成证据：2026-10-19 在项目 Postgres 测试库执行下面的命令，`111 passed in 41.71s`。本机 SQLite 迁移会在 `NewSessionEventRelation` 上失败，所以不用 `DB_ENGINE=sqlite`。没有同环境 RSS 基线，不写节省比例。

## 顺序

1. 冻结窗口。`WindowConfig` 接受 `window_end`。起点、会话终点和 SQL 上界都从它推导。ORM 使用 `[window_end - window_size, window_end)`。
2. 分批装入 DuckDB。按主键每 1000 行投影，去掉整窗 list 和 Pandas。摘要 SQL 去掉 `LIST(event_id)`，资源名按字典序拼接，标题回退和单事件描述取 `received_at DESC, pk DESC`。
3. 组事务。摘要一次取出。每组用同一分组表达式按主键分批挂接，再按主键分批归约历史成员。一组失败只回滚该组。
4. 恢复。判断和补挂都不把整组 Event 一次装进内存。组内新关联提交时写入 Outbox，kind 为 `recovery_reattach`，幂等键 `recovery-reattach:{alert_pk}:{window_end_iso}`。
5. 调度保持原顺序。循环结束后对已成功组调度分派，再因失败组抛错，从而不推进 `last_execute_time`。任务末尾仍跑 `TimeoutChecker`。

## 代码边界

| 区域 | 文件 |
|---|---|
| 窗口 | `aggregation/window/factory.py` |
| 装载 | `aggregation/engine/connection.py`、`aggregation/batching.py` |
| SQL | `aggregation/templates/macros.jinja`、`sliding_window.jinja`、`session_window.jinja`、`aggregation/query/builder.py` |
| 管线 | `aggregation/processor/aggregation_processor.py` |
| 归约与建警 | `aggregation/builder/event_reducer.py`、`alert_builder.py` |
| 恢复与 Outbox | `aggregation/recovery/recovery_checker.py`、`service/outbox.py` |

不改 Instant、缺失检测算法、`RecoveryHandler` 的接入主路径，以及 Outbox 投递状态机。

## 测试

- 既有聚合、建警、SQL 和恢复测试必须继续通过。
- 新增 `server/apps/alerts/tests/test_aggregation_bounded_window.py`：窗口右端、资源名顺序、跨批成员不丢、部分组失败仍分派已成功组、会话终点锚在 `window_end`、Outbox 补挂和同一轮不重复入队。
- 运行：

```bash
cd server && unset DB_ENGINE DB_NAME && uv run pytest \
  apps/alerts/tests/test_aggregation_bounded_window.py \
  apps/alerts/tests/test_aggregation_processor.py \
  apps/alerts/tests/test_aggregation_sql_builder_service.py \
  apps/alerts/tests/test_alert_builder.py \
  apps/alerts/tests/test_enrichment_downstream_service.py \
  apps/alerts/tests/test_recovery_handler.py \
  apps/alerts/tests/test_timeout_checker.py \
  --no-cov
```

## 完成标准

上述命令覆盖实施文档列出的行为。方案状态记为 implemented。没有同环境 RSS 基线，不写节省比例。

下面几项仍按方案原文留着，这次没有另做：

- enrichment 分组仍把整段 JSON 写入 DuckDB，分组表达式用 `json_extract_string` 取值。
- 没有设置 DuckDB `memory_limit` 或临时目录。引擎限额不是进程 RSS，容量目标不记完成。
- 方案 Testing Decisions 里的十万级负载、加载中途漏扫、交接竞态、投递耗尽和并发关闭，没有单独用例。
