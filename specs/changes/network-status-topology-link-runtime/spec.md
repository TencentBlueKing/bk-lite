# 网络状态拓扑连线运行态：端口流量、悬停指标与断开标记

Status: implemented

## Problem Statement

运营分析「网络状态拓扑」连线上目前只有截断后的端口名。运维巡检时看不到这条链路当前有没有流量、端口是不是 down，必须离开画布到监控中心按接口查。节点已经按监控活跃告警叠色，连线仍是静态结构。需要在端口名下展示可选的当前流量，移入端口时看到该口的常用接口指标，并在链路断开时在线上标出，且口径要跟本仓监控 IF-MIB 数据一致，而不是照搬独立「网络拓扑」画布的 WeOps 字段。

## Solution

在现有网络状态拓扑场景组件上叠加连线运行态：叠色拿到设备 `monitor_id` 之后，再按监控实例批量拉取接口最新指标；用 CMDB 端口名候选去对监控 `ifDescr`。每个端口名下展示设置里勾选的入/出流量；只在端口名上悬停时弹出该口的固定指标组；任一端运行状态为断开时在连线中点画红叉。画布和分享页都是全量（含悬停）；PDF 只保留端口名、叉和常驻流量。

## User Stories

1. As an 运维人员, I want 每个端口名下面看到该口当前入/出流量, so that 不用离开拓扑就能判断链路是否在跑数据
2. As an 运维人员, I want 在组件设置里勾选要常驻展示的入向流量和出向流量, so that 大屏上只留我关心的数字
3. As an 运维人员, I want 鼠标移到端口名时看到该口的运行状态、带宽、流量、错包和丢包, so that 点开端口就能核对监控里的常用接口指标
4. As an 运维人员, I want 任一端接口断开时连线中点出现红叉, so that 我能立刻把中断链路和节点告警区分开
5. As an 运维人员, I want 未关联监控或端口名对不上时不显示假数字、也不打叉, so that 我不会把「没数据」当成「链路断了」
6. As a 查看者, I want 分享页也能看到流量、红叉和端口悬停, so that 外链和登录打开的画布口径一致
7. As a 查看者, I want 导出 PDF 只留下端口名、红叉和常驻流量, so that 纸面上是简略快照而不是悬停详情

## Implementation Decisions

