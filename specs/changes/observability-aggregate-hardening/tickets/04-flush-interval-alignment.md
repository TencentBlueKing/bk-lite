# 04 — Server 刷出间隔与采集端同源

Status: done

Blocked by: 01, 02

**What to build:** 运维修改 `APM_AGG_FLUSH_INTERVAL` 或 `RUM_AGG_BATCH_TIMEOUT` 时，在 Server 设置同名变量即可让查询结束时间对齐，
不用改代码。

- [x] `server/apps/apm/adapters/aggregate_red.py` 与 `server/apps/rum/services/aggregate_reads.py` 的刷出间隔改为读取同名环境变量，
  默认 60s / 10s；支持采集端使用的时长写法（如 `60s`、`1m`），非法值按默认值并记一条 WARN（不含变量以外的内容）
- [x] 解析放在一个两边都能引用的位置，例如 `apps/core/aggregate_promql.py`，不新增配置抽象
- [x] 单测：默认值、自定义值、非法值；保持现有查询结果契约
- [x] 文档：上线说明的 Server 段与变量表、`aggregate-metrics-store.md` 写明两边必须一致
- [x] sqlite 跑 `apps/apm/tests`、`apps/rum/tests`、`apps/core/tests`，对照 master 基线不新增失败

## Notes

- 日志遵守 `specs/capabilities/backend-engineering.md` §8；修改日志需要回归测试锁定模板与参数。

## Completion evidence

解析在 `apps/core/aggregate_promql.py` 的 `flush_interval_seconds`，`apm_flush_seconds` / `rum_flush_seconds` 分别读 `APM_AGG_FLUSH_INTERVAL`（默认 60）和 `RUM_AGG_BATCH_TIMEOUT`（默认 10）。没有新的配置类。日志是 `from apps.core.logger import logger`（`logging.getLogger("app")`），`logger.py` 里没有 `core_logger`。

时长写法对齐 Go `time.ParseDuration`：`ns`、`us` / `µs` / `μs`、`ms`、`s`、`m`、`h`，以及组合如 `1m30s`、`1h2m3s`。先匹配更长的单位，避免 `ms` 被看成 `m`。纯数字、正负号、`1d`、科学计数法拒绝。对齐只用整秒：先按微秒四舍五入，再向上取整，保证对齐留出的时间不短于采集端刷出间隔；`0s` 视为非法。`1500ms` 得到 2 秒、`500ms` 得到 1 秒，不告警（复核时由向下取整改为向上取整）。未设置或空白用默认值，不告警，也不进缓存。

缓存是模块级字典，键是 `(变量名, 原始字符串)`，用 `threading.Lock` 保护。非法或非正值缓存成默认秒数，所以同一个非法值只在第一次打 WARN。不同原始字符串各自独立。查询时才读环境变量，测试可以在导入之后改值。

WARN 模板是 `event=aggregate_flush_interval_invalid name=%s default_seconds=%s`，参数只有变量名和采用的默认秒数。不写原始值：原始值可能是误贴的口令或地址，§8 要求这类内容直接省略。这是可恢复的配置回落，没有 traceback，也没有 `failed_stage` / `error_type`。

APM 的 `align_query_end` 和趋势步长改读 `apm_flush_seconds()`。RUM 三处 `align_query_end` 改读 `rum_flush_seconds()`。`align_query_end` 的计算没改：先收到 `min(ended, now)`，落到整分，再减去刷出秒数。未设置时 APM 仍把 `2026-11-10 00:16:30` 对齐到 `00:15:00`，RUM 仍对齐到 `00:15:50`。

单测 `apps/core/tests/test_aggregate_flush_interval.py`：未设置时 60 / 10 且无 WARN；APM `30s` 对齐到 `00:15:30`，RUM `1m` 对齐到 `00:15:00`，APM 适配器的 `align_query_end` 跟着变；`1m30s` 为 90 秒、`1h2m3s` 为 3723 秒、`1500ms` 为 2 秒、`500ms` 为 1 秒。非法值用哨兵 `redis://:super-secret-password@10.9.8.7:6379/0` 加换行和 `token=secret`：两次读取都是 60，只一条 WARNING，`record.msg` 与 `args` 是模板和 `("APM_AGG_FLUSH_INTERVAL", 60)`，`getMessage()` 与 `Formatter` 输出都是 `event=aggregate_flush_interval_invalid name=APM_AGG_FLUSH_INTERVAL default_seconds=60`，`exc_info` 为空，哨兵、口令、地址、`token=secret`、`redis://` 和换行都不在消息、格式化结果和参数里。RUM `test_catalog_end_follows_the_gateway_batch_timeout` 在 `1m` 时目录查询时间戳为 `00:15:00`。

文档写明改这两个值必须同时改采集端和 Server：`docs/operations/apm-rum-query-performance-rollout.md` 的采集端变量表和 Server 5.1、`docs/operations/aggregate-metrics-store.md`、`deploy/apm/README.md`、`deploy/rum/OPS-DEPLOY.md`，以及 `deploy/apm/.env.example`、`deploy/rum/.env.example`、`deploy/rum/collector/env/rum.gateway.dev.env.example`。Server 没有列出 `AGG_VICTORIAMETRICS_QUERY_URL` 的环境变量模板，没有改 `server/.env`。

验证命令（`.env` 的 `INSTALL_APPS` 不含 `cmdb`，monitor 导入会在 Django 启动时失败，所以补了 `cmdb`）：

`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb uv run pytest apps/apm/tests apps/rum/tests apps/core/tests --no-cov -q --tb=no`

结果：7 failed，1646 passed，9 skipped，906 errors，65.82s。上面的新单测都在 passed 里。

906 个 error 都是同一条既有迁移错误：sqlite 应用 `apm/migrations/0006_application_integration.py` 的 `RemoveField(apmingestsourceorganization, ingest_source)` 时，唯一约束 `apm_ingest_source_org_unique` 仍引用该字段，`FieldDoesNotExist: NewApmIngestSourceOrganization has no field named 'ingest_source'`。该迁移相对 master 无差异。Django 的 sqlite 测试库是内存库，`--reuse-db` 挡不住这次迁移。master 点名的 11 项因此没有跑到断言，全部落在这 906 个 setup error 里：`test_topology_service.py` 的 8 个 `test_topology_api_*`，`test_deployments.py` 里的 backfill，`test_cross_database_guard_migration_service.py`，以及 `test_owned_alert_lifecycle_migration.py`。这几个文件里的 django_db 测试都在迁移阶段报错，看不到原来的断言失败。

另外 7 个断言失败不在本次改动的文件里，单独重跑仍然失败：

- `apps/core/tests/test_api_token_permission.py::TestCollectAncestorGroupIds` 的 4 项：`apps.core.backends` 没有 `Group`
- `apps/core/tests/test_celery_routing_service.py::test_static_manifest_covers_local_decorated_tasks_without_importing_them`：`apps/job_mgmt/tasks.py:42` 的 `queue` 需要人工解析
- `apps/core/tests/test_logger_source_contract_pure.py::test_server_apps_production_uses_central_logger_sources`：`license_mgmt` 等处直接 `getLogger`
- `apps/core/tests/test_logger_source_contract_pure.py::test_central_logger_aliases_match_the_owning_app`：`rpc/job_mgmt.py` 把 `job_logger` 用作 `logger`

本次没有新增断言失败。当前进程没有设置这两个刷出间隔变量。

