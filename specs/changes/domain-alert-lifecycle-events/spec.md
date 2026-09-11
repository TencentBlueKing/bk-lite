# 监控 / 日志 / APM 告警生命周期事件

Status: complete

## Completion Evidence

- 三域认领 / 分派在既有单一服务入口与 `handlers` 同一事务写入 `claimed` / `assigned`；拒绝请求不落行。监控 unique 仍只覆盖 `triggered` / `recovered` / `closed`。APM 认领 / 分派直接插 `ApmEvent`，不走评估写事件、不建 Event Snapshot。
- 日志 `Event.action` 可空；历史空 action 视为命中。页面关闭与删策略关单写 `closed`，二次关闭不加倍。扫描 / 通知补偿 / last_event / 热力图 / raw log 只看命中行。
- 监控 / APM 关闭与恢复仍走原路径，614 不插第二条。原因是结构化审计文案，未新增必填弹窗。
- 详情事件序列展示认领 / 分派；APM 指标快照图仍只用扫描点。capability / 术语表已改写 613「认领 / 分派不写事件」。
- 测试：`apps/monitor/tests/test_alert_handlers.py`、`test_alert_lifecycle_events.py`、`test_monitor_alert_view.py`；`apps/apm/tests/test_alert_handlers.py`、`test_alert_snapshot_api.py`；`apps/log/tests/test_alert_handlers.py`、`test_policy_alert_actions_views.py`、`test_alert_organization_snapshot.py`、`test_policy_destroy_atomic_3948.py`；前端 `event.actionMap.test.tsx`、`alertDetail.eventTimeline.test.tsx`（监控 / 日志）、`alertHandlerUtils.test.ts`、`alertDetail.eventStream.test.tsx`。
- 验证（2026-09-09）：后端针对本规格测试文件，本机 Postgres `--reuse-db` 100 passed；sqlite `--nomigrations --create-db` 同集 100 passed（仓库既有 `alerts.0009` / `NewSessionEventRelation.event` 阻断全量 migrate）。前端 vitest：监控 / 日志时间线、APM 事件流与 `page.test.tsx`（含认领行不拉 Event Snapshot）、`alertHandlerUtils`、`event.actionMap` 均通过。本机 HTTPS `8443` 对监控 / 日志 / APM 各认领一条空处理人活跃告警：200 且详情事件出现 `claimed`；二次认领 409；日志 `last_event` 仍返回命中空 action；APM 认领后状态仍为 active，认领 `event_id` 的 event-evidence 为 0 条。

## Problem Statement

613 已经让监控、日志、APM 的空处理人活跃告警可以认领、分派和关闭，但这些动作不会出现在告警详情的事件序列里。监控和 APM 能看到触发、升级、恢复、关闭；日志连手动关闭都不写事件。值班无法在本模块核对「谁认领了、分给了谁、何时关掉」，只能看当前处理人字段。

## Solution

认领、分派、自动恢复、手动关闭发生时，往该域现有事件表追加一条不可变生命周期事件，并在告警详情已有的事件序列里展示。原因是结构化说明（谁、做了什么、处理人变成谁），不新增必填原因弹窗。创建时快照策略处理人仍不是分派，不写事件。三域各自实现，不抽公共库。事件页就是各域告警详情里的事件序列，不新开独立页。

## User Stories

1. As a 值班人, I want 认领成功后在告警详情事件序列里看到一条认领, so that 我能核对是谁把空单接走的
2. As a 值班人, I want 手工分派成功后看到一条分派，并看得出被分派人, so that 交班有据可查，而不只改处理人字段
3. As a 值班人, I want 监控 / APM 的自动恢复和手动关闭继续出现在同一条事件序列里, so that 全生命周期和认领 / 分派在同一处看
4. As a 日志值班人, I want 手动关闭（含删策略导致的关单）也出现在事件序列里, so that 日志告警的收尾和监控一样可审计
5. As a 值班人, I want 事件上的「原因」是谁做了什么、处理人变成谁, so that 我不必每次认领或关单再填一段话
6. As a 日志值班人, I want 关键字 / 聚合命中仍按命中事件看原始日志，认领 / 分派 / 关闭不会当成一条命中, so that 生命周期行打不开 raw log、也不污染命中热力图
7. As a 已经有处理人的告警的操作者, I want 第二次认领或分派仍然失败且不追加事件, so that 审计行不会在拒绝请求上出现

## Implementation Decisions

