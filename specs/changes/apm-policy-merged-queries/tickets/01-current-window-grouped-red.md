# 01 — 当前窗按目标分组取回 RED

Status: done

Blocked by: None

**What to build:** 一条展开出 N 个入口目标（端点 × 版本 × 实例）或 N 个依赖目标的策略，一轮评估的当前窗只发常数次
VictoriaTraces 查询；判断、证据曲线、目标状态与逐目标查询一致；超上限退回逐目标；分组查询失败按现有查询失败处理。

- [x] telemetry store 新增按目标维度分组的 RED 汇总与趋势读取（入口与依赖各一），保留去重口径、慢请求/Apdex、
      唯一 Span 上限与截断检测；内存实现同步提供，供测试与本地使用
- [x] 评估器在一个子任务内先批量取回当前窗，再分发给各目标；Top 操作结果与现状一致且不随目标数增长
- [x] 超上限时本轮退回逐目标路径；分组查询失败时全部目标记查询失败并整轮重试
- [x] 试算 / 预览走同一路径
- [x] 等价性测试（全部端点、指定端点、版本、实例、依赖）、查询次数为常数的测试、适配器 LogsQL 形状测试、
      超上限与失败测试
- [x] `server/apps/apm/tests` 在 sqlite 下通过

## Notes

- 多条件策略已有窗口级缓存，合并后仍需保持“同一窗口只查一次”。同一慢阈值 / Apdex 组合只发一组分组查询。
- 去重口径与 `_deduped_entry_query` 相同：窗口不超过 1 天时按 `trace_id, span_id` 去重，并用 `max()` 保留分组维度。趋势是同一次去重后的区间查询，不带唯一 Span 上限；上限检测在汇总查询上。
- 端点模式 SERVICE 只有一个目标，不走分组。
- Top 操作：当前窗最长 1 天，沿用精确去重路径，只按端点和版本过滤，不按实例。分组键已含操作名且不含实例时，从前 10 派生；否则再发一次分组查询，调用次数不随目标数增长。
- HTTP 依赖的现有过滤含 `http.route:*`，目标之间会重叠，分组会改数值，仍逐目标查。数据库和缓存按分类身份分组。
- 一条 Span 的语句别名（`db.statement` / `db.query.text` / `name`）或系统别名同时命中多个已配置依赖时，分组结果不能代替逐目标 OR 过滤，本轮退回逐目标，不记 `last_failed_at`。VictoriaTraces 里同一依赖身份被拆成多组原始字段、分位值无法合并时，同样退回。
- 分组查询的其他失败沿用查询失败：该服务本轮全部目标记 `last_failed_at`，异常继续抛出供 Celery 重试。超上限使用 `TelemetryUniqueSpanLimitExceeded`，与查询失败分开。
- 试算、预览和单独的 `test_query` 在目标列表不需要现场发现时先走同一分组缓存。全部端点、按实例发现和空依赖列表仍由 `evaluate` / `dry_run` 在展开之后预取。历史对照窗留给下一张 ticket，查询对象本身可以复用。

## Completion evidence

- 新增 22 个测试：`server/apps/apm/tests/test_policy_grouped_red.py` 18 个，`server/apps/apm/tests/test_victoriatraces_adapter.py` 4 个。覆盖全部端点、指定端点、版本、实例、端点×版本×实例、数据库/缓存依赖、HTTP 依赖保持逐目标、语句别名重叠时退回、N=3 与 N=30 调用次数相同、多条件同一窗口只查一次、超上限退回、分组失败记 `last_failed_at` 并重试、试算/`test_query`、Top 操作，以及分组 LogsQL 的维度、去重和上限。
- 验证命令：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 900 uv run pytest apps/apm/tests --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
- 结果：799 passed，2 skipped，11 failed。失败项与干净代码上的既有 sqlite 失败一致：`test_backfill_table_queries_scale_by_batch_not_release_count`，`test_topology_service.py` 里 8 个 `test_topology_api_*`，`test_existing_apm_outbox_data_survives_portable_unique_upgrade_and_rollback`，`test_owned_alert_lifecycle_backfill_batches_queries_and_keeps_semantics`。相对该基线的 777 passed，本次净增 22 passed。
