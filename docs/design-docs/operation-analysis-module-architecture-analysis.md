# OperationAnalysis 模块架构与代码结构分析

> 分析日期：2026-08-21
> 分析范围：`server/apps/operation_analysis/`，以及直接相连的 NATS、MySQL/PostgreSQL、REST/Prometheus、WeOps、Transform Runner、MinIO、Chromium、SMTP 和 Celery/Beat 边界。
> 分析方式：按“画布—数据源—查询执行—分享—订阅报告—制品与投递”完整模块分析，不以单个 tech-debt 或大文件为拆分依据。

## 1. 结论摘要

OperationAnalysis 不是单纯的可视化 CRUD，而是一个可配置查询与报告执行平台：Dashboard、Screen、Topology、Report 等画布在 JSON 中声明 Widget 和数据源；DataSource/Connection 把配置编译为 NATS、数据库、REST、Prometheus、Excel 或 WeOps 调用；分享和报告渲染会复用同一取数路径；订阅执行再把结果渲染成 PDF 并通过 SMTP 投递。

当前模块已经形成一批值得保留的可靠性基础：Connection 凭据加密和响应脱敏；REST/Prometheus 的 SSRF 防护与响应体限制；Transform Runner 的进程隔离；Excel candidate/success generation；订阅输入与渲染快照不可变；Execution 状态 CAS；一次性、限 scope 的 Render Token；分享会话、声明式参数和拓扑目标白名单。这些机制说明模块正在从页面后端走向运行平台，优化时应深化而非绕开它们。

最重要的问题是“数据源”同时充当了配置、权限、任意执行入口和容量边界，却没有统一的只读能力协议：

- NATS 数据源可从配置选择方法名，最终动态调用客户端方法；少量黑名单不能证明其只读，也不能约束参数、成本与返回结构。
- 数据库查询用 `SELECT` 正则近似只读沙箱，但 `SELECT` 仍可能执行副作用函数、长时间函数或超大扫描；连接只有 connect timeout，没有 statement timeout 和共享查询预算。
- 数据库与 WeOps 目标没有复用统一 egress policy；可配置地址可能扩大内网访问面。
- 报告快照冻结了画布与 Widget 清单，却仍在渲染时读取当前 DataSource/Connection/query/transform/Excel generation；同一 Execution 重试可能生成不同内容。
- Execution、Excel materialization 都缺少带 token 的 lease/fencing；过期 worker 即使状态被回收，仍可能继续浏览器、MinIO 或 SMTP 副作用。

短期不建议拆微服务。先在同一 Django app 内建立 `DataCapabilityRegistry`、`ReadOnlyQueryPlanCompiler`、`ConnectorBudgetGateway`、`CanvasDependencyProjection`、`ExecutionBundle` 和 token 化 `WorkItem/EffectOutbox`，把能力、授权、成本、快照与副作用收敛为少数可审计接口。

## 2. 模块规模与职责边界

本次统计生产 Python 约 24,829 行（排除 migrations/tests），测试目录有 98 个 Python 文件。最大文件超过 1,100 行，但更关键的是画布、数据源、分享、报告、导入导出、Excel 和网络拓扑多条变化轴共享 JSON 引用与执行器，不能只按文件尺寸切分。

| 能力域 | 当前实现 | 应拥有的事实 |
|---|---|---|
| 画布与目录 | Dashboard、Screen、Topology、Architecture、Report、Directory | typed canvas revision、Widget 声明、依赖投影 |
| 数据源控制面 | DataSource、DataConnection、groups、query/transform config | 只读 capability、连接 scope、配置 revision |
| 查询运行时 | NATS、DB、REST、Prom、Excel、WeOps、Runner | QueryPlan、预算、超时、字节数、截断与审计 |
| 分享 | share principal、session、参数/数据源/拓扑白名单 | 固定资源 revision、声明交互与 scope digest |
| 订阅报告 | Subscription、Execution、Input/Render Snapshot、Chromium | ScheduleRun、ExecutionBundle、StepWorkItem |
| 制品与副作用 | PDF、MinIO、SMTP、Excel generation | artifact digest、effect intent、token、outcome |
| 导入导出 | schema、precheck、placeholder、apply | 依赖图、冲突策略、重放结果 |

模块边界应围绕“受 scope 约束的只读查询计划”和“可重放执行包”建立，而不是继续让 View、serializer、task 各自解释 JSON。

## 3. 现状架构图

