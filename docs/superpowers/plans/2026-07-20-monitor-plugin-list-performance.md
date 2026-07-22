# 监控插件列表性能优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变监控插件列表接口任何外部行为的前提下，将 `monitor_plugin` 列表查询从 `3N + 1` 次 SQL 收敛为 2 次常量查询。

**Architecture:** 仅在 `MonitorPluginViewSet.list()` 的过滤后 queryset 上预取 `monitor_object` 多对多关系；`MonitorPluginSerializer.get_parent_monitor_object()` 遍历同一关系结果，命中预取缓存并沿用 `MonitorObject.Meta.ordering`。不改变 serializer 字段、过滤器、分页、权限、国际化、前端调用或数据库结构。

**Tech Stack:** Python 3.12、Django 4.2 ORM、Django REST Framework、django-filter、pytest、pytest-django。

## Global Constraints

- 接口 URL、请求参数、认证和权限行为必须保持不变。
- 响应外层结构、字段集合、字段类型、字段值和插件列表顺序必须保持不变。
- 空 `monitor_object_id` 继续返回全部插件；所有现有过滤语义保持不变。
- `parent_monitor_object` 必须返回 `MonitorObject.Meta.ordering`（`type__order, order, id`）下第一个父对象的 ID，不能改成最小 ID。
- 预取只作用于列表 action；创建、详情、更新、删除、导入、导出及模板 action 不增加预取。
- 不增加缓存、默认分页、数据库迁移、第三方依赖、轻量 serializer 或前端改动。
- 仅修改本计划列出的四个 Server 文件；不得顺手重构或全仓格式化。
- 新增/修改代码必须覆盖率不低于 75%，测试行为而非内部实现。
- 数据库访问只能使用 Django ORM，禁止原生 SQL。
- 修改任何文件前调用 projectmem `precheck_file(path)`；Issue #0053 的每次实现尝试后调用 `record_attempt`，验证成功后调用 `record_fix`。

## File Structure

- `server/apps/monitor/views/plugin.py`：列表过滤完成后批量预取插件关联的监控对象。
- `server/apps/monitor/serializers/plugin.py`：从关联对象的既有顺序中选择第一个父对象，复用预取缓存。
- `server/apps/monitor/tests/test_plugin_view.py`：锁定真实 HTTP 列表路径的响应语义和常量查询数。
- `server/apps/monitor/tests/test_plugin_serializer.py`：锁定多个父对象时沿用 `MonitorObject.Meta.ordering` 的兼容性语义。

---

### Task 1: 以 TDD 消除监控插件列表 N+1 查询

**Files:**
- Modify: `server/apps/monitor/views/plugin.py:49-52`
- Modify: `server/apps/monitor/serializers/plugin.py:64-76`
- Test: `server/apps/monitor/tests/test_plugin_view.py`
- Test: `server/apps/monitor/tests/test_plugin_serializer.py`

**Interfaces:**
- Consumes: `MonitorPluginViewSet.list(request, *args, **kwargs)`、`MonitorPluginSerializer.get_parent_monitor_object(obj)`、`MonitorObject.Meta.ordering`。
- Produces: 列表 action 使用预取后的 `QuerySet[MonitorPlugin]`；`get_parent_monitor_object(obj) -> int | None` 保持原签名和响应语义。

- [ ] **Step 1: 预检四个待修改文件并确认没有相关失败历史**

依次调用 projectmem：

```text
precheck_file("server/apps/monitor/views/plugin.py")
precheck_file("server/apps/monitor/serializers/plugin.py")
precheck_file("server/apps/monitor/tests/test_plugin_view.py")
precheck_file("server/apps/monitor/tests/test_plugin_serializer.py")
```

Expected: 四个文件均返回可安全修改，或先根据返回的历史警告调整本计划，不能跳过警告继续实施。

- [ ] **Step 2: 增加父对象默认排序的行为刻画测试**

在 `server/apps/monitor/tests/test_plugin_serializer.py` 的 `TestGetParentMonitorObject` 中增加：

```python
def test_returns_first_parent_using_monitor_object_default_ordering(self):
    lower_id_later = MonitorObject.objects.create(
        name="PSParentOrderedLater",
        level="base",
        order=200,
    )
    higher_id_earlier = MonitorObject.objects.create(
        name="PSParentOrderedEarlier",
        level="base",
        order=100,
    )
    plugin = MonitorPlugin.objects.create(name="PSPluginOrderedParents")
    plugin.monitor_object.add(lower_id_later, higher_id_earlier)

    assert MonitorPluginSerializer().get_parent_monitor_object(plugin) == higher_id_earlier.id
```

该测试应在优化前通过，用于证明兼容性基线不是“选择最小 ID”。

