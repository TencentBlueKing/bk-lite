# Historical Superpowers change: 2026-07-14-cmdb-functional-production-review

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-14-cmdb-functional-production-review.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按业务功能完成当前 `feature_windyzhao` CMDB 全量现状的生产级代码审查，逐域交付可验证、可排序、可复查的报告，并形成跨域总评。

**Architecture:** 采用业务纵切审查，每个任务从 HTTP/NATS/Beat/callback 入口追踪到权限、Service、Graph/ORM/MinIO、Celery/Outbox、Stargazer 或外部系统及最终可观察结果。每个功能域独立生成报告并提交，最后归并跨域职责、错误模型、callback、状态机和测试质量问题。

**Tech Stack:** Python 3.12、Django 4.2、DRF、Celery/Beat、NATS、FalkorDB 兼容图层、Django ORM、多数据库、MinIO、Stargazer/Sanic、pytest、pytest-cov、CodeGraph、projectmem。

## Global Constraints

- 审查基线为执行时当前 `feature_windyzhao` 工作树，不以历史 diff 代替现状审查。
- 范围包含 `server/apps/cmdb/`、`server/apps/cmdb_enterprise/` 和 CMDB 相关 `agents/stargazer/` 链路；排除 `web/`。
- Review 阶段只读业务代码；不得修改生产代码或测试。需要修复时必须另开 `/fix` + TDD 流程。
- 使用 CodeGraph 定位符号和调用链；CodeGraph 未覆盖的文档、配置、动态注册和测试清单才使用 `rg`/逐文件读取。
- 发现确定 bug 时立即调用 projectmem `log_issue`；历史问题必须重新验证当前代码后才能进入 Finding。
- 所有 Finding 必须包含 Severity、Location、Root cause category、Evidence、Trigger、Impact、Why existing tests missed it、Minimal safe fix、Required tests、Long-term design note。
- Finding 按 P0 → P1 → P2 → P3 排序；只有满足代码定位、确定行为、触发路径、外部后果、缺陷理由和测试漏检原因六项证据门槛才能收录。
- 根因只能归入：局部实现错误、跨层契约不一致、状态机设计缺陷、错误模型不清晰、重复逻辑导致的不一致、资源边界缺失、并发或幂等设计问题、架构职责放置错误。
- 同一根因跨多个功能域时只保留一个主 Finding，其他报告引用主 Finding，不重复计数。
- 核心业务路径覆盖率目标 90%，相关模块行覆盖率目标 80%；无法测量时必须记录命令、错误和受影响结论。
- 报告必须依次包含 `1. Summary`、`2. Findings`、`3. Test Review`、`4. Maintainability Verdict`、`5. Recommendation`。
- 每个功能任务结束时独立提交该报告、`00-overview.md` 进度和 `evidence-index.md` 证据索引。

## File Structure

- Create: `docs/reviews/cmdb-functional-review-2026-07-14/00-overview.md` — 总进度、主 Finding 索引、跨域风险和最终结论。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/evidence-index.md` — 每域入口、调用链、关键文件、测试、命令、结果和未验证项。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/01-model-governance.md` — 模型治理报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/02-instance-write.md` — 实例写入报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/03-query-topology.md` — 查询与拓扑报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/04-auto-collection.md` — 自动采集报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/05-stargazer-boundary.md` — Stargazer 边界报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/06-config-file.md` — 配置文件报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/07-ipam.md` — IPAM 报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/08-specialized-resources.md` — 专项资源视图报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/09-node-sync.md` — Node 同步报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/10-custom-reporting.md` — Enterprise 自定义上报报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/11-change-subscription.md` — 变更与订阅报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/12-nats-rpc.md` — NATS/RPC 报告。
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/13-cross-domain-architecture.md` — 跨域职责和维护性复核。

---

### Task 1: 初始化审查台账和基线

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/00-overview.md`
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/evidence-index.md`
- Read: `server/apps/cmdb/BUSINESS_ARCHITECTURE.md`
- Read: `docs/superpowers/specs/2026-07-14-cmdb-functional-production-review-design.md`

**Interfaces:**
- Consumes: 已批准的功能域、证据门槛、严重级别和报告格式。
- Produces: 13 个审查任务的状态表、主 Finding ID 规则 `CMDB-FNN`、统一证据索引字段。

- [ ] **Step 1: 记录不可变基线**

运行：`git rev-parse HEAD && git branch --show-current && git status --short`。

在 `evidence-index.md` 写入 commit、分支、工作树状态、审查日期和环境说明；不得把执行期间的新提交误当成初始基线。

- [ ] **Step 2: 创建功能域状态表**

在 `00-overview.md` 建立 01–13 行状态表，字段固定为：`功能域 | 状态 | P0 | P1 | P2 | P3 | Recommendation | 报告链接`；初始状态统一为 `未开始`。

- [ ] **Step 3: 创建证据索引结构**

