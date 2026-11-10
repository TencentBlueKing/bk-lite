# 06 — RUM 应用目录、概览与页面列表改读

Status: ready

Blocked by: 03 — Server 聚合查询客户端与 APM 首页、服务列表、服务 RED 改读；05 — RUM 网关生成聚合指标

**What to build:** 应用目录与应用概览的浏览次数、JS 错误次数、LCP/INP p75 与浏览趋势，以及按路由（未按版本筛选或分组时）
的页面列表的浏览次数、错误次数、Web Vitals p75 读聚合库；其余数字仍读 VictoriaLogs；窗口早于聚合起点时整体走现状。

- [ ] RUM 聚合读取：复用 03 的客户端与起点记录；按租户+应用收窄、跨 `shard` 求和、保持各页面现有流量口径
      （目录与概览全部流量；页面列表默认访客，`traffic` 参数可选）
- [ ] 目录 / 概览：会话数、错误会话、国家/环境/版本/设备分布继续读 VictoriaLogs，只把上述数字换成聚合读数
- [ ] 页面列表：`mode=release` 或带 `release` 过滤时整体继续走 VictoriaLogs；按路由时，聚合路由「其他」作为一行展示
- [ ] 缺数据不显示为 0；聚合库错误时对应数字降级，页面其他部分正常
- [ ] 测试：数值映射、流量口径、版本模式回退、起点回退、降级；sqlite 下 `server/apps/rum/tests` 通过；
      改了前端则 `pnpm lint`、`pnpm type-check`
