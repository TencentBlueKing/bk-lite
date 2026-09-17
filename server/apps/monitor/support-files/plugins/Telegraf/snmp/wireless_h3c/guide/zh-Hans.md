# H3C 无线控制器 SNMP 接入指南

本插件使用 Telegraf `inputs.snmp`，从选定节点采集 H3C 无线控制器（AC）的设备健康、已连接 AP 数量与关联终端数量。

## 前置要求

- 选定节点能够访问目标设备的 SNMP 端口（默认 `161/UDP`）。
- 设备已启用 SNMPv2c 或 SNMPv3，并授权只读访问。
- 建议使用 SNMPv3（认证+加密）。若使用 v2c，团体名仅填写在页面专用字段中，不要写入其他文本框。
- 目标设备需暴露本模板声明的控制器对象；部分机型或未授权视图可能缺少个别可选标量，缺失对象不会阻断其余指标。

## 接入步骤

1. 确认节点到设备 IP 的 SNMP 连通性（见“接入前校验”）。
2. 选择 SNMP 版本。v2c 填写团体名；v3 填写安全名称、安全级别、认证/加密协议和密码。
3. 按需调整端口、超时和采集间隔。默认端口 `161`，超时 `10` 秒，间隔 `60` 秒。
4. 在监控对象表格中选择节点，填写设备 IP、实例名称和分组。
5. 保存并等待至少一个采集周期。

## 接入前校验

将 `TARGET` 换成设备 IP，将团体名换成只读团体（v3 环境请改用对应的 v3 探测方式）：

```bash
TARGET=192.0.2.10
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.3.0
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.2.0
```

`sysUpTime`（`1.3.6.1.2.1.1.3.0`）应返回 TimeTicks。`sysObjectID`（`1.3.6.1.2.1.1.2.0`）在 H3C Comware 无线控制器上通常属于 `1.3.6.1.4.1.25506` 家族。

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| IP | 是 | 无 | 目标设备管理地址。 |
| 端口 | 是 | `161` | SNMP UDP 端口。 |
| 版本 | 是 | v2c | `v2c` 或 `v3`。 |
| 团体名 | v2c 必填 | `public` | 只读团体名。 |
| 名称 / 级别 / 认证协议 / 认证密码 / 加密协议 / 加密密码 | v3 按级别 | 按页面 | 仅 SNMPv3 使用；密码经环境变量注入，不会写入明文配置。 |
| 超时时间 | 是 | `10` 秒 | 单次 SNMP 请求超时。 |
| 间隔 | 是 | `60` 秒 | 采集周期，最小 `1` 秒。 |
| 节点 | 是 | 无 | 执行采集的节点。 |
| 实例名称 | 是 | 无 | 平台中的展示名称。 |
| 组 | 是 | 无 | 实例所属分组。 |

## 接入后验证

等待至少一个采集周期，确认实例出现并检查：

- `snmp_uptime` 持续增长。
- `device_cpu_usage`、`device_memory_usage` 有实体维度读数。多数物理实体返回 `0`，承载 CPU/内存的板卡才有真实值。
- `wlan_ap_connect_count`、`wlan_station_connect_count` 与现场规模大致相符。

## 常见问题

### 只有 uptime，没有 CPU/内存

设备 SNMP 视图可能未授权实体健康对象。请确认只读视图包含 `1.3.6.1.4.1.25506.2.6`（HH3C-ENTITY-EXT-MIB）。

### 没有 AP 或终端数据

对应无线控制器对象未授权，或该机型未暴露这些标量。请确认只读视图包含 `1.3.6.1.4.1.25506.2.75`（HH3C-DOT11-ACMT-MIB）。这不代表整机采集失败。

### 多数行的 CPU 或内存一直为 0

`hh3cEntityExtCpuUsage` 与 `hh3cEntityExtMemUsage` 按物理实体采集。多数实体返回 `0`，只有实际承载 CPU/内存的板卡为非 0。告警阈值请对准非 0 实体，不要对所有行取平均。

### 没有最大 AP 许可数

`wlan_max_ap_num_permitted`（`hh3cDot11MaxAPNumPermitted`）是可选标量，部分软件版本可能不提供。已连接 AP 数仍以 `wlan_ap_connect_count` 为准。

### 多个 AP 计数口径不一致

`wlan_ap_connect_count`（`hh3cDot11APConnectCount`）是当前已连接 AP 数；`wlan_master_ap_count`（`hh3cDot11MasterAPCount`）是 Master AP 数；`wlan_total_ap_connected`（`hh3cDot11TotalAPconnected`）是另一套合计。三者不是同一计数，软件版本或视图差异下可能不相等。现场规模以已连接数判断；不要把三个口径混用同一阈值。
