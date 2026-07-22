# Historical Superpowers change: 2026-07-16-node-management-sync-reconciliation

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-16-node-management-sync-reconciliation.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task with review checkpoints.

**Goal:** 修复“开关显示已开启但长期无数据”的节点管理同步链路，并让首次打开、关闭后再次打开、调度漂移、权限隔离、同步前置、采集提交与最终完成状态都可被验证和恢复。

**Architecture:** `NodeMgmtSyncConfig` 只保存全局期望状态；新增 `NodeMgmtSyncReconciler` 将期望状态对账到 Celery Beat 和节点采集参数，并把健康度写回配置。同步/采集运行通过单活令牌、代次和区域子状态形成可恢复状态机；定时采集必须等待一次成功同步，系统调度使用显式系统身份查询节点管理，HTTP 用户权限只负责授权入口。

**Tech Stack:** Python 3.12、Django 4.2、Django REST Framework、Celery、django-celery-beat、pytest、Next.js 16、React 19、TypeScript、Ant Design。

## Global Constraints

- 设计依据：[节点管理同步期望状态对账设计](../specs/2026-07-16-node-management-sync-reconciliation-design.md) 和 [产品决策](../../design/product-decisions/node-management-sync.md)。
- 全程 TDD：每个行为先写失败测试并保留 RED 证据，再写最小实现得到 GREEN，最后重构。
- 必测用户指定场景：①首次打开页面且默认开关为开；②已打开后关闭，刷新/重启不得自行恢复；另补充关闭后重新开启。
- 节点管理后台任务必须显式传 `skip_permission=True`；普通 HTTP 请求不得复用该旁路扩大权限。
- 配置 GET 需要 `View`，配置 PUT 需要 `Execute`，全局手动执行仅平台管理员。
- 禁止原生 SQL；迁移和运行期全部使用 Django ORM。
- 不记录凭据、节点下发参数和节点管理原始异常；API 只返回稳定 `reason_code` 与脱敏摘要。
- 所有分页、单次运行和节点参数下发均有上限、截止时间、幂等键和可重试状态。
- 后端核心新增代码覆盖率目标 ≥90%，CMDB 改动整体覆盖率 ≥75%。

---

### Task 1: 建立单例配置、运行状态机和区域子状态 schema

**Files:**

- Modify: `server/apps/cmdb/models/models.py`
- Create: `server/apps/cmdb/migrations/0039_node_mgmt_sync_reconciliation.py`
- Create: `server/apps/cmdb/tests/test_node_mgmt_sync_models.py`

**Step 1: 写 schema 行为测试（RED）**

```python
import pytest
from django.db import IntegrityError, transaction

from apps.cmdb.models import NodeMgmtSyncConfig, NodeMgmtSyncRegionState, NodeMgmtSyncRun


pytestmark = pytest.mark.django_db


def test_config_is_database_singleton():
    NodeMgmtSyncConfig.objects.create(singleton_key="default")
    with pytest.raises(IntegrityError), transaction.atomic():
        NodeMgmtSyncConfig.objects.create(singleton_key="default")


def test_only_one_run_can_hold_global_active_scope():
    config = NodeMgmtSyncConfig.objects.create(singleton_key="default")
    NodeMgmtSyncRun.objects.create(task=config, run_type="sync", status="running", active_scope="node_mgmt_sync")
    with pytest.raises(IntegrityError), transaction.atomic():
        NodeMgmtSyncRun.objects.create(task=config, run_type="collect", status="waiting_sync", active_scope="node_mgmt_sync")


def test_region_state_is_unique_per_run_and_region():
    config = NodeMgmtSyncConfig.objects.create(singleton_key="default")
    run = NodeMgmtSyncRun.objects.create(task=config, run_type="collect", status="submitted")
    scope_key = f"run:{run.generation}:region:1"
    NodeMgmtSyncRegionState.objects.create(
        config=config, run=run, scope_key=scope_key,
        cloud_region_id="1", status="submitted",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        NodeMgmtSyncRegionState.objects.create(
            config=config, run=run, scope_key=scope_key,
            cloud_region_id="1", status="submitted",
        )
```

**Step 2: 运行测试，确认因字段/模型缺失而失败**

Run:

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_models.py
```

Expected: RED，导入 `NodeMgmtSyncRegionState` 或创建新字段失败。

**Step 3: 增加模型状态和约束**

在 `NodeMgmtSyncConfig` 增加：

```python
singleton_key = models.CharField(max_length=32, default="default", unique=True, editable=False)
version = models.PositiveBigIntegerField(default=1)
schedule_status = models.CharField(max_length=32, default="reconciling")
node_config_status = models.CharField(max_length=32, default="reconciling")
last_reconciled_at = models.DateTimeField(null=True, blank=True)
reconcile_error_code = models.CharField(max_length=64, blank=True, default="")
reconcile_error_message = models.CharField(max_length=255, blank=True, default="")
```

扩充 `NodeMgmtSyncRun`：

```python
STATUS_CHOICES = (
    ("waiting_sync", "等待同步"),
    ("running", "执行中"),
    ("submitted", "已提交"),
    ("success", "成功"),
    ("partial_success", "部分成功"),
    ("blocked", "已阻塞"),
    ("failed", "失败"),
    ("timeout", "超时"),
)

generation = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
active_scope = models.CharField(max_length=32, null=True, blank=True, unique=True)
reason_code = models.CharField(max_length=64, blank=True, default="")
submitted_at = models.DateTimeField(null=True, blank=True)
heartbeat_at = models.DateTimeField(null=True, blank=True)
deadline_at = models.DateTimeField(null=True, blank=True)
```

新增区域状态：

```python
class NodeMgmtSyncRegionState(TimeStampedModel):
    config = models.ForeignKey(NodeMgmtSyncConfig, related_name="region_states", on_delete=models.CASCADE)
    run = models.ForeignKey(NodeMgmtSyncRun, null=True, blank=True, related_name="region_states", on_delete=models.CASCADE)
    scope_key = models.CharField(max_length=160, unique=True)
    cloud_region_id = models.CharField(max_length=64)
    config_version = models.PositiveBigIntegerField(default=1)
    status = models.CharField(max_length=32, default="pending")
    reason_code = models.CharField(max_length=64, blank=True, default="")
    error_message = models.CharField(max_length=255, blank=True, default="")
    collect_task = models.ForeignKey("CollectModels", null=True, blank=True, on_delete=models.SET_NULL)
    child_execution_id = models.CharField(max_length=64, blank=True, default="")
    node_config_status = models.CharField(max_length=32, default="pending")
    instance_count = models.PositiveIntegerField(default=0)
    submitted_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

