# Historical Superpowers change: 2026-07-13-cmdb-phase2-async-state-delivery-idempotency

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-13-cmdb-phase2-async-state-delivery-idempotency.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current worktree. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让订阅通知、采集执行和配置文件回调具备持久化、执行代次、终态单向与数据库约束兜底的生产级语义。

**Architecture:** 订阅事件先写关系库 delivery，再由 Celery 按行条件抢占和重试；采集任务继续复用 `CollectModels.task_id` 作为 execution ID，所有 Worker、超时巡检和配置回调只允许更新当前 `RUNNING` 代次；配置版本用数据库唯一约束裁决并发，并拒绝同业务键不同正文的协议冲突。全部数据库访问使用 Django ORM，不引入原生 SQL。

**Tech Stack:** Python 3.12、Django 4.2、Celery、pytest-django、Django ORM、Stargazer Sanic/ARQ。

## Global Constraints

- 每个 Task 严格执行 RED→GREEN→REFACTOR；生产代码之前必须观察目标测试因当前缺陷失败。
- 状态更新必须包含稳定业务键和旧状态条件，禁止无条件 `save()` 覆盖并发新状态。
- 订阅通知不追求外部渠道“绝对 exactly-once”；保证数据库 delivery 至少一次处理、同一进程重投不重复发送，并完整保留失败诊断。
- `SENT/FAILED` 与采集 `SUCCESS/ERROR/TIME_OUT/FORCE_STOP` 为终态；迟到结果只记录日志，不回退状态。
- MinIO 正文生命周期的补偿与临时对象治理属于阶段三；阶段二只保证同业务键不会覆盖已存在正文或制造第二条 DB 版本。
- 新迁移必须支持仓库声明的多数据库方言，禁止 raw SQL、`.raw()`、`RawSQL`、`cursor.execute`。
- SQLite 文件测试库使用 `/private/tmp/bk_lite_cmdb_phase2.sqlite3` 一类显式路径，不使用 `DB_NAME=:memory:`。

---

## File Structure

- Create: `server/apps/cmdb/models/subscription_delivery.py` — 持久化通知 delivery、状态、重试和诊断。
- Modify: `server/apps/cmdb/models/__init__.py` — 导出 delivery 模型。
- Create: `server/apps/cmdb/migrations/0031_subscriptiondelivery.py` — 创建投递表、唯一键和扫描索引。
- Modify: `server/apps/cmdb/services/subscription_task.py` — 事务内持久化事件、条件抢占、发送与退避。
- Modify: `server/apps/cmdb/tasks/celery_tasks.py` — delivery ID 任务契约；采集 execution ID 条件写回与动态 deadline。
- Modify: `server/apps/cmdb/tests/test_subscription_task_service.py` — 投递、重投、失败终态与无丢失测试。
- Modify: `server/apps/cmdb/tests/test_collect_celery_tasks_svc.py` — 迟到 Worker、超时终态和 deadline 测试。
- Modify: `server/apps/cmdb/node_configs/ssh/config_file.py` — 将当前 execution ID 下发给 Stargazer。
- Modify: `agents/stargazer/plugins/inputs/config_file/config_file_info.py` — 成功回调携带 execution ID。
- Modify: `agents/stargazer/service/collection_service.py` — 错误回调携带 execution ID。
- Modify: `agents/stargazer/tasks/handlers/plugin_handler.py` — handler 生成的配置回调携带 execution ID。
- Modify: `server/apps/cmdb/services/config_file_service.py` — 校验 execution ID、条件闭环、并发幂等与冲突保护。
- Modify: `server/apps/cmdb/models/config_file_version.py` — 声明业务唯一约束。
- Create: `server/apps/cmdb/migrations/0032_dedupe_config_file_versions.py` — ORM 数据去重后增加唯一约束。
- Modify: `server/apps/cmdb/tests/test_config_file_process_collect_db.py` — stale execution、唯一约束、幂等与协议冲突。
- Modify: `agents/stargazer/tests/test_host_collector.py` — 回调 execution ID 契约。
- Modify: `agents/stargazer/tests/test_api_http_layer.py` — HTTP 拆分后 execution ID 保留契约。