在 `evidence-index.md` 为每域预建以下字段：`业务承诺`、`入口`、`核心调用链`、`外部依赖`、`关键测试`、`执行命令`、`结果`、`覆盖率`、`未验证项`。

- [ ] **Step 4: 校验台账完整性**

运行：`rg -n '^\| (0[1-9]|1[0-3]) ' docs/reviews/cmdb-functional-review-2026-07-14/00-overview.md`。

预期：准确返回 13 行功能域记录。

- [ ] **Step 5: 提交台账**

```bash
git add docs/reviews/cmdb-functional-review-2026-07-14/00-overview.md docs/reviews/cmdb-functional-review-2026-07-14/evidence-index.md
git commit -m "docs(cmdb): 初始化全功能审查台账"
```

### Task 2: 审查模型治理

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/01-model-governance.md`
- Read: `server/apps/cmdb/views/classification.py`
- Read: `server/apps/cmdb/views/model.py`
- Read: `server/apps/cmdb/services/classification.py`
- Read: `server/apps/cmdb/services/model.py`
- Read: `server/apps/cmdb/services/unique_rule.py`
- Read: `server/apps/cmdb/services/auto_relation_rule.py`
- Read: `server/apps/cmdb/services/field_group.py`
- Read: `server/apps/cmdb/services/public_enum_library.py`
- Read: `server/apps/cmdb/display_field/`
- Test: `server/apps/cmdb/tests/test_classification_service.py`
- Test: `server/apps/cmdb/tests/test_model_service_advanced.py`
- Test: `server/apps/cmdb/tests/test_unique_rule_crud.py`
- Test: `server/apps/cmdb/tests/test_auto_relation_rule_validate.py`
- Test: `server/apps/cmdb/tests/test_field_group_service.py`
- Test: `server/apps/cmdb/tests/test_public_enum_service.py`

**Interfaces:**
- Consumes: 架构中的模型治理承诺和图数据库主数据边界。
- Produces: 模型、字段、规则和展示治理的契约结论，供实例写入与采集模型映射任务引用。

- [ ] **Step 1: 用 CodeGraph 建立入口到图写调用链**

查询分类/模型 CRUD、字段删除引用检查、唯一规则、自动关联规则、布局保存、字段分组和公共枚举；把符号、调用方和存储边界写入证据索引。

- [ ] **Step 2: 检查业务与架构风险**

逐项验证组织权限、字段删除保护、规则字段组合、模型关系方向、公共枚举引用、图写失败行为、布局回滚、SQLite JSON 查询兼容性和 Enterprise 扩展委派。

- [ ] **Step 3: 审查并运行聚焦测试**

在 `server/` 运行：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_classification_service.py apps/cmdb/tests/test_model_service_advanced.py apps/cmdb/tests/test_unique_rule_crud.py apps/cmdb/tests/test_auto_relation_rule_validate.py apps/cmdb/tests/test_field_group_service.py apps/cmdb/tests/test_public_enum_service.py
```

记录退出结果、有效断言、过度 Mock 和无法证明的核心分支。

- [ ] **Step 4: 写报告并更新台账**

按统一五段结构完成 `01-model-governance.md`；更新 `00-overview.md`、`evidence-index.md` 和主 Finding 引用。

- [ ] **Step 5: 校验并提交**

运行 Finding 字段完整性检查和 `git diff --check`，然后提交：`docs(cmdb): 完成模型治理生产级审查`。

### Task 3: 审查实例写入

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/02-instance-write.md`
- Read: `server/apps/cmdb/views/instance.py`
- Read: `server/apps/cmdb/services/instance.py`
- Read: `server/apps/cmdb/services/operation_service.py`
- Read: `server/apps/cmdb/services/unique_write_lock.py`
- Read: `server/apps/cmdb/services/auto_relation_reconcile.py`
- Read: `server/apps/cmdb/models/operation.py`
- Read: `server/apps/cmdb/instance_ops/extensions.py`
- Test: `server/apps/cmdb/tests/test_instance_service_crud.py`
- Test: `server/apps/cmdb/tests/test_operation_service.py`
- Test: `server/apps/cmdb/tests/test_operation_outbox.py`
- Test: `server/apps/cmdb/tests/test_unique_write_lock.py`
- Test: `server/apps/cmdb/tests/bdd/test_instance_crud_bdd.py`

**Interfaces:**
- Consumes: Task 2 的字段、唯一规则和关系契约。
- Produces: 实例写入状态机、幂等、跨存储一致性和后置事件结论。

- [ ] **Step 1:** 用 CodeGraph 追踪 create/update/delete/batch 到权限、唯一锁、`CmdbOperation`、图写和 Outbox。
- [ ] **Step 2:** 验证相同/冲突 Idempotency-Key、并发 owner、图写成功但 SQL 失败、恢复核对、旧 Worker、删除副作用、自动关系重投和终态覆盖。
- [ ] **Step 3:** 在 `server/` 运行上述五个测试文件的聚焦 pytest，并使用 `--cov=apps.cmdb.services.instance --cov=apps.cmdb.services.operation_service --cov-report=term-missing` 记录覆盖率。
- [ ] **Step 4:** 完成 `02-instance-write.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成实例写入生产级审查`。

### Task 4: 审查查询与拓扑

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/03-query-topology.md`
- Read: `server/apps/cmdb/views/instance.py`
- Read: `server/apps/cmdb/services/instance.py`
- Read: `server/apps/cmdb/services/topology_theme.py`
- Read: `server/apps/cmdb/graph/drivers/graph_client.py`
- Read: `server/apps/cmdb/graph/falkordb.py`
- Test: `server/apps/cmdb/tests/test_instance_views.py`
- Test: `server/apps/cmdb/tests/test_search_inst_batch.py`
- Test: `server/apps/cmdb/tests/test_topology_theme.py`
- Test: `server/apps/cmdb/tests/test_import_organization.py`
- Test: `server/apps/cmdb/tests/test_import_asso_export.py`
- Test: `server/apps/cmdb/tests/test_permission_util.py`

