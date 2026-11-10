# 02 — 明细保留期不足时 SLO 不给达成率

Status: done

Blocked by: None

**What to build:** SLO 走 VictoriaTraces 计算、且窗口长于 `APM_TRACE_RETENTION` 时，这条 SLO 的达成率为空，原因是“明细保留期不足”，
首页、SLO 列表和详情一致；聚合库路径不受影响。

- [x] 复用健康检查的保留期解析（`server/apps/apm/services/health.py` 的 `_retention_days`），必要时挪到两边都能引用的位置
- [x] 在 VictoriaTraces 回退路径（可用性与延迟 SLO）判断窗口长度与保留期；超出时不查询，返回空达成率和原因
- [x] 保留期配置无法解析时按现有健康检查语义处理，并在报告里说明 SLO 侧的取舍
- [x] 前端如需展示新原因，补 i18n 文案；不动布局
- [x] 测试：保留期短于窗口、等于窗口、聚合路径不受影响、首页与列表一致；sqlite 下 `server/apps/apm/tests` 通过
- [x] 更新 APM 功能清单 capability 中 SLO 的说明

## Completion evidence

- 判断在 `ApmAvailabilitySloStore.slo_measurement` 的 VictoriaTraces 回退分支，可用性未覆盖聚合起点时和延迟 SLO 都走这里。窗口长度严格大于 `APM_TRACE_RETENTION` 解析出的天数（自然月用实际跨度，`168h` 与 7 天相等）时不调用明细查询，达成率为空，原因是“明细保留期不足”。等于窗口仍计算。聚合库路径不判断。
- 解析失败：健康检查把写了但无法解析的值记为 degraded（`victoria_traces_retention_invalid`），不回退默认 35 天。SLO 回退同样不查询，原因单独用“明细保留期配置无效”。环境变量未设置时仍按 35 天。
- 燃烧率未改。`_read_burn_window` 和 `_replay_burn` / `slo_compliance_by_window` 直接读 VictoriaTraces，窗口是分钟级（长窗最大 1440 分钟，回放大约一天再加长窗），不是 7 天、30 天或自然月 SLO 窗口。
- 首页卡片、列表和详情共用这次计算。首页不再把该原因画成整节加载失败：达成率是“—”，状态是“无数据”，原因写在服务名下方。列表标签、服务详情当前列和服务目录 SLO 列展示同一句原因。中英文文案在 `apm.slo.retentionTooShort` / `retentionInvalid`。
- sqlite：`apps/apm/tests` 876 passed，11 failed，2 skipped。11 项是既有失败（topology_api 8、deployments backfill 1、cross_database_guard 1、owned_alert_lifecycle 1）。`pnpm lint` 0 error。`pnpm type-check` 通过。首页、SLO 列表、服务目录 vitest 27 passed。

## Notes

- 告警燃烧率是否受影响先查清：如果它也按 30 天窗口读 VictoriaTraces，同样适用这个判断；不确定时在报告里说明，不扩大范围。