### Task 1: 建立订阅通知持久化 Delivery

**Files:**
- Create: `server/apps/cmdb/models/subscription_delivery.py`
- Modify: `server/apps/cmdb/models/__init__.py`
- Create: `server/apps/cmdb/migrations/0031_subscriptiondelivery.py`
- Modify: `server/apps/cmdb/tests/test_subscription_task_service.py`

**Data model:**

```python
class SubscriptionDeliveryStatus(models.TextChoices):
    PENDING = "pending", "待发送"
    SENDING = "sending", "发送中"
    RETRY = "retry", "待重试"
    SENT = "sent", "已发送"
    FAILED = "failed", "发送失败"


class SubscriptionDelivery(models.Model):
    dedupe_key = models.CharField(max_length=64, unique=True)
    rule = models.ForeignKey(
        SubscriptionRule,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deliveries",
    )
    rule_id_snapshot = models.BigIntegerField()
    trigger_type = models.CharField(max_length=32)
    events = models.JSONField(default=list)
    recipients = models.JSONField(default=dict)
    channel_id = models.BigIntegerField()
    status = models.CharField(
        max_length=16,
        choices=SubscriptionDeliveryStatus.choices,
        default=SubscriptionDeliveryStatus.PENDING,
    )
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

Indexes:

- `(status, next_retry_at)` 用于扫描待处理/待重试记录。
- `(rule_id_snapshot, created_at)` 用于规则维度诊断。

- [ ] **Step 1: 写模型 RED 测试**

在 `test_subscription_task_service.py` 增加真实 ORM 测试：

- 同一个 `dedupe_key` 第二次创建抛 `IntegrityError`。
- 删除 `SubscriptionRule` 后 delivery 仍存在，`rule` 变为 `None`，`rule_id_snapshot` 保留。
- 默认状态为 `PENDING`，尝试次数为 0。

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_subscription_task_service.py -k 'delivery_model'
```

Expected: collection/import FAIL，因为模型尚不存在。

- [ ] **Step 2: 实现模型与迁移**