```

运行态的 `scope_key` 固定为 `run:{run.generation}:region:{cloud_region_id}`；启动/配置对账态固定为 `config:{config.version}:region:{cloud_region_id}`。这样同一模型既能保存无 run 的节点参数补偿状态，也能保存每次采集的区域子执行，且所有数据库方言都由普通唯一索引保证幂等。

**Step 4: 编写兼容现有数据的 ORM 迁移**

迁移顺序必须是：先添加可空/非唯一字段 → `RunPython` 将所有旧 run 指向最早配置并删除多余配置 → 回填 `singleton_key="default"` → 加唯一约束。旧 `running` run 若超过截止时间则迁移为 `timeout` 并清空 `active_scope`，不能让部署后永久占锁。

**Step 5: 运行模型测试和迁移检查（GREEN）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_models.py
uv run python manage.py makemigrations --check --dry-run
```

Expected: 全部通过；`makemigrations` 输出 `No changes detected`。

**Step 6: 提交**

```bash
git add server/apps/cmdb/models/models.py server/apps/cmdb/migrations/0039_node_mgmt_sync_reconciliation.py server/apps/cmdb/tests/test_node_mgmt_sync_models.py
git commit -m "fix(cmdb): 建立节点同步可恢复状态模型"
```

---

### Task 2: 实现调度期望状态对账，覆盖首次打开、关闭和漂移恢复

**Files:**

- Create: `server/apps/cmdb/services/node_mgmt_sync_reconciler.py`
- Modify: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Create: `server/apps/cmdb/tests/test_node_mgmt_sync_reconciler.py`

**Step 1: 写首次打开和开关往返测试（RED）**

```python
import pytest
from django_celery_beat.models import PeriodicTask

from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService


pytestmark = pytest.mark.django_db


def _task_names():
    return set(PeriodicTask.objects.values_list("name", flat=True))


def test_first_open_reconciles_default_enabled_switches_to_beat():
    payload = NodeMgmtSyncService.get_task_payload(reconcile=True)
    assert payload["auto_sync_enabled"] is True
    assert payload["auto_collect_enabled"] is True
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME in _task_names()
    assert payload["schedule_status"] == "healthy"


def test_disable_then_refresh_keeps_both_schedules_absent():
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": False})
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME not in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME not in _task_names()

    payload = NodeMgmtSyncService.get_task_payload(reconcile=True)
    assert payload["auto_sync_enabled"] is False
    assert payload["auto_collect_enabled"] is False
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME not in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME not in _task_names()


def test_disable_then_enable_recreates_both_schedules():
    NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": False})
    NodeMgmtSyncService.update_task({"auto_sync_enabled": True, "auto_collect_enabled": True})
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME in _task_names()
    assert NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME in _task_names()


def test_reconcile_repairs_deleted_or_wrong_interval_schedule():
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    PeriodicTask.objects.filter(name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME).delete()
    NodeMgmtSyncService.get_task_payload(reconcile=True)
    assert NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME in _task_names()
```

**Step 2: 运行测试，确认首次打开不建任务（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_reconciler.py
```

Expected: 首次打开用例失败，证明当前只有 PUT 才同步 Beat。

**Step 3: 实现幂等对账器**

```python
@dataclass(frozen=True)
class NodeMgmtSyncReconcileResult:
    schedule_status: str
    node_config_status: str
    error_code: str = ""
    error_message: str = ""


class NodeMgmtSyncReconciler:
    @classmethod
    def reconcile(cls, config, *, reconcile_node_configs=False):
        try:
            cls._reconcile_periodic_task(
                enabled=config.auto_sync_enabled,
                name=NodeMgmtSyncService.SYNC_PERIODIC_TASK_NAME,
                task=NodeMgmtSyncService.SYNC_TASK,
                interval=config.sync_interval_minutes,
            )
            cls._reconcile_periodic_task(
                enabled=config.auto_collect_enabled,
                name=NodeMgmtSyncService.COLLECT_PERIODIC_TASK_NAME,
                task=NodeMgmtSyncService.COLLECT_TASK,
                interval=config.collect_interval_minutes,
            )
            node_status = cls._reconcile_node_configs(config) if reconcile_node_configs else config.node_config_status
            result = NodeMgmtSyncReconcileResult("healthy", node_status or "unknown")
        except Exception as exc:
            logger.exception("节点管理同步对账失败")
            result = NodeMgmtSyncReconcileResult("degraded", "degraded", "RECONCILE_FAILED", str(exc)[:255])
        cls._persist_health(config, result)
        return result
```

`_reconcile_periodic_task` 必须比较任务名、task path、crontab 和 enabled；期望关闭时删除，期望开启时创建或修正。异常只能写脱敏摘要，不能吞掉后继续返回 `healthy`。

在现有 service 中保持 `get_task()` 为纯单例读取/创建，新增明确入口：

```python
@classmethod
def get_task_payload(cls, *, reconcile: bool = True) -> dict[str, Any]:
    task = cls.get_task()
    if reconcile:
        NodeMgmtSyncReconciler.reconcile(task)
        task.refresh_from_db()
    return cls.serialize_task(task)
```

`update_task()` 在事务中仅保存期望状态和递增 `version`；事务提交后调用 reconciler，避免 Beat 写入与主库事务互相制造假原子性。

**Step 4: 运行调度测试（GREEN）**

使用 Step 2 命令。Expected: 4 个场景全部通过。

**Step 5: 提交**

```bash
git add server/apps/cmdb/services/node_mgmt_sync_reconciler.py server/apps/cmdb/services/node_mgmt_sync_service.py server/apps/cmdb/tests/test_node_mgmt_sync_reconciler.py
git commit -m "fix(cmdb): 对账节点同步开关与周期任务"
```

---

### Task 3: 收紧配置与全局执行权限，并暴露健康状态

**Files:**

- Modify: `server/apps/cmdb/views/node_mgmt_sync.py`
- Modify: `server/apps/cmdb/serializers/node_mgmt_sync.py`
- Modify: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Create: `server/apps/cmdb/tests/test_node_mgmt_sync_views.py`

**Step 1: 写权限和 API 合同测试（RED）**

```python
def test_view_permission_can_get_but_cannot_put(api_client, view_user):
    api_client.force_authenticate(view_user)
    assert api_client.get(CONFIG_URL).status_code == 200
    assert api_client.put(CONFIG_URL, {"auto_sync_enabled": False}, format="json").status_code == 403


def test_execute_permission_can_update_config(api_client, execute_user):
    api_client.force_authenticate(execute_user)
    response = api_client.put(CONFIG_URL, {"auto_sync_enabled": False}, format="json")
    assert response.status_code == 200
    assert response.json()["data"]["auto_sync_enabled"] is False


def test_non_superuser_cannot_start_global_run(api_client, execute_user):
    api_client.force_authenticate(execute_user)
    assert api_client.post(RUN_SYNC_URL).status_code == 403


def test_config_response_exposes_reconciliation_health(api_client, view_user):
    api_client.force_authenticate(view_user)
    data = api_client.get(CONFIG_URL).json()["data"]
    assert set(data["health"]) == {
        "schedule_status", "node_config_status", "last_reconciled_at",
        "reason_code", "message",
    }