- 范围是运营分析网络状态拓扑场景组件（含内置大屏及用户画布上的同一组件）。不改 CMDB 网络拓扑编辑页，不改独立「网络拓扑」画布的 WeOps 取数与连线配色。
- 场景结构接口仍只返回 CMDB 拓扑。连线运行态由前端在节点叠色之后编排，复用已有的 `monitor_id` 映射，不再为结构接口补 `ifIndex`。
- 端口对监控：CMDB 连线端口取 `source_port` / `target_port`，没有则用去掉设备名前缀后的 `source_inst_name` / `target_inst_name`。与监控 `ifDescr` 匹配时使用与 CMDB 拓扑相同的接口名候选（大小写/空白归一，以及 Gi↔GigabitEthernet、Te↔TenGigabitEthernet、Eth↔Ethernet、Po↔Port-Channel）。对不上则该端无数字、悬停说明未匹配。
- 断开判定对齐独立网络拓扑画布的 `oper_status_down_only` 语义，但取值用本仓 IF-MIB：查 `interface_ifOperStatus` 的最新数值。`1` 为 up；`2`（down）和 `7`（lowerLayerDown）为断开；`3` testing 以及其它枚举、缺测、对不上均为未知。一条连线任一端断开即打叉；两端都匹配且均为 up 才算通；否则未知。未知和通都不打叉。
- 连线视觉：通为绿、断为红（中点仍画红色叉）、未知为现有结构灰线。选中告警节点时的故障路径仍加粗变红，覆盖运行态线色。
- 常驻指标只有入向流量、出向流量，默认都勾。口径为近 5 分钟平均速率。优先 64 位 `interface_ifHCInOctets` / `interface_ifHCOutOctets`；该口没有 HC 再退 32 位 `interface_ifInOctets` / `interface_ifOutOctets`。单位与监控接口流量一致（byteps，展示时走现有单位换算）。每个端口名下只写该口自己的数字。
- 悬停固定一组，设置不再另配：运行状态、带宽、流量、接收/发送错包、接收/发送丢包。带宽用采集到的 `ifHighSpeed`（监控概览接口表同一口径）；没有再退 `interface_ifSpeed`。错包/丢包用带 `rate[5m]` 的 `interface_ifIn/OutErrors` 与 `interface_ifIn/OutDiscards`。
- 配置写在现有组件抽屉：模型 / 实例 / 深度下面两个勾选，以及入向/出向流量各自的阈值配色（与画布单值相同的「值 ≥ 阈值则上色」；比较口径为 B/s；空列表保持默认文字色）。持久化到场景组件配置，产品键为入向/出向，缺省或存量无此字段视为两项都开。用户两项都去掉则线上不写流量数字，端口名和断开叉仍在。设置不控制悬停清单，也不出现数据源或 PromQL。
- 悬停热区覆盖端口名与流量整块标签，并带较大透明命中区（`pointer-events: all`）；离开延迟足够从标签移到浮层。滑过中间线段或红叉不弹浮层。
- 取数不走 `monitor/mm_query`：该入口已停止新增、不按监控实例收权，且只返回第一条序列、丢掉 `ifDescr`。也不照搬独立网络拓扑画布的 WeOps `interface_status/batch`。新增监控 NATS（内置 `rest_api`，前端写死）：按 `instance_ids` 批量返回接口最新值，每条必须带 `instance_id`、`ifDescr` 和固定指标集合的当前值。PromQL 留在监控侧，查询不写死 `instance_type`，交换机/路由器/防火墙等只要采了公共 IF-MIB 都能用。计数器类指标在服务端按近 5 分钟 `rate` 算好再返回。身份走运营分析注入的 `user_info`，只返回当前用户有权的监控实例；请求中无权的 ID 省略，不让整次失败。未传或过滤后一个都没有：成功返回空列表。最多 100 个实例 ID（与拓扑节点上限一致）。不经 OpenAPI 网关对外暴露。
- 前端写死该 `rest_api`，保存、导出、分享允许列表、报表 `widget_manifest` 按组件类型把它与现有两个叠色 `rest_api` 一并解析进依赖。分享查询对该数据源允许 `instance_ids`。权限仍由 NATS 按会话身份过滤。
- 失败分层：拓扑结构失败沿用现有空态。节点叠色失败：节点全灰，连线按未知（没 `monitor_id` 不查口、不打叉、不写数字）。接口指标失败：结构与节点叠色保持，连线未知，可单独重试接口运行态，不把节点刷灰。没有 `monitor_id`、对不上、该口无序列：不打叉、不写数字；移到端口名时说明原因（未关联监控 / 未匹配到接口 / 取数失败）。不要把失败画成断开。
- 刷新与现有叠色同一套画布刷新：周期/可见性静默换数字和叉，手动刷新可出 loading。`onReady` 仍只表示是否有拓扑节点，不等接口运行态。
- 登录打开的画布和分享页都是全量：常驻流量、红叉、端口悬停。PDF / 报表渲染只保证画布上已画出的端口名、红叉和常驻流量进入快照，不要求悬停浮层出现在 PDF 里。

## Testing Decisions

- 好测试只验证外部行为：给定拓扑 + `monitor_id` 映射 + 接口指标结果，连线是否打叉、端口下是否出现对应流量、悬停文案/原因是否正确、设置缺省是否两项都开、失败是否不误打叉且不影响节点叠色；分享/报表是否把新数据源纳入允许范围。不锁定 X6 内部 DOM、事件名或叉的 SVG path。
- 接缝与 prior art：
  - 纯函数：接口名候选匹配、`ifOperStatus` 数值到通/断/未知、连线聚合、HC 优先 32 位兜底（对齐 CMDB 拓扑候选与监控 IF-MIB 目录）
  - 新监控 NATS：有权/无权实例、空列表、响应含 `ifDescr`、固定指标集合、部分实例省略不整次失败（对齐 `query_latest_active_alerts` 与现有 monitor NATS 单测风格）
  - 网络状态拓扑前端现有 fetch 测试：在叠色之后覆盖通/断/未知、常驻勾选、对不上、接口失败与叠色失败分层、分享仍取接口运行态
  - 配置提交测试：新字段写入场景配置；缺省与存量无字段视为两项都开
  - 分享查询与报表 manifest：允许新 `rest_api` 与 `instance_ids`，仍拒绝无关数据源