创建模型，加入 `apps/cmdb/models/__init__.py` 导出，并运行：

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run python manage.py makemigrations cmdb --name subscriptiondelivery
```

检查生成迁移只创建预期表、唯一约束和索引，不包含无关模型变更。

- [ ] **Step 3: 确认 GREEN 并提交**

Run Step 1；Expected: 全部 PASS。

```bash
git add server/apps/cmdb/models/subscription_delivery.py server/apps/cmdb/models/__init__.py server/apps/cmdb/migrations/0031_subscriptiondelivery.py server/apps/cmdb/tests/test_subscription_task_service.py
git commit -m "feat(cmdb): 新增订阅通知投递记录"
```

### Task 2: 切换订阅检查和发送到持久化消费

**Files:**
- Modify: `server/apps/cmdb/services/subscription_task.py`
- Modify: `server/apps/cmdb/tasks/celery_tasks.py`
- Modify: `server/apps/cmdb/tests/test_subscription_task_service.py`

**Interfaces:**

- `check_rules()`：对每条规则在 `transaction.atomic()` 内 `select_for_update()`，执行触发检测并写 delivery；快照更新与 delivery 写入同事务。
- `_persist_event_groups(rule, groups) -> list[int]`：按渠道拆行，使用稳定 SHA-256 dedupe key；逐条通过 `get_or_create` 写入，由数据库唯一约束兜底，并在并发 `IntegrityError` 后于独立保存点外读取胜出记录。全程使用 Django ORM，避免依赖 `ignore_conflicts` 的数据库方言差异。
- `send_subscription_notifications(delivery_ids: list[int] | None)`：Celery 参数只传 ID，不再传事件正文。
- `send_notifications(delivery_ids=None)`：扫描/处理指定 delivery；每行条件抢占后发送。

**Dedupe payload:**

```python
{
    "rule_id": rule.id,
    "trigger_type": group["trigger_type"],
    "channel_id": channel_id,
    "events": sorted(group["events"], key=lambda item: canonical_json(item)),
}
```

使用 `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)` 后 SHA-256。禁止使用 Python `hash()`。

- [ ] **Step 1: 写持久化和快照原子性 RED 测试**

新增行为测试：

1. `check_rules` 检测一个事件、两个渠道后创建两条 `PENDING` delivery，并且 Celery kwargs 只包含 `delivery_ids`。
2. 同一事件重跑不会新增 delivery。
3. mock delivery 写入抛异常时，`SubscriptionTriggerService.process()` 对规则快照/`last_check_time` 的修改回滚。
4. broker `send_task` 抛异常时 delivery 仍为 `PENDING`；下一次 `check_rules` 会再次派发已有可处理 ID。

Expected RED: 当前只把事件放在 Celery 参数里，没有 delivery，broker 失败后无可恢复记录。

- [ ] **Step 2: 实现事务内持久化与恢复派发**

- 去掉 `SEND_LOCK_KEY` 作为正确性机制。
- 每次 `check_rules` 开始或结束扫描：

```python
Q(status=PENDING) | Q(status=RETRY, next_retry_at__lte=now())
```

- 事务提交后再 `app.send_task`；派发失败只记录日志，不改变 delivery。
- Celery task 签名改为 `delivery_ids`，旧 `event_groups` 参数直接删除，不保留影子兼容入口。

- [ ] **Step 3: 写抢占、重投和失败状态 RED 测试**

真实 ORM 测试覆盖：

- 两条不同 delivery 由两个 Worker 调用后均为 `SENT`，不会因全局锁丢失其中一条。
- 同一 delivery ID 重投两次，RPC 只调用一次；第二次条件抢占返回 0。
- RPC 失败后：`attempt_count < MAX_ATTEMPTS` 进入 `RETRY`，记录 `last_error/next_retry_at`。
- 达到上限进入 `FAILED`，后续重投不再调用 RPC。
- 规则删除/停用或事件解码失败进入 `FAILED`，保留诊断，不静默 return。

`MAX_ATTEMPTS = 3`；退避使用常量序列 `(60, 300, 900)` 秒，测试 patch `now()` 验证时间，不真实等待。

- [ ] **Step 4: 实现条件抢占和终态更新**

抢占必须使用单条条件更新：

```python
updated = SubscriptionDelivery.objects.filter(
    id=delivery_id,
    status__in=[PENDING, RETRY],
).filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now())).update(
    status=SENDING,
    attempt_count=F("attempt_count") + 1,
    last_error="",
)
```

发送成功条件更新 `SENDING -> SENT`；异常按刷新后的 `attempt_count` 写 `RETRY/FAILED`。`_process_single_event_group` 改为返回成功或抛出明确异常，禁止内部吞错后让 delivery 假成功。

- [ ] **Step 5: 运行回归并提交**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_subscription_task_service.py apps/cmdb/tests/test_subscription_trigger_service.py
```

Expected: 全部 PASS。

```bash
git add server/apps/cmdb/services/subscription_task.py server/apps/cmdb/tasks/celery_tasks.py server/apps/cmdb/tests/test_subscription_task_service.py
git commit -m "fix(cmdb): 持久化并可靠消费订阅通知"
```

### Task 3: 采集 Worker execution ID 条件写回与超时状态机

**Files:**
- Modify: `server/apps/cmdb/tasks/celery_tasks.py`
- Modify: `server/apps/cmdb/tests/test_collect_celery_tasks_svc.py`

**Interfaces:**

- `_save_collect_result_if_current(instance_id, execution_id, values) -> bool`
- `_resolve_execution_timeout_seconds(task) -> int`
- `_timeout_collect_task_if_current(task, checked_at) -> bool`

Timeout resolution:

1. `task.params["task_job_timeout"]` 的正整数秒值；
2. 服务端环境变量 `TASK_JOB_TIMEOUT`；
3. 默认 600 秒，与 Stargazer `WorkerSettings.job_timeout` 一致。