```

**Step 2: 运行并确认 PUT 和 run 权限测试失败（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_views.py
```

**Step 3: 按 HTTP 方法配置权限**

```python
@action(methods=["get", "put"], detail=False, url_path="task")
def task(self, request, *args, **kwargs):
    if request.method.upper() == "PUT":
        return self._update_task(request)
    return self._get_task(request)


@HasPermission("auto_collection-View")
def _get_task(self, request):
    return WebUtils.response_success(NodeMgmtSyncService.get_task_payload(reconcile=True))


@HasPermission("auto_collection-Execute")
def _update_task(self, request):
    task = NodeMgmtSyncService.update_task(request.data)
    return WebUtils.response_success(NodeMgmtSyncService.serialize_task(task))
```

`config` 兼容路由继续调用同一个 `task()`，确保 GET/PUT 不出现权限分叉。`run_sync`、`run_collect` 保留 `auto_collection-Execute` 装饰器，并在方法体最前面检查 `request.user.is_superuser`；非平台管理员直接返回 `WebUtils.response_403("仅平台管理员可执行全局节点同步")`。不要修改全局 `HasPermission`，避免影响其 200 多个调用点。

**Step 4: 返回稳定健康合同**

```python
"health": {
    "schedule_status": task.schedule_status,
    "node_config_status": task.node_config_status,
    "last_reconciled_at": cls._serialize_dt(task.last_reconciled_at),
    "reason_code": task.reconcile_error_code,
    "message": task.reconcile_error_message,
}
```

序列化器增加跨字段校验：`auto_collect_enabled=True` 时，后端仍允许同步开关暂时关闭，但健康状态必须为 `waiting_sync`，执行器不得直接采集。间隔字段限制在 `1..1440`。

**Step 5: 运行测试（GREEN）并提交**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_views.py
git add apps/cmdb/views/node_mgmt_sync.py apps/cmdb/serializers/node_mgmt_sync.py apps/cmdb/services/node_mgmt_sync_service.py apps/cmdb/tests/test_node_mgmt_sync_views.py
git commit -m "fix(cmdb): 收紧节点同步配置与执行权限"
```

---

### Task 4: 修复节点管理系统查询身份并限制分页资源

**Files:**

- Modify: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_helpers.py`
- Modify: `server/apps/cmdb/tests/test_node_mgmt_sync_resilience.py`

**Step 1: 把现有错误合同改成系统身份合同（RED）**

```python
def test_fetch_nodes_uses_explicit_system_permission_bypass(mocker):
    node_list = mocker.patch("apps.cmdb.services.node_mgmt_sync_service.NodeMgmt.node_list")
    node_list.return_value = {"result": True, "data": {"items": [], "count": 0}}

    NodeMgmtSyncService._fetch_node_mgmt_pages({"page_size": 100})

    assert node_list.call_args.args[0]["skip_permission"] is True


def test_fetch_nodes_stops_at_page_budget(mocker):
    node_list = mocker.patch("apps.cmdb.services.node_mgmt_sync_service.NodeMgmt.node_list")
    node_list.return_value = {"result": True, "data": {"items": [{}] * 100, "count": 999999}}
    with pytest.raises(NodeMgmtSyncError, match="NODE_PAGE_LIMIT_EXCEEDED"):
        NodeMgmtSyncService._fetch_node_mgmt_pages({"page_size": 100}, max_pages=2)
    assert node_list.call_count == 2
```

另保留 `apps/node_mgmt/tests/test_b75_node_service.py` 中现有的
`test_get_node_list_without_permission_or_org_scope_returns_empty`，证明普通无权限查询仍 fail-close；只修改 CMDB helper 对 `skip_permission=True` 的断言，不能修改节点管理的安全默认值。

**Step 2: 运行定向测试（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_helpers.py apps/cmdb/tests/test_node_mgmt_sync_resilience.py apps/node_mgmt/tests/test_b75_node_service.py
```

**Step 3: 实现显式系统查询与边界**

```python
SYSTEM_NODE_QUERY = {"skip_permission": True}
MAX_NODE_PAGES = 100
NODE_PAGE_SIZE = 500


@classmethod
def _fetch_node_mgmt_pages(cls, query, *, max_pages=MAX_NODE_PAGES, deadline_at=None):
    payload = {**query, **cls.SYSTEM_NODE_QUERY, "page_size": min(int(query.get("page_size", cls.NODE_PAGE_SIZE)), cls.NODE_PAGE_SIZE)}
    rows = []
    for page in range(1, max_pages + 1):
        if deadline_at and timezone.now() >= deadline_at:
            raise NodeMgmtSyncError("NODE_QUERY_TIMEOUT")
        payload["page"] = page
        response = NodeMgmt().node_list(payload)
        cls._raise_for_node_response(response)
        items = response["data"].get("items", [])
        rows.extend(items)
        if len(items) < payload["page_size"]:
            return rows
    raise NodeMgmtSyncError("NODE_PAGE_LIMIT_EXCEEDED")
```

`_raise_for_node_response` 将 RPC/HTTP 异常映射为稳定码，日志保留堆栈但 API `message` 只保留 255 字符脱敏摘要。

**Step 4: 运行测试（GREEN）并提交**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_helpers.py apps/cmdb/tests/test_node_mgmt_sync_resilience.py apps/node_mgmt/tests/test_b75_node_service.py
git add apps/cmdb/services/node_mgmt_sync_service.py apps/cmdb/tests/test_node_mgmt_sync_helpers.py apps/cmdb/tests/test_node_mgmt_sync_resilience.py apps/node_mgmt/tests/test_b75_node_service.py
git commit -m "fix(cmdb): 使用系统身份查询节点管理数据"
```

---

### Task 5: 让同步真正写入新增和更新主机，并准确报告结果

**Files:**

- Modify: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Create: `server/apps/cmdb/tests/test_node_mgmt_sync_persistence.py`

**Step 1: 写更新持久化和部分失败测试（RED）**

```python
def test_existing_host_diff_calls_instance_update(mocker, existing_host, node_payload):
    update = mocker.patch("apps.cmdb.services.node_mgmt_sync_service.InstanceManage.instance_update")
    NodeMgmtSyncService._persist_hosts([node_payload], existing_hosts={node_payload["ip_addr"]: existing_host}, operator="system")
    update.assert_called_once_with(
        user_groups=[], roles=[], inst_id=existing_host["_id"],
        update_attr=mocker.ANY, operator="system", allowed_org_ids=None,
        skip_permission_check=True, operation_id=mocker.ANY,
        schedule_post_actions=False,
    )


def test_update_failure_is_partial_success_not_fake_success(mocker):
    existing = {"_id": 7, "ip_addr": "10.0.0.7", "inst_name": "old-name"}
    desired = {"ip_addr": "10.0.0.7", "inst_name": "new-name"}
    mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_service.InstanceManage.instance_update",
        side_effect=RuntimeError("write failed"),
    )
    result = NodeMgmtSyncService._persist_hosts(
        [desired], existing_hosts={"10.0.0.7": existing}, operator="system"
    )
    assert result["update"] == 1
    assert result["update_error"] == 1
    assert result["update_success"] == 0
```

