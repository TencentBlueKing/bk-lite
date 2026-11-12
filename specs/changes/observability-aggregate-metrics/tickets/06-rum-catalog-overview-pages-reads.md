# 06 — RUM 应用目录、概览与页面列表改读

Status: done

Blocked by: 03 — Server 聚合查询客户端与 APM 首页、服务列表、服务 RED 改读；05 — RUM 网关生成聚合指标

**What to build:** 应用目录与应用概览的浏览次数、JS 错误次数、LCP/INP p75 与浏览趋势，以及按路由（未按版本筛选或分组时）
的页面列表的浏览次数、错误次数、Web Vitals p75 读聚合库；其余数字仍读 VictoriaLogs；窗口早于聚合起点时整体走现状。

- [x] RUM 聚合读取：复用 03 的客户端与起点记录；按租户+应用收窄、跨 `shard` 求和、保持各页面现有流量口径
      （目录与概览全部流量；页面列表默认访客，`traffic` 参数可选）
- [x] 目录 / 概览：会话数、错误会话、国家/环境/版本/设备分布继续读 VictoriaLogs，只把上述数字换成聚合读数
- [x] 页面列表：`mode=release` 或带 `release` 过滤时整体继续走 VictoriaLogs；按路由时，聚合路由「其他」作为一行展示
- [x] 缺数据不显示为 0；聚合库错误时对应数字降级，页面其他部分正常
- [x] 测试：数值映射、流量口径、版本模式回退、起点回退、降级；sqlite 下 `server/apps/rum/tests` 通过；
      改了前端则 `pnpm lint`、`pnpm type-check`

## Completion evidence

- 读取路由：聚合可用、已记录 `recorded_origin("rum")`、且窗口起点不早于起点时，目录/概览替换浏览次数、JS 错误、LCP/INP p75 和浏览趋势；按路由且无 `release` 时，页面列表替换浏览次数、错误次数和 LCP/INP/CLS p75。会话、错误率、国家/环境/版本/设备、加载耗时、走势和按版本列表仍来自 VictoriaLogs。
- PromQL：`sum by (...) (increase(rum_views_total|rum_js_errors_total{选择器}[窗口秒]))`，p75 为 `histogram_quantile(0.75, sum by (le, 分组) (increase(..._bucket{选择器}[窗口秒])))`。目录/概览选择器只有租户和应用。页面列表默认 `rum_traffic_class!~"bot|synthetic|crawler"`。结束时间对齐到最近完整分钟再减去 10 秒。跨 `shard` 用 `sum()`，选择器不含 `shard`。
- 缺序列保持空；浏览序列存在而错误序列不存在时错误数为 0（与 APM RED 相同，表示没有错误样本）。聚合库错误记一条 WARNING，traceback 用 `safe_exception_info`，不回退把日志里的浏览/错误/p75 填回来。
- `apps/rum/tests` 233 passed（新增 18），`apps/core/tests/test_aggregate_origin_probe.py` 8 passed，合计 241 passed。`apps/apm/tests` 11 failed, 866 passed, 2 skipped，失败项与 sqlite 基线相同。前端改动文件 eslint 通过，相关 vitest 24 passed，`pnpm type-check` 通过。
- `specs/capabilities` 没有 RUM 功能清单。起点探测文档与 spec 已改为只探测 `rum_views_total`。

## Notes

浏览趋势只在整窗 `rum_views_total` 有值时，把窗口内且不早于聚合起点的空桶记为 0；整窗没有序列或聚合库报错时趋势保持全空。分位数不补 0。VictoriaLogs 原先对每个启用应用的空桶都预填 0。
