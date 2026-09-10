# 运营分析 Flow 仪表盘

Status: implemented

## Problem Statement

运维人员已经在监控里接入了 NetFlow/sFlow，但只能在监控对象详情里看设备级 Top 会话。他们希望在运营分析有一张专属 Flow 盘：选一批网络设备后，看到总流量、趋势、协议分布和谁占用带宽。运营分析不能写 PromQL，现有受控查询又只返回第一条序列、且绑环境相关的指标 ID，铺不出可移植的内置盘。

## Solution

监控提供两个通用 NATS 查询（实例选项、指标视图），运营分析登记三个数据源，并由 `init_builtin_canvases` 写入内置 Flow 仪表盘。画布只用现有单值、折线、饼图、TopN、表格。监控继续持有 PromQL、采样率归一化和实例权限。

## User Stories

1. As an 运维人员, I want 在运营分析按权限多选交换机/路由器/防火墙/负载均衡, so that 一张盘能看全部已接入 Flow 的 exporter。
2. As an 运维人员, I want 看到所选设备在时间窗内的总流量、总包速、平均包大小和采样率, so that 先判断有没有异常放量。
3. As an 运维人员, I want 看到 Bytes/s、Packets/s 以及 TCP/UDP 趋势, so that 能分辨突增是哪类协议。
4. As an 运维人员, I want 用 TopN 切换 Source / Destination / 源 IP+端口 / 目标 IP+端口 / Protocol, so that 能回答谁占用带宽。
5. As an 运维人员, I want 用表格看到 Top Conversation 的源、目的、端口、协议和流量, so that 能定位具体通信对象。
6. As an 运维人员, I want 清空设备选择后组件不退回全量, so that 不会误看无权或未选设备的流量。
7. As a 看板搭建者, I want 用稳定指标名而不是环境里的 metric_id 绑数据源, so that 内置盘可以跨环境初始化。

## Implementation Decisions

- 新 NATS：`get_monitor_instance_list`、`query_metric_series`。不新增 Flow 专用 Top 接口，不改 `query_monitor_data_by_metric` 的 VictoriaMetrics 原结构。
- 实例列表默认对象名为 Switch / Router / Firewall / Loadbalance；可选 `protocol` 过滤 `enabled_protocols`；只返回未删除、启用且调用方有权的实例。空 `enabled_protocols` 的实例不出现。出参：`instance_id`、`display_name`、`ip`、`object_name`、`enabled_protocols`。
- `query_metric_series` 入参：`metric`（已注册指标名）、`instance_ids`、`time`、`step`、`mode=range|instant`、可选 `collect_type`、可选 `limit`（instant 默认 10，最大 100）。未选 `instance_ids` 返回空成功，不查 VM。无权 ID 省略；过滤后一个都没有则空成功。实例上限 200。
- 由实例反查监控对象，按对象+插件执行该指标名的注册查询；`collect_type` 过滤插件。剥掉查询外层 `topk`，instant 用时间窗 `avg_over_time`，再按指标维度（去掉 `instance_id`）折叠求和。协议号映射为 TCP/UDP 等短名。会话行提供 `src`、`dst`、`src_port`、`dst_port`、`protocol`、`name`（`src → dst:port`）、`value`。
- `range` 返回 `{series_name: [[ts, value], ...]}`；`instant` 返回按 `value` 降序的行列表。概览指标（无额外维度）instant 折叠成一行 `name=total`。
- 不接受裸 PromQL。非法 `mode`/`metric`/`collect_type`/`limit` 返回失败消息，不崩 worker。
- 运营分析登记三个内置数据源：实例选项（不出图）、趋势（`mode=range`，折线）、排行（`mode=instant`，TopN/表格/单值）。`instance_ids` 与主机盘相同：字符串 + 多选筛选。指标名用组件内切换。
- Flow 仪表盘 YAML 并入 `init_builtin_canvases` 默认文件（`flow_dashboard.yaml` 与 `builtin_canvases.yaml` 合并），数据源仍以 `source_api.json` 为单一事实来源。
- 这些 NATS 不经 OpenAPI 网关对外暴露。

## Testing Decisions

只测外部行为：授权过滤、空选择不查 VM、跨对象合并、协议映射、会话列、range/instant 形状、数据源定义和 YAML 依赖。

接缝：

- 纯函数：折叠、topk 剥离、协议名、会话 `name`、窗口时长（对齐 `host_dashboard.py`）
- NATS handler：授权/空选择/非法参数（对齐 `test_host_dashboard_handler.py`）
- RPC 方法名转发（对齐 `test_monitor_forwarding.py`）
- 契约集合含新 handler（对齐 `test_nats_monitor_handlers.py`；注册名同时在 `test_metric_series_handler.py` 断言，避免依赖 django_db 建库）
- `source_api.json` 定义（对齐 `test_host_dashboard_datasource_definitions.py`）
- YAML 可解析、随 `init_builtin_canvases` 进入内置目录、组件绑定正确数据源

不测 Telegraf 采集、真实 VM、前端 E2E。

## Out of Scope

- SNMP 告警下钻到会话
- IPFIX 接入
- Sankey、通信关系图、热力图、异常/基线/扫描
- 图表点击钻取、Flows/s、P95
- 通用多指标快照
- Packetbeat 与设备 NetFlow 打通
- 新增图表组件

## Further Notes

产品决策：`docs/design/product-decisions/ops-analysis-flow-dashboard.md`。  
通信关系图为后续独立变更：`specs/changes/ops-analysis-node-graph/spec.md`。
