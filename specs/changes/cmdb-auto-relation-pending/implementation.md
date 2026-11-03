# 自动关联周期重算

Status: 已实现。

自动关联在实例写入后异步收敛，不要求跟采集同一拍生效。采集和页面写入只把待重算对象记入数据库，每 5 分钟由一条单例任务排空。

## 表

新表 `cmdb_auto_relation_pending`，不在图实例上加字段。迁移 `0063_auto_relation_pending`。

| 列 | 约束 |
|---|---|
| `instance_id` | 可空，唯一。实例变更使用 |
| `model_asst_id` | 可空，唯一。规则变更或删除后的入向收敛使用 |
| `created_at` | 写入时间 |

一行只填其中一列。重复写入同一实例或同一规则保持原行，不新增。

## 行为

- `schedule_instance_auto_relation_reconcile` 只插入实例行，不 `send_task`。
- `schedule_rule_auto_relation_full_sync` 只插入规则行，不 `send_task`。
- Beat `reconcile_auto_relation_pending_task` 每 5 分钟一次，`celery_singleton` 单例，锁 30 分钟过期。
- 任务先按 500 个一批重算实例行。成功的删除，失败的留到下一轮。整批抛错时把本轮已认领的实例行放回去。然后在同一条任务里对入向规则和待处理规则行做全量同步，不再另开 Celery 任务。
- 队列里已有的单实例、批量、规则全量和入向任务只把参数记入这张表。

写入点保持原调用：采集新增/更新、采集删除、实例创建/修改/批量/导入、实例删除、节点同步、规则保存/修改/删除/替换/导入、操作 outbox 的 `auto_relation`。outbox 改为直接登记实例行。

## 测试接缝

1. 写入后查询名单：重复实例只有一行，空名单不写，规则名会去掉空白。
2. 周期任务：写入两条源实例后执行任务，图上出现对应关联，名单被清空；失败的实例行还在。
3. 调度契约：Beat 为 `*/5`，任务带单例锁和 30 分钟过期。
4. 旧任务名只登记，不直接重算。

## 验证

2026-10-28，迁移完成后用现有测试库重跑（走迁移，不用 `--nomigrations`）：

```bash
cd server && uv run pytest apps/cmdb/tests/test_auto_relation_pending.py \
  apps/cmdb/tests/test_auto_relation_reconcile_svc.py \
  apps/cmdb/tests/test_auto_relation_reconcile_regression_service.py \
  apps/cmdb/tests/test_collect_celery_tasks_svc.py::test_reconcile_instance_task_records_pending_row \
  apps/cmdb/tests/test_collect_celery_tasks_svc.py::test_full_sync_rule_task_records_pending_row \
  --no-cov -q
```

结果：71 passed，17.02s。

`manage.py makemigrations cmdb --check --dry-run`：No changes detected。

写入后查询：登记实例 1、2 后表中有 2 行；排空后图上 2 条关联，表被清空，入向规则 `incoming` 在同一轮全量同步。重复登记同一实例不会增加行。10001 个实例只产生 10001 行。