再加“不变数据不写”“同一 generation 重试不重复创建”“新增成功计数”三个行为测试。

**Step 2: 运行测试（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_persistence.py
```

**Step 3: 实现字段白名单 diff 和真实更新**

```python
HOST_SYNC_FIELDS = ("inst_name", "ip_addr", "cloud_region", "organization", "os_type", "os_name")


def _changed_attrs(existing, desired):
    return {key: desired.get(key) for key in HOST_SYNC_FIELDS if desired.get(key) != existing.get(key)}


changes = _changed_attrs(existing, desired)
if changes:
    InstanceManage.instance_update(
        user_groups=[], roles=[], inst_id=existing["_id"], update_attr=changes,
        operator=operator, allowed_org_ids=None, skip_permission_check=True,
        operation_id=str(run.generation), schedule_post_actions=False,
    )
```

批量结束后统一调度一次关联对账；单条异常进入 detail 和计数，不能使整批静默成功，也不能泄露原始敏感字段。

**Step 4: 运行测试（GREEN）并提交**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_persistence.py
git add apps/cmdb/services/node_mgmt_sync_service.py apps/cmdb/tests/test_node_mgmt_sync_persistence.py
git commit -m "fix(cmdb): 持久化节点同步主机更新"
```

---

### Task 6: 建立单活执行、截止时间和陈旧运行恢复

**Files:**

- Modify: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Modify: `server/apps/cmdb/tasks/node_mgmt_sync.py`
- Create: `server/apps/cmdb/tests/test_node_mgmt_sync_execution.py`

**Step 1: 写并发与超时测试（RED）**

```python
def test_second_run_is_blocked_while_global_scope_is_held():
    first = NodeMgmtSyncService.acquire_run("sync")
    second = NodeMgmtSyncService.acquire_run("collect")
    assert first.status == "running"
    assert second.status == "blocked"
    assert second.reason_code == "RUN_ALREADY_ACTIVE"


def test_stale_run_is_timed_out_and_scope_released():
    stale = make_run(status="running", active_scope="node_mgmt_sync", deadline_at=timezone.now() - timedelta(seconds=1))
    NodeMgmtSyncService.recover_stale_runs()
    stale.refresh_from_db()
    assert stale.status == "timeout"
    assert stale.active_scope is None
    assert stale.finished_at is not None


def test_terminal_transition_clears_active_scope():
    run = NodeMgmtSyncService.acquire_run("sync")
    NodeMgmtSyncService.finish_run(run, status="success")
    run.refresh_from_db()
    assert run.active_scope is None
```

**Step 2: 运行测试（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_execution.py
```

**Step 3: 用数据库唯一约束实现单活，不用进程内锁**

```python
@classmethod
def acquire_run(cls, run_type):
    task = cls.get_task()
    try:
        return NodeMgmtSyncRun.objects.create(
            task=task, run_type=run_type, status="running",
            active_scope="node_mgmt_sync", heartbeat_at=timezone.now(),
            deadline_at=timezone.now() + timedelta(minutes=30),
        )
    except IntegrityError:
        return NodeMgmtSyncRun.objects.create(
            task=task, run_type=run_type, status="blocked",
            reason_code="RUN_ALREADY_ACTIVE", finished_at=timezone.now(),
        )
```

所有终态必须通过同一个 `finish_run()` 更新并清空 `active_scope`。长循环每页/每区域刷新 `heartbeat_at` 并检查 `deadline_at`。Celery task 的 `finally` 只在未进入终态时标记 failed，不能覆盖已写入的 partial_success/timeout。

**Step 4: 运行测试（GREEN）并提交**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_execution.py
git add apps/cmdb/services/node_mgmt_sync_service.py apps/cmdb/tasks/node_mgmt_sync.py apps/cmdb/tests/test_node_mgmt_sync_execution.py
git commit -m "fix(cmdb): 增加节点同步单活与超时恢复"
```

---

### Task 7: 实现节点参数下发的补偿式对账

**Files:**

- Modify: `server/apps/cmdb/services/node_mgmt_sync_reconciler.py`
- Modify: `server/apps/cmdb/services/collect_service.py`
- Create: `server/apps/cmdb/tests/test_node_mgmt_sync_node_config.py`

**Step 1: 写关闭、开启和失败补偿测试（RED）**

```python
def test_disable_collect_only_deletes_node_params(mocker, config, region_task):
    delete = mocker.patch.object(CollectModelService, "delete_butch_node_params")
    push = mocker.patch.object(CollectModelService, "push_butch_node_params")
    config.auto_collect_enabled = False
    NodeMgmtSyncReconciler.reconcile(config, reconcile_node_configs=True)
    delete.assert_called_once_with(region_task)
    push.assert_not_called()


def test_enable_collect_deletes_then_pushes(mocker, config, region_task):
    calls = []
    mocker.patch.object(CollectModelService, "delete_butch_node_params", side_effect=lambda task: calls.append("delete"))
    mocker.patch.object(CollectModelService, "push_butch_node_params", side_effect=lambda task: calls.append("push"))
    NodeMgmtSyncReconciler.reconcile(config, reconcile_node_configs=True)
    assert calls == ["delete", "push"]


def test_push_failure_persists_retryable_degraded_state(mocker, config, region_task):
    mocker.patch.object(CollectModelService, "delete_butch_node_params")
    mocker.patch.object(
        CollectModelService,
        "push_butch_node_params",
        side_effect=RuntimeError("push failed"),
    )
    NodeMgmtSyncReconciler.reconcile(config, reconcile_node_configs=True)
    config.refresh_from_db()
    state = NodeMgmtSyncRegionState.objects.get(
        config=config,
        config_version=config.version,
        cloud_region_id=region_task.system_code.removeprefix(NodeMgmtSyncService.SYSTEM_TASK_PREFIX),
    )
    assert config.node_config_status == "degraded"
    assert state.node_config_status == "push_pending"
```

fixture 必须创建真实 config 和 region collect task；区域状态由 reconciler 首次执行时 `update_or_create`，以便同时验证初始化行为。

**Step 2: 运行测试（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_node_config.py
```

**Step 3: 实现 delete/push 两阶段可重试状态**

每个区域先写 `delete_pending`，删除成功后写 `push_pending`；开启时 push 成功才写 `healthy`，关闭时 delete 成功直接写 `disabled`。失败保留所在阶段，下一轮 reconciler 从该阶段重试。幂等键使用 `(config.version, cloud_region_id)`，旧版本回调不得覆盖新版本健康状态。

**Step 4: 运行测试（GREEN）并提交**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_node_config.py
git add apps/cmdb/services/node_mgmt_sync_reconciler.py apps/cmdb/services/collect_service.py apps/cmdb/tests/test_node_mgmt_sync_node_config.py
git commit -m "fix(cmdb): 对账节点采集参数下发状态"
```

