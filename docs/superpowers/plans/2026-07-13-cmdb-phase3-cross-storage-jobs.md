# CMDB 阶段三：跨存储一致性与后台作业实施计划

> 执行规则：每个 Task 独立完成 RED → GREEN → 回归 → 提交。禁止原生 SQL；迁移只使用 historical model ORM；所有外部副作用必须在数据库状态可恢复后执行。

**目标：** 关闭 #0043、#0044、#0042，使 MinIO 正文、IPAM 全量对账和 FalkorDB 主数据写入在进程崩溃、事务回滚、broker/外部服务失败及重复请求下可恢复、可幂等、可观察。

**实施顺序：**

1. MinIO 内容生命周期与补偿；
2. IPAM 单执行者后台作业；
3. FalkorDB 操作日志与审计 outbox；
4. 阶段三组合故障注入、覆盖率与迁移门禁。

---

## Task 1：配置正文生命周期模型

**Files**

- Modify: `server/apps/cmdb/models/config_file_version.py`
- Create: `server/apps/cmdb/migrations/0033_config_file_content_lifecycle.py`
- Modify: `server/apps/cmdb/tests/test_config_file_process_collect_db.py`

### RED

- 新版本默认内容状态为 `PENDING`，并保存唯一临时对象键。
- `READY` 必须有正式 `content`；失败发布进入 `ERROR` 并保留错误摘要/重试次数。
- 删除请求只把行推进为 `DELETE_PENDING`，不得在数据库提交前删除对象。
- 迁移把已有有正文记录标记为 `READY`，无正文记录标记为 `ERROR`。

### GREEN

- 增加 `content_status`、`temp_content_key`、`content_error`、`content_attempt_count`、`content_updated_at`。
- 状态枚举：`PENDING/READY/DELETE_PENDING/ERROR`。
- 增加状态与更新时间索引；不改变阶段二业务唯一键。
- 数据迁移只更新关系库，不访问 MinIO。

### Verify

```bash
cd server
DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb_phase3_lifecycle.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_config_file_process_collect_db.py
DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb_phase3_lifecycle.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run python manage.py makemigrations --check --dry-run
```

**Commit:** `feat(cmdb): 增加配置正文生命周期`

---

## Task 2：临时上传、提交后发布与安全删除

**Files**

- Create: `server/apps/cmdb/services/config_file_content_lifecycle.py`
- Modify: `server/apps/cmdb/services/config_file_service.py`
- Modify: `server/apps/cmdb/models/config_file_version.py`
- Modify: `server/apps/cmdb/views/config_file.py`
- Modify: `server/apps/cmdb/tests/test_config_file_process_collect_db.py`
- Modify: `server/apps/cmdb/tests/test_config_file_views.py`

### RED

- DB 事务回滚：正式对象写入函数零调用；元数据不存在。
- 新建版本：先写 `tmp/config-file/<uuid>`，数据库保存 `PENDING`；仅 `on_commit` 后复制/保存正式对象并更新 `READY`。
- 发布失败：DB 行保留，状态 `ERROR`、错误摘要和重试次数可见；业务键重投不覆盖正文。
- 删除时 DB 标记失败：对象删除零调用，原行仍可读取。
- DB 成功标记 `DELETE_PENDING` 后对象删除失败：行保留待补偿，不返回“对象已彻底删除”的假状态。
- 重复发布/删除调用幂等。

### GREEN

- 生命周期 Service 集中封装 `stage_content/publish_version/request_delete/retry_*`。
- `stage_content` 只写唯一临时键；正式键仍由 `build_object_key` 生成。
- `transaction.on_commit` 回调只接收 version id，重新读取行并用状态条件更新。
- 发布顺序：读取临时对象 → 写正式对象 → 条件更新 DB 为 READY → 删除临时对象。
- 删除顺序：条件更新 DB 为 DELETE_PENDING → on_commit 删除正式/临时对象 → 删除元数据；失败保留行和错误。
- 移除 Model.delete 中“先删对象”的隐式副作用，所有业务删除统一走生命周期 Service。

