# Historical Superpowers change: 2026-07-14-alerts-production-module-review

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-14-alerts-production-module-review.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以当前分支 `server/apps/alerts/` 全量代码为基线，按照 Event → Alert → Incident 架构链路逐模块完成可验证、可排序、可复查的生产级代码审查。

**Architecture:** 采用业务纵切审查，每个任务从 HTTP/NATS/Beat/callback 入口追踪到认证、领域规则、ORM 状态、Celery/Outbox、外部 RPC 和最终可观察结果。九个模块分别交付独立报告，跨模块问题只在根因报告定义一次，最后由总览和证据索引汇总。

**Tech Stack:** Python 3.12、Django 4.2、DRF、Django ORM、多数据库 JSONField、Celery/Beat、NATS、System Management/CMDB/Job Management RPC、pytest、pytest-cov、CodeGraph、projectmem。

## Global Constraints

- 审查基线是执行开始时的当前分支和工作树；必须记录 commit、分支和已有未提交文件。
- Review 阶段只读 Alerts 生产代码和测试；只创建或更新 `docs/reviews/alerts/` 下的审查文档。
- 不修改生产代码，不写修复测试，不自动修复 Finding；后续修复必须另行进入 `/fix`、TDD 和 OpenSpec 流程。
- 优先使用 CodeGraph 定位符号、调用方和影响面；文档、配置、动态注册和测试清单才使用 `rg` 或逐文件读取。
- 发现确定缺陷后立即使用 projectmem `log_issue`；历史问题只有在当前代码仍可复现时才能形成 Finding。
- Finding 只接受具备具体位置、确定行为、触发路径、外部后果、缺陷理由和测试漏检原因的证据闭环。
- Finding 根因只能归入：局部实现错误、跨层契约不一致、状态机设计缺陷、错误模型不清晰、重复逻辑导致的不一致、资源边界缺失、并发或幂等设计问题、架构职责放置错误。
- Finding 按 P0 → P1 → P2 → P3 排序；P0 立即停止当前模块后续审查并交付，P1 在当前模块证据闭环后交付。
- 每个 Finding 必须包含 Severity、Location、Root cause category、Evidence、Trigger、Impact、Why existing tests missed it、Minimal safe fix、Required tests、Long-term design note。
- 同一根因跨多个模块时只保留一个主 Finding，其他报告引用主 Finding ID；ID 格式为 `ALERTS-FNN`，从 `ALERTS-F01` 连续编号。
- 相关模块生产文件行覆盖率目标不低于 80%，核心业务路径目标不低于 90%；无法证明时记录命令、错误、未覆盖分支和对结论的影响。
- 每份模块报告严格包含 `1. Summary`、`2. Findings`、`3. Test Review`、`4. Maintainability Verdict`、`5. Recommendation`。
- 每个模块完成后更新 `00-overview.md` 和 `evidence-index.md`，独立提交报告，并等待用户复查后再进入下一模块。
- 测试默认在 `server/` 工作目录运行，统一设置 `MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=/private/tmp/bklite-alerts-review.sqlite3 ENABLE_CELERY=true CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory://`。

## File Structure

- Create: `docs/reviews/alerts/00-overview.md` — 模块进度、Finding 主索引、跨模块风险和最终 Recommendation。
- Create: `docs/reviews/alerts/evidence-index.md` — 基线、业务承诺、入口、调用链、外部依赖、测试、命令、结果、覆盖率和未验证项。
- Create: `docs/reviews/alerts/01-ingress-governance-review.md` — 事件接入与治理报告。
- Create: `docs/reviews/alerts/02-alert-detection-generation-review.md` — 告警检测与生成报告。
- Create: `docs/reviews/alerts/03-recovery-auto-close-review.md` — 恢复与自动关闭报告。
- Create: `docs/reviews/alerts/04-alert-lifecycle-review.md` — Alert 生命周期报告。
- Create: `docs/reviews/alerts/05-assignment-notification-review.md` — 分派、通知、提醒与升级报告。
- Create: `docs/reviews/alerts/06-outbox-delivery-review.md` — Outbox 可靠投递报告。
- Create: `docs/reviews/alerts/07-action-remediation-review.md` — Action 自动处置报告。
- Create: `docs/reviews/alerts/08-incident-collaboration-review.md` — Incident 事故协同报告。
- Create: `docs/reviews/alerts/09-cross-module-boundaries-review.md` — 权限、事务、资源、错误模型和可观测性横切报告。

---

### Task 1: 初始化审查台账和不可变基线

**Files:**
- Create: `docs/reviews/alerts/00-overview.md`
- Create: `docs/reviews/alerts/evidence-index.md`
- Read: `server/apps/alerts/ARCHITECTURE.md`
- Read: `docs/superpowers/specs/2026-07-14-alerts-production-module-review-design.md`
- Read: `docs/reviews/backend-production-review-protocol.md`

**Interfaces:**
- Consumes: 已批准的九模块边界、证据准入、严重级别和逐模块交付方式。
- Produces: 模块状态表、`ALERTS-FNN` 主 Finding 编号规则和统一证据索引，供 Task 2–11 更新。

- [ ] **Step 1: 记录审查基线**

运行：`git rev-parse HEAD`、`git branch --show-current`、`git status --short`。

在 `evidence-index.md` 写入 commit、分支、工作树状态、日期、时区和测试环境。现有未提交文件只记录，不修改、不暂存。

- [ ] **Step 2: 创建九模块状态表**

在 `00-overview.md` 建立九行表格，字段固定为：`模块 | 状态 | P0 | P1 | P2 | P3 | Recommendation | 报告`。初始状态统一为 `未开始`。

- [ ] **Step 3: 创建证据索引结构**

