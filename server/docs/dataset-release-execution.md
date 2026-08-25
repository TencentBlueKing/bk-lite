# MLOps 数据集发布执行租约 Runbook

## 适用范围

本 Runbook 适用于异常检测、分类、日志聚类、时间序列、图片分类和目标检测六类数据集发布任务。任务的调用参数和发布状态保持不变；执行租约只在服务内部生效。

## 配置

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MLOPS_DATASET_RELEASE_EXECUTION_MODE` | `shadow` | `shadow` 保持旧重投与对象命名行为：先通过 Storage 标准名称分配得到实际候选路径，持久化带 grace lease 的补偿意图，再写对象；失败补偿延后到 lease 到期的 sweep，且绝不删除仍被 Release 文件字段引用的对象。`enforce` 启用执行租约、接管和终态 fencing。非法值回退 `shadow`。 |
| `MLOPS_DATASET_RELEASE_LEASE_SECONDS` | `7500` | 租约秒数；代码最小限制为 `7320`，高于图片任务 7260 秒 hard time limit。 |

数据库迁移会创建内部执行归属、对象补偿意图和 sweep cursor 表。三张表不属于业务 API，不应由业务调用方直接写入。

## 上线顺序

1. 先执行数据库迁移，并以默认 `shadow` 部署全部 API 与 MLOps Celery worker。
2. 先用 Django shell 对存量 `processing` 做只读盘点；输出各模型总数、最早更新时间和最多 20 条样本（含对象引用），不修改业务状态：

```python
from django.apps import apps

for model in apps.get_app_config("mlops").get_models():
    if not model.__name__.endswith("DatasetRelease"):
        continue
    processing = model.objects.filter(status="processing").order_by("updated_at", "id")
    print(model._meta.label_lower, processing.count(), list(processing.values("id", "updated_at", "dataset_file")[:20]))
```

3. 确认所有旧版本 worker 已停止接收任务。通过 Celery `inspect active`、`reserved`、`scheduled` 检查六类 `publish_dataset_release_async` 均无旧版本在途任务；有在途任务时等待其终态或按现有安全停机流程 drain，禁止直接切换。将盘点结果与 Celery 状态逐项核对；无法确认归属的 `processing` 记录先保留，首次 enforce 重投会给予一段旧 worker grace lease。
4. 观察一个发布周期：重复领取只应出现 `shadow 命中` 告警，发布参数、文件名和失败状态应与旧版本一致。
5. 仅在步骤 3 的 drain 判据满足后，将所有同队列 worker 的 `MLOPS_DATASET_RELEASE_EXECUTION_MODE` 同步切为 `enforce` 并滚动重启。
6. 验证同一发布只有一个 execution owner；重投命中 active lease 时应 retry，过期后才 takeover。对象补偿意图应在发布成功或清理成功后归零。

可用 Django shell 只读检查待补偿数量：

```python
from apps.mlops.models.dataset_release_execution import DatasetReleaseObjectCleanup

DatasetReleaseObjectCleanup.objects.count()
```

若数量持续增长，先检查 MinIO 可用性和 `清理陈旧数据集发布对象失败` 日志。补偿意图会保留到对象删除成功，不要手工删除数据库记录。

确认 MinIO 恢复后，执行以下 ORM 补偿命令。命令默认每次最多处理 1000 条，并跳过仍由活跃 execution owner 持有的对象；可重复执行直至待补偿数量归零：

```bash
python manage.py cleanup_dataset_release_objects --limit 1000 --dry-run
python manage.py cleanup_dataset_release_objects --limit 1000
```

命令按不可变 intent ID 使用数据库持久 keyset cursor，处理到尾部后回绕，使跳过或删除失败项不会阻塞后续对象、最终仍会再次进入扫描。命令对每条意图输出 `cleaned`、`skipped` 或 `retained`；`--dry-run` 显示当前快照下的候选 intent ID、对象路径和预期动作，不推进 cursor、不领取意图、不连接 MinIO、不删除对象。

## 回滚

1. 将全部同队列 worker 同步切回 `shadow` 并滚动重启。
2. 不回滚迁移、不删除 execution、cleanup intent 或 sweep cursor 表。旧 enforce worker 的 token 仍会被 fencing；新 shadow 终态会撤销残留 owner。
3. 回滚后继续观察 cleanup intent 数量和补偿失败日志。MinIO 暂时不可用不会反向改写已发布或已失败的业务终态。

`shadow` 回滚恢复旧并发语义，因此它是兼容止损手段，不是长期修复状态。故障排除后应重新完成 drain 判据，再切回 `enforce`。
