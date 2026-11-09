# 07 — RUM Web Vitals 告警改读

Status: ready

Blocked by: 06 — RUM 应用目录、概览与页面列表改读

**What to build:** LCP、INP、CLS、FCP、TTFB p75 告警每分钟评估读聚合库，告警详情里的这些指标趋势也读聚合库；会话数、
错误会话率告警仍读 VictoriaLogs，行为不变。

- [ ] 告警读数：`histogram_quantile(0.75, …increase(…[窗口]))`，窗口沿用策略的 5/15/60 分钟，结束时间对齐到完整分钟并留一个
      刷出周期；默认访客口径；无样本 = 无数据（不是 0）
- [ ] 窗口早于聚合起点或聚合库不可用：按现有“读取失败/无数据”语义处理，不改变告警状态机
- [ ] 告警详情趋势中的 Web Vitals 指标读聚合库；已固化的告警证据不重画
- [ ] 测试：每个 vital 的读数、无数据与 0 的区分、读取失败不改状态、会话类告警不受影响；sqlite 下 `server/apps/rum/tests` 通过
- [ ] 本目录 spec 状态更新为 done 并补完成证据