- [OperationAnalysis 现状架构（Archify HTML）](./operation-analysis-current.architecture.html)
- [OperationAnalysis 现状架构规格](./operation-analysis-current.architecture.json)
- [OperationAnalysis 现状架构静态图](./operation-analysis-current.architecture.light.png)

主路径可以概括为：

```text
Editor / Viewer / Share → Feature + Team Access → Canvas JSON → DataSource / Connection
                                                              └→ Connector Executors → External Data Systems

Beat → Subscription Scanner → Execution Orchestrator → Input / Render Snapshot
                                                    └→ Chromium → 当前 DataSource → PDF → SMTP
```

两条路径共享 DataSource，却没有共享一个显式的 capability registry、query plan、运行预算和 revision digest，这是后续维护及并发放大的根源。

## 4. 应保留并深化的设计

### 4.1 凭据与外部 HTTP 防线已经有正确基础

DataConnection 对敏感配置做加密与脱敏，并校验数据源组织范围不超出连接范围；REST/Prometheus 执行器使用安全请求机制和响应上限。后续数据库、WeOps、NATS gateway 也应进入同一 egress 与预算协议，而不是降低现有边界。

### 4.2 Transform 与 Excel 已具备隔离和 generation 思维

自定义转换通过独立 Runner 执行，并限制时间和结果行数；Excel 使用 candidate/success slot 和 generation，成功后原子切换。这个方向正确。缺口是 PROCESSING claim 没有 lease token/heartbeat/reaper，而不是需要回退到同步上传即覆盖。

### 4.3 报告的不可变事实与一次性令牌值得保留

