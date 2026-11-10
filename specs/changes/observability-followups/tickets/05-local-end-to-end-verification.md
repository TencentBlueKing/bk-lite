# 05 — 本机接聚合库的全链路验证与页面走查

Status: ready

Blocked by: 02 — 明细保留期不足时 SLO 不给达成率；03 — RUM 告警详情趋势区分无样本与 0

**What to build:** 在本机真实开发环境里接上一个临时聚合库，确认 Server 读取、聚合起点探测与页面展示符合
`observability-aggregate-metrics` spec，并留下截图证据。

- [ ] 起一个临时单节点 VictoriaMetrics（独立容器名，端口避开 8428、9428、10428），保留期 35 天
- [ ] 按 `deploy/rum` 与 `deploy/apm` 的指标名和标签，向临时库写入合成的 `apm_` / `rum_` 累计样本（覆盖多分片、「其他」路由、
      无样本的时间段）；不向用户的 VictoriaMetrics、VictoriaLogs、VictoriaTraces 写数据
- [ ] 用 `deploy/local` 的 Make 目标在本机启动 Server（以及验证起点探测所需的 Celery），`AGG_VICTORIAMETRICS_QUERY_URL` 指向临时库
- [ ] 起点探测写入 `AggregateMetricOrigin`；窗口早于起点时回退明细，晚于起点时读聚合
- [ ] 浏览器走查并截图：APM 首页、服务列表、服务详情（最大耗时「—」）、SLO 列表；RUM 应用目录、概览、页面列表（「其他」行）、告警详情趋势
- [ ] 停掉临时聚合库后，相关区块降级、页面其他部分正常、Server 不报启动错误
- [ ] 只读检查用户 APM 栈中 `bk-lite-apm-apm-system-collector-1` 为何 unhealthy，报告原因，不做修改
- [ ] 结束后删除临时容器，恢复本机进程到验证前的状态

## Notes

- 遇到登录、权限、缺数据等无法自行解决的阻塞时停下并报告，不绕过。
- 不提交任何本机配置、凭据或 `.env`。
