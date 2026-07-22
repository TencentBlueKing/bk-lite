# Historical Superpowers change: 2026-06-17-flow-metrics-enrichment

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-17-flow-metrics-enrichment-design.md

## 背景

网络设备下的内置对象包括交换机、路由器、防火墙、负载均衡。每个对象需要提供两个流量分析监控模板：NetFlow 和 sFlow。

当前 Flow 接入已采用云区域级 Telegraf 接收器：网络设备主动向云区域接收地址上报 Flow 数据，Telegraf 通过 `FLOW_ASSET_MAP_JSON` 将来源设备映射为监控实例，并补充 `instance_id`、`instance_type`、`collect_type`、兜底采样率等标签。

现有 Flow 指标过少，只覆盖入/出方向总流量，不能满足常见的运维趋势观察和流量排障。此次设计目标是优化 Telegraf 采集配置，并补充专业、常用、可运营的 Flow 指标和语言包。

## 目标

1. 为 NetFlow 和 sFlow 提供稳定的云区域级采集配置。
2. 根据 Telegraf 官方建议，将 NetFlow 五元组关键字段转换为 tag，避免流记录在时序存储中因 series key 不完整而互相覆盖。
3. 统一 NetFlow 和 sFlow 的逻辑指标名，让四类网络设备对象获得一致的流量分析能力。
4. 丰富默认运维指标和常用排障指标，同时控制高基数字段的默认展示和告警风险。
5. 完善 `metrics.json`、`policy.json` 和后端语言包中的中英文名称与描述。

## 非目标

1. 不保留旧 Flow 指标名。NetFlow/sFlow 功能尚未正式推出，不需要兼容旧数据或旧模板。
2. 不在第一版实现端口组指标，例如 `dst_port_group`。
3. 不在第一版实现源/目的网段指标，例如 `src_network`、`dst_network`。
4. 不在第一版实现内外网方向指标，例如 `traffic_scope`。
5. 不在第一版将 sFlow 迁移为 `inputs.netflow protocol = "sflow v5"`。该迁移会改变原始 measurement 形态，应另行设计。

## 采集配置设计

修改 `server/apps/node_mgmt/support-files/collectors/Telegraf.json` 中 Linux 和 Windows 两份 `default_config.add_config`。

建议配置结构：

```toml
[[inputs.netflow]]
    service_address = "udp://:2055"
    read_buffer_size = "64MiB"
    tags = { collect_type = "netflow" }

[[inputs.sflow]]
    service_address = "udp://:6343"
    read_buffer_size = "64MiB"
    tags = { collect_type = "sflow" }

[[processors.converter]]
    order = 1
    namepass = ["netflow"]

    [processors.converter.fields]
        tag = ["protocol", "src", "src_port", "dst", "dst_port"]

[[processors.starlark]]
    order = 2
    # 使用 FLOW_ASSET_MAP_JSON 做资产映射和采样率补充
```

关键规则：

1. `inputs.netflow` 第一版不显式固定 `protocol`，避免把通用 NetFlow 接入收窄到单一协议版本。后续如需分别支持 NetFlow v5/v9/IPFIX/sFlow v5，可单独设计协议配置项或多接收器方案。
2. `processors.converter` 仅作用于 `netflow`，将 `protocol`、`src`、`src_port`、`dst`、`dst_port` 从 field 转为 tag。
3. `processors.starlark` 在 converter 之后执行，继续通过 `{cloud_region_id}:{device_ip}` 匹配资产映射。
4. Starlark 命中资产后补充：
   - `instance_id`
   - `instance_type`
   - `collect_type`
   - `fallback_sampling_rate`
   - `effective_sampling_rate`
5. `FLOW_DEVICE_IP_FIELDS` 应覆盖常见来源字段：
   - `agent_ip`
   - `agent_address`
   - `device_ip`
   - `source_ip`
   - `src_addr`
   - `source`
   - `exporter_ip`
6. `FLOW_SAMPLING_FIELDS` 应覆盖现有和常见大小写字段：
   - `effective_sampling_rate`
   - `SAMPLING_INTERVAL`
   - `SAMPLING_ALGORITHM`
   - `sampling_interval`
   - `sampling_algorithm`
   - `sampling_rate`
   - `samplingRate`
7. 如果设备未上报有效采样率，则使用资产上的 `fallback_sampling_rate`。默认值为 `1000`。

采样率提示文案保持：

> 系统优先使用 Flow 数据中携带的采样率进行流量换算；当上报数据中未包含采样率信息时，使用此默认采样率计算。

## 指标体系设计

NetFlow 和 sFlow 使用统一的逻辑指标名。插件仍按协议和对象分文件：

```text
server/apps/monitor/support-files/plugins/Telegraf/netflow/{switch,router,firewall,loadbalance}/metrics.json
server/apps/monitor/support-files/plugins/Telegraf/sflow/{switch,router,firewall,loadbalance}/metrics.json
```