Render Snapshot 禁止更新，保存画布、筛选和 Widget manifest，见 [subscription_models.py:651](../../server/apps/operation_analysis/models/subscription_models.py#L651)；Render Token 绑定 execution、snapshot、attempt 和允许的数据源/拓扑接口。Execution 还保存投递结果并以终态 CAS 收敛。这些是 `ExecutionBundle`、`StepWorkItem` 与 `EffectOutbox` 的直接基础。

### 4.4 分享边界比普通公开链接更强

分享通过 session-bound principal 重新校验分享者、资源组织和访客会话；只允许声明过的数据源、固定参数和拓扑目标。后续应让分享、普通查看和报告渲染共用同一个 QueryPlan 编译器，不能为追求复用而绕过分享边界。

## 5. 数据能力与安全边界

### P0：NATS 配置可选择动态方法，黑名单不能证明只读

NATS 数据源把 namespace/path 映射为客户端属性并调用；本地 overlay 也使用 `AppClient.run(path, **params)`，见 [get_nats_source_data.py:127](../../server/apps/operation_analysis/common/get_nats_source_data.py#L127)。这意味着数据源编辑权限实际上可能获得“调用已注册 NATS 方法”的能力。只禁止少数已知危险 route，无法覆盖未来新增的写接口、高成本接口或参数变化。

应引入白名单 `DataCapabilityRegistry`：每个能力使用稳定 ID，注册 handler、只读声明、参数 schema、组织权限、成本函数、最大返回字节和输出 schema。DataSource 只能引用 registry ID，不能保存 Python/NATS 方法名。新增 NATS 接口默认不可用于可视化，必须显式通过只读能力评审和契约测试。

### P0：`SELECT` 前缀不是数据库只读沙箱

数据库预览只检查单语句且以 `SELECT` 开头，已有 LIMIT 时原样接受，见 [database.py:11](../../server/apps/operation_analysis/services/datasource_preview/database.py#L11)。`SELECT pg_sleep(...)`、副作用函数、MySQL `INTO OUTFILE` 或超大扫描仍可能消耗资源或改变外部状态；`fetchmany(1000)` 只限制客户端读取，不限制数据库执行。执行器每次创建 engine，仅配置 5 秒 connect timeout，缺少 statement timeout、只读 transaction、连接池策略和响应字节上限，见 [database.py:81](../../server/apps/operation_analysis/services/datasource_preview/database.py#L81)。

短期必须使用专用只读数据库账号、数据库侧 read-only transaction、dialect statement timeout、结果字节/列/单元格限制和 `NullPool`/明确 dispose；SQL 先解析为 AST，禁止文件、锁、过程、危险函数和多语句。即使 AST 通过，也必须经过团队/连接级预算。产品上优先提供受控 dataset/table/query-template，减少自由 SQL 面。

### P0：数据库与 WeOps 没有统一 egress policy

WeOps base URL 只强制 http(s) scheme，见 [models.py:248](../../server/apps/operation_analysis/models/models.py#L248)；Adapter 随后通过普通 HTTP client 请求，见 [weops_adapter.py:251](../../server/apps/operation_analysis/services/network_topology/weops_adapter.py#L251)。数据库 host 同样直接进入连接 URL。两者都可能访问部署网络中的敏感地址。

建立统一 `EgressPolicy`：解析并固定 DNS/IP、阻止 loopback/link-local/metadata/private ranges（除明确登记的受信 connector）、禁止重定向逃逸、记录 resolved endpoint digest。数据库连接应优先引用管理员登记的 Connection，而不是让普通数据源配置任意 host。

## 6. 订阅报告执行数据流

- [OperationAnalysis 报告执行数据流（Archify HTML）](./operation-analysis-report.dataflow.html)
- [OperationAnalysis 报告执行数据流规格](./operation-analysis-report.dataflow.json)
- [OperationAnalysis 报告执行数据流静态图](./operation-analysis-report.dataflow.light.png)

### P1：快照冻结画布，不冻结查询语义

Render Snapshot 从 adapter 提取画布字段并不可变创建，见 [render_snapshot_service.py:16](../../server/apps/operation_analysis/services/render_snapshot_service.py#L16)，但模型只保存 view_sets、filters、other 和 widget_manifest，没有冻结 DataSource/Connection/query_config/transform_config、connector endpoint digest 或 Excel generation。同一 Execution 在第一次失败后若数据源被编辑或删除，重试会按当前配置重新取数，内容和安全边界都可能变化。

创建 `ExecutionBundle`，至少冻结：resource revision、scope digest、每个 Widget 的 QueryPlan/digest、DataSource/Connection revision、resolved endpoint digest、transform script digest、Excel generation、render schema 和预算。需要严格可重放的报告可进一步保存查询结果制品 digest；不要求冻结实时结果时，也必须保证同一 execution 使用相同计划并显式记录事实时间。

### P1：Execution claim 没有 fencing，重试在同一任务内紧循环

Orchestrator 要求 Execution 已处于 RUNNING，但没有 worker claim token/lease；失败后在 `while True` 中立即开始下一 attempt，最多 3 次，没有持久 `retry_at` 和退避，见 [execution_orchestrator.py:406](../../server/apps/operation_analysis/services/execution_orchestrator.py#L406)。超时扫尾可以收敛数据库状态，却不能阻止旧 worker 继续 Chromium 或 SMTP。紧循环还会让一个失败报告连续占据 render worker。

把阶段拆为持久 `ExecutionStepWorkItem(execution, step, token, lease_until, heartbeat, attempt, retry_at)`。每个外部动作前后都验证 token；超时 worker 失去 claim 后不能上传、投递或写回。重试由调度器按 retry_at 重新领取，而不是在一个 Celery task 内自旋。浏览器使用显式 render slot，SMTP 通过带幂等键的 DeliveryOutbox 执行。

### P1：查询扇出没有共享预算

浏览器会为每个 Widget 走实时 DataSource 查询；普通 Viewer、Share 和 Report Render 也分别触发同一执行器。当前限制多分散在单请求内，没有 team/connector/execution 维度的 query count、bytes、duration、并发和重试预算。多个打开页面、公开分享和批量订阅会对同一外部系统形成乘法放大。

所有入口必须先编译 `ScopedQueryPlan`，再通过 `ConnectorBudgetGateway`。网关按团队、数据源、连接、run 分配并发与 token bucket，支持相同 plan 的短 TTL 去重/cache；响应必须携带 effective window、truncated、cost 和 source revision。

## 7. 画布依赖、分享与导入导出

### P1：Canvas JSON 引用数据源但没有依赖投影

Canvas 在 JSON 内保存 datasource id；模块能够构建 widget manifest 和分享白名单，但没有持久、可查询的依赖索引。删除数据源时只检查权限后直接 `instance.delete()`，见 [datasource_view.py:1125](../../server/apps/operation_analysis/views/datasource_view.py#L1125)，会静默破坏画布、分享和订阅报告。缩小 Connection/DataSource groups 也可能让已有资源在运行期突然失败。

建立 `CanvasDependencyProjection(resource_type, resource_id, resource_revision, dependency_type, dependency_id, usage_path)`。画布保存、导入和发布在同一事务更新投影；DataSource/Connection 删除、禁用或缩小 scope 前返回影响画布、分享和订阅清单，并要求迁移、替换或显式强制。运行时仍校验真实 scope，投影用于影响分析而非替代授权。

### P1：JSON schema 在多个流程中被重复解释

普通查看、分享、报告、导入导出、网络拓扑分别遍历 view_sets、filters、datasource IDs 和 named option datasources。新增 Widget 或交互字段时，任一遍历器遗漏都可能造成依赖漏报、分享越权或报告渲染失败。

将 Canvas JSON 迁移为 typed aggregate：`CanvasDocument` 只负责版本化结构，`CanvasCompiler` 一次产生 dependency projection、share interaction manifest、report widget manifest 与 QueryPlan 输入。导入导出使用同一 parser/validator，并明确 schema version 与升级器；禁止各 service 维护自己的 JSON 路径知识。

## 8. Excel、网络拓扑与容量

### P1：Excel PROCESSING 无 lease/reaper

Excel materializer 用条件更新把 PENDING 改成 PROCESSING，见 [materializer.py:42](../../server/apps/operation_analysis/services/excel_materialize/materializer.py#L42)，但没有 token、claimed_at、heartbeat 或 lease。补投任务只扫描长时间停留的 PENDING，见 [tasks.py:156](../../server/apps/operation_analysis/tasks/tasks.py#L156)；worker 在 PROCESSING 后退出时，slot 可永久卡住。

复用统一 WorkItem 协议，按 token claim，上传与转换期间 heartbeat，reaper 将过期 PROCESSING 变回可重试或失败终态。promotion 必须校验 token 与 candidate generation，旧 worker 不得覆盖新 generation。

### P1：网络拓扑批量指标和外部调用缺少硬成本边界

网络拓扑从 Canvas JSON 组装节点、接口和 metric 请求，WeOps Adapter 可重试外部请求，但缺少统一最大节点数、metric values 数、总请求数和响应字节预算。大画布或恶意配置会把一次交互放大为大批外部调用，并与报告渲染并发竞争。

保存画布时计算 topology cost；运行时按节点/指标分区、限制总字节和 deadline，返回部分结果与截断原因。WeOps 调用进入同一 ConnectorBudgetGateway，不在 adapter 内形成独立容量孤岛。

### P2：外部制品需要一致的 intent/GC 协议

Excel、PDF 和导入文件在数据库事务与对象/共享文件系统之间存在补偿窗口。以内容 digest 和稳定 artifact key 创建制品，数据库只保存 artifact intent/reference；上传成功后 token 条件提交，周期 GC 对账无引用对象。不要在行锁事务内等待 MinIO、Chromium 或 SMTP。

## 9. 不合理设计要素与优先级

| 优先级 | 设计要素 | 影响 | 优化方向 |
|---|---|---|---|
| P0 | NATS 数据源可动态选择方法名 | 数据源编辑能力可能升级为写操作或高成本 RPC | DataCapabilityRegistry 白名单 + 参数/权限/成本/输出契约 |
| P0 | `SELECT` 正则近似只读，无 statement/byte/cost 限制 | 副作用函数、长查询、数据库容量耗尽 | 只读账号/事务 + SQL AST + statement timeout + shared budget |
| P0 | DB/WeOps 可配置目标未统一 egress | SSRF/内网探测与敏感服务访问面 | 管理员登记 connector + DNS/IP pinning + redirect policy |
| P1 | Canvas JSON 无规范化依赖索引，数据源可直接删除 | 画布、分享、订阅静默损坏，scope 缩小不可评估 | typed Canvas + CanvasDependencyProjection + impact gate |
| P1 | Render Snapshot 不冻结查询计划和 generation | 同一 Execution 重试内容、端点和脚本可能漂移 | ExecutionBundle + plan/config/endpoint/generation digest |
| P1 | Execution 无 token lease；任务内同步重试 | 陈旧 worker 继续副作用，单任务长期占用浏览器 worker | StepWorkItem + fencing + retry_at + render slots |
| P1 | Excel PROCESSING 无 reaper | worker 崩溃后永久卡住，需人工修复 | token/lease/heartbeat + stale reaper |
| P1 | Viewer/Share/Render 查询无共享预算 | 并发用户和订阅形成外部请求乘法放大 | ScopedQueryPlan + ConnectorBudgetGateway + dedupe/cache |
| P1 | 网络拓扑节点/指标批量成本无总上限 | WeOps 请求和响应规模不可预测 | 保存期 cost + 分区 + deadline/bytes/truncation |
| P1 | 多个 service 重复解释 Canvas JSON | 新 Widget 容易漏授权、漏依赖或报告不兼容 | 单一 CanvasCompiler 产出各类 manifest |
| P2 | 制品外部 I/O 缺少统一 intent/GC | 孤儿对象、长事务和重试对账复杂 | Artifact intent + digest key + token commit + GC |

## 10. 分阶段优化路线

### 短期：0—2 个迭代

1. 停止新增可由配置任意指定的 NATS path；建立首批只读 capability 白名单并迁移高频内置数据源；
2. 数据库连接强制只读账号/事务、statement timeout、结果字节上限和管理员登记 endpoint；WeOps/DB 接入统一 egress policy；
3. 数据源删除与 groups 缩小增加 Canvas/Share/Subscription 影响检查，先阻断静默破坏；
4. 报告快照补充 DataSource/Connection/query/transform/Excel generation digest，重试检测 revision 漂移并进入明确终态；
5. Execution 与 Excel claim 增加 token、lease、heartbeat 和 stale reaper；报告重试改为持久 retry_at；
6. 给 viewer/share/render、网络拓扑和各 connector 增加团队级并发、请求数、时间和字节硬预算。

### 中期：2—5 个迭代

1. 建立 `DataCapabilityRegistry + ReadOnlyQueryPlanCompiler`，统一 NATS/DB/REST/Prom/Excel/WeOps 的参数、scope、成本和输出；
2. 建立 `CanvasAggregate + CanvasDependencyProjection`，由同一 Compiler 产生依赖、分享和报告 manifest；
3. 建立 `ExecutionBundle + ExecutionStepWorkItem`，浏览器、查询、制品和投递分别使用可恢复步骤；
4. 建立 `ConnectorBudgetGateway`，提供公平调度、共享 deadline、短 TTL dedupe/cache 和统一审计；
5. 将 PDF/Excel/SMTP 统一为 Artifact/Effect intent，所有完成写回使用 fencing token。

### 长期：5 个迭代以后

1. Canvas revision、scope digest、query plan digest、connector endpoint digest、ExecutionBundle、artifact digest 和 delivery outcome 形成可重放审计链；
2. 导入导出、分享、报告和网络拓扑只依赖公开 typed port，不再直接遍历内部 JSON；
3. 只有当 Chromium、connector runtime 或 topology runtime 确实需要独立扩缩容/发布时，再沿既有 Port 拆进程；不要先用微服务掩盖能力与预算边界缺失。

## 11. 目标架构图

- [OperationAnalysis 目标架构（Archify HTML）](./operation-analysis-target.architecture.html)
- [OperationAnalysis 目标架构规格](./operation-analysis-target.architecture.json)
- [OperationAnalysis 目标架构静态图](./operation-analysis-target.architecture.light.png)

目标架构的主协议是：

```text
OperationAccessScope
  → CanvasAggregate + dependency revision
  → ReadOnly QueryPlan + cost + digest
  → ConnectorBudgetGateway
  → Read-only external capability

ScheduleRun / Execution
  → immutable ExecutionBundle
  → tokenized Render StepWorkItem
  → Artifact + Effect Outbox
```

## 12. 开发提醒

1. **禁止把 NATS/HTTP 方法名当作数据源能力 ID。** 新接口默认不可用于画布；只有注册为只读、参数受限、成本可算的 capability 才能开放。
2. **`SELECT` 不是安全边界。** 正则、fetchmany 和前端 LIMIT 都不能代替数据库只读账号、statement timeout、AST 和服务端预算。
3. **所有可配置外部目标必须经过统一 egress policy。** DNS 解析、重定向、私网地址和 endpoint revision 都要可审计。
4. **删除或缩小 scope 前必须做依赖影响分析。** Canvas JSON 中的 ID 不是“弱引用”；它会影响分享、订阅和历史报告。
5. **报告快照要冻结查询语义。** 只冻结布局和 datasource id 不够；query、connection、transform、generation 与 scope 都必须有 revision/digest。
6. **Celery 状态 claim 必须带 fencing token。** `status=RUNNING/PROCESSING` 或时间戳不足以阻止旧 worker；外部副作用前后都要验 token。
7. **重试是持久调度事实，不是在一个 task 内循环。** 保存 retry_at、resume step、attempt 和失败分类，给其他租户释放 worker 容量。
8. **每个列表和批量接口都要有四个上限。** item count、response bytes、duration/deadline、concurrency；达到上限时返回截断信息，不静默丢数据。
9. **普通查看、分享和报告必须共用同一 QueryPlan 编译器。** 入口可有不同 scope adapter，但不得各自解释 Canvas JSON 或绕过预算。
10. **保留现有安全与可靠性基础。** Connection 加密、HTTP SSRF 防护、Transform Runner、Excel generation、不可变快照、Render Token、分享 principal 和状态 CAS 都应继续深化。
