# 显示字段回填空闲停用，孤儿临时对象改为每日续扫

Status: implemented

完成证据：sqlite 下 `test_display_field_backfill_runtime.py` 10 项、`test_config_file_content_lifecycle.py` 里孤儿清理、调度和列出失败用例通过。UUID 停用条件未改。

## Problem Statement

显示字段回填完成后，每 5 分钟仍会唤醒 `backfill_cmdb_display_fields`。空闲分支不再扫图，但 `ensure_display_field_backfill_periodic_task()` 只接受启用中的任务，禁用会被下一次执行或 `batch_init` 重新打开。模型新增 `_display` 时又必须能把任务叫醒，不能照抄 CI 上下文的「禁用后永不再开」。

配置文件孤儿临时对象每 15 分钟清理一次，保留期是 24 小时。清理没有游标，每次只看对象列表开头最多 1000 个键、删除 100 个。键的字典序与时间无关，排在前面的未过期对象会挡住后面的孤儿。

## Solution

显示字段回填的停用和重新投递见 `specs/changes/cmdb-display-backfill-once/spec.md`。孤儿临时对象改到每天 03:40，正文补偿仍是每 15 分钟。清理按上次列出的对象键续扫，单次最多删除 1000 个。

## Implementation Decisions

- 历史 `*/5` 回填任务停用，不再创建。空闲入口如果发现它仍启用，也把它关掉，并返回 `{"status": "idle"}`。
- 回填跑完且游标为空时写下 `completed=True`，再禁用这条历史任务。
- 模型新增 `_display` 时清掉完成标记和游标，并投递一次。投递失败只记不含载荷的日志，阶段保持未完成，下次启动再投递。进行中的回填若见到代数变化，放弃旧游标，不沿旧结果续跑。
- 查询失败、软超时、锁冲突保持 `completed=False`，60 秒后自己再投递。图里没有实例时，0 行也是完成，可以停。
- 不把未使用的冷却时间接成 24 小时全量重扫。
- `batch_init` 在回填已空闲时不投递。未完成才 `delay(force=False)`。启动时顺手停用历史周期任务。
- 孤儿临时对象的 crontab 改为 `hour=3, minute=40`。`reconcile_config_file_content_task` 保持 `*/15`，两条任务不合并。
- 用修复状态 `config_file_orphan_temp` 记下上次处理完的对象键。下次从该键之后列出。引用中的键和未满保留期的键不删，但游标越过它们。本页在扫完前用尽 `scan_limit` 或达到删除上限时，留下游标。本页提前结束时把游标清回开头。列出或删除失败只停在该键之前，下次重试这个键。单次删除上限为 1000。

## Testing Decisions

- 显示字段回填的停用、空闲不投递、新字段重新投递，以 `specs/changes/cmdb-display-backfill-once/spec.md` 和 `test_display_field_backfill_runtime.py` 为准。
- 孤儿清理的小时是 3、分钟是 40，正文补偿仍是每 15 分钟。
- 字典序靠后的孤儿能在后续页被删到。删除失败不越过该键。列出失败保持原游标，日志只有错误类型。

## Out of Scope

- 不改 UUID 清洗的停用条件。
- 不把孤儿清理并进正文补偿任务。