**Interfaces:**
- Consumes: Task 2 模型定义和 Task 3 实例真相边界。
- Produces: 查询、搜索、拓扑、导入导出和权限裁剪结论。

- [ ] **Step 1:** 追踪列表、全文搜索、关联、拓扑、导入、导出和实例文件入口到图查询及权限过滤。
- [ ] **Step 2:** 验证功能权限、组织范围、实例权限、父级 fail-closed、分页稳定性、查询上限、跨组织导入和图驱动兼容性。
- [ ] **Step 3:** 运行列出的六个测试文件，记录真实结果和对权限/分页/外部行为的断言质量。
- [ ] **Step 4:** 完成 `03-query-topology.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成查询拓扑生产级审查`。

### Task 5: 审查自动采集

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/04-auto-collection.md`
- Read: `server/apps/cmdb/views/collect.py`
- Read: `server/apps/cmdb/services/collect_service.py`
- Read: `server/apps/cmdb/services/collect_dispatch_service.py`
- Read: `server/apps/cmdb/services/collect_credential_pool_service.py`
- Read: `server/apps/cmdb/collection/common.py`
- Read: `server/apps/cmdb/collection/collect_tasks/`
- Read: `server/apps/cmdb/tasks/celery_tasks.py`
- Test: `server/apps/cmdb/tests/test_collect_service_methods.py`
- Test: `server/apps/cmdb/tests/test_collect_dispatch_service.py`
- Test: `server/apps/cmdb/tests/test_collect_celery_tasks_svc.py`
- Test: `server/apps/cmdb/tests/test_collect_management_hooks.py`
- Test: `server/apps/cmdb_enterprise/tests/test_new_collect_objects_pipeline.py`

**Interfaces:**
- Consumes: Task 2 模型映射和 Task 3 实例合并契约。
- Produces: 采集任务生命周期、凭据错误模型、结果格式和执行代次结论。

- [ ] **Step 1:** 追踪采集任务 create/update/execute、on_commit 派发、Worker 抢占、凭据轮换、格式化和实例合并链路。
- [ ] **Step 2:** 验证重复触发、旧 execution、timeout、部分成功、凭据失败与业务失败、批次上限、清理、敏感信息和下游异常传播。
- [ ] **Step 3:** 运行列出的五个测试文件；E2E 需要 `uv run --with jsonschema pytest`，记录覆盖率和基线排除项。
- [ ] **Step 4:** 完成 `04-auto-collection.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成自动采集生产级审查`。

### Task 6: 审查 Stargazer 边界

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/05-stargazer-boundary.md`
- Read: `agents/stargazer/api/collect.py`
- Read: `agents/stargazer/service/collection_service.py`
- Read: `agents/stargazer/tasks/handlers/plugin_handler.py`
- Read: `agents/stargazer/tasks/utils/nats_helper.py`
- Read: `agents/stargazer/plugins/inputs/config_file/`
- Read: `agents/stargazer/plugins/inputs/network_config_file/`
- Read: `agents/stargazer/plugins/inputs/ip/`
- Read: `agents/stargazer/plugins/inputs/network_topo/`
- Test: `agents/stargazer/tests/test_collect_multicred.py`
- Test: `agents/stargazer/tests/test_collect_credential_push.py`
- Test: `agents/stargazer/tests/test_ip_discovery_targets.py`
- Test: `agents/stargazer/tests/collect_fixtures/`

**Interfaces:**
- Consumes: Task 5 的下发、凭据、结果和 callback 契约。
- Produces: Agent 远程执行安全、资源边界、投递确认和回调一致性结论。