---

### Task 8: 让采集等待同步，并区分提交成功与执行成功

**Files:**

- Modify: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Modify: `server/apps/cmdb/tasks/node_mgmt_sync.py`
- Create: `server/apps/cmdb/tests/test_node_mgmt_sync_collection.py`

**Step 1: 写前置条件、拒绝提交和最终聚合测试（RED）**

```python
def test_collect_waits_for_first_successful_sync(config):
    run = NodeMgmtSyncService.execute_collect(operator="system")
    assert run.status == "waiting_sync"
    assert run.reason_code == "SYNC_REQUIRED"


def test_rejected_child_submission_is_blocked_not_success(mocker, successful_sync, collect_task):
    mocker.patch.object(
        CollectModelService, "exec_task",
        return_value=WebUtils.response_error({}, "任务正在执行", status_code=400),
    )
    run = NodeMgmtSyncService.execute_collect(operator="system")
    assert run.status == "blocked"
    assert run.region_states.get().reason_code == "COLLECT_ALREADY_RUNNING"


def test_accepted_children_make_parent_submitted_not_success(mocker, successful_sync, collect_tasks):
    mocker.patch.object(CollectModelService, "exec_task", side_effect=accepted_responses)
    run = NodeMgmtSyncService.execute_collect(operator="system")
    assert run.status == "submitted"
    assert run.finished_at is None


@pytest.mark.parametrize(
    ("child_statuses", "expected"),
    [(["success", "success"], "success"), (["success", "failed"], "partial_success"), (["failed", "failed"], "failed")],
)
def test_parent_finishes_from_child_terminal_states(child_statuses, expected, submitted_run):
    set_child_collect_statuses(submitted_run, child_statuses)
    NodeMgmtSyncService.refresh_collect_run(submitted_run.id)
    submitted_run.refresh_from_db()
    assert submitted_run.status == expected
```

**Step 2: 运行测试（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_collection.py
```

**Step 3: 解析真实 `JsonResponse` 并记录 child execution**

```python
response = CollectModelService.exec_task(collect_task, operator)
payload = json.loads(response.content)
if response.status_code >= 400 or not payload.get("result"):
    cls._mark_region_blocked(region_state, "COLLECT_ALREADY_RUNNING")
else:
    collect_task.refresh_from_db(fields=("task_id", "exec_status"))
    region_state.status = "submitted"
    region_state.child_execution_id = str(collect_task.task_id or "")
    region_state.submitted_at = timezone.now()
    region_state.save(update_fields=("status", "child_execution_id", "submitted_at", "updated_at"))
```

`execute_collect()` 的前置判断必须是“存在本 config 最近一次成功/部分成功同步且版本不落后于当前 config.version”；否则自动触发一次 sync 或写 `waiting_sync`，不得直接把空节点集记为成功。

**Step 4: 运行测试（GREEN）并提交**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_collection.py
git add apps/cmdb/services/node_mgmt_sync_service.py apps/cmdb/tasks/node_mgmt_sync.py apps/cmdb/tests/test_node_mgmt_sync_collection.py
git commit -m "fix(cmdb): 闭环节点同步与采集运行状态"
```

---

### Task 9: 在启动和运行期自动恢复调度、下发和陈旧运行

**Files:**

- Create: `server/apps/cmdb/management/commands/reconcile_node_mgmt_sync.py`
- Modify: `server/apps/core/management/commands/batch_init.py`
- Modify: `server/apps/core/tests/test_batch_init_command.py`
- Modify: `server/apps/cmdb/tasks/node_mgmt_sync.py`
- Create: `server/apps/cmdb/tests/test_reconcile_node_mgmt_sync_command.py`

**Step 1: 写启动编排和命令幂等测试（RED）**

```python
def test_cmdb_batch_init_reconciles_node_sync(calls):
    cmd = _make_command()
    cmd.handle(apps="cmdb", continue_on_error=False)
    names = [call[0] for call in calls]
    assert names[-1] == "reconcile_node_mgmt_sync"


def test_management_command_runs_reconcile_and_stale_recovery(mocker):
    reconcile = mocker.patch("apps.cmdb.management.commands.reconcile_node_mgmt_sync.NodeMgmtSyncReconciler.reconcile")
    recover = mocker.patch("apps.cmdb.management.commands.reconcile_node_mgmt_sync.NodeMgmtSyncService.recover_stale_runs")
    call_command("reconcile_node_mgmt_sync")
    reconcile.assert_called_once()
    recover.assert_called_once()
```

**Step 2: 运行测试（RED）**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/core/tests/test_batch_init_command.py apps/cmdb/tests/test_reconcile_node_mgmt_sync_command.py
```

**Step 3: 增加幂等启动命令和运行期恢复 task**

```python
class Command(BaseCommand):
    help = "对账节点管理同步期望状态并恢复陈旧运行"

    def handle(self, *args, **options):
        config = NodeMgmtSyncService.get_task()
        NodeMgmtSyncService.recover_stale_runs()
        result = NodeMgmtSyncReconciler.reconcile(config, reconcile_node_configs=True)
        if result.schedule_status != "healthy":
            raise CommandError(f"节点管理同步对账失败: {result.error_code}")
        self.stdout.write(self.style.SUCCESS("节点管理同步对账完成"))
```

在 `_init_cmdb()` 最后添加 `call_command("reconcile_node_mgmt_sync")`。另创建固定 5 分钟的恢复 PeriodicTask；恢复任务本身不受 auto 开关控制，只做健康检查、陈旧运行回收、submitted 子任务聚合和 degraded 下发重试，不直接发起业务同步/采集。

**Step 4: 运行测试（GREEN）并提交**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/core/tests/test_batch_init_command.py apps/cmdb/tests/test_reconcile_node_mgmt_sync_command.py
git add apps/cmdb/management/commands/reconcile_node_mgmt_sync.py apps/core/management/commands/batch_init.py apps/core/tests/test_batch_init_command.py apps/cmdb/tasks/node_mgmt_sync.py apps/cmdb/tests/test_reconcile_node_mgmt_sync_command.py
git commit -m "fix(cmdb): 启动并周期恢复节点同步状态"
```

---

### Task 10: 前端显示真实健康、等待、提交和失败状态

**Files:**

- Modify: `web/src/app/cmdb/types/autoDiscovery.ts`
- Modify: `web/src/app/cmdb/api/nodeMgmtSync.ts`
- Modify: `web/src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/nodeMgmtSyncDetail.tsx`
- Modify: `web/src/app/cmdb/locales/zh.json`
- Modify: `web/src/app/cmdb/locales/en.json`

**Step 1: 先扩充静态类型，让旧组件编译失败（RED）**