四类对象的指标结构保持一致，只替换 `instance_type`。

### 默认核心指标

这些指标进入 `supplementary_indicators`，适合作为默认监控视图和常规告警输入。

| 指标名 | 含义 | 分组 | 维度 | 单位 |
| --- | --- | --- | --- | --- |
| `device_flow_bytes_rate` | 设备总流量速率 | Traffic Overview | `instance_id` | `byteps` |
| `device_flow_packets_rate` | 设备总包速率 | Traffic Overview | `instance_id` | `pps` |
| `device_flow_in_bytes_rate` | 入方向总流量速率 | Traffic Overview | `instance_id` | `byteps` |
| `device_flow_out_bytes_rate` | 出方向总流量速率 | Traffic Overview | `instance_id` | `byteps` |
| `device_flow_in_packets_rate` | 入方向包速率 | Traffic Overview | `instance_id` | `pps` |
| `device_flow_out_packets_rate` | 出方向包速率 | Traffic Overview | `instance_id` | `pps` |
| `device_flow_avg_packet_size` | 平均包大小 | Traffic Overview | `instance_id` | `bytes` |
| `device_flow_effective_sampling_rate` | 生效采样率 | Sampling | `instance_id` | `none` |

### 接口维度指标

这些指标用于观察接口热点，不默认生成告警策略。

| 指标名 | 含义 | 分组 | 维度 | 单位 |
| --- | --- | --- | --- | --- |
| `device_flow_interface_bytes_rate` | 接口流量速率 | Interface Traffic | `instance_id`, `interface`, `direction` | `byteps` |
| `device_flow_interface_packets_rate` | 接口包速率 | Interface Traffic | `instance_id`, `interface`, `direction` | `pps` |
| `device_flow_top_interfaces_by_bytes` | Top 接口流量速率 | Interface Traffic | `instance_id`, `interface` | `byteps` |

NetFlow 接口字段优先使用 `in_snmp`、`out_snmp`。sFlow 接口字段优先使用 `input_ifindex`、`output_ifindex`。如果设备未上报对应字段，查询结果可为空，不伪造接口维度。

### 协议和端口指标

这些指标用于识别协议或应用端口流量热点。

| 指标名 | 含义 | 分组 | 维度 | 单位 |
| --- | --- | --- | --- | --- |
| `device_flow_protocol_bytes_rate` | 协议流量速率 | Protocol | `instance_id`, `protocol` | `byteps` |
| `device_flow_protocol_packets_rate` | 协议包速率 | Protocol | `instance_id`, `protocol` | `pps` |
| `device_flow_dst_port_bytes_rate` | 目的端口流量速率 | Application Port | `instance_id`, `dst_port` | `byteps` |
| `device_flow_dst_port_packets_rate` | 目的端口包速率 | Application Port | `instance_id`, `dst_port` | `pps` |
| `device_flow_src_port_bytes_rate` | 源端口流量速率 | Application Port | `instance_id`, `src_port` | `byteps` |

### 高级排障指标

这些指标保留 Flow 排障能力，但不进入默认展示字段，不生成默认告警策略。

| 指标名 | 含义 | 分组 | 维度 | 单位 |
| --- | --- | --- | --- | --- |
| `device_flow_top_src_bytes_rate` | Top 源地址流量速率 | Endpoint | `instance_id`, `src` | `byteps` |
| `device_flow_top_dst_bytes_rate` | Top 目的地址流量速率 | Endpoint | `instance_id`, `dst` | `byteps` |
| `device_flow_top_src_packets_rate` | Top 源地址包速率 | Endpoint | `instance_id`, `src` | `pps` |
| `device_flow_top_dst_packets_rate` | Top 目的地址包速率 | Endpoint | `instance_id`, `dst` | `pps` |
| `device_flow_top_conversation_bytes_rate` | Top 会话流量速率 | Conversation | `instance_id`, `src`, `dst`, `protocol`, `dst_port` | `byteps` |

## 查询规则

所有流量类指标统一使用 `effective_sampling_rate` 进行采样率换算。

NetFlow 查询优先使用以下原始指标和标签：

```text
netflow_in_bytes
netflow_in_packets
netflow_out_bytes
netflow_out_packets
src
dst
src_port
dst_port
protocol
in_snmp
out_snmp
effective_sampling_rate
```

sFlow 查询优先使用以下原始指标和标签：

```text
sflow_bytes
sflow_packets
src
dst
src_port
dst_port
protocol
input_ifindex
output_ifindex
effective_sampling_rate
```

如果某些设备未上报方向、接口、端口或协议字段，对应维度指标可以为空。默认核心总量指标应尽量从可用 bytes/packets 字段聚合，保证接入成功后有基础趋势。

## 策略模板设计

`policy.json` 不为高基数字段生成默认策略。