- [ ] **Step 1:** 追踪 CMDB 下发到插件执行、结果归一化、NATS publish 和 callback 的完整链路。
- [ ] **Step 2:** 验证命令策略、shell/PowerShell 转义、文件大小、CIDR 数量、并发 gather、日志脱敏、投递确认、instance_name 拆分和空命令行为。
- [ ] **Step 3:** 在 `agents/stargazer/` 运行 `make lint` 和列出的聚焦 pytest；记录无法在本机执行的真实采集依赖。
- [ ] **Step 4:** 完成 `05-stargazer-boundary.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成Stargazer边界生产级审查`。

### Task 7: 审查配置文件生命周期

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/06-config-file.md`
- Read: `server/apps/cmdb/views/config_file.py`
- Read: `server/apps/cmdb/services/config_file_service.py`
- Read: `server/apps/cmdb/services/config_file_content_lifecycle.py`
- Read: `server/apps/cmdb/models/config_file_version.py`
- Read: `server/apps/cmdb/collection/collect_tasks/config_file_collect.py`
- Test: `server/apps/cmdb/tests/test_config_file_process_collect_db.py`
- Test: `server/apps/cmdb/tests/test_config_file_content_lifecycle.py`
- Test: `server/apps/cmdb/tests/test_config_file_views.py`
- Test: `server/apps/cmdb/tests/e2e/test_config_file_pipeline.py`

**Interfaces:**
- Consumes: Task 5/6 的 execution 和 callback 契约。
- Produces: 版本业务键、MinIO 状态机、读取权限和补偿结论。

- [ ] **Step 1:** 追踪采集回调、临时对象、PENDING 元数据、on_commit 发布、READY/ERROR/DELETE_PENDING 和恢复任务。
- [ ] **Step 2:** 验证同键同文/异文、旧 execution、跨实例 diff、发布失败、删除失败、临时对象清理、正文上限和敏感日志。
- [ ] **Step 3:** 使用 `uv run --with jsonschema pytest` 运行四个测试文件并记录状态转换断言和覆盖率。
- [ ] **Step 4:** 完成 `06-config-file.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成配置文件生产级审查`。

### Task 8: 审查 IPAM

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/07-ipam.md`
- Read: `server/apps/cmdb/services/ipam_view.py`
- Read: `server/apps/cmdb/services/ipam_subnet.py`
- Read: `server/apps/cmdb/services/ipam_discovery.py`
- Read: `server/apps/cmdb/services/ipam_reconcile.py`
- Read: `server/apps/cmdb/services/ipam_reconcile_job.py`
- Read: `server/apps/cmdb/models/ipam_models.py`
- Test: `server/apps/cmdb/tests/test_ipam_views.py`
- Test: `server/apps/cmdb/tests/test_ipam_discovery_service.py`
- Test: `server/apps/cmdb/tests/test_ipam_reconcile_service.py`
- Test: `server/apps/cmdb/tests/test_ipam_reconcile_job.py`
- Test: `server/apps/cmdb/tests/test_ipam_reconcile_task.py`

**Interfaces:**
- Consumes: Task 3 查询权限和 Task 5/6 IP 发现结果契约。
- Produces: IPAM 权限、单活状态机、游标、资源上限和错误脱敏结论。

- [ ] **Step 1:** 追踪 IP 视图、发现、来源管理、人工/Beat 对账、单活创建、owner 抢占和结果持久化。
- [ ] **Step 2:** 验证入口权限、实例权限、CIDR 边界、并发作业、租约、稳定游标、参考集上限、失败释放 active_scope 和 broker 错误脱敏。
- [ ] **Step 3:** 运行列出的五个测试文件并记录资源边界、并发和跨数据库约束的有效证明。
- [ ] **Step 4:** 完成 `07-ipam.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成IPAM生产级审查`。

### Task 9: 审查专项资源视图

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/08-specialized-resources.md`
- Read: `server/apps/cmdb/views/k8s_setup.py`
- Read: `server/apps/cmdb/services/k8s_setup.py`
- Read: `server/apps/cmdb/services/k8s_resource_overview.py`
- Read: `server/apps/cmdb/services/application_resource_overview.py`
- Read: `server/apps/cmdb/services/infra.py`
- Read: `server/apps/cmdb/services/rack_room.py`
- Test: `server/apps/cmdb/tests/test_k8s_resource_overview_service.py`
- Test: `server/apps/cmdb/tests/test_k8s_resource_overview_views.py`
- Test: `server/apps/cmdb/tests/test_application_resource_overview_views.py`
- Test: `server/apps/cmdb/tests/test_infra_service.py`
- Test: `server/apps/cmdb/tests/test_rack_room_service.py`

**Interfaces:**
- Consumes: Task 3 的父级权限和图查询契约。
- Produces: K8s、应用、网络和机房视图的权限、分页与查询预算结论。

- [ ] **Step 1:** 追踪根实例授权、父资源分页、子资源候选、批量关系查询、安装 token 和专项响应构造。
- [ ] **Step 2:** 验证不可见父级泄露、N+1、内存分页、默认全量 Pod、token 权限/生命周期、查询预算、名称冲突和空关系行为。
- [ ] **Step 3:** 运行列出的五个测试文件并记录查询次数、分页边界和权限断言质量。
- [ ] **Step 4:** 完成 `08-specialized-resources.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成专项资源视图生产级审查`。

### Task 10: 审查 Node Management 同步

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/09-node-sync.md`
- Read: `server/apps/cmdb/views/node_mgmt_sync.py`
- Read: `server/apps/cmdb/services/node_mgmt_sync_service.py`
- Read: `server/apps/cmdb/models/node_mgmt_sync.py`
- Test: `server/apps/cmdb/tests/test_node_mgmt_sync_resilience.py`
- Test: `server/apps/cmdb/tests/test_node_mgmt_sync_helpers.py`

