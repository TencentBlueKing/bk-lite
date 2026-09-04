# 运营分析 Flow 仪表盘产品决策记忆

- 最近更新：2026-09-03
- 当前规格：`specs/changes/ops-analysis-flow-dashboard/spec.md`
- 后续图表：`specs/changes/ops-analysis-node-graph/spec.md`

## 产品定位

运营分析继续只做可视化与配置。Flow 事实、PromQL、采样率归一化和实例权限留在监控。专属 Flow 仪表盘是监控 Flow 分析的编排面，不是第二套 NTA 产品，也不是 SNMP 接口告警下钻闭环的第一期。

## 已确认范围

- 第一期做一张运营分析专属 Flow 仪表盘：KPI、趋势、协议分布、TopN、会话表。
- 设备下拉跨交换机 / 路由器 / 防火墙 / 负载均衡混选；空选择省略参数，不退化成全量。
- 监控新开 2 个通用 NATS，运营分析登记 3 个数据源。不按 Top 维度拆专用接口。
- 第一期不新增图表类型。通信关系图作为独立后续变更，见 `ops-analysis-node-graph`。

## 已确认设计决策

- NATS 用通用契约，不用 Flow 专用 handler。原因：主机综合盘已证明「实例列表 + 指标名切换」可复用；Flow 只是对象类型和指标名不同。
  - `get_monitor_instance_list`：可选 `object_names`、`protocol`（滤 `enabled_protocols`）；返回 `instance_id` / `display_name` / `ip` / `object_name` / `enabled_protocols`。
  - `query_metric_series`：`metric` 用已注册稳定名，`mode=range|instant`，可选 `collect_type`；由实例反查对象并合并序列；不接受裸 PromQL。不改 `query_monitor_data_by_metric` 的 VictoriaMetrics 原结构。
- 运营分析数据源 3 个、指向上述 2 个 NATS：实例选项源（不出图）、受控指标趋势（`range` / 折线）、受控指标排行（`instant` / TopN·表格·单值）。
- 画布组件：单值做 KPI（可周期对比）；折线做 Bytes/s、Packets/s 和 TCP/UDP 多序列；饼图或 TopN 做协议占比；TopN 做 Source / Dest / 源 IP+端口 / 目标 IP+端口 / Protocol；Conversation 用表格多列。通信关系图挂在内置 Flow 盘上。
- 内置初始化加载 `flow_dashboard.yaml`，新环境开箱即有 Flow 盘；数据源仍以 `source_api.json` 为准。
- 协议号到 TCP/UDP、会话展示名、B/s 到 Mbps 都在监控查询或画布单位配置完成，不为此新做图。
- 不复用 `get_host_*`、`query_metric_range_scoped`（只返回第一条且依赖环境相关 `metric_id`）、`get_network_device_resource_top`（SNMP 总流量）、`query_latest_interface_metrics`（IF-MIB）。

## 明确后置

- SNMP 接口告警下钻到具体会话。
- IPFIX 采集接入。
- Sankey、热力图、异常/基线/扫描检测。通信关系图已拆到独立规格，不再算本盘后置项。
- 图表点击钻取、Flows/s、P95。
- 通用多指标快照（四个单值 instant 请求过多时再补）。
- Packetbeat 主机流量与设备 NetFlow 打通。

## 仍待确认

无。

## 已替代决策

- 评估阶段考虑过的「按 Top Source / Destination / Conversation 各开 NATS」未采纳。原因：维度用指标名 `componentSwitch` 即可。
- 「第一期先选对象类型再选实例」未采纳。原因：内置盘还要再做一个对象筛选，混选才能一次看全部 exporter。
- 「第一期新增 Sankey / 通信图 / 热力图」未采纳。原因：现有组件已够第一期。通信关系图于 2026-09-03 改为独立通用图表，随后挂进本盘 YAML。
- TopN「目的端口」未采纳为默认排行维度。原因：只按端口聚合看不出对象。改为源 IP+端口、目标 IP+端口。

## 决策来源

- 用户于 2026-09-03 确认：专属 Flow 仪表盘；混选四类网络设备；2 个通用 NATS + 3 个数据源；第一期不新增图表；会话用表格，Source/Protocol 用 TopN。同日确认通信关系图作为后续通用组件，不复用网络状态拓扑、本盘 YAML 后挂。
- 对照：监控已有 NetFlow v5/v9 与 sFlow 采集及设备级 Top 会话页；运营分析无 Sankey/热力图；`query_metric_range_scoped` 单序列且 `metric_id` 不可移植。
