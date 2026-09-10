# 领域告警处理人复验跟进

Status: complete

## Completion Evidence

- 日志 `alert_list_all` / `stats` 与主列表共用 `is_my_alert_query` + `filter_my_handler_alerts`。APM `distribution` 吃同一套 `my_alert` / `actor`，并排除 `claimed` / `assigned`；前端勾选时 `getAlertDistribution` 带 `my_alert: 1`。
- 监控 `retrieve`、认领、分派响应补 `handlers_display`。APM `list` 对当前页 handlers 一次 `build_user_display_map`。
- 日志分派通知改用 `log_logger`；监控 / 日志 `assign_notify_failed` 去掉 `exc_info=True`。过时 PRD / 日志 ARD / APM alerting 契约已改写。
- 测试：`apps/monitor/tests/test_alert_handlers.py`、`apps/log/tests/test_alert_handlers.py`、`apps/apm/tests/test_alert_handlers.py`、`apps/apm/tests/test_alert_snapshot_api.py`；前端 `web/src/app/apm/events/alerts/__tests__/page.test.tsx`。
- 验证（2026-09-09）：本机 Postgres `--reuse-db` 上述后端 63 passed；前端 vitest `page.test.tsx` 10 passed。

## Problem Statement

613 / 614 主闭环已经能用，但复验发现「我的告警」只筛了主列表、分布图和次要列表没跟上；监控详情直拉时处理人展示名可能丢；分派通知日志归属和失败 traceback 不满足生产日志红线。值班勾选「我的告警」后会看到列表和图表对不上。

## Solution

让所有面向当前告警列表的查询（主列表、`/all`、统计、分布图）在同一套可见集合上再筛处理人。「我的告警」下的分布图只数评估类事件，不因数认领 / 分派多一根柱。监控单条告警响应补 `handlers_display`。分派通知日志改回本 app logger，失败 ERROR 只带 `error_type`。过时 ARD / PRD 改成与 613 / 614 一致。

## User Stories

1. As a 值班人, I want 勾选「我的告警」后日志分布图和 APM 分布图与列表同一批单, so that 我不会以为自己队列里还有别人的告警
2. As a 值班人, I want 打开监控告警详情或认领成功后仍能看到处理人展示名, so that 不必依赖列表缓存
3. As a 日志调用方, I want `GET /log/alert/all/?my_alert=1` 与主列表一样只出我的单, so that 次要入口不会静默忽略筛选
4. As a 运维, I want 分派通知失败的生产日志不含渠道响应、且记在日志 app 自己的 logger 上, so that 排查时对得上模块且不泄露外部正文

## Implementation Decisions

- 「我的告警」语义不变：叠在现有组织可见性之后，筛 `handlers` 含当前用户 id 或 username。不改权限，不改告警中心。
- 日志 `list` 已吃 `my_alert`。`alert_list_all` 与 `stats` 用同一对 `is_my_alert_query` + `filter_my_handler_alerts`。`stats` 在现有可见 queryset 上再筛，再按状态 / 时间聚合。
- APM `distribution` 增加与 `list` 相同的 `my_alert` / `actor`。按**告警**处理人过滤其事件，不是按事件动作是否为认领。勾选时前端 `getAlertDistribution` 带上与列表相同的 `my_alert: 1`。
- APM 分布图只统计 `triggered` / `escalated` / `recovered` / `closed`。`claimed` / `assigned` 不进柱状图，与 614「认领 / 分派不上指标图」一致。未勾选「我的告警」时同样排除这两类，避免点一次认领图上多一根。
- 监控 `retrieve`、认领、分派响应都走现有 `enrich_alerts_handlers_display`（单元素列表即可）。不改列表以外的权限或字段名。日志 / APM 序列化已有 `handlers_display`，不重复做。
- APM `list` 先对当前页 `handlers` 建一次用户展示 map，再传入 `serialize`，禁止每条告警单独查 User。
- 日志分派通知新增/改写的日志改用 `log_logger`。不把 `alert_lifecycle_notify.py` 整文件从既有 `celery_logger` 迁走。
- 监控 / 日志 `assign_notify_failed` 的 ERROR 只保留稳定模板和 `error_type`，去掉 `exc_info=True`。不清理该文件里 613 之前的其它 `exc_info`。
- 补行为测试：分派成功 INFO 模板与独立参数；分派通知失败 ERROR 无 traceback 所有权、无渠道响应哨兵。认领既有用例保留。
- 改写 `legacy-prd-监控系统-事件.md` 的「指定处理人」为策略可选处理人 + 空单认领 / 分派，`operator` 仍是关单人。日志 ARD 补一句：空单可认领 / 分派，生命周期动作写入 Event，`my_alert` 筛处理人。不扩写无关章节。

## Testing Decisions

- 只测对外行为：带 `my_alert=1` 的 stats / distribution / `alert/all` 与主列表同一批 id；不带则与今天一致。APM 分布在认领后柱数不增加。监控 retrieve / claim 响应含 `handlers_display`。分派日志模板、参数、`getMessage()`、无 traceback、无响应哨兵。
- 最高接缝是现有告警列表、stats、distribution、claim、assign 测试。在 613 / 614 的 handler 测试上改期望，不另起框架。
- 必须覆盖：处理人是自己的告警出现在 `my_alert` 的 stats / distribution / `all`；`operator` 是自己但 `handlers` 空的不出；APM 认领后分布桶计数不变；监控 claim 响应有展示名；分派通知失败不把假渠道响应写进格式化日志。
- 前端锁定：APM 勾选「我的告警」时 distribution 请求带 `my_alert: 1`。日志图表本来就会带参，补后端即可。

## Out of Scope

- 转派、原因弹窗、日志自动恢复、历史回填、告警中心同步。
- 重写监控 / 日志整份生命周期通知的 logger 与历史 `exc_info`。
- 把三域 `handlers_display` 抽成公共库。
- 改「我的告警」为跨组织值班队列。

## Further Notes

复验来源：613 `domain-alert-handlers-assignment`、614 `domain-alert-lifecycle-events`。本跟进只修边角一致性和 613 新增日志路径的生产日志红线，不改处理人语义。