**Interfaces:**
- Consumes: Task 3 实例写入和 Task 5 外部任务契约。
- Produces: 同步配置、任务状态、幂等、外部错误和恢复结论。

- [ ] **Step 1:** 追踪 config/task/operator/latest_run/display/k8s_meta/snmp_trap_nodes 入口到 Node Management 调用和状态持久化。
- [ ] **Step 2:** 验证权限、组织范围、重复运行、部分失败、远端超时、状态终态、错误脱敏和配置更新竞态。
- [ ] **Step 3:** 在 `server/` 运行 `apps/cmdb/tests/test_node_mgmt_sync_resilience.py` 和 `apps/cmdb/tests/test_node_mgmt_sync_helpers.py`，记录 View/Service 的状态、错误和恢复断言质量。
- [ ] **Step 4:** 完成 `09-node-sync.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成Node同步生产级审查`。

### Task 11: 审查 Enterprise 自定义上报

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/10-custom-reporting.md`
- Read: `server/apps/cmdb/views/custom_reporting.py`
- Read: `server/apps/cmdb/custom_reporting/extensions.py`
- Read: `server/apps/cmdb_enterprise/custom_reporting/models.py`
- Read: `server/apps/cmdb_enterprise/custom_reporting/services/`
- Read: `server/apps/cmdb_enterprise/custom_reporting/tasks.py`
- Read: `server/apps/cmdb_enterprise/custom_reporting/provider.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_authz.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_ingest_service.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_merge_service.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_relation_service.py`
- Test: `server/apps/cmdb_enterprise/tests/test_custom_reporting_cleanup_service.py`
- Test: `server/apps/cmdb_enterprise/tests/bdd/test_custom_reporting_bdd.py`

**Interfaces:**
- Consumes: Task 2 快速模型契约和 Task 3 实例/关系写入契约。
- Produces: Overlay 注册、凭证、批次、字段扩展、合并、审核和资源边界结论。

- [ ] **Step 1:** 追踪社区稳定入口到 Enterprise provider、凭证校验、批次、模型/字段、实例/关系合并和清理审核。
- [ ] **Step 2:** 验证认证关闭入口的实际授权、凭证轮换/作废、组织绑定、身份键、请求体/实例/关系/字段上限、重投、部分失败和社区降级行为。
- [ ] **Step 3:** 运行列出的六个 Enterprise 测试文件并记录 Overlay 缺失/启用两种运行模式的证明力。
- [ ] **Step 4:** 完成 `10-custom-reporting.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成自定义上报生产级审查`。

### Task 12: 审查变更记录与订阅

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/11-change-subscription.md`
- Read: `server/apps/cmdb/views/change_record.py`
- Read: `server/apps/cmdb/utils/change_record.py`
- Read: `server/apps/cmdb/services/change_record_mirror.py`
- Read: `server/apps/cmdb/services/subscription_trigger.py`
- Read: `server/apps/cmdb/services/subscription_task.py`
- Read: `server/apps/cmdb/models/change_record.py`
- Read: `server/apps/cmdb/models/subscription_delivery.py`
- Test: `server/apps/cmdb/tests/test_change_record_mirror_service.py`
- Test: `server/apps/cmdb/tests/test_change_record_mirror_outbox.py`
- Test: `server/apps/cmdb/tests/test_subscription_trigger_service.py`
- Test: `server/apps/cmdb/tests/test_subscription_task_service.py`

**Interfaces:**
- Consumes: Task 3/5/11 的变更来源和外部副作用契约。
- Produces: 审计真实性、Mirror Outbox、Delivery 状态机和通知错误模型结论。

- [ ] **Step 1:** 追踪变更生成、查询/导出、镜像 payload、Outbox 消费、订阅检测、Delivery 去重、发送和恢复。
- [ ] **Step 2:** 验证批量资源边界、事务外副作用、payload 一致性、租约接管、attempt_count 代次、永久错误、收件人组织范围和日志脱敏。
- [ ] **Step 3:** 运行列出的四个测试文件并记录状态转换、重投和异常传播的断言质量。
- [ ] **Step 4:** 完成 `11-change-subscription.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成变更订阅生产级审查`。

