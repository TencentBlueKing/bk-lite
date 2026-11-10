# 07 — RUM Web Vitals 告警改读

Status: done

Blocked by: 06 — RUM 应用目录、概览与页面列表改读

**What to build:** LCP、INP、CLS、FCP、TTFB p75 告警每分钟评估读聚合库，告警详情里的这些指标趋势也读聚合库；会话数、
错误会话率告警仍读 VictoriaLogs，行为不变。

- [x] 告警读数：`histogram_quantile(0.75, …increase(…[窗口]))`，窗口沿用策略的 5/15/60 分钟，结束时间对齐到完整分钟并留一个
      刷出周期；默认访客口径；无样本 = 无数据（不是 0）
- [x] 窗口早于聚合起点或聚合库不可用：按现有“读取失败/无数据”语义处理，不改变告警状态机
- [x] 告警详情趋势中的 Web Vitals 指标读聚合库；已固化的告警证据不重画
- [x] 测试：每个 vital 的读数、无数据与 0 的区分、读取失败不改状态、会话类告警不受影响；sqlite 下 `server/apps/rum/tests` 通过
- [x] 本目录 spec 状态更新为 done 并补完成证据

## Completion evidence

现有策略只有应用，没有环境、路由或版本。覆盖窗口内的 LCP / INP / FCP / TTFB / CLS p75 用
`histogram_quantile(0.75, sum by (le) (increase(<vital>_bucket{租户、应用、流量}[窗口秒])))`。窗口是策略的 5 / 15 / 60 分钟，
结束时间对齐到完整分钟再留出 RUM 默认 10 秒刷出周期。默认访客：`rum_traffic_class!~"bot|synthetic|crawler"`；调用方若带
`traffic`，与页面列表同一套口径。`sum by (le)` 把环境、路由和分片并回应用级，不比原来的 LogsQL 更宽。无样本是 `None`，数值 0
仍是 0。起点未覆盖、未记录或聚合库未配置时仍走 VictoriaLogs。聚合查询失败不扫明细，也不触发或恢复：评估记一次跳过，状态机不动。
详情趋势读聚合库；失败只清空曲线。已经写入的告警值和事件不重算。会话数、错误会话率仍读 VictoriaLogs。

- `cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true INSTALL_APPS=system_mgmt,console_mgmt,node_mgmt,monitor,log,apm,alerts,rum,cmdb timeout 900 uv run pytest apps/rum/tests --no-cov --nomigrations -o addopts= -q -p no:cacheprovider`
  结果：`256 passed`。基线 234，新增 22。覆盖五个 vital、5/15/60 分钟窗口、无样本与 0、读取失败不改状态、起点与未配置回退、标签转义与流量收窄、会话类告警、趋势分桶和已固化事件。未改 `apps/core` 或 `apps/alerts` 的共用代码，未改前端。
