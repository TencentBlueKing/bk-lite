# 华为 WLAN AC SNMP 接入指南

本插件使用 Telegraf `inputs.snmp`，从选定节点采集华为 WLAN 控制器（AC）的设备健康、无线接入点、射频与上联接口指标。

## 前置要求

- 选定节点能够访问目标设备的 SNMP 端口（默认 `161/UDP`）。
- 设备已启用 SNMPv2c 或 SNMPv3，并授权只读访问。
- 建议使用 SNMPv3（认证+加密）。若使用 v2c，团体名仅填写在页面专用字段中，不要写入其他文本框。
- 目标设备需暴露标准 IF-MIB、实体健康对象以及本模板声明的无线控制器对象；部分机型或未授权视图可能缺少个别表项，缺失对象不会阻断其余指标。

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

`sysUpTime`（`1.3.6.1.2.1.1.3.0`）应返回 TimeTicks。`sysObjectID`（`1.3.6.1.2.1.1.2.0`）在华为 WLAN AC 上通常属于 `1.3.6.1.4.1.2011.2.240` 家族。

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| IP | 是 | 无 | 目标设备管理地址。编辑时不可修改。 |
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
- `device_cpu_usage`、`device_memory_usage` 有实体维度读数。
- 机箱功耗可见 `device_power_used` / `device_power_total`（`hwDevicePowerInfoUsedPower` / `hwDevicePowerInfoTotalPower`，单位瓦特）。无效值（`-1` / 空）会被丢弃。
- 有风扇机型可见 `device_fan_state` / `device_fan_speed_pct`（满速百分比），维度为风扇槽位与序列号。无风扇机型风扇表可为空。
- `wlan_cur_joint_ap_num`、`wlan_cur_assoc_sta_num` 与现场规模大致相符。
- `interface_ifHCInOctets` / `interface_ifHCOutOctets` 在上联口上有速率。
- 已插光模块时会出现光模块 DDM 序列（`optical_temp_c`、`optical_voltage_mV`、`optical_bias_uA`、`optical_rx_dbm`、`optical_tx_dbm`）。

## 常见问题

### 只有 uptime 和接口，没有 CPU/内存

设备 SNMP 视图可能未授权实体健康对象。请确认只读视图包含 `1.3.6.1.4.1.2011.5.25.31`。

### 没有机箱已用/总功耗指标

请确认只读视图包含 `1.3.6.1.4.1.2011.5.25.31.3`。这些标量单位为瓦特（`device_power_used` / `device_power_total`）。缺少机箱功耗不代表实体 CPU/内存或 IF-MIB 采集失败。

### 没有风扇转速或风扇状态

无风扇机型 `hwFanStatusTable` 为空是预期行为，不代表采集失败。有风扇机型请确认只读视图包含 `1.3.6.1.4.1.2011.5.25.31.1.1.10`。风扇转速 `device_fan_speed_pct` 是满速百分比，不是 RPM。无效值（`-1` / 空）会被丢弃。

### 没有 AP、终端或射频数据

对应无线对象未授权，或该机型未暴露这些标量/表。请确认只读视图包含 `1.3.6.1.4.1.2011.6.139`。这不代表整机采集失败。

### 高速口流量为 0 或不准

请确认采集到的是 64 位 `ifHCInOctets` / `ifHCOutOctets`。本模板通过公共 IF-MIB 表采集这些计数器。

### 两个终端数量口径不一致

`wlan_cur_assoc_sta_num`（`hwWlanCurAssocStaNum`）是当前已关联会话数；`wlan_sta_cur_num`（`hwWlanStaCurNum`）是控制器当前终端对象数。二者不是同一计数，软件版本或视图差异下可能不相等。容量判断以许可上限 `wlan_access_max_sta_number` 对照关联数；不要把两个口径混用同一阈值。认证成功数 `wlan_cur_auth_success_sta_num` 是第三口径，与关联数差距扩大通常表示认证失败增多。

### 全局无线速率单位

`wlan_global_up_speed` / `wlan_global_down_speed`（`hwWlanGlobalUpSpeed` / `hwWlanGlobalDownSpeed`）按 MIB 以 Kbps 采集，平台单位为 `kbitps`，不做 bit/s 换算。

### 没有光模块 DDM 序列

机箱未插光模块时 `hwOpticalModuleInfoTable` 为空是预期行为。无效读数 `2147483647` 会丢弃。Rx/Tx 功率按 dBm×100 存储，查询侧除以 100 显示为 dBm。电压原始单位为毫伏，查询侧除以 1000 显示为伏特。