- [ ] **Step 3: 增加真实列表路径的常量查询数失败测试**

在 `server/apps/monitor/tests/test_plugin_view.py` 顶部增加：

```python
from django.db import connection
from django.test.utils import CaptureQueriesContext
```

在 `TestPluginList` 中先增加响应语义刻画测试：

```python
def test_list_preserves_related_object_order_and_parent_choice(self, api_client):
    lower_id_later = MonitorObject.objects.create(
        name="PVParentOrderedLater",
        level="base",
        order=200,
    )
    higher_id_earlier = MonitorObject.objects.create(
        name="PVParentOrderedEarlier",
        level="base",
        order=100,
    )
    child = MonitorObject.objects.create(
        name="PVChildOrderedFirst",
        level="derivative",
        parent=higher_id_earlier,
        order=50,
    )
    plugin = MonitorPlugin.objects.create(
        name="PVOrderingPlugin",
        template_type="builtin",
    )
    plugin.monitor_object.add(lower_id_later, higher_id_earlier, child)

    response = api_client.get(f"{BASE}/api/monitor_plugin/?name=PVOrderingPlugin")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert len(rows) == 1
    assert rows[0]["monitor_object"] == [child.id, higher_id_earlier.id, lower_id_later.id]
    assert rows[0]["parent_monitor_object"] == higher_id_earlier.id
```

该断言显式锁定本次优化可能影响的 `monitor_object` 顺序和 `parent_monitor_object` 值；已有 `test_list_marks_custom_and_display` 继续锁定展示字段与 `is_custom`。

随后增加常量查询数测试：

```python
def test_list_queries_remain_constant_for_multiple_plugins(self, api_client):
    parent = MonitorObject.objects.create(name="PVPerfParent", level="base")
    for index in range(4):
        plugin = MonitorPlugin.objects.create(
            name=f"PVPerfPlugin{index}",
            template_type="builtin",
        )
        plugin.monitor_object.add(parent)

    with CaptureQueriesContext(connection) as queries:
        response = api_client.get(
            f"{BASE}/api/monitor_plugin/?monitor_object_id=&name=PVPerfPlugin"
        )

    assert response.status_code == 200
    assert len(response.json()["data"]) == 4
    assert len(queries) == 2
```

测试通过完整 ViewSet、filter、serializer 和响应封装路径，并以唯一名称过滤隔离测试数据。

- [ ] **Step 4: 运行 RED 测试并确认只暴露 N+1 性能缺陷**

Run:

```bash
cd server
.venv/bin/pytest \
  apps/monitor/tests/test_plugin_serializer.py::TestGetParentMonitorObject::test_returns_first_parent_using_monitor_object_default_ordering \
  apps/monitor/tests/test_plugin_view.py::TestPluginList::test_list_preserves_related_object_order_and_parent_choice \
  apps/monitor/tests/test_plugin_view.py::TestPluginList::test_list_queries_remain_constant_for_multiple_plugins \
  -q
```

Expected:

- 两个响应/默认排序行为测试通过。
- 查询数量测试失败，当前实现对 4 个插件产生 13 次查询，而断言期望 2 次。
- 若失败原因是测试环境或数据库初始化，不得修改业务代码；先记录 `record_attempt(..., outcome="failed")` 并恢复测试环境。

- [ ] **Step 5: 在列表路径预取 `monitor_object`**

将 `server/apps/monitor/views/plugin.py` 中 `list()` 开头改为：

```python
def list(self, request, *args, **kwargs):
    queryset = self.filter_queryset(self.get_queryset()).prefetch_related("monitor_object")
    serializer = self.get_serializer(queryset, many=True)
    results = serializer.data
```

只改这一处 queryset；不要修改类级 `queryset`，避免影响其他 action。

- [ ] **Step 6: 让父对象计算复用关系缓存并保持默认排序**

将 `server/apps/monitor/serializers/plugin.py` 中 `get_parent_monitor_object()` 替换为：

```python
def get_parent_monitor_object(self, obj):
    """获取 MonitorObject 默认排序下的第一个父监控对象 ID。"""
    return next(
        (
            monitor_object.id
            for monitor_object in obj.monitor_object.all()
            if monitor_object.parent_id is None
        ),
        None,
    )
```

`obj.monitor_object.all()` 在列表路径命中预取缓存，且预取结果继承 `MonitorObject.Meta.ordering`；不要再次调用 `.filter()`、`.exists()`、`.first()` 或自行按 ID 排序。

- [ ] **Step 7: 运行 GREEN 测试并立即记录本次实现结果**

先运行：