在 `evidence-index.md` 为 01–09 模块分别预建：`架构承诺`、`入口`、`核心调用链`、`外部依赖`、`关键测试`、`执行命令`、`结果`、`覆盖率`、`未覆盖分支`、`环境限制`。

- [ ] **Step 4: 校验台账结构**

运行：`rg -n '^\| 0[1-9] ' docs/reviews/alerts/00-overview.md`。

Expected: 准确返回九行模块记录，编号从 01 到 09，无重复或缺号。

- [ ] **Step 5: 提交初始化文档**

```bash
git add docs/reviews/alerts/00-overview.md docs/reviews/alerts/evidence-index.md
git commit -m "docs(alerts): 初始化全模块审查台账"
```

### Task 2: 审查事件接入与治理

**Files:**
- Create: `docs/reviews/alerts/01-ingress-governance-review.md`
- Read: `server/apps/alerts/views/receiver.py`
- Read: `server/apps/alerts/nats/nats.py`
- Read: `server/apps/alerts/common/source_adapter/base.py`
- Read: `server/apps/alerts/common/source_adapter/nats.py`
- Read: `server/apps/alerts/common/source_adapter/prometheus.py`
- Read: `server/apps/alerts/common/source_adapter/restful.py`
- Read: `server/apps/alerts/common/source_adapter/webhook.py`
- Read: `server/apps/alerts/common/source_adapter/zabbix.py`
- Read: `server/apps/alerts/enrichment/engine.py`
- Read: `server/apps/alerts/common/shield.py`
- Test: `server/apps/alerts/tests/test_source_adapter.py`
- Test: `server/apps/alerts/tests/test_event_log_receiver_views.py`
- Test: `server/apps/alerts/tests/test_nats_handlers.py`
- Test: `server/apps/alerts/tests/test_prometheus_adapter.py`
- Test: `server/apps/alerts/tests/test_webhook_adapter.py`
- Test: `server/apps/alerts/tests/test_zabbix_adapter.py`
- Test: `server/apps/alerts/tests/test_enrichment_engine.py`
- Test: `server/apps/alerts/tests/test_shield.py`

**Interfaces:**
- Consumes: 架构中的来源认证、字段标准化、幂等、丰富、屏蔽和接入结果契约。
- Produces: Event 进入系统前的信任边界、租户归属、错误表达和实际接受数量结论，供 Task 3 与 Task 9 引用。

- [ ] **Step 1: 建立入口到 Event 持久化调用链**

使用 CodeGraph 查询 `receiver nats AlertSourceAdapter authenticate normalize build_unsaved_event bulk_save_events EnrichmentEngine shield`，在证据索引写入 HTTP/NATS 入口、认证分支、team 解析、Event 唯一键、CMDB 调用、屏蔽和响应映射。

- [ ] **Step 2: 检查业务和生产风险**

逐项验证源级/team secret、trusted internal、空 team、重复批次、部分失败、恢复事件 external_id、CMDB 异常、屏蔽统计、日志正文、批量上限、HTTP 200/207/422 与 NATS result 契约。

- [ ] **Step 3: 审查测试有效性**

为认证拒绝、跨团队、重复输入、部分接受、丰富失败、屏蔽命中和 NATS 结果建立“行为 → 断言”映射；标记只验证 Mock 调用、未验证 Event 状态或错误响应的测试。

- [ ] **Step 4: 运行定向测试与覆盖率**

在 `server/` 运行：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=/private/tmp/bklite-alerts-review.sqlite3 ENABLE_CELERY=true CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory:// uv run pytest -q -o addopts='' apps/alerts/tests/test_source_adapter.py apps/alerts/tests/test_event_log_receiver_views.py apps/alerts/tests/test_nats_handlers.py apps/alerts/tests/test_prometheus_adapter.py apps/alerts/tests/test_webhook_adapter.py apps/alerts/tests/test_zabbix_adapter.py apps/alerts/tests/test_enrichment_engine.py apps/alerts/tests/test_shield.py --cov=apps.alerts.common.source_adapter --cov=apps.alerts.enrichment --cov=apps.alerts.views.receiver --cov=apps.alerts.nats.nats --cov-report=term-missing
```

Expected: 命令退出码为 0；报告记录各生产文件覆盖率、未执行分支和 SQLite/RPC Mock 的证明边界。若失败，先分类为产品、测试或环境问题再形成结论。

- [ ] **Step 5: 写报告、更新台账并提交**

完成 `01-ingress-governance-review.md` 的五段结构；更新 `00-overview.md` 和 `evidence-index.md`。运行 `git diff --check` 后提交：`docs(alerts): 完成事件接入治理审查`，然后等待用户复查。

### Task 3: 审查告警检测与生成

**Files:**
- Create: `docs/reviews/alerts/02-alert-detection-generation-review.md`
- Read: `server/apps/alerts/aggregation/processor/instant_dispatcher.py`
- Read: `server/apps/alerts/aggregation/processor/aggregation_processor.py`
- Read: `server/apps/alerts/aggregation/strategy/instant_matcher.py`
- Read: `server/apps/alerts/aggregation/strategy/matcher.py`
- Read: `server/apps/alerts/aggregation/builder/alert_builder.py`
- Read: `server/apps/alerts/aggregation/builder/synthetic_alert_builder.py`
- Read: `server/apps/alerts/aggregation/core/fingerprint.py`
- Read: `server/apps/alerts/service/active_fingerprint.py`
- Read: `server/apps/alerts/models/active_fingerprint.py`
- Test: `server/apps/alerts/tests/test_instant_alert_pipeline.py`
- Test: `server/apps/alerts/tests/test_instant_dispatcher.py`
- Test: `server/apps/alerts/tests/test_instant_matcher.py`
- Test: `server/apps/alerts/tests/test_aggregation_processor.py`
- Test: `server/apps/alerts/tests/test_aggregation_beat_lock.py`
- Test: `server/apps/alerts/tests/test_alert_builder.py`
- Test: `server/apps/alerts/tests/test_alert_builder_enrichment.py`
- Test: `server/apps/alerts/tests/test_active_fingerprint.py`
- Test: `server/apps/alerts/tests/bdd/test_aggregation_bdd.py`

**Interfaces:**
- Consumes: Task 2 的 Event 真实性、team 和接入结果契约。
- Produces: 即时、周期和缺失检测三条建警路径的策略匹配、Alert 字段、并发唯一性和生命周期入口结论。

- [ ] **Step 1:** 使用 CodeGraph 追踪 Event → matcher → dispatcher/processor → builder → fingerprint lease → Alert → lifecycle 的三条路径。
- [ ] **Step 2:** 验证策略缓存、时间窗口、group_by、级别映射、enrichment 合并、批量上限、Beat 互斥、并发首次建警、重复 Event、租户隔离和异常传播。
- [ ] **Step 3:** 检查测试是否证明只产生一个活跃 Alert、Alert 与 Event 关联、失败任务状态、三入口一致生命周期，而非只证明 Builder 或 Mock 被调用。
- [ ] **Step 4:** 在 `server/` 使用 Global Constraints 的环境变量运行列出的九个测试文件，并增加 `--cov=apps.alerts.aggregation --cov=apps.alerts.service.active_fingerprint --cov=apps.alerts.models.active_fingerprint --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0，并记录模块行覆盖率和核心路径覆盖缺口。
- [ ] **Step 5:** 完成 `02-alert-detection-generation-review.md`，更新台账和证据索引，运行 `git diff --check`，提交 `docs(alerts): 完成告警检测生成审查`，等待用户复查。