现有 `CollectModels.timeout` 明确表示单 IP 超时，不得误用为整次 execution deadline。

- [ ] **Step 1: 写迟到 Worker RED 测试**

在 `test_collect_celery_tasks_svc.py` 增加：

- Worker A 以 `execution_id=A` 开始；测试 double 在采集过程中把 DB 行切换为 `task_id=B, exec_status=RUNNING`；A 返回成功时不得覆盖 B 的 `exec_status/collect_data/format_data/collect_digest`。
- Worker A 抛异常时同样不得把 B 写为 `ERROR`。
- 配置文件 pending 写回必须包含 `id + task_id=A + RUNNING` 条件。

Expected RED: 当前非 pending 路径调用 `instance.save()`，异常保存路径只按 `id` 更新，会覆盖 B。

- [ ] **Step 2: 实现所有 Worker 条件写回**

- 非 pending 成功/失败统一构造 update dict，通过 `id + task_id + RUNNING` 条件更新。
- 保存异常的兜底更新也必须带相同条件。
- 条件更新返回 0 时记录 `stale_execution_result` 日志并正常结束，不重试图写或状态写。
- execution ID 为空的历史定时入口在 `_claim_collect_task_execution` 成功后生成 UUID 并立即写入 `task_id`，保证所有新执行都有代次；不保留无 token 写回分支。

- [ ] **Step 3: 写动态 deadline 和 TIME_OUT RED 测试**

覆盖：

- `params.task_job_timeout=30` 的 RUNNING 任务在 31 秒后置 `TIME_OUT`。
- 无专属配置使用 `TASK_JOB_TIMEOUT=600`，5 分钟时不超时，601 秒时超时。
- 超时巡检读取行后，任务已切换到新 `task_id` 时条件更新失败，新执行保持 RUNNING。
- 已是 `SUCCESS/ERROR/FORCE_STOP/TIME_OUT` 的终态不改变。
- 超时摘要包含 execution ID、deadline 秒数和开始时间。

Expected RED: 当前固定 5 分钟并写 `ERROR`，且不带 task ID 条件。

- [ ] **Step 4: 实现动态巡检并回归**

使用 `.only("id", "task_id", "exec_status", "exec_time", "params").iterator(chunk_size=200)` 有界扫描 RUNNING 行；每行计算 deadline 后，以 `id + task_id + RUNNING` 条件更新为 `TIME_OUT`。

Run:

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_collect_celery_tasks_svc.py apps/cmdb/tests/test_collect_service_methods.py
```

Expected: 全部 PASS。

```bash
git add server/apps/cmdb/tasks/celery_tasks.py server/apps/cmdb/tests/test_collect_celery_tasks_svc.py
git commit -m "fix(cmdb): 按执行代次收敛采集状态"
```

### Task 4: execution ID 贯穿配置文件回调

**Files:**
- Modify: `server/apps/cmdb/node_configs/ssh/config_file.py`
- Modify: `agents/stargazer/plugins/inputs/config_file/config_file_info.py`
- Modify: `agents/stargazer/service/collection_service.py`
- Modify: `agents/stargazer/tasks/handlers/plugin_handler.py`
- Modify: `server/apps/cmdb/services/config_file_service.py`
- Modify: `server/apps/cmdb/tests/test_config_file_process_collect_db.py`
- Modify: `agents/stargazer/tests/test_host_collector.py`
- Modify: `agents/stargazer/tests/test_api_http_layer.py`

- [ ] **Step 1: 写链路 RED 测试**

Server 测试：

- `ConfigFileNodeParams.set_credential()` 输出当前 `task.task_id` 到 `execution_id`。
- `process_collect_result` 缺 execution ID 返回业务错误且不改任务状态。
- payload execution ID 与当前 `task.task_id` 不同：返回 `stale=True/task_updated=False`，不创建版本、不改终态。
- execution ID 相同但任务已 `TIME_OUT/SUCCESS/ERROR/FORCE_STOP`：记录 stale，不创建版本、不回退终态。

Stargazer 测试：

- 成功 plugin 结果包含原始 `execution_id`。
- CollectionService 和 plugin handler 构造的失败回调也包含原始 `execution_id`。
- HTTP host 拆分、credential 重试和 NATS publish 不删除/改写 execution ID。

Expected RED: 当前回调只有 `collect_task_id`，Server 只能用版本时间猜测 stale。

- [ ] **Step 2: 实现透传与 fail-closed 校验**

- Server 触发参数新增 `execution_id=self.instance.task_id`。
- Stargazer 所有配置文件成功/失败结果从 params 原样复制 `execution_id`。
- Server 在解码正文或写 MinIO 前校验：

```python
payload_execution_id == task.task_id
and task.exec_status == CollectRunStatusType.RUNNING
```

- 不匹配统一返回 `{"stale": True, "task_updated": False, ...}`；保留 `_is_stale_callback` 时间判断作为同 execution 内的补充保护，不再作为主要代次判断。
- `_update_task_lifecycle` 最终保存改为 `id + task_id + RUNNING` 条件更新，禁止 `task.save()` 无条件回退终态。

- [ ] **Step 3: 分模块回归并提交**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_config_file_process_collect_db.py apps/cmdb/tests/e2e/test_config_file_pipeline.py
```