```typescript
export type NodeMgmtSyncStatus =
  | 'waiting_sync' | 'running' | 'submitted' | 'success'
  | 'partial_success' | 'blocked' | 'failed' | 'timeout';

export interface NodeMgmtSyncHealth {
  schedule_status: 'healthy' | 'reconciling' | 'degraded';
  node_config_status: 'healthy' | 'waiting_sync' | 'reconciling' | 'degraded' | 'disabled' | 'unknown';
  last_reconciled_at: string | null;
  reason_code: string;
  message: string;
}

export interface NodeMgmtSyncTask {
  // 保留现有字段
  health: NodeMgmtSyncHealth;
}
```

把组件中状态映射改为穷尽 `Record<NodeMgmtSyncStatus, BadgeStatus>`，在状态映射未补全时运行：

```bash
cd web
pnpm type-check
```

Expected: RED，TypeScript 报状态映射缺少 `waiting_sync/submitted/blocked/timeout` 或 task health 未处理。

**Step 2: 实现健康提示与空状态分流**

- 开关开但 `schedule_status=degraded`：顶部显示错误 Alert，不再用 `--` 暗示“只是还没运行”。
- `waiting_sync`：显示“等待首次同步完成后开始采集”。
- `submitted`：显示“已提交到区域采集任务，等待执行结果”，不能显示成功。
- `blocked/timeout/failed`：按 `reason_code` 使用本地化稳定文案；未知码使用通用脱敏 message。
- 真正无节点：显示“节点管理返回 0 个节点”；请求失败：显示“节点管理查询失败”；无接入点：显示“区域没有可用接入点”。
- 保存开关期间 disable switch；PUT 成功后使用服务端返回值覆盖本地状态，PUT 失败回滚本地显示。

**Step 3: 增加中英文文案并运行前端门禁（GREEN）**

```bash
cd web
pnpm lint
pnpm type-check
```

Expected: 两条命令退出码均为 0。

**Step 4: 提交**

```bash
git add src/app/cmdb/types/autoDiscovery.ts src/app/cmdb/api/nodeMgmtSync.ts 'src/app/cmdb/(pages)/assetManage/autoDiscovery/collection/profess/components/nodeMgmtSyncDetail.tsx' src/app/cmdb/locales/zh.json src/app/cmdb/locales/en.json
git commit -m "fix(cmdb): 展示节点同步真实健康与运行状态"
```

---

### Task 11: 回归完整链路、覆盖率和产品验收

**Files:**

- Modify when evidence changes: `docs/reviews/cmdb-functional-review-2026-07-14/09-node-sync.md`
- Verify: all files changed in Tasks 1–10

**Step 1: 运行节点同步完整后端测试集**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' \
  apps/cmdb/tests/test_node_mgmt_sync_models.py \
  apps/cmdb/tests/test_node_mgmt_sync_reconciler.py \
  apps/cmdb/tests/test_node_mgmt_sync_views.py \
  apps/cmdb/tests/test_node_mgmt_sync_helpers.py \
  apps/cmdb/tests/test_node_mgmt_sync_resilience.py \
  apps/cmdb/tests/test_node_mgmt_sync_persistence.py \
  apps/cmdb/tests/test_node_mgmt_sync_execution.py \
  apps/cmdb/tests/test_node_mgmt_sync_node_config.py \
  apps/cmdb/tests/test_node_mgmt_sync_collection.py \
  apps/cmdb/tests/test_reconcile_node_mgmt_sync_command.py \
  apps/node_mgmt/tests/test_b75_node_service.py \
  apps/core/tests/test_batch_init_command.py
```

Expected: 全部通过。

**Step 2: 运行覆盖率门禁**

```bash
cd server
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -o addopts='' \
  --cov=apps.cmdb.services.node_mgmt_sync_service \
  --cov=apps.cmdb.services.node_mgmt_sync_reconciler \
  --cov-report=term-missing \
  --cov-fail-under=90 \
  apps/cmdb/tests/test_node_mgmt_sync_*.py
