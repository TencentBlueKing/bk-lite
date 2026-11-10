# 02 — 基线对比的历史窗按目标分组

Status: done

Blocked by: 01 — 当前窗按目标分组取回 RED

**What to build:** 带基线对比（上一窗、1 小时前、24 小时前、偏移小时/天、过去几天同一时段）的策略，历史窗也按目标
分组一次取回；对比值、sigma 判断、基线证据曲线与逐目标查询一致。

- [x] 各偏移类历史窗复用 01 的分组读取
- [x] `baseline_days` 的按天读取加上目标维度分组；原有按天回退路径与 20 目标上限的语义保持
- [x] sigma / replay 路径结果一致
- [x] 等价性测试覆盖每种对比方式；查询次数不随目标数增长
- [x] `server/apps/apm/tests` 在 sqlite 下通过
- [x] 本变更 spec 状态更新为 done，并补完成证据

## Completion evidence

- 新增 25 个测试：`server/apps/apm/tests/test_policy_grouped_baseline.py` 22 个，`server/apps/apm/tests/test_victoriatraces_adapter.py` 3 个。覆盖上一窗、1 小时前、24 小时前、偏移小时、偏移天的对比值和基线证据曲线，`baseline_days` 的均值与 sigma 判断，回放仍逐目标且结果一致，N=3 与 N=30 调用次数相同，分组成功时 21 个目标保持原上限，唯一 Span 超上限后退回逐日查询并把上限收到 20，HTTP 依赖保持逐目标，语句别名重叠整轮退回且不记 `last_failed_at`，其他分组失败记全部目标失败，以及按天 LogsQL 的目标维度、超过 1 天跳过去重、依赖身份重叠退回。
- 入口偏移窗的分组读取带趋势，基线曲线才与逐目标 `service_red` 的 timeseries 一致；依赖历史窗不带趋势。分组按天读取的存储失败记全部目标失败并重新抛出；只有超上限和别名重叠整轮退回逐目标，退回后的逐目标按天失败才走 20 上限。
- 验证命令：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 900 uv run pytest apps/apm/tests --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
- 结果：824 passed，2 skipped，11 failed。失败项与既有 sqlite 基线一致：`test_backfill_table_queries_scale_by_batch_not_release_count`，`test_topology_service.py` 里 8 个 `test_topology_api_*`，`test_existing_apm_outbox_data_survives_portable_unique_upgrade_and_rollback`，`test_owned_alert_lifecycle_backfill_batches_queries_and_keeps_semantics`。相对该基线的 799 passed，本次净增 25 passed。