### Task 4: 审查恢复与自动关闭

**Files:**
- Create: `docs/reviews/alerts/03-recovery-auto-close-review.md`
- Read: `server/apps/alerts/aggregation/recovery/match_key.py`
- Read: `server/apps/alerts/aggregation/recovery/recovery_handler.py`
- Read: `server/apps/alerts/aggregation/recovery/recovery_checker.py`
- Read: `server/apps/alerts/aggregation/recovery/auto_closer.py`
- Read: `server/apps/alerts/aggregation/recovery/timeout_checker.py`
- Read: `server/apps/alerts/common/auto_close.py`
- Read: `server/apps/alerts/models/models.py`
- Test: `server/apps/alerts/tests/test_recovery_handler.py`
- Test: `server/apps/alerts/tests/test_auto_close.py`
- Test: `server/apps/alerts/tests/test_timeout_checker.py`
- Test: `server/apps/alerts/tests/test_queryset_batching.py`
- Test: `server/apps/alerts/tests/test_models.py`

**Interfaces:**
- Consumes: Task 2 的恢复 Event 标识和 Task 3 的活跃 Alert/指纹租约。
- Produces: 恢复复合键、终态转换、提醒停止、租约释放、会话超时和批量扫描结论。

- [ ] **Step 1:** 追踪 recovery Event → 复合匹配键 → Event/Alert 关联 → auto_recovery，以及 Beat → cursor scan → auto_close/session timeout 的调用链。
- [ ] **Step 2:** 验证跨 source/push_source/team 的 external_id 冲突、歧义 fallback、重复恢复、已终态 Alert、状态与租约原子性、提醒/升级停止、旧批次和主键游标上限。
- [ ] **Step 3:** 检查测试是否断言 Alert 终态、恢复 Event 关联、指纹删除、Reminder/Escalation 停止和重复执行结果。
- [ ] **Step 4:** 在 `server/` 使用统一环境运行列出的五个测试文件，并增加 `--cov=apps.alerts.aggregation.recovery --cov=apps.alerts.common.auto_close --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0；数据库竞争和真实 Beat 调度无法由 SQLite 证明时单列限制。
- [ ] **Step 5:** 完成 `03-recovery-auto-close-review.md`，更新台账和证据索引，校验并提交 `docs(alerts): 完成恢复自动关闭审查`，等待用户复查。

### Task 5: 审查 Alert 生命周期

**Files:**
- Create: `docs/reviews/alerts/04-alert-lifecycle-review.md`
- Read: `server/apps/alerts/service/alert_lifecycle.py`
- Read: `server/apps/alerts/models/models.py`
- Read: `server/apps/alerts/views/alert.py`
- Read: `server/apps/alerts/service/alter_operator.py`
- Read: `server/apps/alerts/tasks/action_tasks.py`
- Test: `server/apps/alerts/tests/test_action_lifecycle_hooks_service.py`
- Test: `server/apps/alerts/tests/test_action_dispatch_hooks_service.py`
- Test: `server/apps/alerts/tests/test_alert_operator.py`
- Test: `server/apps/alerts/tests/bdd/test_alert_lifecycle_bdd.py`
- Test: `server/apps/alerts/tests/bdd/test_alert_lifecycle_full_bdd.py`

**Interfaces:**
- Consumes: Task 3 的 Alert 创建入口和 Task 4 的终态/租约语义。
- Produces: created、assigned、acknowledged、reassigned、closed、resolved 的状态前置条件、统一副作用和错误传播结论。

- [ ] **Step 1:** 追踪所有 Alert 状态写入口，确认 API、Builder、恢复、自动关闭和任务是否统一进入 lifecycle service。
- [ ] **Step 2:** 验证合法前置状态、重复状态事件、事务边界、Action/assignment outbox、失败传播、终态后副作用停止和 `recovered` 未接入契约是否显式。
- [ ] **Step 3:** 逐项核对 BDD 场景是否断言数据库状态和副作用，而非只断言 HTTP 状态或 Mock 调用。
- [ ] **Step 4:** 在 `server/` 使用统一环境运行列出的五个测试文件，并增加 `--cov=apps.alerts.service.alert_lifecycle --cov=apps.alerts.views.alert --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0，核心状态转换和每个生命周期事件均有可观察断言或明确缺口。
- [ ] **Step 5:** 完成 `04-alert-lifecycle-review.md`，更新台账和证据索引，校验并提交 `docs(alerts): 完成告警生命周期审查`，等待用户复查。