### Verify

- 使用内存 fake storage 验证调用顺序和故障注入，不连接真实 MinIO。
- 回归配置文件 DB、View、E2E 全链路。

**Commit:** `fix(cmdb): 补偿配置正文跨存储生命周期`

---

## Task 3：配置正文周期补偿与孤儿治理

**Files**

- Modify: `server/apps/cmdb/services/config_file_content_lifecycle.py`
- Modify: `server/apps/cmdb/tasks/celery_tasks.py`
- Modify: `server/config/celery.py`（仅当现有 beat 注册不支持 app task 自动发现）
- Create: `server/apps/cmdb/tests/test_config_file_content_lifecycle.py`

### RED

- 超时 `PENDING/ERROR` 发布记录可重试并最终 READY。
- `DELETE_PENDING` 可重试并最终删除 DB 行。
- 清理只处理超过租约时间的记录；当前 Worker 正在处理的行不被抢占。
- 临时前缀中无 DB 引用且超过保留期的对象会删除；正式对象不做无依据扫描删除。
- 每轮使用 `iterator(chunk_size=...)` 和固定 limit，失败隔离到单条。

### GREEN

- 增加周期 Celery task 和批次上限。
- 条件抢占使用状态 + `content_updated_at` 租约；重复 Worker 不重复发布/删除。
- 孤儿临时对象按固定前缀、最后修改时间和 DB 引用集合清理。
- 输出 scanned/recovered/failed/orphans_deleted 统计和结构化日志。

**Commit:** `feat(cmdb): 增加配置正文补偿任务`

---

## Task 4：IPAM 作业记录与单执行者抢占

**Files**

- Modify: `server/apps/cmdb/models/ipam_models.py`
- Create: `server/apps/cmdb/migrations/0034_ipam_reconcile_run.py`
- Create: `server/apps/cmdb/services/ipam_reconcile_job.py`
- Modify: `server/apps/cmdb/tasks/celery_tasks.py`
- Modify: `server/apps/cmdb/views/instance.py`
- Modify: `server/apps/cmdb/tests/test_ipam_views.py`
- Modify: `server/apps/cmdb/tests/test_ipam_reconcile_task.py`
- Create: `server/apps/cmdb/tests/test_ipam_reconcile_job.py`

### RED

- 手动接口只创建/返回作业并派发 Celery，不同步调用 `run_reconciliation`。
- 手动与周期同时触发只产生一个 RUNNING 作业；重复请求返回同一 run id。
- worker 使用 owner token 抢占；非 owner 不能释放锁或完成作业。
- 成功记录统计、开始/结束时间；异常记录 ERROR 和安全错误摘要并向 Celery 传播。
- broker 派发失败保留 PENDING 作业，可由扫描任务恢复。
- 租约过期的 RUNNING 作业可被新 owner 接管；旧 owner 不能覆盖新代次。

### GREEN

- `IPAMReconcileRun`：run_id、trigger、status、owner_token、lease_expires_at、stats、last_error、started_at、finished_at、timestamps。
- 数据库条件更新是最终 owner 裁决；缓存分布式锁仅减少竞争，释放使用 compare-and-delete/owner token。
- View 返回 `run_id/status/reused`；周期入口调用同一 enqueue service。
- worker 只在持有 owner token 时执行现有 `run_reconciliation`。

**Commit:** `fix(cmdb): 将IPAM对账收敛为单执行作业`

---

## Task 5：IPAM 分批边界

**Files**

- Modify: `server/apps/cmdb/services/ipam_reconcile.py`
- Modify: `server/apps/cmdb/tests/test_ipam_reconcile_service.py`

### RED

- 来源实例查询按稳定主键游标和 batch size 调用，不一次性返回全部资产。
- 每批失败可定位 source/cursor，重跑不会重复制造 IP/关联。
- 子网/已有 IP 字典的允许规模与生命周期明确；若仍需全量，必须配置上限并在超限时失败关闭作业。

### GREEN

