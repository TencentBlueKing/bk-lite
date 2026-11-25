# 显示字段回填只做一次

Status: implemented

## Problem Statement

`_display` 是 organization、user、enum、tag、table 的派生文本。新建和修改已经在保存时写入。存量回填做完之后，每 5 分钟的周期任务仍会叫醒 Worker。按模型各查一次时，空模型也会扫整张实例标签。

## Solution

`migrate` 和 `batch_init` 不扫实例。`batch_init` 只补模型定义，停用历史周期任务，并在阶段未完成时投递一次。Celery Worker 起来后按实例 id 一条流清洗。洗完不再投递、不再扫描。

## Implementation Decisions

- 阶段仍是 `CmdbRepairState.display_backfill`。完成且游标为空才算洗完。
- 没有阶段记录、未完成、或游标还在：启动 `delay(force=False)`。已完成且游标为空：不投递。
- 启动停用已有的 `cmdb_display_field_backfill`。没有这条记录时不创建。任务入口发现已完成且游标为空时，再停一次仍启用的历史任务。
- Broker 不可达只告警。下次启动看到未完成再投递。
- 新开的回填使用 `model_id IN` 加 `id > 游标`，每页 500，一轮最多 2000 条。游标是 `{last_id}`。
- 已有游标 `{model_id, last_id}` 按模型走完。
- 相同的 `_display` 不写。
- 没扫完 1 秒后续跑。查询失败、软超时、锁冲突 60 秒后续跑，不标完成。
- 进程死在记下一次游标之前，下次启动从库里的游标继续。
- 新写下 `_display` 定义，或界面新增 organization、user、enum、tag、table 字段时，清掉完成标记和游标，代数加一，并投递一次。进行中的回填见到代数变化后不写回旧游标。
- 采集新建、更新、心跳，以及 PC 发现新建 PC 和软件时，同一次写入带上 `organization_display`。
- 人工重做：清掉完成标记，或 `force=True`，或不带 `--models-only` 的 `init_display_fields`。

## Testing Decisions

- 已完成时启动不投递，并停用周期任务。未完成时投递 `force=False`。Broker 失败不让启动失败。
- 查询失败、锁冲突、软超时以 60 秒再投递，游标保持未完成。正常翻页仍是 1 秒。
- 新回填一次查询带上全部展示模型，空模型不在列表里。旧的模型游标仍按模型查询。
- 代数变化时不把本轮标成完成。
- 采集心跳和 PC 新建写入 `organization_display`。

## Verification

2026-11-24，本机 Docker FalkorDB `127.0.0.1:6380` 和 PostgreSQL 克隆库 `bklite_cmdb_perf`。四档都是带展示字段的实例，第一次回填写入 `organization_display`，扫完后再调用任务得到 `idle`。`cmdb_graph`、`cmdb_uuid_fresh_startup_test`、`cmdb_uuid_migration_test` 的节点数没有变化。

| 实例 | 轮次 | 写入 | 回填耗时 |
|---|---|---|---|
| 1 万 | 6 | 1 万 | 73.9 秒 |
| 3 万 | 16 | 3 万 | 591.4 秒 |
| 5 万 | 26 | 5 万 | 1460.1 秒 |
| 10 万 | 51 | 10 万 | 5794.8 秒 |

耗时是直接调用锁内回填，不含页与页之间的 1 秒间隔。生产环境再加页数减一的 1 秒。最后一页确认扫完约 0.1 秒。

## Out of Scope

- 不把扫描放回 `batch_init` 或 `migrate`。
- 不做每天全量重扫。
- 不给 `model_id` 建索引，查询仍返回整节点。
- 不改变组织改名同步和枚举选项保存时的实例刷新。