### Task 6: 审查分派、通知、提醒与升级

**Files:**
- Create: `docs/reviews/alerts/05-assignment-notification-review.md`
- Read: `server/apps/alerts/common/assignment.py`
- Read: `server/apps/alerts/common/notify/dispatcher.py`
- Read: `server/apps/alerts/common/notify/notify.py`
- Read: `server/apps/alerts/service/notify_service.py`
- Read: `server/apps/alerts/service/reminder_service.py`
- Read: `server/apps/alerts/service/escalation_service.py`
- Read: `server/apps/alerts/service/un_dispatch.py`
- Read: `server/apps/alerts/models/alert_operator.py`
- Test: `server/apps/alerts/tests/test_assignment.py`
- Test: `server/apps/alerts/tests/test_assignment_config_validation.py`
- Test: `server/apps/alerts/tests/test_notify_dispatcher.py`
- Test: `server/apps/alerts/tests/test_notify_params_format.py`
- Test: `server/apps/alerts/tests/test_notify_result_service.py`
- Test: `server/apps/alerts/tests/test_reminder_service.py`
- Test: `server/apps/alerts/tests/test_escalation_service.py`
- Test: `server/apps/alerts/tests/test_escalation_assignment_flow.py`
- Test: `server/apps/alerts/tests/test_un_dispatch_and_reminder_extra.py`
- Test: `server/apps/alerts/tests/bdd/test_assignment_bdd.py`
- Test: `server/apps/alerts/tests/bdd/test_escalation_bdd.py`

**Interfaces:**
- Consumes: Task 5 的 created/assigned 生命周期事件。
- Produces: 责任人范围、通知 payload、Reminder/Escalation 状态推进、重复调度和终止条件结论。

- [ ] **Step 1:** 追踪 assignment rule → operator/status → notification/reminder/escalation intent → System Management 的完整链路。
- [ ] **Step 2:** 验证 team 范围、无有效责任人、append/replace、重复分派、最大提醒次数、零次无限语义、升级层推进、终态停止、时钟边界、通知失败和日志脱敏。
- [ ] **Step 3:** 检查测试是否同时断言 Alert、ReminderTask/EscalationTask、outbox、通知 payload 和重复执行结果。
- [ ] **Step 4:** 在 `server/` 使用统一环境运行列出的十一个测试文件，并增加 `--cov=apps.alerts.common.assignment --cov=apps.alerts.common.notify --cov=apps.alerts.service.reminder_service --cov=apps.alerts.service.escalation_service --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0，并明确真实 System Management 投递未被 Mock 证明的部分。
- [ ] **Step 5:** 完成 `05-assignment-notification-review.md`，更新台账和证据索引，校验并提交 `docs(alerts): 完成分派通知升级审查`，等待用户复查。

### Task 7: 审查 Outbox 可靠投递

**Files:**
- Create: `docs/reviews/alerts/06-outbox-delivery-review.md`
- Read: `server/apps/alerts/models/outbox.py`
- Read: `server/apps/alerts/service/outbox.py`
- Read: `server/apps/alerts/tasks/tasks.py`
- Read: `server/apps/alerts/config.py`
- Read: `server/apps/alerts/service/reminder_service.py`
- Read: `server/apps/alerts/service/escalation_service.py`
- Read: `server/apps/alerts/action/engine.py`
- Test: `server/apps/alerts/tests/test_outbox.py`
- Test: `server/apps/alerts/tests/test_notify_dispatcher.py`
- Test: `server/apps/alerts/tests/test_reminder_service.py`
- Test: `server/apps/alerts/tests/test_escalation_service.py`
- Test: `server/apps/alerts/tests/test_action_dispatch_hooks_service.py`

**Interfaces:**
- Consumes: Task 5/6 的 action、auto_assignment、notification、reminder 和 escalation 投递意图。
- Produces: pending → delivering → delivered/pending/failed 状态机、幂等键、租约、退避、Broker 恢复和副作用一致性结论。

- [ ] **Step 1:** 追踪业务事务内 enqueue、on_commit 首次派发、Worker 条件抢占、kind handler、失败退避、Beat 重扫和 delivering 租约恢复。
- [ ] **Step 2:** 验证事务回滚、Broker 首次失败、相同 key 并发、旧 Worker 终态覆盖、payload 不一致、最大尝试、永久失败、未知 kind、敏感 last_error 和 Beat 注册。
- [ ] **Step 3:** 检查测试是否证明“业务状态与投递意图同事务”“外部副作用最多一次/幂等”“崩溃后可恢复”，而不是只调用单个 service 方法。
- [ ] **Step 4:** 在 `server/` 使用统一环境运行列出的五个测试文件，并增加 `--cov=apps.alerts.service.outbox --cov=apps.alerts.models.outbox --cov=apps.alerts.tasks.tasks --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0；SQLite 无法证明的锁竞争必须列为限制和所需数据库集成测试。
- [ ] **Step 5:** 完成 `06-outbox-delivery-review.md`，更新台账和证据索引，校验并提交 `docs(alerts): 完成Outbox可靠投递审查`，等待用户复查。

