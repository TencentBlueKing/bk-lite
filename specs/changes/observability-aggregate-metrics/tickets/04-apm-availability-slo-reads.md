# 04 — APM 可用性 SLO 改读

Status: done

Blocked by: 03 — Server 聚合查询客户端与 APM 首页、服务列表、服务 RED 改读

**What to build:** 可用性类 SLO（7 天、30 天、自然月）在聚合起点覆盖整个窗口后读聚合库，秒级返回；覆盖前继续走现有
VictoriaTraces 按天切片的查询；延迟类 SLO 不变。

- [x] 可用性 SLI 的总数/坏数由聚合库 `increase()` 计算，按服务（及 SLO 已有的入口操作 / 环境范围）收窄、跨 `shard` 求和
- [x] 窗口起点早于聚合起点 → VictoriaTraces；聚合库错误 → 该 SLO 降级，不显示为 0
- [x] 首页 SLO 卡片与 SLO 列表/详情一致
- [x] 测试：7d / 30d / 自然月、起点未覆盖时回退、延迟 SLO 仍走 VictoriaTraces、降级；sqlite 下 `server/apps/apm/tests` 通过
- [x] 更新 APM 功能清单 capability；本目录 spec 中 APM 部分的完成证据

## Completion evidence

- 读取入口是 `ApmAvailabilitySloStore.slo_measurement`。首页 `ApmDashboardViewSet` 与 SLO 列表/详情 `ApmSloViewSet` 都经 `apm_availability_slo_store` 进入同一条路径。
- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 900 uv run pytest apps/apm/tests --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
  结果：`11 failed, 866 passed, 2 skipped`。相对 03 的 `849 passed` 新增 17 项通过。11 项失败都在既有 sqlite 基线内：`test_topology_service.py` 8 项、`test_deployments.py::test_backfill_table_queries_scale_by_batch_not_release_count`、`test_cross_database_guard_migration_service.py::test_existing_apm_outbox_data_survives_portable_unique_upgrade_and_rollback`、`test_owned_alert_lifecycle_migration.py::test_owned_alert_lifecycle_backfill_batches_queries_and_keeps_semantics`。
- 未改前端。延迟 SLO、告警燃烧率仍读 VictoriaTraces。