- 抽取 batch iterator；默认批次 500，可配置且有上下界。
- 每批独立统计，最终聚合；不在循环中重复加载来源配置。

**Commit:** `perf(cmdb): 为IPAM对账增加稳定分批`

---

## Task 6：FalkorDB 操作日志与幂等入口

**Files**

- Create: `server/apps/cmdb/models/operation.py`
- Modify: `server/apps/cmdb/models/__init__.py`
- Create: `server/apps/cmdb/migrations/0035_cmdb_operation_outbox.py`
- Create: `server/apps/cmdb/services/operation_service.py`
- Modify: `server/apps/cmdb/services/instance.py`
- Modify: `server/apps/cmdb/views/instance.py`
- Create: `server/apps/cmdb/tests/test_operation_service.py`
- Modify: relevant instance service/view tests

### RED

- 相同调用方幂等键与同请求摘要只执行一次图写并返回同一 operation/result。
- 相同幂等键不同请求摘要返回明确冲突，不执行图写。
- 图写成功后审计/后置失败：HTTP 主结果不伪装为图写失败；operation 保持 GRAPH_COMMITTED。
- 图写抛错：operation ERROR，不生成 outbox。
- PENDING 崩溃恢复先核对目标事实；不盲目重复 create。

### GREEN

- `CmdbOperation` 保存 operation_id、idempotency_key、request_hash、action、target、request/result snapshot、status、error、timestamps。
- `CmdbOperationOutbox` 保存 operation FK、event_type、payload、status、attempt_count、lease/error/timestamps，唯一 `operation + event_type`。
- View 从 `Idempotency-Key` 读取调用方键；内部/NATS 调用必须显式传稳定键，缺失时仅对安全的非重试调用生成 operation id。
- 图写完成后在关系库记录 GRAPH_COMMITTED 并创建 outbox；审计和自动关联调度由 outbox 消费。

**Commit:** `feat(cmdb): 持久化实例操作与后置事件`

---

## Task 7：操作 outbox 消费与不确定状态补偿

**Files**

- Modify: `server/apps/cmdb/services/operation_service.py`
- Modify: `server/apps/cmdb/tasks/celery_tasks.py`
- Modify: `server/apps/cmdb/utils/change_record.py`
- Create: `server/apps/cmdb/tests/test_operation_outbox.py`

### RED

- broker 失败后 outbox 仍 PENDING/RETRY，扫描可恢复。
- 两个不同 operation 并发均消费；同一 outbox 仅一个 lease owner 执行。
- 旧 lease worker 不能覆盖新代次终态。
- 审计写入幂等；重复消费不重复 ChangeRecord/平台日志。
- 达上限 FAILED 保留诊断；主图写结果不回滚。

### GREEN

- 条件抢占、有限重试、退避和租约模式复用阶段二 delivery 的已验证原则。
- `change_record` 接受 operation/event 幂等标识，数据库约束裁决重复。
- 补偿 task 扫描 PENDING/RETRY/过期 SENDING。

**Commit:** `fix(cmdb): 可靠消费实例操作后置事件`

---

## Task 8：阶段三组合门禁

### Fault injection

- DB rollback、MinIO stage/publish/delete 失败、进程在 on_commit 前后退出。
- Celery broker 失败、IPAM owner 过期/接管、旧 owner 迟到完成。
- FalkorDB 成功 + 审计失败、图写失败、相同幂等键重投、PENDING 不确定恢复。

### Regression

- 配置文件 DB/View/E2E。
- IPAM View/Service/Task/Job。
- Instance create/update/delete/association、ChangeRecord、auto relation。
- `makemigrations --check --dry-run`、`git diff --check`。
- 核心新增状态机与幂等分支覆盖率 ≥90%，阶段三修改行 ≥80%。

### Project memory

- 证据满足后关闭 #0043、#0044、#0042。
- 记录 MinIO、IPAM 和操作 outbox 的状态机/租约/幂等决策。

只有上述门禁全部通过，才能进入阶段四规模治理。
