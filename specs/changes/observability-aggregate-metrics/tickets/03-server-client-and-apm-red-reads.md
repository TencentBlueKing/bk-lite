# 03 — Server 聚合查询客户端与 APM 首页、服务列表、服务 RED 改读

Status: done

Blocked by: 02 — APM 中心 Collector 生成聚合指标

**What to build:** 配置了聚合库后，APM 首页、服务列表的批量 RED、服务详情的 RED（整窗、趋势、Top 操作）读聚合库；
窗口早于聚合起点时回退 VictoriaTraces；聚合库不可用时对应区块降级、缺数据不显示为 0。

- [x] 公共 PromQL 查询客户端（instant / range，超时、可选认证、响应大小上限），只读 `AGG_VICTORIAMETRICS_*`；
      未配置即视为不可用；标签值转义工具
- [x] 聚合起点：运行期周期任务探测并持久化各产品首次出现序列的时间；不在启动期或 `batch_init` 中探测
- [x] APM 读取：在 telemetry store 层新增聚合实现，按 spec 的口径映射到现有 `ServiceRed` 结构；最大耗时返回空；
      查询结束对齐到最近完整分钟并留一个刷出周期；跨 `shard` 求和
- [x] 路由：首页、服务列表批量、服务 RED 在“聚合可用且窗口起点不早于聚合起点”时读聚合，否则走现有 VictoriaTraces；
      慢请求、Apdex、版本、实例、依赖、告警策略和试算路径不变
- [x] 前端对最大耗时为空的显示为“—”（只改读取与显示，不动布局）
- [x] 测试：数值映射、趋势点数、Top 操作、起点回退、缺数据、聚合库错误降级、租户/服务标签收窄与转义；
      `server/apps/apm/tests` 在 sqlite 下通过；改了前端则 `pnpm lint`、`pnpm type-check`
- [x] 更新 APM 功能清单 capability 中这些页面的数据来源

## Notes

- 健康页可增加聚合库连通性展示，但不得让它影响 VictoriaTraces 相关健康结论。本张未做连通性展示。
- 聚合起点表示 RED 序列开始存在。APM 只探测 `apm_calls_total`，不按 `apm_` 前缀，避免晚到计数把起点提前。RUM 指标名未定，暂时按 `rum_` 前缀探测。已记录起点的产品不再做 35 天探测；全部已记录时不发查询，直接返回 `ok`。

## Completion evidence

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 60 uv run python manage.py makemigrations --check --dry-run`
  结果：`No changes detected`。
- `cd server &&` 同上环境变量 `timeout 900 uv run pytest apps/apm/tests --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
  结果：`11 failed, 849 passed, 2 skipped`。11 项失败都在既有 sqlite 基线内：`test_topology_service.py` 8 项、`test_deployments.py::test_backfill_table_queries_scale_by_batch_not_release_count`、`test_cross_database_guard_migration_service.py::test_existing_apm_outbox_data_survives_portable_unique_upgrade_and_rollback`、`test_owned_alert_lifecycle_migration.py::test_owned_alert_lifecycle_backfill_batches_queries_and_keeps_semantics`。
- 新增 core 测试：`apps/core/tests/test_aggregate_promql_client.py` 13 项、`apps/core/tests/test_aggregate_origin_probe.py` 7 项，与 `apps/apm/tests/test_aggregate_red.py`、`test_dashboard_service.py` 的新增用例一起通过。
- `cd web && pnpm exec eslint` 覆盖本次改动的 `services/[serviceId]/page.tsx`、其测试和 `types.ts`，无告警。全仓 `pnpm lint` 仍有既有错误，不在这些文件。`pnpm type-check` 通过（exit 0；isoflow 构建有既有体积警告）。服务详情页测试 `vitest` 12 项通过，其中最大耗时为空显示“—”。
- 起点探测收紧后：`apps/core/tests/test_aggregate_origin_probe.py` 8 passed。同一环境下 `apps/apm/tests` 仍是 `11 failed, 849 passed, 2 skipped`，失败项与上面的 sqlite 基线相同。