- 614 是 613 同一条领域告警闭环的审计面，不是新对象、不是告警中心时间线、不是独立操作日志。处理人语义、空单才能认领 / 分派、创建快照不是分派，全部继承 `domain-alert-handlers-assignment`。
- 三域各自往本域事件表写行，不抽 `domain_alert_*` 公共库。监控用 `MonitorEvent`，APM 用 `ApmEvent`，日志用现有 `Event` 并补 `action`。
- 新增动作名三域对齐：`claimed`、`assigned`。已有 `triggered` / `escalated` / `recovered` / `closed` 保持原义。监控对 `triggered` / `recovered` / `closed` 的「每告警每动作一条」唯一约束不得扩到 `claimed` / `assigned`。
- 「原因」是结构化审计，写入事件内容：认领记操作者与处理后的 `handlers`；分派记分派人与被分派人名单；关闭沿用监控已有的操作者与可选原因拼接，日志 / APM 不新开原因框；恢复是系统动作，无操作人。不新增原因字段，也不改认领 / 分派 / 关闭 API 要 body 填原因。
- 认领 / 分派只允许写在 613 已收敛的各域单一服务入口里，且必须与处理人名单更新同一事务：名单写成则事件写成，事件失败则整次认领 / 分派回滚。分派通知仍在提交后 `on_commit` 发送，通知失败不删审计行。
- 创建告警快照策略处理人、认领，都不发分派通知，也不把创建写成 `assigned`。
- 监控 / APM 的恢复和关闭已经写事件：614 不在原关闭 / 恢复路径再插一条。日志今天关闭只改告警状态，须在所有把活跃告警置为关闭的入口（页面关闭、策略删除）补写 `closed`，与监控已落地的关闭入口对齐。
- 日志域没有自动恢复状态机。614 不给日志发明恢复；没有 `recovered` 路径就不写 `recovered`。
- 日志 `Event` 同时承载命中和生命周期。历史无 `action` 的行视为命中，不做回填。详情里的命中热力图和原始日志只看命中事件；生命周期行用动作标签出现在同一序列，点击不打开 raw log。
- APM 认领 / 分派必须单独插入 `ApmEvent`，禁止走评估侧写事件入口。那条路径会改告警状态并 stage 事件快照。认领 / 分派不创建 `ApmEventSnapshot`，也不在指标快照图上打点。事件标识必须按发生次唯一，不得复用评估侧「告警 + 动作 + 级别」那种会和触发撞车的键。
- 事件查询仍走各域现有按告警列事件的接口，增加或暴露 `action`。权限与「能看见这条告警」相同，不新增权限点。
- 页面：监控详情时间线补认领 / 分派文案；APM 详情事件列表同样展示；日志详情事件列表增加动作列。不新开事件页，不回填历史认领 / 分派 / 日志关闭。
- 落地时改写 613 写进功能清单和 `apm-alerting.md` 的「认领 / 分派不写事件」；监控 / APM 术语表中事件动作补上认领与分派。不回写告警中心，不新增对外 OpenAPI。

## Testing Decisions

- 只测对外行为：给定认领、分派、关闭或恢复后，告警状态与 `handlers` 不变坏，事件列表出现对应 `action` 与结构化内容；拒绝请求不新增事件。不测内部如何拼 content 字符串。
- 最高接缝是各域现有认领 / 分派服务、关闭入口、监控 / APM 自动恢复扫描，以及告警详情事件查询。沿用 613 的 handler 测试和监控生命周期事件测试，改期望并补动作，不另起平行框架。
- 必须覆盖：空单认领成功有一条 `claimed`，第二次 409 且仍只有一条；分派成功有一条 `assigned`，内容能看出被分派人；创建告警不写 `assigned` / `claimed`；监控 / APM 关闭与恢复条数不因 614 加倍；日志页面关闭和删策略关单各写出 `closed`；APM 认领 / 分派后没有新的事件快照、告警仍是活跃；日志命中事件仍能看 raw log，生命周期行不能；并发第二个认领失败且不落第二行。
- 前端锁定：监控 / APM / 日志详情能展示认领与分派文案；日志热力图或 raw log 不把 `claimed` / `assigned` / `closed` 当命中。

## Out of Scope

- 关单 / 认领 / 分派必填原因弹窗。
- 日志自动恢复，或把日志告警状态改成与监控一样的 `recovered`。
- 转派、升级、认领通知、创建当分派。
- 回填历史事件、历史 `operator`、历史关闭。
- 告警中心时间线同步，或领域侧复制告警中心状态机。
- 把三域 Event 收成跨 App 统一表。
- 新增对外 OpenAPI。

## Further Notes

协同规格：`specs/changes/domain-alert-handlers-assignment/spec.md`（613，Status: complete）。监控状态变更收薄见 `specs/changes/monitor-alert-lifecycle-events/spec.md`；614 只在那份契约上追加认领 / 分派，不改「扫描流水不再写成 Event」。p398_614 原文要的「事件页」按本仓库实现，就是告警详情事件序列。复验跟进见 `specs/changes/domain-alert-handlers-followup/spec.md`。