```bash
cd server
.venv/bin/pytest \
  apps/monitor/tests/test_plugin_serializer.py::TestGetParentMonitorObject::test_returns_first_parent_using_monitor_object_default_ordering \
  apps/monitor/tests/test_plugin_view.py::TestPluginList::test_list_preserves_related_object_order_and_parent_choice \
  apps/monitor/tests/test_plugin_view.py::TestPluginList::test_list_queries_remain_constant_for_multiple_plugins \
  -q
```

Expected: `3 passed`，查询数量断言确认列表仅执行 2 次 SQL。

测试通过后立即调用：

```text
record_attempt(
  summary="monitor_plugin 列表预取 monitor_object，parent_monitor_object 改为遍历预取关系并保留模型默认排序",
  outcome="worked",
  location="server/apps/monitor/views/plugin.py; server/apps/monitor/serializers/plugin.py"
)
```

若任一测试失败，则将 `outcome` 改为 `failed` 并写明实际失败断言，然后回到根因分析，不得在同一尝试中叠加其他优化。

- [ ] **Step 8: 运行完整插件相关回归测试**

Run:

```bash
cd server
.venv/bin/pytest \
  apps/monitor/tests/test_plugin_view.py \
  apps/monitor/tests/test_plugin_serializer.py \
  apps/monitor/tests/test_plugin_permission.py \
  apps/monitor/tests/test_collect_detect_service.py \
  -q
```

Expected: 所有测试通过；覆盖报告中本次新增和修改的执行分支全部被命中，改动覆盖率高于 75%。

- [ ] **Step 9: 执行格式、静态和迁移门禁**

Run:

```bash
cd /Users/baiyufei/Documents/Codex/2026-06-01/new-chat/bk-lite
pre-commit run --config server/.pre-commit-config.yaml --files \
  server/apps/monitor/views/plugin.py \
  server/apps/monitor/serializers/plugin.py \
  server/apps/monitor/tests/test_plugin_view.py \
  server/apps/monitor/tests/test_plugin_serializer.py
cd server
.venv/bin/python manage.py makemigrations --check --dry-run
```

Expected:

- `pyupgrade`、`black`、`isort`、`flake8`、`check-migrate` 和 `check-requirements` 全部通过。
- `makemigrations --check --dry-run` 输出 `No changes detected`。

- [ ] **Step 10: 复测本地真实数据性能**

Run:

```bash
cd server
.venv/bin/python manage.py shell -c "import time; from django.db import connection; from django.test.utils import CaptureQueriesContext; from apps.monitor.models import MonitorPlugin; from apps.monitor.serializers.plugin import MonitorPluginSerializer; queryset = MonitorPlugin.objects.prefetch_related('monitor_object').all(); started = time.perf_counter(); context = CaptureQueriesContext(connection); context.__enter__(); data = MonitorPluginSerializer(queryset, many=True).data; context.__exit__(None, None, None); print({'rows': len(data), 'queries': len(context.captured_queries), 'seconds': round(time.perf_counter() - started, 3)})"
```

Expected: 当前 301 条本地数据输出 `queries: 2`，耗时显著低于优化前稳定态约 6 秒；绝对耗时仅记录，不作为容易受环境影响的硬断言。

- [ ] **Step 11: 运行 Server 全量门禁并处理既有阻断**

Run:

```bash
cd server
make test
```

Expected: 全量测试通过。若被与本次无关的既有应用配置、测试库占用或收集错误阻断，保存完整命令与首个错误，调用 `record_attempt(..., outcome="partial")` 记录阻断；本计划 Step 8 的聚焦回归必须全部通过，不能用既有阻断替代专项验证。

- [ ] **Step 12: 确认 diff 范围、关闭 Issue #0053 并提交**

Run:

```bash
cd /Users/baiyufei/Documents/Codex/2026-06-01/new-chat/bk-lite
git diff --check
git diff -- \
  server/apps/monitor/views/plugin.py \
  server/apps/monitor/serializers/plugin.py \
  server/apps/monitor/tests/test_plugin_view.py \
  server/apps/monitor/tests/test_plugin_serializer.py
```

Expected: diff 仅包含本计划四个文件，没有响应字段、过滤器、权限、分页或前端改动。

验证证据满足后调用：

```text
record_fix(
  issue_id="0053",
  summary="monitor_plugin 列表通过预取 monitor_object 并复用关系缓存，将 301 条数据的 SQL 从 904 次降至 2 次且插件相关回归通过",
  location="server/apps/monitor/views/plugin.py; server/apps/monitor/serializers/plugin.py"
)
```

提交：

```bash
git add \
  server/apps/monitor/views/plugin.py \
  server/apps/monitor/serializers/plugin.py \
  server/apps/monitor/tests/test_plugin_view.py \
  server/apps/monitor/tests/test_plugin_serializer.py
git commit -m "perf(monitor): 优化插件列表关联查询"
```