- 不强制本阶段做完整大屏 E2E。手动验收：有监控且端口名能对上的链路上能看到流量；down 口打叉；对不上的口无数字无叉且悬停说明；分享页可悬停；PDF 上看得到叉和常驻数字、没有悬停层。

## Out of Scope

- 为拓扑结构补 `ifIndex` 或改 CMDB 连线模型
- 用户填写 PromQL，或把悬停指标做成第二套设置
- 把常驻候选扩成利用率或其它 IF-MIB 指标
- 独立「网络拓扑」画布的 WeOps 连线颜色、流动虚线、每条连线自选 `interface_metrics`
- CMDB 网络拓扑编辑页
- 改变节点叠色、告警弹框或故障路径规则
- 将新 NATS 经 OpenAPI 网关对外暴露
- 补写历史脏 `monitor_id`

## Further Notes

- 判定语义参考独立网络拓扑画布的「任一 down 即 critical」，指标名和枚举以本仓公共 IF-MIB 为准：采集表里已有 `ifHighSpeed` / `ifHCInOctets`，不要用 WeOps 的 `ifInOctets_5min` 字符串状态。
- 通用 Switch/Router/Firewall 插件的「命名指标」可能只声明了 32 位流量和 `ifSpeed`，但公共 IF-MIB 采集表仍在采 HC 与 `ifHighSpeed`；运行态查询应对序列本身，而不是只认插件 `metrics.json` 里点名的那几条。
- CMDB 连线端口名来自接口实例 `inst_name`（图查询 `local_if`），与监控 `ifDescr` 在实际环境中基本对应；候选名只处理缩写差异，不是主路径。

## Completion Evidence

- 监控 NATS `query_latest_interface_metrics`：按 `instance_ids` 返回 `instance_id` + `ifDescr` + 固定 IF-MIB 最新值（计数器 `rate[5m]`）；无权 ID 省略；最多 100；不经 OpenAPI。内置数据源与叠色 `rest_api` 元组已登记第三路。
- 前端：端口名候选匹配、`ifOperStatus` 1/2/7、HC/HighSpeed 兜底、常驻入/出向勾选（缺省两项都开、空数组为用户清空）、入/出流量阈值配色（B/s，空配置保持默认色）、断开中点红叉且线色不变、端口标签大热区悬停。叠色失败连线未知且悬停「未关联监控」；接口失败不刷灰节点。流量展示对齐监控 `byteps`（IEC：B/s、KiB/s）。
- 聚焦测试（2026-08-19）：
  - `cd web && ./node_modules/.bin/vitest run src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/linkRuntimeModel.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/overlayModel.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/statusTopologyGraph.badge.test.ts src/app/ops-analysis/components/widgets/networkStatusTopology/__tests__/networkStatusTopology.fetch.test.tsx`：**68 passed**
  - `cd web && pnpm exec tsx --test src/app/ops-analysis/utils/__tests__/networkStatusTopologyLayout.test.ts src/app/ops-analysis/components/widgetConfig/utils/__tests__/submitConfig.networkStatusTopology.test.ts`：**30 passed**
  - `cd server && uv run pytest apps/monitor/tests/test_interface_metrics_query.py apps/monitor/tests/test_query_latest_interface_metrics_nats.py apps/rpc/tests/test_monitor_forwarding.py::test_query_latest_interface_metrics apps/operation_analysis/tests/test_network_status_topology_overlay.py apps/operation_analysis/tests/test_share_service.py::test_allowed_share_query_keys_include_overlay_when_canvas_has_topology -q`：**20 passed**（含分享第三路 `instance_ids` 允许列表）
- 未做完整大屏 E2E。手动验收仍按 Testing Decisions：有监控且端口名能对上的链路看流量；阈值配色生效；down 口打叉；端口热区更大、浮层不易消失；对不上无数字无叉且悬停说明；分享页可悬停；PDF 有叉和常驻数字、无悬停层。