### Task 8: 审查 Action 自动处置

**Files:**
- Create: `docs/reviews/alerts/07-action-remediation-review.md`
- Read: `server/apps/alerts/action/engine.py`
- Read: `server/apps/alerts/action/matcher.py`
- Read: `server/apps/alerts/action/payload.py`
- Read: `server/apps/alerts/action/resolver.py`
- Read: `server/apps/alerts/action/target_resolver.py`
- Read: `server/apps/alerts/action/handlers/base.py`
- Read: `server/apps/alerts/action/handlers/job.py`
- Read: `server/apps/alerts/models/action.py`
- Read: `server/apps/alerts/views/action.py`
- Read: `server/apps/alerts/tasks/action_tasks.py`
- Test: `server/apps/alerts/tests/test_action_engine_service.py`
- Test: `server/apps/alerts/tests/test_action_callback_views.py`
- Test: `server/apps/alerts/tests/test_action_execution_views.py`
- Test: `server/apps/alerts/tests/test_action_rule_views.py`
- Test: `server/apps/alerts/tests/test_action_target_resolve_service.py`
- Test: `server/apps/alerts/tests/test_action_resolver_pure.py`
- Test: `server/apps/alerts/tests/test_job_handler_service.py`
- Test: `server/apps/alerts/tests/test_job_script_rpc_service.py`
- Test: `server/apps/alerts/tests/test_manual_trigger_views.py`
- Test: `server/apps/alerts/tests/test_action_audit_service.py`
- Test: `server/apps/alerts/tests/bdd/test_action_engine_bdd.py`

**Interfaces:**
- Consumes: Task 5 的 lifecycle event 和 Task 7 的 action outbox。
- Produces: rule/alert 有效租户交集、远程执行授权、ActionExecution 状态机、手工幂等、callback 和错误契约结论。

- [ ] **Step 1:** 追踪 lifecycle/outbox/manual trigger → ActionEngine → matcher → handler → Job Management → signed callback → ActionExecution 的完整链路。
- [ ] **Step 2:** 验证 alert.team ∩ rule.team、空 team、同 IP 跨租户目标、脚本详情权限、skip_permission、重复自动/手工触发、同步配置失败、Celery 失败、callback 签名、job_task_id 绑定、重复和乱序 callback。
- [ ] **Step 3:** 检查测试是否断言零越权 RPC、唯一远程执行、Execution 真实终态、API result 与任务状态一致，以及日志不含脚本/凭据/命令输出。
- [ ] **Step 4:** 在 `server/` 使用统一环境运行列出的十一个测试文件，并增加 `--cov=apps.alerts.action --cov=apps.alerts.models.action --cov=apps.alerts.views.action --cov=apps.alerts.tasks.action_tasks --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0；真实 Job RPC/callback 网络边界未覆盖部分逐项记录。
- [ ] **Step 5:** 完成 `07-action-remediation-review.md`，更新台账和证据索引，校验并提交 `docs(alerts): 完成Action自动处置审查`，等待用户复查。

### Task 9: 审查 Incident 事故协同

**Files:**
- Create: `docs/reviews/alerts/08-incident-collaboration-review.md`
- Read: `server/apps/alerts/views/incident.py`
- Read: `server/apps/alerts/views/incident_update.py`
- Read: `server/apps/alerts/serializers/incident.py`
- Read: `server/apps/alerts/serializers/incident_update.py`
- Read: `server/apps/alerts/service/incident_operator.py`
- Read: `server/apps/alerts/filters/incident.py`
- Read: `server/apps/alerts/models/models.py`
- Test: `server/apps/alerts/tests/test_incident_alert_views.py`
- Test: `server/apps/alerts/tests/test_incident_update_views.py`
- Test: `server/apps/alerts/tests/test_incident_update_views_extra.py`
- Test: `server/apps/alerts/tests/test_incident_operator.py`
- Test: `server/apps/alerts/tests/test_incident_serializer_methods.py`
- Test: `server/apps/alerts/tests/test_filters.py`

**Interfaces:**
- Consumes: Task 3–5 的 Alert 状态，以及 Alerts 共享权限 helper 计算的当前团队可见范围。
- Produces: Incident CRUD、Alert 关联、批量 operator、错误响应和操作日志的一致性结论。

- [ ] **Step 1:** 追踪 list/detail/create/update/add/remove/operator 到授权 queryset、serializer、M2M 写入和 operator log。
- [ ] **Step 2:** 验证 list/detail/action 权限一致性、跨团队 ID 枚举、错误标题泄露、合法关联替换、重复 add/remove、部分成功、批量操作事务、Incident 与 Alert team 关系和审计失败行为。
- [ ] **Step 3:** 检查测试是否覆盖所有六个入口的授权正反路径、数据库关联结果、稳定错误契约和敏感字段不回显。
- [ ] **Step 4:** 在 `server/` 使用统一环境运行列出的六个测试文件，并增加 `--cov=apps.alerts.views.incident --cov=apps.alerts.views.incident_update --cov=apps.alerts.service.incident_operator --cov=apps.alerts.serializers.incident --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0，授权和关联核心路径覆盖率达到目标或列出明确缺口。
- [ ] **Step 5:** 完成 `08-incident-collaboration-review.md`，更新台账和证据索引，校验并提交 `docs(alerts): 完成事故协同审查`，等待用户复查。

### Task 10: 审查跨模块生产边界

