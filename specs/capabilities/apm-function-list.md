# APM · 功能清单

**文档版本：** V1.0
**发布日期：** 2026-08-24
**适用范围：** BK-Lite APM 模块
**编制依据：** 与 `server/apps/apm`、`web/src/app/apm` 源代码核对

对应产品：[[apm-product.md#产品入口]]

对应架构：[[apm-architecture.md#职责与边界]]

对应告警契约：[[apm-alerting.md#长期契约]]

---

## 一、模块定位

APM 提供应用性能观察与自有告警，覆盖接入、服务目录、调用链探索、SLO 与策略告警。本清单只列已实现能力。数据面契约夹具存在，但仓库声明从未正式生产部署，故状态标 Beta。

## 二、功能清单

### 1. 集成与目录

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 应用管理 | 创建与维护应用，并分配组织；超级用户可筛选未归属应用并重新指定组织 | 组织失败则拒绝；未归属不进入默认当前组织列表 | Beta |
| 接入指引 | 按语言生成离线安装说明 | Java / Python 3.12 / Node.js / Go 1.26 / PHP NTS 8.1–8.5 / .NET Linux x86_64 glibc / .NET Windows 主机 / eBPF 指定 Go 进程（Linux 6.6+） / Ruby Rack / C++ / Erlang/Elixir / Swift Package Manager；页面只写进离线包的框架；指向系统内下载与区域内网接入；可选本次脚本采样率（默认全量，不持久化）；不支持公网令牌 | Beta |
| 探针能力说明 | 接入抽屉展示钉死版本的精选 Web/RPC 框架，以及可打出 Client Span 的推断组件类型 | 静态矩阵，不调探针、不扫 OTel 源码；发现能力是应用详情拓扑推断，不进服务目录 / 应用列表 / CMDB | Beta |
| 探针下载 | 在目标主机下载白名单探针制品 | 免登录；未知制品返回不存在 | Beta |
| 服务目录 | 展示发现的服务，支持归档/恢复与组织授权；超级用户可筛选未归属服务并重新指定组织 | 活跃窗口 15 分钟；分钟级对账；未归属不进入默认当前组织列表 | Beta |
| 实例目录 | 展示上报实例并分配组织；超级用户可筛选未归属实例 | 与服务身份规范化唯一；未归属不放开 Trace / 指标 | Beta |

### 2. 观察

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 首页总览 | 展示健康、SLO、告警与 Top 指标 | KPI、健康、服务 Top、可用性 SLO：聚合库已配置且窗口起点不早于已记录聚合起点时读聚合库，否则 VictoriaTraces；缺样本为无数据，聚合错误不回退明细。回退到明细的 SLO 若窗口长于 `APM_TRACE_RETENTION`，达成率为空，原因是“明细保留期不足”，不显示为 0。延迟 SLO 仍读 VictoriaTraces，并适用同一判断。分节可空或降级，不编造数据 | Beta |
| 调用链探索 | 检索近窗 Trace / Span 样本并下钻详情 | 最长 35 天；默认最多 50 条；不对账窗内错误率；敏感属性脱敏；禁止任意查询语言 | Beta |
| Span / 端点探索 | 检索 Span 与端点 | 组织过滤；参数白名单 | Beta |
| 错误聚合 | 按异常语义聚类错误 | 基于可见服务；服务详情错误 Tab 计数看入口失败、归因看该服务全部 Error Span，分区标注；探索错误分析按 Issue fingerprint 翻页并展示已加载种类；探索列表不标窗内错误合计 | Beta |
| 服务拓扑 | 展示服务依赖 | 窗口不超过 7 天 | Beta |
| RED 指标 | 查看服务错误率、时延、吞吐 | 服务列表批量与服务详情的整窗、趋势、Top 操作按首页同一路由读聚合库；最大耗时为空时显示“—”。环境/端点/窗口受控。慢请求、Apdex、版本、实例、依赖仍读 VictoriaTraces | Beta |

### 3. 可靠性

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| SLO | 定义并评估可用性或时延目标 | 目标 (0,100]；时延类必须带阈值。可用性（7 天、30 天、自然月）在聚合起点覆盖整个窗口时读聚合库 `apm_calls_total`，否则 VictoriaTraces；聚合库错误时该 SLO 降级且不回退。回退到 VictoriaTraces 时，窗口（自然月按实际天数）长于 `APM_TRACE_RETENTION` 则不查询，达成率为空，原因是“明细保留期不足”，不显示为 0；保留期无法解析时同样不查询，原因是“明细保留期配置无效”。首页卡片与列表、详情同一条计算路径。延迟类仍读 VictoriaTraces，并适用同一保留期判断 | Beta |
| 告警策略 | 配置并启停策略 | 仅五种指标；必选环境与所属组织；处理人必须属于策略组织且未禁用；不支持监控表达式 | Beta |
| 告警与事件 | 查看生命周期，空单可认领 / 分派，当前处理人可转派；空单或当前处理人可手工关闭 | 告警状态 active/recovered/closed；事件不可变；认领 / 分派 / 转派写 `claimed` / `assigned` / `reassigned` 事件；手工分派与转派对系统用户渠道通知新处理人；`my_alert` 只筛处理人，列表与分布图同一套；分布图不含认领 / 分派 / 转派 | Beta |
| 告警证据 | 查看扫描点趋势与事件原始证据 | 禁止用实时库重建历史；证据可 pending/expired | Beta |
| 通知投递 | 按渠道投递并可人工重试 | 可补偿；告警中心副本不回写 | Beta |
| 运行健康 | 探测追踪库、采集链路与通知依赖 | 仅运行期；不阻断进程启动 | Beta |

> 证据来源：server/apps/apm/urls.py:25-46，web/src/app/apm/constants/menu.json:2-120，server/apps/apm/models/control_plane.py:182-308，server/apps/apm/adapters/victoriatraces.py:36-37，server/apps/apm/config.py:3-27，deploy/apm/README.md:1-22　|　同步基线：61bace9f　|　【已实现】

## 三、能力边界与约束

- 入口 RED（首页 KPI、健康、服务 Top，服务列表批量 RED，服务详情 RED 的整窗、趋势、Top 操作）和可用性 SLO（7 天、30 天、自然月；首页卡片与 SLO 列表、详情同一条计算路径）在聚合库已配置、已记录聚合起点且查询窗口起点不早于该起点时读聚合库，否则读 VictoriaTraces。缺样本返回无数据，不当 0。聚合库错误时对应区块或该 SLO 降级，不自动回退扫描 VictoriaTraces。回退到 VictoriaTraces 的可用性与延迟 SLO，窗口长于 `APM_TRACE_RETENTION`（与运行健康同一解析；自然月按实际天数）时不查询明细，达成率为空，原因是“明细保留期不足”；配置无法解析时不套用默认 35 天，同样不查询，原因是“明细保留期配置无效”。聚合库路径不看明细保留期。最大耗时在聚合路径为空，页面显示“—”。慢请求、Apdex、延迟 SLO、版本、实例、依赖、告警策略和试算仍读 VictoriaTraces。明细、下钻与拓扑仍以 VictoriaTraces 为准。目标契约见 [ADR 0011](../../docs/adr/0011-apm-rum-aggregate-metrics-store.md)，落地见[聚合层变更](../changes/observability-aggregate-metrics/spec.md)。
- 不提供尾采样或独立边缘网关。
- 不提供跨租户公网 OTLP。
- 不把监控对象、采集插件或日志检索纳入策略。

> 证据来源：server/apps/apm/adapters/aggregate_red.py，server/apps/apm/services/trace_retention.py，server/apps/core/aggregate_promql.py，server/apps/apm/views/control_plane.py，server/apps/apm/views/dashboard.py，docs/adr/0011-apm-rum-aggregate-metrics-store.md　|　【已实现；可用性 SLO 在起点覆盖窗口后读聚合库，延迟 SLO 仍读 VictoriaTraces；明细回退在保留期不足时不给达成率】

## 四、平台协同

- 组织与通知渠道来自系统管理。
- 接入区域信息来自节点管理。
- 可选把事件副本抄送到告警中心，告警中心不得回写。

> 证据来源：server/apps/apm/adapters/notifications.py:7-27，specs/capabilities/apm-alerting.md:12　|　同步基线：61bace9f　|　【已实现】
