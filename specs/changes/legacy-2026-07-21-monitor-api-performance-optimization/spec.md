# Historical Superpowers change: 2026-07-21-monitor-api-performance-optimization

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-21-monitor-api-performance-optimization.md

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

## 实际验证范围

- [x] 语言加载、ASGI 预热、指标断点检测、监控对象视图四个相关测试文件。
- [x] 变更行覆盖率、Django system check、迁移检查、变更行格式检查、Flake8 E/W/C90、`git diff --check`。
- [ ] `cd server && make test`：本地测试配置的既有问题会在收集阶段产生未安装应用模型错误（projectmem #0100），本次未将其标记为通过。

## specs: 2026-07-21-monitor-api-performance-optimization-design.md

## 背景

监控页面存在两类明显慢请求：菜单与监控对象接口在冷启动阶段约 12 秒，多条 VictoriaMetrics `query_range` 请求约 1～3 秒。只读基准确认：

- `LanguageLoader` 首次加载监控中文翻译时会解析 289 个插件 YAML，约 2.58 MB，本地耗时 4.35～6.35 秒；热缓存后的 `monitor_object` 请求约 0.18 秒。
- `monitor_object` 在 47 个监控对象、3 个实例的本地数据集上执行 57 条 SQL，其中 46 条是读取 `MonitorObjectType` 的 N+1 查询。
- 开启断点检测且 `step` 等于 `collection_interval` 时，同一 PromQL、时间范围和步长会被串行查询两次。
- 实例数量统计会读取全部未删除实例及其组织关系，再逐条执行 Python 权限判断，成本随全局实例量增长。

## 目标

1. 保留 `LanguageLoader(app, lang)` 通用调用接口，同时消除普通应用误扫监控插件语言资源和监控请求冷启动解析大量 YAML 的问题。
2. 在不改变断点检测结果的前提下，消除相同步长的重复 VictoriaMetrics 查询。
3. 消除监控对象类型序列化的 N+1 SQL。
4. 在保持现有权限结果不变的前提下，缩小实例数量统计的数据库候选集。
5. 用行为测试和性能回归指标证明优化有效，不以缓存、权限或响应契约变化换取速度。

## 非目标

- 不调整监控页面一次展示哪些指标，也不改变前端懒加载和并发策略。
- 不合并不同 PromQL 为一个复杂查询。
- 不改变 `check_instance_permission` 的授权语义。
- 不引入 Redis、数据库翻译表或新的外部服务。
- 不处理本轮截图中的 Next.js 308 尾斜杠重定向和 HTTP 压缩；它们收益较小，可另行优化。

## 方案选择

### 方案 A：仅让 monitor 扫描插件 YAML，并在 ASGI worker 启动时预热

普通应用不再受影响；monitor 插件翻译按语言和插件目录共享进程缓存，并在每个 ASGI worker 启动时预热，使扫描成本不落在首个业务请求上。该方案保持 `LanguageLoader` 通用入口和现有 YAML 资源格式，不引入生成文件及额外启动依赖。

### 方案 B：生成聚合 JSON，运行时兼容回退

部署初始化阶段将插件语言 YAML 合并为每种语言一个 JSON。该方案能进一步降低 worker 初始化耗时，但会新增生成文件、版本兼容和初始化失败处理；最新主干已采用方案 A，因此本轮不重复引入该机制。

### 方案 C：翻译进入数据库或 Redis

可以跨进程共享，但会引入部署依赖、缓存失效和数据迁移问题，超出本次性能优化需要。

采用方案 A。该方案已由上游提交 `14c8f3e58` 实现并通过专项测试，本轮直接复用。

## 设计

### 1. 通用语言加载与 worker 预热

`LanguageLoader` 继续负责三类来源的合并：应用基础翻译、应用专属扩展翻译、企业覆盖。普通应用只加载自己的基础与企业目录；只有 `app == "monitor"` 时才加载监控插件翻译。

插件翻译继续复用现有插件发现顺序和深度合并规则，但使用 `(lang, builtin_root, enterprise_root)` 作为共享缓存键，避免同一 worker 内重复扫描。`server/asgi.py` 在 Django application 创建后执行 `preload_language_cache(apps=["monitor"])`，提前加载两种支持语言；业务请求继续使用 `(app, lang)` 应用级缓存，调用方无需改变。

单个插件语言文件缺失或解析失败时记录 warning/error 并继续加载其他插件，不因非关键翻译资源阻断业务请求。测试直接调用 `LanguageLoader` 时不会经过 ASGI 预热，因此仍可观察到 monitor 原始冷扫描成本；该行为不代表生产请求缓存未生效。

### 2. VictoriaMetrics 相同步长结果复用

`Metrics.get_metrics_range` 仍先执行展示数据查询。开启断点检测后：

- 若 `parse_step_to_seconds(step) == collection_interval`，直接使用首次响应中的原始 `result` 计算断点。
- 若两者不同，继续以采集间隔发起第二次精细查询。
- 断点检测必须发生在 `fill_missing_points` 之前，确保只分析 VictoriaMetrics 返回的真实点，而不是服务端补点。
- 查询失败、点数上限和非法采集间隔的现有处理保持不变。