**Files:**
- Create: `docs/reviews/alerts/09-cross-module-boundaries-review.md`
- Read: `server/apps/alerts/utils/permission_scope.py`
- Read: `server/apps/alerts/utils/queryset.py`
- Read: `server/apps/alerts/error.py`
- Read: `server/apps/alerts/config.py`
- Read: `server/apps/alerts/tasks/tasks.py`
- Read: `server/apps/alerts/models/models.py`
- Read: `server/apps/alerts/nats/nats.py`
- Read: `server/apps/core/utils/viewset_utils.py`
- Test: `server/apps/alerts/tests/test_permission_scope.py`
- Test: `server/apps/alerts/tests/test_nats_handlers.py`
- Test: `server/apps/alerts/tests/test_notification_log_security.py`
- Test: `server/apps/alerts/tests/test_queryset_batching.py`
- Test: `server/apps/alerts/tests/test_serializers_and_scope.py`
- Test: `server/apps/alerts/tests/test_models.py`

**Interfaces:**
- Consumes: Task 2–9 的 Findings、未验证项和职责边界观察。
- Produces: 权限、事务、错误映射、callback builder、资源上限、日志和扩展成本的横切结论；只新增此前未报告的主 Finding。

- [ ] **Step 1:** 建立 HTTP/NATS/Celery/callback 的权限、错误、状态和日志契约矩阵，标明每项由 framework、service、adapter、task orchestration、callback builder 或 error mapper 承担。
- [ ] **Step 2:** 主动搜索重复 callback payload、重复错误映射、重复状态判断、布尔参数多行为、隐式 fallback、无界 QuerySet/批次、原生 SQL、敏感日志和测试专用生产分支。
- [ ] **Step 3:** 回答设计规定的八项 Maintainability Verdict；新增插件、错误类型或 callback 模式若需跨多个无关模块复制，必须定位具体复制链路。
- [ ] **Step 4:** 在 `server/` 使用统一环境运行列出的六个测试文件，并增加 `--cov=apps.alerts.utils --cov=apps.alerts.nats.nats --cov=apps.alerts.tasks.tasks --cov-report=term-missing -o addopts='' -q`。Expected: 退出码 0；跨数据库 JSON、真实 Broker 和外部 RPC 限制写入报告。
- [ ] **Step 5:** 完成 `09-cross-module-boundaries-review.md`，更新台账和证据索引，校验并提交 `docs(alerts): 完成跨模块生产边界审查`，等待用户复查。

### Task 11: 全量验证与最终索引

**Files:**
- Modify: `docs/reviews/alerts/00-overview.md`
- Modify: `docs/reviews/alerts/evidence-index.md`
- Read: `docs/reviews/alerts/01-ingress-governance-review.md`
- Read: `docs/reviews/alerts/02-alert-detection-generation-review.md`
- Read: `docs/reviews/alerts/03-recovery-auto-close-review.md`
- Read: `docs/reviews/alerts/04-alert-lifecycle-review.md`
- Read: `docs/reviews/alerts/05-assignment-notification-review.md`
- Read: `docs/reviews/alerts/06-outbox-delivery-review.md`
- Read: `docs/reviews/alerts/07-action-remediation-review.md`
- Read: `docs/reviews/alerts/08-incident-collaboration-review.md`
- Read: `docs/reviews/alerts/09-cross-module-boundaries-review.md`

**Interfaces:**
- Consumes: 九份已由用户逐模块复查的报告、主 Finding 和测试证据。
- Produces: 去重后的严重级别汇总、跨模块依赖、最终 Recommendation 和可复查的全量测试证据。

- [ ] **Step 1: 复核 Finding 唯一性和字段完整性**

运行：`rg -n '^### (ALERTS-F[0-9]+|Finding [0-9]+):|^- (Severity|Location|Root cause category|Evidence|Trigger|Impact|Why existing tests missed it|Minimal safe fix|Required tests|Long-term design note):' docs/reviews/alerts/0[1-9]-*.md`。

Expected: 每个主 Finding 只有一个定义；每个 Finding 的十个字段全部存在。无 Finding 的报告明确写“未发现 P0/P1/P2 阻断问题”。

- [ ] **Step 2: 运行 Alerts 全量测试和覆盖率**

在 `server/` 运行：

```bash
MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,alerts DB_ENGINE=sqlite DB_NAME=/private/tmp/bklite-alerts-review.sqlite3 ENABLE_CELERY=true CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory:// uv run pytest -q -o addopts='' apps/alerts/tests --cov=apps.alerts --cov-report=term-missing
```

Expected: 命令退出码为 0；记录通过/失败/跳过数量和 `apps.alerts` 总覆盖率。任何失败都按产品、测试或环境分类，不能用旧的“972 passed”历史结果替代本次证据。

- [ ] **Step 3: 汇总覆盖率和未验证边界**

在 `evidence-index.md` 汇总九模块覆盖率、低于 80% 的文件、核心路径低于 90% 的原因，以及 SQLite、Mock RPC、内存 Broker 无法证明的生产语义。

- [ ] **Step 4: 完成最终 Recommendation**

在 `00-overview.md` 更新九模块状态和 P0/P1/P2/P3 数量，列出跨模块依赖、阻断项和最终 Approve、Approve with minor comments、Request changes 或 Block。不得从报告摘要新增无证据 Finding。

- [ ] **Step 5: 自审并提交最终索引**

运行：`rg -n '稍后处理|补充内容|占位内容|信息缺失' docs/reviews/alerts` 和 `git diff --check`。

Expected: 无占位符、无空白错误、九份报告均被总览链接。提交：

```bash
git add docs/reviews/alerts/00-overview.md docs/reviews/alerts/evidence-index.md
git commit -m "docs(alerts): 汇总全模块生产级审查结论"
```

## Plan Self-Review