### Task 13: 审查 NATS / RPC

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/12-nats-rpc.md`
- Read: `server/apps/cmdb/nats/nats.py`
- Read: `server/apps/cmdb/nats/__init__.py`
- Read: `server/apps/cmdb/config.py`
- Test: `server/apps/cmdb/tests/test_nats_pure.py`
- Test: `server/apps/cmdb/tests/test_create_delete_instance_nats.py`
- Test: `server/apps/cmdb/tests/test_update_instance_nats.py`
- Test: `server/apps/cmdb/tests/test_get_cmdb_module_data_permission_3662.py`
- Test: `server/apps/cmdb/tests/test_collect_credential_event_nats.py`
- Test: `server/apps/cmdb/tests/test_room3d_layout_nats.py`

**Interfaces:**
- Consumes: Tasks 2–12 已确认的领域契约。
- Produces: 跨模块授权、callback payload、错误映射和兼容性结论。

- [ ] **Step 1:** 枚举所有 NATS 注册函数、调用方、请求 schema、授权上下文、返回 payload 和错误路径。
- [ ] **Step 2:** 验证缺失 scope、调用方伪造组织、实例级权限、传输 ack 与业务结果、批量限制、异常类型、敏感数据和重复 payload 构造。
- [ ] **Step 3:** 运行列出的六个测试文件并检查测试是否只断言 handler 被调用而未验证业务结果。
- [ ] **Step 4:** 完成 `12-nats-rpc.md`，更新台账与证据索引。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成NATS RPC生产级审查`。

### Task 14: 执行跨域架构复核

**Files:**
- Create: `docs/reviews/cmdb-functional-review-2026-07-14/13-cross-domain-architecture.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/01-model-governance.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/02-instance-write.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/03-query-topology.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/04-auto-collection.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/05-stargazer-boundary.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/06-config-file.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/07-ipam.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/08-specialized-resources.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/09-node-sync.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/10-custom-reporting.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/11-change-subscription.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/12-nats-rpc.md`

**Interfaces:**
- Consumes: 十二份功能报告和所有主 Finding。
- Produces: 去重后的结构性 Finding、职责归属、最小安全修复与长期设计取舍。

- [ ] **Step 1:** 汇总 callback payload、错误映射、状态枚举、权限 helper、外部依赖 wrapper、布尔控制参数和 fallback 的定义位置。
- [ ] **Step 2:** 识别 framework/service/adapter/plugin/task orchestration/callback builder/error mapper/test fixture 的职责错放和复制成本。
- [ ] **Step 3:** 对跨域重复表象执行根因归并，选定主 Finding ID，并回写各功能报告引用。
- [ ] **Step 4:** 完成 `13-cross-domain-architecture.md`，逐项回答八个 Maintainability Verdict 问题。
- [ ] **Step 5:** 校验并提交：`docs(cmdb): 完成跨域架构生产级审查`。

### Task 15: 完成总览与终验

**Files:**
- Modify: `docs/reviews/cmdb-functional-review-2026-07-14/00-overview.md`
- Modify: `docs/reviews/cmdb-functional-review-2026-07-14/evidence-index.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/01-model-governance.md`
- Read: `docs/reviews/cmdb-functional-review-2026-07-14/13-cross-domain-architecture.md`

**Interfaces:**
- Consumes: 十三份已完成报告、主 Finding 索引和所有验证记录。
- Produces: CMDB 全量现状的最终风险、阻断结论、测试缺口、维护性结论和 Recommendation。

- [ ] **Step 1: 校验报告齐套**

运行：`for f in docs/reviews/cmdb-functional-review-2026-07-14/{01-model-governance,02-instance-write,03-query-topology,04-auto-collection,05-stargazer-boundary,06-config-file,07-ipam,08-specialized-resources,09-node-sync,10-custom-reporting,11-change-subscription,12-nats-rpc,13-cross-domain-architecture}.md; do test -s "$f" || exit 1; done`。

预期：退出码 0。

- [ ] **Step 2: 校验 Finding 字段和严重级别**

对所有包含 `### Finding` 的报告逐项确认十个字段齐全；运行 `rg -n 'Severity:.*P[0-3]' docs/reviews/cmdb-functional-review-2026-07-14`，并人工确认排序为 P0 → P1 → P2 → P3。

- [ ] **Step 3: 校验测试证据**

确认每域证据索引都有执行命令、结果、覆盖率或明确未验证原因；不得使用“测试通过”但无命令和退出摘要的表述。

- [ ] **Step 4: 写最终 Summary 和 Recommendation**

更新 `00-overview.md`，给出整体风险、是否建议合并、阻断问题、P0/P1/P2/P3 数量、测试有效性、八项维护性结论和 `Approve / Approve with minor comments / Request changes / Block` 之一。

- [ ] **Step 5: 最终一致性检查**

运行：

```bash
rg -n 'TBD|TODO|待定|待确认' docs/reviews/cmdb-functional-review-2026-07-14
git diff --check -- docs/reviews/cmdb-functional-review-2026-07-14
```