该优化在截图中的 10 秒步长场景以及默认短时间窗口中，可将每个图表的上游查询从两次降为一次。

### 3. 监控对象类型关联预取

`MonitorObjectViewSet` 的基础 QuerySet 增加 `select_related("type")`。序列化器继续通过 `type_info` 输出相同字段，模型默认排序 `type__order、order、id`、过滤条件、分页和国际化逻辑均不改变。

测试不只断言总查询数，还必须确认对象数量增加时 `MonitorObjectType` 查询数不随对象数量线性增长。

### 4. 权限安全的实例数量候选集

继续使用 `check_instance_permission` 作为最终授权判断。优化仅在它之前构造不会漏掉合法实例的安全候选集。

候选组织 ID 是以下集合的并集：

- `cur_team`；
- `permissions["all"]["team"]`；
- 每个对象权限条目中的 `team`。

候选显式实例 ID 是所有对象权限条目 `instance[].id` 的并集。数据库候选条件为：

```text
is_deleted = false
AND (
  organizations.organization IN candidate_team_ids
  OR id IN candidate_instance_ids
)
```

查询使用 Django ORM、`distinct()` 和定向字段/关系预取，不使用原生 SQL。得到候选实例后，仍把真实组织集合、对象 ID、实例 ID、完整权限数据和 `cur_team` 传给 `check_instance_permission`；只有最终判断通过才计入对应监控对象。

若候选组织和显式实例集合都为空，QuerySet 直接使用 `.none()`，禁止空 `Q()` 退化为全表扫描。

这一设计保持以下场景不变：

- 超级管理员仅在当前授权组织范围内计数；
- 对象没有专属规则时按 `cur_team` 判断；
- 对象团队规则授权；
- 显式实例授权，即使实例不属于普通团队候选也不会被漏掉；
- 无组织且无显式授权的实例继续不可见；
- 非规范或空权限结果继续 fail-closed。

## 错误处理与可观测性

- 插件语言文件缺失或解析失败继续记录文件位置与异常类型，不记录翻译正文，并允许其他翻译继续加载。
- VictoriaMetrics 调用异常继续沿用现有超时和请求异常处理。
- 权限候选集解析遇到未知结构时不扩大范围；无法识别的 ID 被忽略，最终仍由现有权限函数决定。
- 现有 `RequestTimingMiddleware` 继续记录慢接口；性能验收同时记录冷、热耗时和 SQL/上游调用数。

## 测试策略

所有生产代码按 TDD 实现，先观察回归测试在旧实现上失败。

### 语言加载

- 普通 app 不调用插件加载路径。
- 同一语言的插件翻译只发现一次并共享缓存。
- ASGI worker 创建 application 后预热 monitor 语言缓存。
- 内置与企业插件覆盖顺序及缺失文件容错保持一致。

### VictoriaMetrics

- `step` 与采集间隔相同时 `query_range` 只调用一次，断点结果正确。
- 步长不同时仍调用两次，第二次使用采集间隔。
- 点数超限、关闭断点检测和非法间隔行为不变。

### ORM 与权限

- 多个对象共享或使用不同类型时不出现类型 N+1。
- 管理员团队、默认当前团队、对象团队、显式实例、拒绝路径分别覆盖。
- 优化后的实例计数与逐条全量基准算法对同一 fixture 结果一致。
- 候选 ORM 不读取权限范围外的大量实例。

## 验收标准

1. 普通应用首次 `LanguageLoader` 不访问监控插件目录；实测 `core`、`system_mgmt` 冷加载约 6～8 ms。
2. 正常 ASGI 请求在 worker 预热后命中 monitor 语言缓存；相关语言与 ASGI 预热专项测试全部通过。
3. 47 个对象 fixture 下，对象列表 SQL 数不再随对象数量增加；类型关联只随主查询一次读取。
4. 相同步长断点检测的 VictoriaMetrics 调用数由 2 降为 1，响应数据与优化前一致。
5. 实例统计在全部权限 fixture 上与旧算法结果一致，并且数据库候选不包含无关组织且未被显式授权的实例。
6. 相关专项测试、变更行覆盖率、格式/静态检查和迁移检查通过；全量 Server 门禁的执行状态单独如实记录。

## 验证状态

- 四个相关测试文件的专项回归已通过；实例权限部分还包含严格团队 ID 边界测试，以及与旧全量扫描算法的同 fixture 差分测试。
- 变更行覆盖率、Django system check、迁移检查、变更行格式检查、Flake8 E/W/C90 检查和 `git diff --check` 已通过。
- `cd server && make test` 未作为本次完成依据：当前本地测试配置只启用了部分应用，全量收集会因未安装应用模型产生既有错误（projectmem #0100）。因此本文不宣称全量 Server 回归已通过。

## 发布与回滚

部署顺序不变：迁移与 `batch_init` 完成后启动 Uvicorn。每个 worker 自行预热进程内缓存，不生成共享文件、不写运行目录，也不改变现有翻译资源发布方式。

回滚代码后，`LanguageLoader` 恢复请求首次访问时扫描 YAML；无需清理新增文件或迁移数据。