- Spec coverage: Task 1 建立基线和证据索引；Task 2–10 覆盖设计中的九个模块；Task 11 覆盖全量验证、去重和最终索引。
- Scope: 所有写入均限制在 `docs/reviews/alerts/`；生产代码和测试只读。
- Evidence: 每个模块都包含 CodeGraph 调用链、业务风险检查、测试有效性审查、定向 pytest、覆盖率、报告和用户复查门禁。
- Type and naming consistency: 报告编号 01–09、Finding ID `ALERTS-FNN`、状态表和证据索引命名在所有任务中一致。
- Execution boundary: Review 发现只登记和报告；修复、回归测试实现和长期重构均不在本计划范围。

## specs: 2026-07-14-alerts-production-module-review-design.md

## 1. 背景与目标

`server/apps/alerts/ARCHITECTURE.md` 是 Alerts 当前业务与技术架构的单一入口。本次工作以当前分支 `server/apps/alerts/` 全量代码为基线，按照架构图描述的 Event → Alert → Incident 端到端链路，对每个大模块进行生产级代码 Review。

本次 Review 的目标不是风格点评，也不是通过测试寻找局部补丁，而是确认当前实现是否具备长期可维护的生产质量。所有结论必须可验证、可排序、可复查，并覆盖业务行为、跨层契约、状态机、错误模型、并发幂等、资源边界、职责边界和测试有效性。

## 2. 已确认约束

- 审查基线：当前分支 `server/apps/alerts/` 全量代码，不局限于最近提交。
- 交付节奏：每完成一个大模块，独立交付该模块 Review 报告，用户复查后再进入下一模块。
- 验证深度：静态调用链审查、定向测试和对应模块覆盖率验证。
- 报告位置：`docs/reviews/alerts/NN-<module>-review.md`，同时在对话中交付结论。
- 审查阶段只修改 Review 文档，不修改 Alerts 生产代码，不自动修复 Finding。
- 本次不创建 Alerts 专属 OpenSpec change；若后续用户决定修复，另行进入提案和实现流程。

## 3. 审查方法选择

采用端到端业务链路顺序，而不是风险优先或纯技术分层顺序。该方法能把入口、状态变化、持久化、异步副作用、外部依赖和最终可观察结果放在同一条证据链中，更适合发现跨层契约、状态机和错误传播问题。

每个模块内部仍执行统一的风险检查清单。跨模块问题只在根因所属模块定义一次，其他模块通过 Finding 编号引用，避免重复计数和修复建议分叉。

## 4. 模块边界与交付顺序

### 4.1 事件接入与治理

主要范围包括 `views/receiver.py`、`nats/nats.py` 和 `common/source_adapter/`。审查来源认证、参数校验、字段映射、标准化、事件标识、幂等、CMDB 丰富、屏蔽、Event 入库和接入结果契约。

### 4.2 告警检测与生成

审查即时告警、周期聚合、缺失检测、Alert Builder、Synthetic Alert Builder 和活跃指纹租约，重点验证三条建警入口是否共享相同并发裁决和生命周期约束。

### 4.3 恢复与自动关闭

审查恢复复合键、恢复事件关联、终态转换、会话超时、自动关闭、提醒与升级停止以及活跃指纹释放。

### 4.4 Alert 生命周期

审查生命周期事件分发、显式状态变化、副作用触发，以及各建警和状态更新入口是否统一进入生命周期服务。

### 4.5 分派、通知、提醒与升级

审查自动与手动分派、有效责任人计算、通知构造、ReminderTask、升级状态、重复调度和终止条件。

### 4.6 Outbox 可靠投递

审查业务状态与投递意图的事务一致性、幂等键、条件抢占、租约恢复、重试退避、失败终态、Broker 首次派发失败和 Worker 崩溃恢复。

### 4.7 Action 自动处置

审查规则匹配、租户交集、目标解析、脚本读取、作业下发、手工触发、ActionExecution 状态机、签名 callback 和重复 callback。

### 4.8 Incident 事故协同

审查 CRUD、告警关联、授权范围、状态变化、错误响应和操作日志。

### 4.9 跨模块生产边界

汇总检查权限语义、事务边界、资源上限、日志脱敏、错误模型、可观测性、外部依赖边界和新增插件扩展成本。本模块只补充前八个模块未覆盖的横切问题，不重复既有 Finding。

## 5. 单模块证据循环

每个模块执行以下固定循环：

1. 从架构文档声明的业务契约出发，确定入口、服务、领域对象、模型、异步任务、外部依赖和测试。
2. 优先使用 CodeGraph 建立真实调用链，再补读索引未覆盖的配置、测试、动态注册和数据驱动逻辑。
3. 沿成功、失败、权限拒绝、重复执行、并发、重试、超时、清理和回滚路径检查实际行为。
4. 对候选问题构造确定的触发输入和前置状态，确认 API、数据库、任务、外部副作用或日志中的可观察结果。
5. 反查现有测试，指出未覆盖路径、无效断言、过度 Mock 或错误契约锁定的具体位置。
6. 能安全执行时运行定向测试与覆盖率；环境无法证明的语义必须明确记录验证边界。
7. 仅在证据闭环后形成正式 Finding。

只有怀疑、无法建立触发路径或仅属于个人编码偏好的内容，不进入 Findings。它们可作为审查过程笔记，但不能影响严重级别和合并建议。

## 6. 根因与架构职责

每个 Finding 必须先归入以下根因之一：

1. 局部实现错误
2. 跨层契约不一致
3. 状态机设计缺陷
4. 错误模型不清晰
5. 重复逻辑导致的不一致
6. 资源边界缺失
7. 并发或幂等设计问题
8. 架构职责放置错误

若根因属于跨模块契约、状态模型、错误模型、重复逻辑或职责边界，不使用新增条件判断掩盖结构问题。报告必须指出逻辑应归属的层级：framework、service、adapter、plugin、task orchestration、callback builder、error mapper 或 test fixture。