预期：占位符扫描无输出，diff 检查退出码 0。

- [ ] **Step 6: 提交最终总览**

```bash
git add docs/reviews/cmdb-functional-review-2026-07-14
git commit -m "docs(cmdb): 完成全功能生产级审查总览"
```

## specs: 2026-07-14-cmdb-functional-production-review-design.md

## 1. 背景与目标

本设计用于审查当前 `feature_windyzhao` 分支的 CMDB 全量现状，而不是审查某个局部 diff。审查以 `server/apps/cmdb/BUSINESS_ARCHITECTURE.md` 描述的业务能力和核心流程为入口，验证实际代码是否满足长期可维护的生产级质量。

审查必须做到：

- **可验证**：Finding 必须有具体代码、调用链、触发条件和外部后果证据。
- **可排序**：Finding 按 P0、P1、P2、P3 排序，不夸大低价值问题。
- **可复查**：记录审查入口、调用链、测试、命令和无法验证项，使其他开发者能够复现结论。

本阶段只做代码审查和只读验证，不修改生产代码、不新增回归测试、不自动修复 Finding。需要修复时，由用户另行确认并进入 `/fix`、TDD 和模块门禁流程。

## 2. 审查范围

### 2.1 纳入范围

- `server/apps/cmdb/` 社区层。
- `server/apps/cmdb_enterprise/` Enterprise Overlay，包括自定义上报实现。
- `agents/stargazer/` 中由 CMDB 使用的采集插件、任务、远程执行、NATS 回调和错误闭环。
- CMDB 与 System Management、Node Management、NATS、Celery、MinIO、图数据库之间的接口契约。
- 与上述功能对应的后端测试、Stargazer 测试和迁移/调度配置。

### 2.2 排除范围

- `web/` 和移动端页面实现。
- 与 CMDB 业务链路无关的 Stargazer 插件。
- 未经用户确认的生产代码修复、重构或测试新增。

### 2.3 基线原则

- 以审查执行时当前工作树中的 `feature_windyzhao` 代码为事实基线。
- projectmem 的历史问题只作为调查线索，必须重新验证当前代码后才能形成 Finding。
- 架构文档是预期业务契约，不替代对真实入口、调用方和外部行为的检查。

## 3. 审查方法选择

采用**业务纵切审查**。每个功能域均沿以下链路检查：

```text
HTTP / NATS / Beat / callback
  → 权限与参数校验
  → Service / Manage / Plugin 编排
  → Graph / ORM / MinIO / Cache
  → Celery / Outbox / callback
  → Stargazer / 外部系统
  → 外部可观察结果与测试
```

未采用纯风险横扫作为主组织方式，因为它会使问题散落在技术维度中，不利于逐功能验收。未采用按 views、services、models、tasks 分层审查，因为目录覆盖不能证明完整业务闭环正确。

每个功能域内部仍固定检查权限、幂等、状态机、错误模型、资源边界和职责边界。全部功能域完成后，再进行一次跨域架构复核。

## 4. 功能域拆分与顺序

每个编号对应一份独立 Review 报告。

1. **模型治理**：分类、模型、字段、唯一规则、模型关系、自动关联规则、字段分组、展示字段和公共枚举。
2. **实例写入**：实例创建、更新、删除、批量操作、唯一性、幂等、图写状态机、Outbox 和恢复。
3. **查询与拓扑**：列表、搜索、关系、拓扑、导入导出、实例文件、组织与实例权限裁剪。
4. **自动采集**：任务配置、调度、凭据轮换、结果格式化、实例合并、清理、超时和执行代次。
5. **Stargazer 边界**：CMDB 相关插件、远程执行安全、资源上限、NATS 回调、敏感日志和错误分类。
6. **配置文件**：采集回调、版本业务键、MinIO 正文生命周期、读取与 diff 权限、删除和周期补偿。
7. **IPAM**：IP 视图、来源配置、发现、全量对账、单活租约、资源上限和失败关闭。
8. **专项资源视图**：K8s 安装与资源概览、应用资源、网络拓扑、机房和机架；父级权限与查询预算。
9. **Node 同步**：Node Management 配置、执行状态、节点映射、失败恢复和外部依赖边界。
10. **Enterprise 自定义上报**：任务、凭证、批次、快速模型、字段扩展、实例/关系合并、待关联和清理审核。
11. **变更与订阅**：ChangeRecord、操作日志镜像、订阅检测、Delivery、通知租约、重试和终态。
12. **NATS / RPC**：查询与写入授权、callback payload、错误模型、兼容契约和下游可观察结果。
13. **跨域架构复核**：职责归属、重复状态判断、callback builder、error mapper、隐式 fallback、扩展成本和测试真实性。

执行顺序遵循“治理定义 → 资产主数据 → 数据接入 → 专项资源 → 事件生态 → 跨域复核”，使后续功能能够复用已经确认的上游契约。

## 5. 单功能域证据闭环