默认策略建议覆盖：

1. `device_flow_bytes_rate`：设备总流量异常。
2. `device_flow_packets_rate`：设备总包量异常。
3. `device_flow_avg_packet_size`：平均包大小异常，可选。

方向级、接口级、协议级、端口级和 TopN 指标只提供查询能力，不默认创建告警策略。

## 语言包设计

修改：

```text
server/apps/monitor/language/zh-Hans.yaml
server/apps/monitor/language/en.yaml
```

补齐内容：

1. `Switch`、`Router`、`Firewall`、`Loadbalance` 四个监控对象下所有新指标的 `name` 和 `desc`。
2. 新增指标组翻译：
   - `Traffic Overview`
   - `Interface Traffic`
   - `Protocol`
   - `Application Port`
   - `Endpoint`
   - `Conversation`
   - `Sampling`
3. 8 个 Flow 插件的 `name` 和 `desc`。
4. 删除或不再引用旧 Flow 指标：
   - `device_total_incoming_netflow_traffic`
   - `device_total_outgoing_netflow_traffic`
   - `device_total_incoming_sflow_traffic`
   - `device_total_outgoing_sflow_traffic`

插件描述应明确包含：

1. 协议类型：NetFlow 或 sFlow。
2. 资产映射：通过上报来源 IP 匹配平台网络设备资产。
3. 采样率归一化：优先使用设备上报采样率，缺失时使用兜底采样率。
4. 分析能力：支持设备总览、接口、协议、端口、端点和会话维度分析。

## 测试计划

### 采集配置测试

扩展 `server/apps/node_mgmt/tests/test_telegraf_flow_listener_config.py`：

1. Linux 和 Windows 两份 `Telegraf.json` 都包含 NetFlow/sFlow UDP listener。
2. NetFlow listener 包含 `read_buffer_size`、`collect_type = "netflow"`，且第一版不强制写死 `protocol`。
3. sFlow listener 包含 `read_buffer_size`、`collect_type = "sflow"`。
4. 包含 `[[processors.converter]]`、`order = 1`、`namepass = ["netflow"]`。
5. converter tag 列表包含 `protocol`、`src`、`src_port`、`dst`、`dst_port`。
6. Starlark processor 包含 `order = 2`。
7. 采样率候选字段包含大小写变体和 `effective_sampling_rate`。
8. `FLOW_ASSET_MAP_JSON` 占位符处理仍通过现有安全性断言。

### 指标文件测试

扩展 `server/apps/monitor/tests/test_flow_plugin_metrics.py`：

1. 8 个 Flow `metrics.json` 都包含统一指标集合。
2. 不再出现旧 Flow 指标名。
3. bytes/packets 类查询都引用 `effective_sampling_rate`。
4. NetFlow 文件不引用 `sflow_*` 原始指标。
5. sFlow 文件不引用 `netflow_*` 原始指标。
6. 高基数维度只出现在高级指标中，不进入默认 `supplementary_indicators`。
7. 每个指标都设置 `instance_id_keys = ["instance_id"]`。

### 语言包测试

新增或扩展 Flow i18n 测试：

1. `zh-Hans.yaml` 和 `en.yaml` 都包含四个对象下所有新 Flow 指标翻译。
2. 每个指标都有 `name` 和 `desc`。
3. 每个新增指标组都有中英文翻译。
4. 8 个 Flow 插件都有中英文名称和描述。
5. 语言包不再引用旧 Flow 指标名。

### 导入验收

通过现有插件导入逻辑验收：

1. 8 个 Flow `metrics.json` 能被导入。
2. 四类网络设备对象都能看到 NetFlow 和 sFlow 两个插件。
3. 插件详情能显示新增指标组和指标。
4. 默认展示字段只包含核心低基数指标。
5. 默认策略不包含 TopN、高基数端点或会话类指标。
6. 现有资产映射、接入检测和采样率提示不被破坏。

## 后续增强

后续可单独设计：

1. 端口组映射：将常见端口归类为 Web、Database、DNS、SSH 等应用组。
2. 网段归类：基于平台或云区域 CIDR 配置生成 `src_network`、`dst_network`。
3. 内外网方向：基于内网 CIDR 补充 `traffic_scope`。
4. sFlow 接收器迁移：评估使用 `inputs.netflow protocol = "sflow v5"` 替代 `inputs.sflow`。
5. Flow 高基数数据的保留期、降采样和 TopN 专用视图。

## 参考

1. Telegraf NetFlow input plugin 官方文档。
2. Telegraf sFlow input plugin 官方文档。
3. Telegraf converter processor 官方文档。
4. 现有设计文档：`docs/superpowers/specs/2026-06-01-network-flow-onboarding-design.md`。
5. 现有设计文档：`docs/superpowers/specs/2026-06-08-flow-region-receiver-telegraf-design.md`。