```

Expected: 核心服务覆盖率 ≥90%。

**Step 3: 运行模块门禁**

```bash
cd server
make test
```

```bash
cd web
pnpm lint
pnpm type-check
```

Expected: 所有命令退出码为 0；若仓库既有无关失败，记录完整命令、失败测试和确认其与本 diff 无关的证据，不能把失败描述为通过。

**Step 4: 在真实开发环境按顺序验收用户场景**

1. 删除测试环境中的节点同步配置和对应 Beat 任务，首次打开抽屉；确认默认两开关为开、两条 Beat 任务存在、健康状态为 healthy，随后能产生 sync run。
2. 关闭自动同步和自动采集；确认两条 Beat 任务被删除、节点参数进入 disabled，刷新页面及重启服务后仍保持关闭。
3. 再次开启；确认两条 Beat 任务恢复，节点参数 delete→push 后变 healthy。
4. 人工删除一条 Beat 任务；刷新抽屉或等待恢复任务，确认自动修复并更新 `last_reconciled_at`。
5. 节点管理有数据：确认请求含系统身份，CMDB 新增/更新真实落库；节点管理返回 0、RPC 失败、无接入点分别显示不同状态。
6. 采集先于首次成功同步：确认 waiting_sync；同步成功后自动进入 submitted，只有所有区域子任务终态后父 run 才进入 success/partial_success/failed。
7. 使用仅 View 用户确认可读不可改；Execute 非管理员可改配置但不能触发全局 run；平台管理员可以手动运行。

**Step 5: 更新审计结论并最终提交**

仅在测试和真实验收证据支持时，将 F44–F51 对应项标为已解决或部分解决，并附测试文件名；不得只因代码已写就关闭发现。

```bash
git add docs/reviews/cmdb-functional-review-2026-07-14/09-node-sync.md
git commit -m "docs(cmdb): 更新节点同步修复验证证据"
```

---

## Completion Checklist

- [ ] 首次打开默认开启时会立即建立/修复同步与采集 PeriodicTask。
- [ ] 打开后关闭会删除 PeriodicTask 和节点参数，刷新及重启不反弹。
- [ ] 关闭后重新打开会恢复 PeriodicTask，并完成节点参数补偿下发。
- [ ] 节点管理后台查询显式使用系统身份，普通无权限查询仍 fail-close。
- [ ] 已有主机更新真实写入，计数与失败明细一致。
- [ ] 全局执行单活、可超时、可恢复，不会永久卡 running。
- [ ] 采集等待成功同步，submitted 不冒充 success，父状态由区域子任务聚合。
- [ ] GET/PUT/manual-run 权限符合 View/Execute/平台管理员边界。
- [ ] UI 区分等待、提交、空节点、查询失败、无接入点、阻塞和超时。
- [ ] 后端核心覆盖率、server 门禁、web lint/type-check 和真实验收全部留有证据。

## specs: 2026-07-16-node-management-sync-reconciliation-design.md

- 日期：2026-07-16
- 状态：已批准，待实施计划
- 范围：`server/apps/cmdb`、`server/apps/node_mgmt`、`web/src/app/cmdb`
- 关联问题：projectmem #0242；`CMDB-F44`–`CMDB-F51`

## 1. 背景与结论

节点管理已有数据，但 CMDB“节点管理同步”页面长期显示两个自动开关开启、最近同步/采集时间为空且发现数为 0。调查确认存在两个可独立触发现象的断点：

1. `NodeMgmtSyncConfig` 默认开启自动同步和自动采集，首次读取只创建配置行，不创建对应的 django-celery-beat `PeriodicTask`。页面因此显示“已开启”，实际没有调度。
2. 同步调用 `NodeMgmt.node_list` 时没有传权限上下文、组织范围或 `skip_permission=True`。Node Management 当前对这种调用 fail-closed，稳定返回空列表。

现有链路还存在权限、更新事实、父子任务状态、并发、资源预算和跨系统配置交付缺陷。批准方案采用“期望状态对账”：`NodeMgmtSyncConfig` 表达期望状态，Beat 周期任务和各区域节点采集配置表达实际状态，幂等 Reconciler 负责首次初始化、开关变化、部署重启和运行态漂移的收敛。

## 2. 目标与非目标

### 2.1 目标

- 首次打开页面时，默认开关与真实周期任务一致。
- 关闭、重新开启和重复切换均幂等，后端强制 `auto_collect_enabled => auto_sync_enabled`。
- 配置开启但周期任务或区域节点配置缺失时能够检测并恢复。
- Beat 系统执行和用户手工执行使用不同、明确的授权主体。
- 同步能够真实取得 Node Management 节点，并区分合法空源与授权/调用契约错误。
- 已有 CMDB 主机按真实字段差异更新，不再把未写入误报为更新成功。
- 自动采集等待有效同步结果；子任务投递不等于采集成功。
- 页面展示期望开关和实际健康状态，异常状态可行动。
- 新行为遵循 TDD，核心状态和授权逻辑覆盖率不低于 90%。

### 2.2 非目标

- 本次不重写通用 Celery、采集或 NATS 框架。
- 本次不建设通用工作流编排平台。
- 本次不引入审批、维护窗口或复杂报表。
- 不改变 Node Management 的 fail-closed 安全默认值。

## 3. 方案选择

### 3.1 备选方案

1. **最小热修**：首次创建配置时补建 Beat 任务，并为系统 RPC 增加 `skip_permission=True`。改动小，但不能修复任务漂移、采集抢跑和错误成功。
2. **期望状态对账（采用）**：以配置为期望状态，使用幂等 Reconciler 对账周期任务和区域节点配置，并补齐主体、前置条件、状态和可观测性。
3. **完整执行架构重构**：一次性引入租约、父子 execution、delivery、deadline 和补偿状态机。可靠性最高，但超出本次可控范围。

采用方案 2，并让运行与区域状态具备未来升级为方案 3 的稳定身份和代次字段。

## 4. 核心对象与职责

### 4.1 `NodeMgmtSyncConfig`

全局唯一的期望状态源。增加数据库可证明的 singleton 业务键，禁止并发首次访问创建多行。保存：

- 自动同步、自动采集及各自周期；
- 对账状态 `healthy | reconciling | degraded`；
- 最近对账时间和稳定错误码/脱敏摘要；
- 配置版本，用于拒绝旧请求覆盖新状态。

约束：自动采集开启时自动同步必须开启。关闭自动同步时，后端强制同时关闭自动采集，不能依赖前端联动。

### 4.2 `NodeMgmtSyncReconciler`

只负责把期望状态收敛为实际状态：

- 幂等创建、更新或删除同步/采集 `PeriodicTask`；
- 校验 task path、cron、enabled 状态，而非只判断名称存在；
- 对账各云区域隐藏 `CollectModels` 和 Node Management 节点配置；
- 对失败区域保留 generation、阶段、稳定错误码和重试状态；
- 返回结构化差异与修复结果，不直接拼接面向用户的原始异常。

触发点：首次配置创建、配置 PUT、配置 GET 健康检查、同步/采集执行前置检查、服务启动初始化命令。周期任务过期但没有任何运行记录时，页面按 `2 × interval + grace` 判定 `schedule_overdue`，从而暴露 Beat/Worker 不工作。

### 4.3 `NodeMgmtSyncRun`

表达一次可观察 execution，而不只是 UI 日志。状态集合：

- `waiting_sync`
- `running`
- `submitted`
- `success`
- `partial_success`
- `blocked`
- `failed`
- `timeout`

保存稳定 reason code、脱敏摘要、开始/投递/完成时间。`last_sync_at` 和 `last_collect_at` 只在定义明确的最终完成状态推进。

### 4.4 区域运行/交付状态

新增独立的 `NodeMgmtSyncRegionState`，让每个父运行按云区域保存稳定子 execution 身份、generation、接入点、实例数量、投递状态和实际终态；不得仅依赖可被并发覆盖的聚合 JSON 判断完成。节点配置 delete→push 同样按区域和 generation 持久化阶段，使 push 失败后可以从 `PUSH_PENDING/DEGRADED` 重试，旧 generation 不得覆盖新配置。

## 5. 开关与调度状态机

| 用户操作 | 期望同步 | 期望采集 | Reconciler 结果 |
|---|---:|---:|---|
| 首次打开 | 开 | 开 | 创建唯一配置和两个唯一周期任务；采集等待首次同步 |
| 关闭自动采集 | 开 | 关 | 保留同步任务，删除采集任务，停用区域采集配置 |
| 关闭自动同步 | 关 | 强制关 | 删除两个周期任务，停用区域采集配置 |
| 重新开启自动同步 | 开 | 仍为关 | 只恢复同步任务 |
| 再开启自动采集 | 开 | 开 | 恢复采集任务；无有效快照时先同步 |
| 配置开但周期任务丢失 | 按配置 | 按配置 | 标记漂移并幂等恢复 |
| 重复打开或重复切换 | 不变 | 不变 | 不产生重复配置、任务或节点下发 |

配置和 django-celery-beat 位于同一关系库时，在同一事务中完成期望状态及周期任务变更。Node Management 属于外部副作用，只能在数据库提交后按持久化 generation 交付和补偿，不能用数据库回滚假装撤销远端 delete/push。

## 6. 同步数据流

```text
Beat 系统主体 / 平台管理员手工主体
  -> NodeMgmt.node_list(明确授权上下文)
  -> 有界分页、去重与 deadline
  -> 非容器节点按云区域分组
  -> 查询各区域容器接入点
  -> CMDB host before/after 差异
  -> create / update / unchanged / failed
  -> 区域隐藏采集任务与节点配置期望状态
  -> NodeMgmtSyncRun 最终状态与 last_sync_at