```bash
cd agents/stargazer && uv run pytest -q tests/test_host_collector.py tests/test_api_http_layer.py
```

Expected: 两组全部 PASS。

```bash
git add server/apps/cmdb/node_configs/ssh/config_file.py agents/stargazer/plugins/inputs/config_file/config_file_info.py agents/stargazer/service/collection_service.py agents/stargazer/tasks/handlers/plugin_handler.py server/apps/cmdb/services/config_file_service.py server/apps/cmdb/tests/test_config_file_process_collect_db.py agents/stargazer/tests/test_host_collector.py agents/stargazer/tests/test_api_http_layer.py
git commit -m "fix(cmdb): 为配置回调绑定执行代次"
```

### Task 5: 配置版本数据库幂等与协议冲突

**Files:**
- Modify: `server/apps/cmdb/models/config_file_version.py`
- Create: `server/apps/cmdb/migrations/0032_dedupe_config_file_versions.py`
- Modify: `server/apps/cmdb/services/config_file_service.py`
- Modify: `server/apps/cmdb/tests/test_config_file_process_collect_db.py`

**Business key:** `(collect_task, instance_id, version)`。

**Duplicate migration rule:** 按 `(created_at, id)` 升序保留最早一条；删除其余 DB 行。迁移只使用 `RunPython` + historical model ORM。重复对象的 MinIO 清理属于阶段三，不在迁移中调用存储后端。

- [ ] **Step 1: 写数据库约束 RED 测试**

- 直接创建两个相同业务键的 `ConfigFileVersion`，第二次必须抛 `IntegrityError`。
- 手动版本 `collect_task=None` 不受该约束互相冲突。
- 迁移函数输入重复数据后只保留 `(created_at, id)` 最早记录。

Expected RED: 当前 Meta 无唯一约束。

- [ ] **Step 2: 声明约束和数据迁移**

模型 Meta 增加：

```python
models.UniqueConstraint(
    fields=["collect_task", "instance_id", "version"],
    name="uniq_cfg_ver_task_inst_version",
)
```

创建 `0032_dedupe_config_file_versions.py`，先 `RunPython(dedupe, noop)`，再 `AddConstraint`。

- [ ] **Step 3: 写服务幂等和冲突 RED 测试**

- 同 execution、同业务键、相同正文重投：返回原行、`changed=False`，不再次调用 `save_content`。
- 同 execution、同业务键、不同正文：返回明确 `error`/协议冲突，原行 `content_hash/content_key/file_size/status` 完全不变，任务闭环为 `ERROR`。
- patch 首次 `create` 抛 `IntegrityError` 模拟并发胜者：服务在新事务读取已存在行；相同 hash 幂等成功，不同 hash 冲突。
- 使用 `TransactionTestCase` 或 `pytest.mark.django_db(transaction=True)` 加两个独立连接并发提交同一业务键，最终 count 为 1；SQLite 锁冲突允许 Worker 重试数据库操作，但不得放宽唯一性断言。

