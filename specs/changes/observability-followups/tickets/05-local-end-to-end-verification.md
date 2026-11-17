# 05 — 本机接聚合库的全链路验证与页面走查

Status: done

Blocked by: 02 — 明细保留期不足时 SLO 不给达成率；03 — RUM 告警详情趋势区分无样本与 0

**What to build:** 在本机真实开发环境里接上一个临时聚合库，确认 Server 读取、聚合起点探测与页面展示符合
`observability-aggregate-metrics` spec，并留下截图证据。

- [x] 起一个临时单节点 VictoriaMetrics（独立容器名，端口避开 8428、9428、10428），保留期 35 天
- [x] 按 `deploy/rum` 与 `deploy/apm` 的指标名和标签，向临时库写入合成的 `apm_` / `rum_` 累计样本（覆盖多分片、「其他」路由、
      无样本的时间段）；不向用户的 VictoriaMetrics、VictoriaLogs、VictoriaTraces 写数据
- [x] 用 `deploy/local` 的 Make 目标在本机启动 Server（以及验证起点探测所需的 Celery），`AGG_VICTORIAMETRICS_QUERY_URL` 指向临时库
- [x] 起点探测写入 `AggregateMetricOrigin`；窗口早于起点时回退明细，晚于起点时读聚合
- [x] 浏览器走查并截图：APM 首页、服务列表、服务详情（最大耗时「—」）、SLO 列表；RUM 应用目录、概览、页面列表（「其他」行）、告警详情趋势
- [x] 停掉临时聚合库后，相关区块降级、页面其他部分正常、Server 不报启动错误
- [x] 只读检查用户 APM 栈中 `bk-lite-apm-apm-system-collector-1` 为何 unhealthy，报告原因，不做修改
- [x] 结束后删除临时容器，恢复本机进程到验证前的状态

## Notes

- 遇到登录、权限、缺数据等无法自行解决的阻塞时停下并报告，不绕过。
- 不提交任何本机配置、凭据或 `.env`。
- 停掉临时聚合库后，首页 Top 错误率、P95 与健康度在批量 RED 全部没有结果且至少一条为存储不可用时会被记成空列表或未知分布；已与 SLO 一样标为 failed（KPI 仍为 null），部分成功只展示成功服务，没有服务时仍为 empty。

## Completion evidence

2026-11-10 先通过 Server 服务层（`manage.py shell`，连本机开发库和 `deploy/local` 拉起的 Server）验证各项，
用户登录后重新起临时库补做浏览器走查。临时库为 `bk-agg-verify`（127.0.0.1:18430）。

- 浏览器走查（截图存于验证 agent 的 store，不入库），窗口在聚合起点之后：
  - APM 首页：请求量 2.9/s、P95 584ms 与两个 Top5 来自聚合库；
  - 服务列表：演示应用吞吐 2.9/s、错误率 1.68%，无指标的服务显示「无数据」；
  - 服务详情 demo-storefront：吞吐、错误率、P99/P95、三条趋势与 Top 端点来自聚合库，「最大耗时 —」；
  - SLO 列表：两条 SLO 为滚动 7 天，早于起点回退 VictoriaTraces，显示「暂无数据」；
  - RUM 应用目录、概览（1h）：浏览、错误、LCP/INP P75 来自聚合库。
- 浏览器未能走查的两页，已在服务层核对：
  - 页面列表：本机未起 RUM 网关栈，控制面不可用，`list_views` 在读分析前就返回空（页面提示「RUM 控制面暂不可用」）；
  - 告警详情趋势：本机无 Celery、无 RUM 控制面，没有告警事件。
- 环境造成、非缺陷：
  - RUM 会话、错误率、「窗口内无数据」「SDK 未接入」来自 VictoriaLogs 会话明细，合成数据只写聚合库，因此与聚合数字不一致；
  - APM 首页健康度全为「未知」，因演示服务在目录中为「静默」（VictoriaTraces 近期无 span），主干已按此规则归为未知。

- 起点探测：未起 Celery，在 shell 中直接调用 `probe_aggregate_metric_origins`；写入 apm、rum 两条 `AggregateMetricOrigin`；再次运行对已有起点的产品不再发查询。
- APM：1h 窗口 `service_red` 读聚合（请求率约 1.87/s，`max_ms` 为 null，Top 接口有序）；6h 窗口早于起点回退 VictoriaTraces；
  首页 KPI 与 Top P95 来自聚合库。
- RUM：应用目录数字与合成数据一致，静默段为 0；页面列表按路由返回访客口径（排除 bot），含「其他」行；
  `lcp_p75` / `inp_p75` 告警读数约 2622ms / 199ms，15 分钟内无样本时为 null 而不是 0。
- 降级：停掉临时库后，APM KPI 与 RUM 目录聚合数字为 null，首页 Top 区块为 failed，RUM 告警读数抛错由告警运行时按评估失败处理；
  每个失败区块一条 WARNING（含 `failed_stage`、`error_type`）；Server 在临时库停止时重载，登录绑定接口返回 200。
- 走查中发现并已修复：
  - 页面列表 LogsQL 移动端条件多一个引号导致 400（主干已有，`77732115ce`）；
  - 浏览趋势首桶重复计数（`2749dfd656`）；
  - 首页 Top 区块故障时显示为空（`af3655c2cc`）。
- `bk-lite-apm-apm-system-collector-1` unhealthy：容器绑定挂载工作区的 `deploy/apm/otel/system.yaml`，本分支（`8b260e4f2b`）已加入
  `count` connector，但容器仍是 11-06 启动的 `0.153.0-bklite.1` 镜像；健康检查用旧二进制校验新配置报 `unknown type: "count"`。
  运行中的进程仍用启动时加载的旧配置，采集不受影响；容器一旦重启会起不来。经用户授权，以
  `APM_COLLECTOR_IMAGE=bklite/apm-otel-collector:0.153.0-bklite.2 docker compose -f deploy/apm/compose.yaml up -d` 重建
  （本机 `deploy/apm/.env` 固定了 `bklite.1`，不覆盖会用旧镜像加载新配置）；两个 collector 与新建的 APM 聚合库均 healthy。
- 本机配置缺 `RUM_VICTORIA_LOGS_URL`，开发 Server 中 RUM 分析不可用（既有问题）；验证时只在当前 shell 临时导出。
- 清理（两轮验证后各做一次）：临时容器已删除，`server/.env` 已从备份恢复，`AggregateMetricOrigin` 记录已删除（表保留），Server 重载后返回 200，
  用户容器与 3000、8443 端口进程未变。
- `apps/rum/tests` 257 passed；`apps/apm/tests` 878 passed、11 项为既有 sqlite 失败。
