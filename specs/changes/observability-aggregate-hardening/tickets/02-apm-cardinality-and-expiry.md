# 02 — APM 聚合序列按服务设上限并过期

Status: done

Blocked by: 01

**What to build:** 单个服务的 Span 名失控时，聚合进程内存和聚合库活跃序列只按该服务的上限增长；
不活跃的接口在过期后释放名额；容量文档与告警反映真实语义。

- [x] 核对 spanmetrics v0.153 源码：上限的作用范围、序列过期与资源过期字段、资源缓存默认值，在报告里写明结论
- [x] `APM_AGG_CARDINALITY_LIMIT` 默认改为 500，文档写明是“每服务”；开启序列过期，默认 1 小时；显式设置资源缓存上限
- [x] 契约：超过上限的组合并入溢出序列；序列过期后再次出现，`increase()` 结果正确（夹具用短过期时间）
- [x] 容量文档重写：最坏值 = 每服务上限 × 服务资源数 × 每组合序列数，同时给出典型值；删除“全局 9 万组合”
- [x] 告警清单增加“出现溢出序列”（聚合库可查询的条件），说明处理办法（修 Span 命名或调高上限）
- [x] `make -C deploy/apm test validate` 通过；契约结果记录

## Notes

- 溢出序列没有服务名和环境标签，Server 查询不改；不要为此改成按 `job` 查询。
- 过期时长与 Server 的最长查询窗口无关：`increase()` 能处理计数器重置，过期只影响内存和活跃序列数。

## Completion evidence

对照 `github.com/open-telemetry/opentelemetry-collector-contrib/connector/spanmetricsconnector@v0.153.0`：

- `aggregation_cardinality_limit` 按每个 `resourceMetrics` 生效，不是全局。`getOrCreateResourceMetrics` 为每个资源单独 `NewSumMetrics` / `initHistogramMetrics`，并把同一个上限传进去。`IsCardinalityLimitReached` 看的是该 map 的 `len(metrics) >= limit`。调用计数、直方图、事件各自一张 map，所以上限互不影响。`limit <= 0` 表示不限制；工厂默认就是 0。资源键默认是全部资源属性的哈希；本仓库配置了 `resource_metrics_key_attributes` 为 `service.namespace`、`service.name`、`deployment.environment`，因此一个服务资源是这一组。同一服务的多个实例合并，不同环境分开。超出上限的新键并进 `otel.metric.overflow=true`，这条序列本身不占前面的名额（上限 2 时是 2 条正常加 1 条溢出），属性里只有这个标记。
- 按序列过期的字段是 `series_expiration`（`time.Duration`，默认 0 = 永不过期）。刷出时对调用计数、直方图、事件分别 `ExpireSeries`：`now - lastSeen >= duration` 就从那张 map 删掉这一条。`lastSeen` 在这条序列再次被看到时更新。这是按序列，不是按资源。
- 按资源过期的字段是 `metrics_expiration`（同样默认 0）。它看的是整个 `resourceMetrics.lastSeen`，到期删掉这份资源下的全部序列。本次不设置它。
- `resource_metrics_cache_size` 的代码默认值是 `defaultResourceMetricsCacheSize = 1000`（`connector.go`），工厂在未配置时写入这个值。实现是 LRU。超过上限时，最久没见到的服务资源在当次刷出后丢掉，计数器状态随之消失。

取值：`APM_AGG_CARDINALITY_LIMIT` 默认 500，约 166 个入口操作 × 3 种状态，只约束一个服务资源。`APM_AGG_SERIES_EXPIRATION` 默认 `1h`，只为契约能覆盖成 `3s`，没有另做开关。`resource_metrics_cache_size` 写死 1000，与容量文档的最坏值因子相同，不另做变量。镜像仍是 `0.153.0-bklite.3`，这次只改配置。

最坏序列数 = 500 × 1000 × 18 = 9,000,000，35 天约 422 GiB。18 是 1 条 `apm_calls_total` 加直方图 15 个桶、`_count`、`_sum`。典型值是 200 个服务 × 3 个环境 × 50 个入口操作 × 3 种状态 = 600 × 150 × 18 = 1,620,000，约 76 GiB。已去掉“全局 9 万组合”。溢出告警条件是 `count(apm_calls_total{otel_metric_overflow="true"}) > 0`。溢出序列没有服务名和环境，Server 查询未改。

- `make -C deploy/apm test validate`：退出码 0。三个 Go 包 cached ok。镜像构建缓存命中，digest 仍是 `sha256:6f247abb765d`。`aggregate.yaml` 带着 `series_expiration` 和 `resource_metrics_cache_size: 1000` 校验通过。
- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb uv run pytest -q apps/apm/tests/test_data_plane_config.py --no-cov -o addopts= -p no:cacheprovider`：13 passed in 0.08s。
- `make -C deploy/apm contract`（同上 Django 变量，因为数据面用例自己会 `django.setup()`）：6 passed, 4 warnings in 273.95s。包含原有聚合用例、VictoriaTraces 故障不重复计数，以及 `APM_AGG_SERIES_EXPIRATION=3s` 时 3 条 Span 过期后再来 1 条：即时值回到 1，`increase()` 为 4。契约 project 已清理。没有改 `deploy/apm/.env`，也没有操作 Compose project `bk-lite-apm`。

