# Historical Superpowers change: 2026-07-20-monitor-plugin-list-performance

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-20-monitor-plugin-list-performance.md

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

## specs: 2026-07-20-monitor-plugin-list-performance-design.md

## 背景

监控插件列表接口：

```text
GET /api/v1/monitor/api/monitor_plugin/?monitor_object_id=
```

由 Web 端通过 `/api/proxy/monitor/api/monitor_plugin` 转发。集成列表页初始进入“全部”视图时会传递空的 `monitor_object_id`，后端按现有契约返回全部插件，因此该请求不是异常调用，也不能通过拒绝空参数或强制分页规避。

本地数据库当前有 301 个插件。对接口的只读分析和 SQL 捕获结果如下：

| 场景 | 返回插件数 | SQL 数 | 观测耗时 |
|---|---:|---:|---:|
| 空 `monitor_object_id`，完整接口稳定态 | 301 | 904 | 约 6.06 秒 |
| 空 `monitor_object_id`，完整接口冷请求 | 301 | 904 | 约 10.43 秒 |
| `monitor_object_id=3` | 86 | 259 | 约 1.37 秒 |
| 预取关系并复用缓存的对照实验 | 301 | 2 | 约 0.13 秒 |

完整响应约 474 KB。Next.js 代理只负责透传请求和响应，不是主要耗时来源；主要瓶颈发生在 Django ORM 关系加载和 DRF 序列化阶段。

## 根因

`MonitorPluginSerializer` 使用 `fields = "__all__"`，其中 `monitor_object` 是多对多字段。列表 queryset 没有预取该关系，因此序列化每个插件时会查询一次关联对象。

同一 serializer 的 `parent_monitor_object` 字段又调用：

```python
parent_objects = obj.monitor_object.filter(parent__isnull=True)
if parent_objects.exists():
    return parent_objects.first().id
```

每个插件因此再产生一次 `exists()` 查询和一次 `first()` 查询。接口整体形成约 `3N + 1` 次 SQL；301 个插件对应 904 次 SQL。数据库往返次数随插件数量线性增长，是本次性能问题的根因。

## 目标

- 保持接口 URL、请求参数和认证权限行为不变。
- 保持响应外层结构、字段集合、字段类型、字段值和列表顺序不变。
- 保持空 `monitor_object_id` 返回全部插件的现有语义。
- 保持 `monitor_object_id`、`name`、`template_type`、`template_id` 的过滤语义不变。
- 保持 `display_name`、`display_description` 和 `is_custom` 的计算与国际化回退语义不变。
- 将列表查询的 SQL 数从随数据量增长的 `3N + 1` 收敛为常量，目标为 2～3 次。
- 不引入数据库迁移、新依赖或跨请求缓存。

## 非目标

- 不修改创建、更新、删除、导入、导出及模板相关接口。
- 不裁剪列表响应字段，不引入新的轻量 serializer。
- 不改变默认不分页的行为，也不要求前端增加 `page_size`。
- 不修改前端调用方式，不移除空查询参数。
- 不通过 Redis、进程缓存或 HTTP 缓存掩盖 ORM 查询问题。
- 不在本次变更中优化语言文件冷启动加载。

## 方案选择

### 采用：列表级关系预取 + serializer 复用关系结果

仅在 `MonitorPluginViewSet.list()` 的过滤后 queryset 上预取 `monitor_object`。这样不会让详情、创建、更新或删除路径承担额外查询。

`MonitorPluginSerializer.get_parent_monitor_object()` 改为遍历 `obj.monitor_object.all()` 得到的关联对象，并返回按 `MonitorObject.Meta.ordering` 排序后的第一个父对象 ID。列表路径会直接命中预取缓存；serializer 在其他路径单独使用时最多执行一次关系查询。

必须保留模型默认的 `type__order, order, id` 排序，不能简化成选择最小 ID。原实现的关联 queryset 继承 `MonitorObject.Meta.ordering`，因此 `.first()` 会返回该排序下的第一条记录；普通 `prefetch_related("monitor_object")` 同样按该默认顺序填充关系缓存。

### 不采用：轻量列表 serializer

轻量 serializer 能缩小约 474 KB 的响应，但当前列表被多个页面复用，裁剪字段容易破坏隐含调用契约。该优化可在未来完成调用方字段审计后独立实施。

### 不采用：默认分页或缓存

默认分页会改变“全部插件”页面的数据完整性及响应结构；跨请求缓存会增加失效、权限和国际化一致性风险。两者均不符合本次无功能影响约束。

## 数据流

优化后的请求流程：