```

### 6.1 主体与权限

- Beat 自动同步是可信系统作业，RPC 显式传 `skip_permission=True`。
- HTTP 手工全局同步/采集仅允许平台管理员，不得把普通用户提升为 `system`。
- 普通组织用户的展示数据按组织裁剪；不能读取其他组织 IP、运行明细或错误。
- 配置 GET 使用 View 权限；配置 PUT 使用配置管理权限，至少为 `auto_collection-Execute`。拒绝路径在进入 Service 前终止，确保零副作用。

### 6.2 节点与资产事实

- Node Management 合法返回 0 条时记录 `source_empty`。
- 权限上下文缺失、RPC 协议错误或调用失败不得归类为空源。
- 已有 host 必须比较 organization、OS、名称、node_id、cloud_name 等受模型约束字段。
- 无变化计 `unchanged`；有变化且统一实例更新链路成功才计 `updated`。
- 单节点失败不中断整批，但整次运行至少为 `partial_success`，并保存稳定节点级错误码。

### 6.3 资源边界

分页必须具备 max pages、max nodes、去重进度和整次 deadline。达到上限时 fail-closed，停止后续图写与节点配置下发。已有 host 查询按区域/IP 定向或一次有界加载，禁止每个区域重复全量扫描全部 host。

## 7. 采集数据流与状态真实性

采集前置条件：

- 最近同步存在有效最终状态；
- 至少存在一个区域隐藏采集任务；
- 区域任务存在实例和可用容器接入点。

处理规则：

- 缺同步结果：创建采集 run=`waiting_sync`，触发/等待同步。
- 同步失败：采集 run=`blocked`，reason=`sync_failed`。
- 无容器接入点：区域 reason=`no_access_point`，父运行按区域结果聚合。
- 同步和采集同一分钟触发：采集等待当前同步 generation，不能读取旧/空快照抢跑。
- `CollectModelService.exec_task` 成功投递只把区域和父运行推进到 `submitted`。
- 所有区域实际进入 SUCCESS/PARTIAL/ERROR/TIMEOUT 后，父运行才聚合成最终状态。
- `last_collect_at` 只在实际完成时更新；投递时间使用独立 `submitted_at`。

## 8. API 与页面契约

配置/展示响应除现有字段外包含：

- `schedule_status`: `healthy | reconciling | degraded`
- `sync_task_exists`
- `collect_task_exists`
- `collect_prerequisite_status`: `ready | waiting_sync | no_access_point`
- `last_reconciled_at`
- `reconcile_error`: 稳定错误码和脱敏摘要

页面同时展示期望开关与实际健康状态。`degraded`、`waiting_sync`、`blocked` 必须说明下一步动作。刷新按钮只刷新状态；若保留手工执行，使用独立按钮和平台管理员权限。页面不得把“任务已投递”展示为“采集成功”。

## 9. 错误与恢复

- Beat 对账失败：期望配置保留，健康状态为 `degraded`，后续启动、GET、PUT 或执行前检查继续重试。
- NodeMgmt RPC 失败：本次同步失败，不生成空快照，不推进成功时间。
- 单节点失败：记录脱敏错误并继续其他节点。
- 节点配置 delete 成功、push 失败：停留在可重试阶段，下一次 Reconciler 继续 push。
- 旧 generation 晚到：条件更新失败，不覆盖新状态。
- 错误只保存稳定错误码和脱敏摘要；禁止把 RPC 原始响应、连接串、凭据写入日志、数据库或 API。

## 10. TDD 与验收矩阵

### 10.1 首次打开

- 空数据库首次 GET 只创建一条 singleton 配置。
- 默认两个开关开启时创建两个正确且启用的 PeriodicTask。
- 连续 GET 和并发首次 GET 不产生重复配置或任务。
- Beat 创建失败时响应为 `degraded`，不能只显示开启。
- 首次采集先于同步时进入 `waiting_sync`。
- 系统 RPC 明确携带 `skip_permission=True` 并能取得真实 NodeService 测试数据。

### 10.2 关闭与重新开启

- 关闭采集只删除采集任务并保留同步任务。
- 关闭同步由后端强制关闭采集并删除两个任务。
- 直接提交“同步关、采集开”被拒绝或归一化为均关闭。
- 重复关闭无重复远端副作用。
- 重新开启同步只恢复同步任务；采集保持关闭。
- 再开启采集恢复采集任务和区域节点配置。
- 无同步快照时等待同步；同步失败时 `blocked(sync_failed)`。
- 配置为开启但 PeriodicTask 被删除时能够检测并恢复。
- delete/push 任一阶段失败后能按区域幂等重试。

### 10.3 数据、权限与状态

- 无权限上下文的 NodeService 保持 fail-closed；系统主体和用户主体分别验证。
- 平台管理员全局路径、普通组织裁剪路径和越权零写入均有测试。
- 新主机创建、已有主机真实更新、无变化 unchanged、单节点部分失败、重复同步幂等均验证最终数据库/图事实。
- 子任务拒绝不进入 executed；成功投递为 submitted；实际 SUCCESS/ERROR/TIMEOUT 聚合父状态。
- `last_collect_at` 仅在实际终态更新。
- 同步/采集竞跑、重复 callback、旧 generation 晚到均保持状态正确。

### 10.4 测试纪律与门禁

- 每个新增行为先运行旧实现并确认测试按预期 RED，再写最小实现。
- 使用真实 ORM 和 django-celery-beat 模型；只 Mock NodeMgmt、broker、图存储等不可控边界。
- 断言最终配置、PeriodicTask、运行状态和资产事实，不以“Mock 被调用”代替行为证明。
- Reconciler、状态转换、权限和 RPC 契约覆盖率不低于 90%；本次涉及模块总体不低于 75%。
- 定向测试通过后运行 CMDB 回归和 Server 模块门禁；Web 运行 `pnpm lint && pnpm type-check`。

## 11. 实施分层

1. **阻断修复**：首次调度一致性、开关后端约束、NodeMgmt 系统查询契约、配置权限、真实 host 更新。
2. **状态闭环**：采集前置同步、submitted/blocked/timeout、区域子 execution 和真实父终态。
3. **恢复与规模**：singleton/generation、启动和运行态 Reconciler、节点配置交付补偿、分页与 deadline 预算。
4. **页面闭环**：实际健康状态、可行动错误、组织裁剪和独立手工执行入口。

每一层独立完成 RED/GREEN、回归和覆盖率门禁后再进入下一层，避免把多个根因揉成一次不可验证的大改。

## 12. 已批准决策与待确认项

已批准：

- 采用期望状态对账，而不是只补首次创建或一次性完整重构。
- 首次打开、关闭、重新开启、重复操作和运行态漂移均属于必测契约。
- Beat 与用户主体分离；采集等待同步；submitted 不等于 success。
- 合法空源、权限/协议错误、无接入点、同步失败必须分别表达。
- 核心状态、授权和失败恢复采用真实行为测试与 TDD。

待确认项：无。
