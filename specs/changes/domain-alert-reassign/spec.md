# 监控 / 日志 / APM 告警转派

Status: complete

## Problem Statement

613 / 614 让三域空单可以认领、分派并写事件，但有处理人之后只能关闭。交班、分错人、策略默认处理人进单后要改人，都没有纠错口。本期补一条轻量转派，不把告警中心状态机下沉到三域。

## Solution

活跃且已有处理人的告警，由当前处理人把 `handlers` 整表替换成新名单（至少一人，可多人），与名单同一事务写一行 `reassigned` 事件，提交后按分派同口径通知新处理人。空单继续走认领 / 分派。三域各自实现，不抽公共库。

## User Stories

1. As a 当前处理人, I want 把活跃告警转派给告警所属组织里的一名或多名用户, so that 交班不必先关单
2. As a 被转派的处理人, I want 按该策略已开的人工渠道收到转派通知, so that 我知道单到了自己队列
3. As a 值班人, I want 详情事件序列看到「谁转派给了哪几个人」, so that 交班有据可查
4. As a 已经不在处理人名单里的人, I want 不能再转派这条告警, so that 处理人名单不会被旁人覆盖

## Implementation Decisions

- 转派只允许活跃且 `handlers` 非空的告警；操作者必须是当前处理人（id 或 username 命中）。权限点与认领 / 分派 / 关闭相同。
- 新名单整表替换，至少一人，可多人；校验与分派相同：存在、未禁用、属于告警所属组织。
- 事件动作三域对齐为 `reassigned`。内容为结构化审计：`{操作者} 转派给 {新处理人名单}`。与 `handlers` 同一事务，拒绝请求不落行。监控唯一约束仍不覆盖认领 / 分派 / 转派。
- 认领、分派规则不变。创建快照仍不是分派。不引入待响应 / 再认领 / 超级用户豁免 / 升级加签。
- 通知复用分派的人工渠道，接收人是新 `handlers`。监控 / 日志标题为转派；APM outbox 键必须按次唯一，不能复用 `assign:{alert_id}:channel:{id}`，否则第二次转派会静默不发。策略已删除或通知未开则跳过。
- 日志 `reassigned` 不当命中；APM 不走评估写事件、不建 Event Snapshot、不上指标图、分布图排除转派。
- 前端：空单显示认领 / 分派；当前处理人的活跃告警显示转派；弹窗复用多选。不抽跨 app 组件。
- 不回写告警中心，不新增对外 OpenAPI，不改手机端告警中心转派。

## Testing Decisions

- 最高接缝是各域现有认领 / 分派服务、告警操作入口、详情事件序列。
- 必须覆盖：当前处理人转派给多人成功且只落一条 `reassigned`；空单 / 非处理人 / 非活跃 409；组织外或禁用 400；并发后到者失败；拒绝不写事件；监控 / 日志通知发给新名单；APM 无 Event Snapshot 且分布图不因转派增加；前端空单无转派、有处理人无认领分派。

## Out of Scope

- 超级用户抢转、升级加签、认领通知、必填原因弹窗。
- 告警中心回写、OpenAPI、手机端。
- 把三域处理人服务抽成公共库。

## Completion Evidence

- 2026-09-20 本机 Postgres：`uv run pytest apps/{monitor,log,apm}/tests/test_alert_handlers.py -k reassign --no-cov` → 14 passed。覆盖当前处理人转派多人、空单/非处理人/非活跃 409、组织外/禁用 400、拒绝不写 `reassigned`、监控/日志通知发给新名单、APM 无 Event Snapshot、分布图不增加、outbox 键按次唯一、INFO 日志模板。
- 2026-09-20 前端：`vitest` 监控/日志/APM 处理人按钮、时间线、事件流共 42 项 passed。空单无转派，当前处理人有转派无认领/分派。
- sqlite `:memory:` 建库会撞无关的 `NewSessionEventRelation` 迁移，本机验证走 Postgres。`test_per_event_ack_legacy_path_forwards_shared_token` 缺 `django_db` 是基线失败，与转派无关。
