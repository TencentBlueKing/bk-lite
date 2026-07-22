# Historical Superpowers change: 2026-07-13-alerts-production-review-fixes

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-13-alerts-production-review-fixes.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 alerts 生产级 Review 已确认的权限、数据一致性、错误契约、可靠投递、资源边界和可观测性缺陷。

**Architecture:** 先把 JSON 团队范围、有效执行团队和生命周期分发收口为 alerts 公共服务，再用复合业务键和数据库约束保证恢复/建警幂等。跨事务异步副作用通过持久化 outbox 记录承接，调用入口只提交业务状态和投递意图，由 Celery 重试消费。

**Tech Stack:** Python 3.12、Django 4.2、DRF、Django ORM、Celery、pytest/pytest-django、SQLite 多方言回归。

## Global Constraints

- 所有缺陷严格按 RED → GREEN → REFACTOR 执行，失败测试必须先证明旧行为。
- 禁止 raw SQL、`.raw()`、`RawSQL`、`cursor.execute`。
- 权限拒绝不得泄露跨团队对象标题、脚本内容或远程执行能力。
- P0/P1 修复必须有外部可观察行为、异常路径、重复执行和事务边界测试。
- 相关模块行覆盖率不低于 80%，核心业务路径覆盖率不低于 90%。

---

### Task 1: 统一 alerts 团队授权与多数据库 JSON 过滤

**Files:**
- Modify: `server/apps/alerts/utils/permission_scope.py`
- Modify: `server/apps/core/utils/viewset_utils.py`
- Modify: `server/apps/alerts/nats/nats.py`
- Test: `server/apps/alerts/tests/test_permission_scope.py`
- Test: `server/apps/alerts/tests/test_nats_handlers.py`

**Interfaces:**
- Produces: `apply_team_scope_with_group_ids(queryset, group_ids, field_name="team") -> QuerySet`
- Produces: 权限查询从空 `Q()` 开始，只 OR 权限系统返回的 team/instance，不默认授予 current_team 全量数据。

- [ ] 写 SQLite JSONField、instance-only、team-only、superuser、无授权的失败测试。
- [ ] 运行聚焦测试，确认旧代码分别触发 `NotSupportedError` 与 current-team 越权。
- [ ] 让 GenericViewSetFun 与 NATS 复用同一跨数据库团队过滤语义。
- [ ] 重跑权限聚焦测试并确认通过。

### Task 2: Action/Job/Enrichment 租户边界

**Files:**
- Modify: `server/apps/alerts/views/action.py`
- Modify: `server/apps/alerts/action/engine.py`
- Modify: `server/apps/alerts/action/handlers/job.py`
- Modify: `server/apps/alerts/action/target_resolver.py`
- Modify: `server/apps/alerts/views/enrichment.py`
- Modify: `server/apps/alerts/enrichment/engine.py`
- Modify: `server/apps/alerts/enrichment/providers/base.py`
- Modify: `server/apps/alerts/enrichment/providers/cmdb.py`
- Test: `server/apps/alerts/tests/test_action_views.py`
- Test: `server/apps/alerts/tests/test_action_handlers.py`
- Test: `server/apps/alerts/tests/test_enrichment_engine.py`

**Interfaces:**
- Produces: `resolve_effective_team(alert_team, rule_team) -> list[int]`，无交集时拒绝执行，空规则团队不得放大范围。
- Produces: provider `fetch_batch(keys, config, context=None)`，context 包含授权 `team_ids`。

- [ ] 写规则/执行记录越权、脚本详情越权、同 IP 跨团队节点、跨团队丰富和缓存隔离失败测试。
- [ ] 确认旧代码能读取/执行/丰富越权对象。
- [ ] 在 API、Engine、Handler、Provider 全链路传递同一有效团队集合。
- [ ] 重跑聚焦测试并确认拒绝路径零外部 RPC 调用。

### Task 3: Incident 授权错误契约

**Files:**
- Modify: `server/apps/alerts/views/incident.py`
- Test: `server/apps/alerts/tests/test_incident_alert_views.py`

**Interfaces:**
- Produces: 关联告警校验只返回无权访问的 ID，不查询或回显未授权标题。

- [ ] 写合法 update(alert) 成功和非法 ID 不泄露标题的失败测试。
- [ ] 确认旧代码合法请求固定 400，非法请求响应含跨团队标题。
- [ ] 仅在 unauthorized 集合非空时返回稳定 400 错误码/ID。
- [ ] 重跑 create/update/add/remove 全路径。

### Task 4: 恢复复合关联键与活跃告警数据库幂等

**Files:**
- Modify: `server/apps/alerts/aggregation/recovery/recovery_handler.py`
- Modify: `server/apps/alerts/aggregation/recovery/recovery_checker.py`
- Modify: `server/apps/alerts/aggregation/builder/alert_builder.py`
- Modify: `server/apps/alerts/aggregation/processor/instant_dispatcher.py`
- Modify: `server/apps/alerts/aggregation/builder/synthetic_alert_builder.py`
- Modify: `server/apps/alerts/models/models.py`
- Create: `server/apps/alerts/migrations/0021_alert_active_fingerprint_and_outbox.py`
- Test: `server/apps/alerts/tests/test_recovery_handler.py`
- Test: `server/apps/alerts/tests/test_alert_builder.py`
- Test: `server/apps/alerts/tests/test_instant_dispatcher.py`

**Interfaces:**
- Produces: 恢复键 `(source_id, push_source_id, external_id, team)`。
- Produces: 数据库唯一活跃指纹租约，周期、即时、缺失检测共用原子 claim/release。