1. ViewSet 获取基础 `MonitorPlugin` queryset。
2. 现有 `MonitorPluginFilter` 原样执行请求参数过滤。
3. 过滤后的 queryset 通过 `prefetch_related("monitor_object")` 批量加载插件及其监控对象关系。
4. DRF 序列化 `monitor_object` 时读取预取缓存。
5. `parent_monitor_object` 按预取列表的模型默认顺序筛选第一个 `parent_id is None` 的对象并返回其 ID；没有父对象时仍返回 `None`。
6. ViewSet 原样执行国际化名称、描述和 `is_custom` 补充逻辑。
7. `WebUtils.response_success()` 原样返回结果。

## 兼容性约束

以下行为必须由自动化测试锁定：

- 空参数、缺少参数和 `monitor_object_id=""` 的结果一致。
- 指定对象时只返回与该对象绑定的插件。
- 一个插件绑定多个对象时，`monitor_object` ID 集合与原实现一致。
- 同时存在多个父对象时，`parent_monitor_object` 仍取 `MonitorObject.Meta.ordering`（`type__order, order, id`）下的第一条记录。
- 仅绑定子对象或没有父对象时，`parent_monitor_object` 仍为 `None`。
- 返回插件的默认顺序不因预取发生变化。
- 中文、英文 locale 下的展示名称和描述保持原样。
- 自定义插件的 `display_name`、`display_description`、`is_custom` 保持原样。
- 详情与写操作继续使用原有 queryset 和 serializer 行为。

## 测试设计

### 查询数量回归

新增聚焦测试，创建多个插件并分别绑定父对象和子对象，通过真实 ViewSet 列表路径请求接口。使用 Django 查询捕获工具断言：

- 返回多个插件时 SQL 数保持常量，不随插件数线性增长。
- 目标查询数为 2～3 次；若测试环境中的公共认证或中间件增加固定查询，断言应隔离这些公共查询，不能放宽为随数据量增长的上限。

### 响应等价回归

构造包含以下形态的数据：

- 单父对象绑定；
- 父对象与子对象同时绑定；
- 多父对象绑定且 `order` 顺序与主键顺序相反；
- 仅子对象绑定；
- 内置插件与自定义 `api`、`pull`、`snmp` 插件。

对空参数和指定对象请求断言完整响应字段、值、顺序及父对象选择语义。测试关注外部行为，不依赖 serializer 内部实现。

### 回归门禁

至少执行：

```bash
cd server
.venv/bin/pytest apps/monitor/tests/test_plugin_view.py apps/monitor/tests/test_plugin_serializer.py -q
.venv/bin/python manage.py makemigrations --check --dry-run
cd ..
pre-commit run --config server/.pre-commit-config.yaml --files \
  server/apps/monitor/views/plugin.py \
  server/apps/monitor/serializers/plugin.py \
  server/apps/monitor/tests/test_plugin_view.py \
  server/apps/monitor/tests/test_plugin_serializer.py
```

再运行仓库中现有 monitor plugin 相关测试；若全量 `make test` 被已知环境或非 monitor 模块问题阻断，需记录完整阻断证据，同时保证本次聚焦回归全部通过。

## 性能验收

性能验收以确定性的 SQL 数为主要门禁，以本地耗时为辅助观察：

- 301 个插件的列表序列化 SQL 数由 904 次降至 2～3 次。
- 查询数不随插件数量线性增加。
- 本地同一数据集的稳定态耗时应显著低于优化前约 6 秒；对照实验约为 0.13 秒，但不把绝对时间写成容易受机器、数据库和冷缓存影响的单元测试断言。
- 完整响应大小允许保持约 474 KB，因为本次不修改字段契约。

## 风险与控制

| 风险 | 控制措施 |
|---|---|
| Python 侧选择父对象与原 `first()` 顺序不一致 | 复用预取列表的 `MonitorObject.Meta.ordering`，并用 `order` 与主键相反的多父对象测试锁定 |
| 预取意外影响其他 ViewSet action | 仅在 `list()` 的过滤后 queryset 上增加预取 |
| 测试只验证查询数而遗漏功能回归 | 同时增加完整响应等价测试 |
| 固定 SQL 数断言受认证公共查询干扰 | 使用强制认证或在 serializer/list 核心边界捕获查询 |
| 仅优化空参数而让指定对象仍有 N+1 | 查询数量测试同时覆盖空参数和指定对象 |

## 发布与回滚

本变更不涉及迁移、配置或前端发布依赖，可随常规 Server 版本发布。上线后比较该接口的响应耗时和数据库查询负载；若出现未被测试覆盖的响应差异，可直接回滚 ViewSet 预取和 serializer 关系读取两处改动，不涉及数据恢复。