结构性问题同时给出：

- 最小安全修复：控制当前生产风险，范围可在后续修复任务内落地。
- 推荐长期设计：消除结构性根因，但不在本轮 Review 自动实施。
- 影响范围与取舍：明确两种方案的修改面、风险和迁移成本。

## 7. Finding 准入和严重级别

正式 Finding 必须同时具备：

- 精确到文件、函数、类或调用链的位置。
- 当前代码的确定行为。
- 可复现的输入、状态或执行路径。
- 外部可观察后果。
- 缺陷成立的客观原因，而非个人偏好。
- 现有测试未阻止问题的代码级原因。
- 当前范围内可执行的最小安全修复。
- 能证明业务行为的回归测试要求。

严重级别按 P0、P1、P2、P3 排序：

- P0：数据丢失、权限绕过、敏感信息泄露、任务错误成功、不可恢复副作用、远程执行风险或可轻易触发的资源耗尽。
- P1：状态不一致、幂等失败、callback 契约破坏、错误失真、超时清理缺失或核心业务路径缺少回归证明。
- P2：重复逻辑、扩展需复制、错误映射散落、接口易误用、排障能力不足或潜在日志泄露。
- P3：不影响核心正确性的命名、局部可读性和小范围结构改进。

发现 P0 时立即停止当前模块后续审查并交付阻断证据。P1 在完成当前模块证据闭环后立即交付，不延迟到最终汇总。

## 8. 测试审查与覆盖率

### 8.1 测试映射

为每个模块建立“业务路径 → 生产代码 → 测试文件 → 关键断言”映射。测试必须证明业务状态、外部可观察行为、任务生命周期、callback 一致性、幂等、超时清理、异常传播、安全边界、资源边界和兼容性。

以下测试不能作为有效质量证明：

- 无有效断言或只断言对象非空。
- 只验证 Mock 被调用，不验证业务结果。
- 重复覆盖同一路径。
- 绑定私有实现细节。
- 对内部每行机械 Mock，绕过真实状态与外部边界。

### 8.2 定向验证环境

优先使用隔离 SQLite、Celery 内存 broker/backend 和测试 MinIO 配置运行对应测试，避免本地 Redis 等环境依赖污染结果。SQLite 无法证明的数据库竞争、锁、JSON 方言和约束语义，以及被 Mock 的 RPC/Broker 行为，必须在报告中列为验证限制，不能推断为已验证。

### 8.3 覆盖率规则

- 相关模块生产文件行覆盖率目标不低于 80%。
- 核心业务路径覆盖率目标不低于 90%。
- 高风险或新增分支必须有行为测试。
- 不能覆盖的分支逐条说明原因。

覆盖率只用于定位未执行路径。即使数字达标，如果关键断言无效、Mock 掩盖真实行为或测试锁定错误契约，Test Review 仍判定不通过。

### 8.4 回归测试要求

每个 P0/P1 Finding 必须列出明确的回归用例，包括前置状态、输入、预期数据库状态、外部副作用、任务结果和重复执行结果。本轮只提出测试要求，不写修复测试或生产代码。

## 9. 报告格式

每份模块报告严格按以下顺序输出：

1. Summary
2. Findings，按 P0 → P1 → P2 → P3 排序
3. Test Review
4. Maintainability Verdict
5. Recommendation：Approve、Approve with minor comments、Request changes 或 Block

每个 Finding 使用以下字段：

```text
### Finding N: 标题

- Severity:
- Location:
- Root cause category:
- Evidence:
- Trigger:
- Impact:
- Why existing tests missed it:
- Minimal safe fix:
- Required tests:
- Long-term design note:
```

若模块没有有效 Finding，明确写“未发现 P0/P1/P2 阻断问题”，不制造低价值问题。每份报告还包含审查范围、排除项、已验证调用链、测试命令与结果摘要、覆盖率、未覆盖分支、跨模块引用和环境限制。

## 10. 可维护性裁决

每个模块必须从未来维护者角度回答：

1. 六个月后其他开发者能否快速理解逻辑？
2. 新增同类插件是否需要复制现有代码？
3. 新增错误类型是否需要修改多个模块？
4. 新增 callback 模式是否容易扩展？
5. 当前接口是否容易被误用？
6. 日志是否足以排障且不会泄露敏感数据？
7. 状态异常时是否能判断任务停在哪个阶段？
8. 当前设计是在降低系统复杂度，还是将问题移动到其他位置？

任一答案为否时，报告必须指出剩余设计缺陷及其归属层。

## 11. 执行控制与复查基线

- 每个模块以生成报告时的 Git commit 和工作区状态作为复查基线。
- 发现已登记缺陷时先确认当前代码是否仍可复现；已修复问题不重复上报。
- 确认新缺陷后按项目规则立即登记 projectmem，再继续证据闭环。
- 测试失败必须区分产品缺陷、测试缺陷和环境限制。
- 每份报告完成后先由用户复查，再进入下一模块。
- 第九模块完成后生成报告索引，汇总报告路径、严重级别和跨模块依赖，但不创建新的重复 Finding。

## 12. 完成标准

本次 Review 在以下条件全部满足后完成：

- 九个模块均有独立报告。
- 每个 Finding 均满足证据准入要求并按严重级别排序。
- 每个模块均完成测试有效性审查和可执行范围内的定向验证。
- 覆盖率数字、未覆盖分支和环境限制均有记录。
- P0/P1 均有明确回归测试要求。
- 跨模块问题有唯一根因归属和可复查引用。
- 最终索引能让维护者从架构模块追溯到代码、测试、Finding 和建议。
