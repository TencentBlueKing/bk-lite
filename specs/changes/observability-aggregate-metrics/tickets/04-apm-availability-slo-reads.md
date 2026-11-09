# 04 — APM 可用性 SLO 改读

Status: ready

Blocked by: 03 — Server 聚合查询客户端与 APM 首页、服务列表、服务 RED 改读

**What to build:** 可用性类 SLO（7 天、30 天、自然月）在聚合起点覆盖整个窗口后读聚合库，秒级返回；覆盖前继续走现有
VictoriaTraces 按天切片的查询；延迟类 SLO 不变。

- [ ] 可用性 SLI 的总数/坏数由聚合库 `increase()` 计算，按服务（及 SLO 已有的入口操作 / 环境范围）收窄、跨 `shard` 求和
- [ ] 窗口起点早于聚合起点 → VictoriaTraces；聚合库错误 → 该 SLO 降级，不显示为 0
- [ ] 首页 SLO 卡片与 SLO 列表/详情一致
- [ ] 测试：7d / 30d / 自然月、起点未覆盖时回退、延迟 SLO 仍走 VictoriaTraces、降级；sqlite 下 `server/apps/apm/tests` 通过
- [ ] 更新 APM 功能清单 capability；本目录 spec 中 APM 部分的完成证据