Expected RED: 当前 `get_or_create` 无约束，且不同正文会更新 hash 但保留旧 content。

- [ ] **Step 4: 实现数据库裁决**

抽取 `_create_or_get_version(...)`：

1. 在嵌套 `transaction.atomic()` savepoint 内先 `create` 元数据（包含 `content_hash`），赢得唯一键后才写正文并保存 `content`。
2. 捕获 `IntegrityError` 后退出失败 savepoint，再按业务键读取胜者。
3. 胜者 hash 相同返回 `(existing, False)`；不同抛 `BaseAppException("配置文件回调业务键内容冲突")`。
4. 禁止修改已存在行的正文相关字段。

- [ ] **Step 5: 回归、迁移检查与提交**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_config_file_process_collect_db.py apps/cmdb/tests/test_config_file_service.py apps/cmdb/tests/e2e/test_config_file_pipeline.py
```

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb .venv/bin/python manage.py makemigrations --check --dry-run
```

Expected: 测试全部 PASS；`No changes detected`。

```bash
git add server/apps/cmdb/models/config_file_version.py server/apps/cmdb/migrations/0032_dedupe_config_file_versions.py server/apps/cmdb/services/config_file_service.py server/apps/cmdb/tests/test_config_file_process_collect_db.py
git commit -m "fix(cmdb): 约束配置回调版本幂等"
```

### Task 6: 阶段二组合回归、覆盖率与收口

**Files:**
- Verify all files from Task 1–5.

- [ ] **Step 1: 运行 Server 阶段二回归**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_subscription_task_service.py \
  apps/cmdb/tests/test_subscription_trigger_service.py \
  apps/cmdb/tests/test_collect_celery_tasks_svc.py \
  apps/cmdb/tests/test_collect_service_methods.py \
  apps/cmdb/tests/test_config_file_process_collect_db.py \
  apps/cmdb/tests/test_config_file_service.py \
  apps/cmdb/tests/e2e/test_config_file_pipeline.py
```

- [ ] **Step 2: 运行 Stargazer 回归**

```bash
cd agents/stargazer && uv run pytest -q tests/test_host_collector.py tests/test_api_http_layer.py tests/test_collect_multicred.py
```

- [ ] **Step 3: 检查核心覆盖率**

```bash
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' \
  --cov=apps.cmdb.services.subscription_task \
  --cov=apps.cmdb.tasks.celery_tasks \
  --cov=apps.cmdb.services.config_file_service \
  --cov-report=term-missing \
  apps/cmdb/tests/test_subscription_task_service.py \
  apps/cmdb/tests/test_collect_celery_tasks_svc.py \
  apps/cmdb/tests/test_config_file_process_collect_db.py
```

验收：本阶段新增/修改行覆盖率 ≥80%；投递抢占、状态转换、execution ID 校验和配置幂等分支 ≥90%。

- [ ] **Step 4: 静态检查**

```bash
git diff --check
git status --short
cd server && DB_ENGINE=sqlite DB_NAME=/private/tmp/bk_lite_cmdb_phase2.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb .venv/bin/python manage.py makemigrations --check --dry-run
```

- [ ] **Step 5: 项目记忆收口**

- #0035：通知 delivery 持久化、重投和并发无丢失测试通过后关闭。
- #0037：旧 Worker/超时/迟到回调均不能覆盖新代次或终态后关闭。
- #0036：数据库唯一约束、并发事务和内容冲突保护通过后关闭。

- [ ] **Step 6: 阶段二完成检查点**

只有以下条件同时成立才能进入阶段三：

- broker 派发失败后 delivery 仍可恢复。
- 两个不同 delivery 并发不会因全局锁丢失。
- 同一 delivery 重投不会重复调用渠道。
- Worker、超时巡检、配置回调全部带 execution ID 条件更新。
- 配置版本并发最终只有一行，同键不同正文不覆盖已有正文。
- Server、Stargazer 回归、迁移检查和覆盖率门槛全部通过。
