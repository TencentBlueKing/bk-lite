# UUID 存量清洗完成后停用周期任务

Status: superseded

2026-11-25 同步社区版后，这条「做完再禁用 */5」的实现不再有效。社区版改为维护窗口手工执行 `migrate_cmdb_instance_uuid_runtime`，`batch_init` 只删除历史 Beat 条目 `cmdb_instance_uuid_migration`，不注册、不 `delay`。见 `docs/operations/server-startup-dependencies.md` 与 `docs/operations/cmdb-instance-uuid-cutover.md`。

采集快照查图失败时不落数字图 ID 的决定仍然有效。下面关于周期任务的决定只保留作历史记录。

## Problem Statement

`cmdb_instance_uuid_migration` 在全部阶段完成后仍然每 5 分钟执行 CMDB 与运营分析的 apply 和 verify。每次 `batch_init` 也会再投递一次。已完成阶段的 apply 会直接返回，verify 却把阶段当成未完成再读表。校验发现的脏数据，下一轮 apply 因为 `completed=True` 不会改。周期任务既不再清洗，也修不了新写入。

实例、关联边、配置回调、订阅、变更记录、监控和节点推送已经在写入时要求 UUID。采集结果快照是例外：`normalize_collect_result_payloads` 查图失败时原样落库，数字图 ID 会再次进入 `format_data`、`collect_data` 或 `topology_snapshot`。

## Solution

迁移未完成时保留 `*/5` 和启动时的一次投递，用来把这一次升级洗完。verify 通过后禁用周期任务。之后的启动只确认任务处于禁用，不再投递，也不再调用四条管理命令。

采集快照仍在落库前补 UUID。查图抛错时不保存这份快照，采集任务按原有失败路径重试。图里已经不存在的数字 ID 补不出 UUID，保留原字段并继续落库，避免采集永久失败。

## User Stories

1. As a 运维人员, I want 升级后的 UUID 清洗在做完后不再每 5 分钟扫库, so that 发布和 Beat 不再重复占用图库和 PostgreSQL
2. As a 运维人员, I want 清洗做到一半进程停了还能继续, so that 启动不必同步洗完全库
3. As a 运维人员, I want 以后新增清洗阶段时任务会再打开, so that 新的存量阶段不会被旧的完成标记跳过
4. As a CMDB 管理员, I want 采集快照查图失败时不要写下数字图 ID, so that 不靠周期任务补写

## Implementation Decisions

- stage 是否洗完继续用 `is_uuid_runtime_migration_complete()`。单独的 `uuid_runtime_done` 不能跳过新增 stage。周期任务退出用 `is_uuid_migration_periodic_retired()`：必需 stage 都完成，并且 verify 通过后写下了 `uuid_runtime_done`。apply 会先把 stage 标完成，所以不能只看 stage。发现还有未完成 stage 时先删掉旧的 `uuid_runtime_done`，避免新阶段 apply 成功、verify 失败后被旧标记停用。
- 未完成：`ensure_uuid_migration_periodic_task()` 保证 `cmdb_instance_uuid_migration` 启用且 crontab 为 `*/5`。`batch_init` 投递一次。Broker 失败只告警，不阻断启动。
- 任务在未完成时仍依次 apply、verify 两条命令。apply 失败或 verify 失败不写完成标记，也不禁用周期任务。成功后写完成标记并禁用周期任务。
- 已完成：任务入口直接禁用周期任务并返回 `{"status": "done", "skipped": True}`，不抢锁，不调用管理命令。`ensure` 若发现任务仍启用，把它关掉；没有记录时不新建。`batch_init` 不再 `delay()`。
- 采集快照的 `normalize_collect_result_payloads` 在查图抛错时记一条不含载荷的 WARNING，并抛出 `CollectSnapshotUuidLookupError`。`sync_collect_task` 现有的结果写入失败分支只把执行标成错误，不写入这份 `collect_data` / `format_data`。
- 拓扑快照在 `save_topology_snapshot` 落库前走同一个函数。转换失败沿用原有跳过保存，保留上一份快照。
- 查图成功但个别数字 ID 没有 UUID 时，能补的补上，不能补的保留数字字段。
- 不新增每天凌晨的校验。人工需要重跑时直接执行原来的管理命令。

## Testing Decisions

- 未完成时周期任务保持启用；完成后 `ensure` 把它禁用，并且不新建一条启用任务。
- 完成后的运行期任务不调用 `call_command`，返回 `skipped=True`。
- 未完成时仍执行四次命令；成功后调用禁用。verify 或 apply 失败时不禁用、不写完成标记。
- `batch_init` 在未完成时投递一次且不同步 apply；已完成时不投递。投递失败不抛出。
- 采集快照查图抛错时不返回原载荷，日志不含载荷正文。没有数字图 ID 时不查图。
- 只完成各 stage、尚未写下 `uuid_runtime_done` 时，运行期任务仍执行 verify，通过后才禁用周期任务。

## Evidence

- sqlite：`apps/cmdb/tests/test_uuid_migration_runtime.py`、`apps/cmdb/tests/test_collect_snapshot_uuid.py`，18 passed。`test_network_topology_pipeline.py` 锁定拓扑快照跳过日志的模板、参数、渲染结果和哨兵不落日志，失败时不写库。
- 1 万条 mock，沿用本地 PostgreSQL `bklite_cmdb_perf` 与 Docker FalkorDB `127.0.0.1:6380` 的 `cmdb_perf_uuid_10000`。第一次清洗 15.161 秒，`query_entity` 63 次、`query_edge` 1 次，1 万个实例补上 `inst_uuid`。克隆库里 54 条变更记录的数字 ID 和图内部 ID 撞上，verify 拒绝停用，周期任务保持启用；这次重试 0.105 秒，没有再扫 1 万个实例。把这 54 条暂时移出校验后再跑：停用那次 `graph_instance_scanned=0`，下一轮 0.012 秒返回 `skipped=true`，图查询 0 次，周期任务已禁用。54 条变更记录已还原成空 `inst_uuid`。压测图测完删除。

## Out of Scope

- 不改各 stage 的清洗规则，不删 `collect_result_snapshots` 完成后的水位扫描。该扫描只在迁移任务仍会调用管理命令时发生。
- 不改 CI 上下文重摊。显示字段回填见 `specs/changes/cmdb-display-backfill-once/spec.md`，孤儿临时对象见 `specs/changes/cmdb-beat-display-and-orphan-temp/spec.md`。
- 不删除读取路径对历史数字 ID 的兼容查找。
