# 02 — 明细保留期不足时 SLO 不给达成率

Status: ready

Blocked by: None

**What to build:** SLO 走 VictoriaTraces 计算、且窗口长于 `APM_TRACE_RETENTION` 时，这条 SLO 的达成率为空，原因是“明细保留期不足”，
首页、SLO 列表和详情一致；聚合库路径不受影响。

- [ ] 复用健康检查的保留期解析（`server/apps/apm/services/health.py` 的 `_retention_days`），必要时挪到两边都能引用的位置
- [ ] 在 VictoriaTraces 回退路径（可用性与延迟 SLO）判断窗口长度与保留期；超出时不查询，返回空达成率和原因
- [ ] 保留期配置无法解析时按现有健康检查语义处理，并在报告里说明 SLO 侧的取舍
- [ ] 前端如需展示新原因，补 i18n 文案；不动布局
- [ ] 测试：保留期短于窗口、等于窗口、聚合路径不受影响、首页与列表一致；sqlite 下 `server/apps/apm/tests` 通过
- [ ] 更新 APM 功能清单 capability 中 SLO 的说明

## Notes

- 告警燃烧率是否受影响先查清：如果它也按 30 天窗口读 VictoriaTraces，同样适用这个判断；不确定时在报告里说明，不扩大范围。