- [ ] 写跨 source/team 同 external_id 不恢复和并发首次建警只产生一条的失败测试。
- [ ] 确认旧代码错误关联并允许重复建警。
- [ ] 用 ORM 事务、唯一约束和 IntegrityError 重读实现最小原子路径。
- [ ] 重跑三种建警入口与恢复回归。

### Task 5: 生命周期钩子与接入处理结果

**Files:**
- Modify: `server/apps/alerts/service/alert_lifecycle.py`
- Modify: `server/apps/alerts/common/source_adapter/base.py`
- Modify: `server/apps/alerts/views/receiver.py`
- Modify: `server/apps/alerts/nats/nats.py`
- Modify: `server/apps/alerts/aggregation/processor/instant_dispatcher.py`
- Modify: `server/apps/alerts/aggregation/builder/synthetic_alert_builder.py`
- Test: `server/apps/alerts/tests/test_action_lifecycle_hooks_service.py`
- Test: `server/apps/alerts/tests/test_source_adapter.py`
- Test: `server/apps/alerts/tests/test_receiver_views.py`

**Interfaces:**
- Produces: `dispatch_alert_lifecycle(alert_ids, event_name)` 作为唯一生命周期入口。
- Produces: `IngestResult(received, accepted, duplicate, skipped, errored, batches)`。

- [ ] 写 instant/synthetic created 分发和 HTTP/NATS 部分/全部丢弃响应失败测试。
- [ ] 确认旧代码漏分发且固定 success。
- [ ] 统一生命周期入口并返回结构化接入结果；全部失败使用非 2xx/`result=False`。
- [ ] 重跑三类建警和两类接入回归。

### Task 6: 任务错误传播与手工动作幂等

**Files:**
- Modify: `server/apps/alerts/tasks/tasks.py`
- Modify: `server/apps/alerts/tasks/action_tasks.py`
- Modify: `server/apps/alerts/views/action.py`
- Test: `server/apps/alerts/tests/test_aggregation_beat_lock.py`
- Test: `server/apps/alerts/tests/test_action_dispatch_hooks_service.py`
- Test: `server/apps/alerts/tests/test_manual_trigger_views.py`

**Interfaces:**
- Produces: 手工触发要求 `Idempotency-Key`，唯一键包含 operator/rule/alert/key。
- Produces: 核心 Celery 失败抛出以进入 retry/failure 状态，业务不存在可稳定 no-op。

- [ ] 写聚合失败、动作失败、重复手工请求、handler 同步失败响应测试。
- [ ] 确认旧任务被标成功、重复远程执行、view 固定 `result=True`。
- [ ] 最小修改异常传播和手工执行结果映射。
- [ ] 重跑任务与手工动作回归。

### Task 7: 持久化 outbox 承接异步副作用

**Files:**
- Create: `server/apps/alerts/models/outbox.py`
- Modify: `server/apps/alerts/models/__init__.py`
- Modify: `server/apps/alerts/tasks/tasks.py`
- Modify: `server/apps/alerts/common/notify/dispatcher.py`
- Modify: `server/apps/alerts/service/reminder_service.py`
- Modify: `server/apps/alerts/service/escalation_service.py`
- Modify: `server/apps/alerts/action/engine.py`
- Test: `server/apps/alerts/tests/test_outbox.py`
- Test: `server/apps/alerts/tests/test_notify_dispatcher.py`
- Test: `server/apps/alerts/tests/test_reminder_service.py`
- Test: `server/apps/alerts/tests/test_escalation_service.py`

**Interfaces:**
- Produces: `enqueue_outbox(kind, payload, idempotency_key)` 与 `deliver_alert_outbox(outbox_id)`。
- 状态: pending → delivering → delivered；异常回 pending/failed 并保留 attempts/last_error/next_retry_at。

- [ ] 写事务回滚不留记录、提交后 broker down 仍保留 pending、重复键单记录、重试最终 delivered 测试。
- [ ] 确认旧代码提交后 broker down 永久丢失，提醒存在重复窗口。
- [ ] 同一业务事务写 outbox，由 Celery 消费器负责实际 `.delay`/通知执行。
- [ ] 重跑通知、提醒、升级、动作生命周期测试。

### Task 8: 统计、批处理和日志资源边界

**Files:**
- Modify: `server/apps/alerts/common/shield.py`
- Modify: `server/apps/alerts/common/auto_close.py`
- Modify: `server/apps/alerts/aggregation/recovery/timeout_checker.py`
- Modify: `server/apps/alerts/tasks/tasks.py`
- Test: `server/apps/alerts/tests/test_shield.py`
- Test: `server/apps/alerts/tests/test_auto_close_extra.py`
- Test: `server/apps/alerts/tests/test_timeout_checker.py`

**Interfaces:**
- Produces: 主键游标分页，每批最多 200 条；日志只记录数量、标识符和截断摘要。

- [ ] 写屏蔽成功统计、查询批次上限、通知日志不含 content 的失败测试。
- [ ] 确认旧统计为 0、QuerySet 被 `len()` 全量加载、日志包含正文。
- [ ] update 前物化最小字段；用 `pk__gt` 游标批处理；移除原始 payload/content。
- [ ] 重跑资源边界与日志测试。

### Task 9: 完整验证

**Files:**
- Verify: `server/apps/alerts/`

- [ ] 运行全部新增/修改测试并确认 RED 已转 GREEN。
- [ ] 运行 `makemigrations --check --dry-run` 与 Django checks。
- [ ] 运行完整 `apps/alerts/tests`，区分修复前基线失败与新增回归。
- [ ] 运行覆盖率，相关模块 >=80%、核心链路 >=90%。
- [ ] 检查 `git diff --check`、敏感日志、raw SQL、未跟踪运行产物。