### 5.1 建立真实业务链路

1. 从架构文档、规格和状态定义提取该功能域的业务承诺。
2. 定位所有真实入口，包括 HTTP、NATS、Celery Beat、Worker 和 callback。
3. 追踪权限、Service、存储、异步任务和外部依赖调用链。
4. 明确成功、失败、超时、重试和并发情况下的外部可观察结果。

### 5.2 主动攻击业务假设

- **权限与契约**：跨组织访问、实例级权限、缺失授权上下文、payload 版本、错误类型和隐式约定。
- **状态与并发**：重复执行、并发抢占、旧 Worker、终态覆盖、部分成功、租约过期和幂等冲突。
- **失败与恢复**：事务回滚、broker/图数据库/对象存储失败、timeout、cleanup、补偿任务和不可恢复副作用。
- **规模与安全**：批次、游标、内存、查询预算、远程命令、敏感日志、输入大小和资源硬上限。
- **架构职责**：插件是否承担框架职责、框架是否耦合特定插件、callback 和错误映射是否重复、扩展同类功能是否需要复制代码。

### 5.3 Finding 准入条件

一个问题只有同时满足以下条件才能进入 Findings：

- 能定位到文件、函数、类或完整调用链。
- 能说明当前代码的确定行为。
- 能给出具体触发输入、状态或执行路径。
- 能描述用户、调用方或外部系统可观察的后果。
- 能证明其违反业务契约、安全边界、可靠性要求或明确的可维护性约束，而非个人偏好。
- 能解释现有测试为什么没有阻止它。

只有“可能”“建议”或代码异味、无法构造外部后果的局部问题、纯命名与格式问题，以及没有错误行为证据的单纯缺测试，不形成 Finding。

### 5.4 根因和严重级别

Finding 先归入以下根因之一：

1. 局部实现错误。
2. 跨层契约不一致。
3. 状态机设计缺陷。
4. 错误模型不清晰。
5. 重复逻辑导致的不一致。
6. 资源边界缺失。
7. 并发或幂等设计问题。
8. 架构职责放置错误。

严重级别按用户定义的 P0、P1、P2、P3 标准判定。结构性根因必须指出正确归属层和最小安全修复，不能用继续堆叠条件判断作为默认方案。

## 6. 测试审查与验证

- 现有测试通过只能作为证据之一，不能替代业务行为审查。
- 优先检查业务状态变化、外部行为、任务生命周期、callback 一致性、幂等重投、timeout、清理、异常传播、安全和资源边界。
- 没有有效断言、只断言对象非空、只验证 Mock 调用、绑定私有实现或机械 Mock 每一行的测试，不视为有效质量证明。
- 能运行时记录真实测试命令、退出结果和功能域覆盖率。核心业务路径目标为 90%，相关模块目标为 80%。
- 覆盖率未达标本身记录为测试风险；只有同时存在错误行为证据时才形成缺陷 Finding。
- 测试环境或基线问题阻止验证时，记录具体错误、受影响结论和未验证分支，不伪造覆盖率或通过结论。
- P0/P1 Finding 必须给出明确的回归测试设计，但 Review 阶段不直接实现测试。

## 7. 报告产物

报告目录为 `docs/reviews/cmdb-functional-review-2026-07-14/`：

- `00-overview.md`：功能域进度、总体风险、跨域问题和最终合并结论。
- `01-model-governance.md` 至 `12-nats-rpc.md`：逐功能域独立报告。
- `13-cross-domain-architecture.md`：跨域职责和维护性复核。
- `evidence-index.md`：已审查入口、调用链、关键文件、测试文件、验证命令、结果和无法验证项。

每份功能报告必须按以下顺序输出：

1. Summary。
2. Findings，按 P0 → P1 → P2 → P3 排序。
3. Test Review。
4. Maintainability Verdict，逐项回答用户指定的八个维护性问题。
5. Recommendation：Approve、Approve with minor comments、Request changes 或 Block。

每个 Finding 使用用户指定的完整字段：Severity、Location、Root cause category、Evidence、Trigger、Impact、Why existing tests missed it、Minimal safe fix、Required tests、Long-term design note。

同一根因影响多个功能域时，只建立一个主 Finding，其他报告引用它，避免重复计数和严重级别膨胀。

## 8. 进度和完成标准

每个功能域只有满足以下条件才标记完成：

- 已记录真实入口和主要调用链。
- 已检查权限、状态、失败、恢复、资源和职责边界。
- 已审查相关测试的业务证明力。
- 已记录执行过的验证命令和无法验证项。
- 所有 Findings 都通过证据准入门，并按严重级别排序。
- 已给出该功能域明确的 Recommendation。

全部十二个功能报告完成后执行跨域架构复核，再更新 `00-overview.md` 给出整体风险和最终结论。发现缺陷不会自动扩大为长期重构；报告同时说明最小安全修复与推荐长期方案的影响范围和取舍，是否实施由用户决定。
