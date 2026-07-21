# 监控接口性能优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保留现有响应与权限语义的前提下，完成最新主干尚未覆盖的三项监控接口性能优化。

**Architecture:** 上游已通过“仅 monitor 扫描插件语言 + ASGI worker 预热”解决语言冷请求，本计划不再实现聚合 JSON。剩余工作分别在 VictoriaMetrics 调用层复用相同步长响应、在 ORM 查询层加载对象类型，并在最终权限判断前用组织与显式实例授权构造安全候选集。

**Tech Stack:** Python 3.12、Django 4.2 ORM、Django REST Framework、pytest。

## Global Constraints

- 禁止原生 SQL，全部使用 Django ORM。
- 权限优化必须继续以 `check_instance_permission` 作为最终判断，不得扩大最终可见范围或漏掉合法实例。
- 新行为遵循 TDD；只修改相关文件并运行 server 定向测试。
- 最新主干的语言加载方案保持不变，其 15 项回归测试必须继续通过。

---

### Task 1: 复用相同步长的 VictoriaMetrics 响应

**Files:**
- Modify: `server/apps/monitor/tests/test_metrics_gap_detection.py`
- Modify: `server/apps/monitor/services/metrics.py:45-86`

**Interfaces:**
- Consumes: `Metrics.get_metrics_range(query, start, end, step, detect_gaps, collection_interval_seconds, max_gap_detection_points)`。
- Produces: 当 `step` 与 `f"{collection_interval}s"` 代表同一秒数时，断点检测直接读取首次 `query_range` 的结果。

- [x] **Step 1: Write the failing test** — 增加 `step="60s"`、采集间隔 `60` 的用例，断言 `query_range` 只调用一次且 `gaps` 正确。
- [x] **Step 2: Run test to verify it fails** — 运行 `uv run pytest apps/monitor/tests/test_metrics_gap_detection.py::<用例名> --no-cov -q`，预期实际调用两次。
- [x] **Step 3: Write minimal implementation** — 比较已解析的 `step_seconds` 与 `collection_interval`；相等时令 `detection_resp = resp`，否则保留细粒度二次查询。
- [x] **Step 4: Run test to verify it passes** — 运行该文件定向测试，预期全部通过。
- [x] **Step 5: Commit** — 仅暂存上述测试和实现文件，提交中文性能优化说明。

### Task 2: 消除监控对象类型 N+1

**Files:**
- Modify: `server/apps/monitor/tests/test_monitor_object_view_extra.py`
- Modify: `server/apps/monitor/views/monitor_object.py:25-38`

**Interfaces:**
- Consumes: `MonitorObjectSerializer.type_info` 对 `MonitorObject.type` 的访问。
- Produces: `MonitorObjectViewSet.get_queryset()` 返回带 `select_related("type")` 的 QuerySet，过滤语义不变。

- [x] **Step 1: Write the failing test** — 创建多个对象和不同类型，用 `CaptureQueriesContext` 比较 1 个与多个对象的列表 SQL 数，断言查询数恒定。
- [x] **Step 2: Run test to verify it fails** — 运行新增用例，预期多对象比单对象增加类型查询。
- [x] **Step 3: Write minimal implementation** — 在 `get_queryset()` 的基础 QuerySet 上增加 `select_related("type")`。
- [x] **Step 4: Run test to verify it passes** — 运行 `TestMonitorObjectList`，预期全部通过且查询数恒定。
- [x] **Step 5: Commit** — 仅暂存视图与对应测试，提交中文性能优化说明。

### Task 3: 缩小实例计数权限候选集

**Files:**
- Modify: `server/apps/monitor/tests/test_monitor_object_view_extra.py`
- Modify: `server/apps/monitor/views/monitor_object.py:90-132`

**Interfaces:**
- Consumes: `instance_permissions` 的 `all.team`、各对象的 `team` 与 `instance[].id`，以及 `cur_team`。
- Produces: `_build_instance_count_queryset(instance_permissions, cur_team)`；返回只含可能通过授权的未删除实例，并预取组织关系。

- [x] **Step 1: Write the failing tests** — 覆盖团队授权、显式实例授权、无候选 `.none()`，并断言无关实例不进入最终权限判断；同时验证接口计数结果与旧语义一致。
- [x] **Step 2: Run tests to verify they fail** — 运行新增测试，预期当前全表 QuerySet 会把无关实例送入权限判断。
- [x] **Step 3: Write minimal implementation** — 归一化候选团队和实例 ID，用 `Q(monitorinstanceorganization__organization__in=...) | Q(id__in=...)`、`distinct()` 构造候选；两者为空时返回 `.none()`，最终仍逐条调用 `check_instance_permission`。
- [x] **Step 4: Run tests to verify they pass** — 运行监控对象视图测试，预期权限矩阵与候选范围断言全部通过。
- [x] **Step 5: Commit** — 仅暂存视图与测试文件，提交中文性能优化说明。

### Task 4: 组合回归验证

**Files:**
- Verify: `server/apps/core/tests/utils/test_language_loader_v3.py`
- Verify: `server/apps/core/tests/test_asgi_preload.py`
- Verify: `server/apps/monitor/tests/test_metrics_gap_detection.py`
- Verify: `server/apps/monitor/tests/test_monitor_object_view_extra.py`

**Interfaces:**
- Consumes: Tasks 1–3 的实现和上游语言冷加载修复。
- Produces: 四项性能问题的最新状态与可重复测试证据。

- [x] **Step 1: Run focused suite** — 运行上述四个测试文件并保留通过数、耗时与失败输出。
- [x] **Step 2: Inspect diff** — 运行 `git diff --check` 和限定路径的 `git diff --stat`，确认无无关格式化。
- [x] **Step 3: Update design status** — 将上游已采用的语言方案和剩余三项实施结果回写设计文档，避免继续实施已过时的聚合 JSON 方案。
- [x] **Step 4: Commit** — 提交计划/设计状态更新，并报告未执行的全量门禁（如有）。
