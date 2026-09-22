# 华为交换机 SNMP 接入指南

本插件用于监控华为园区、框式与 CloudEngine 交换机的设备健康：实体 CPU/内存/温度/电压（毫伏换算为伏特）、风扇（状态、在位、满速百分比转速）、整机已用/总功耗与实体单板功耗（瓦特）、整机与板卡能耗（毫瓦）、电源（在位、供电状态、毫安电流、毫伏电压、模块额定瓦特）、光模块 DDM、堆叠/CSS，以及启用后的 M-LAG 成员心跳与成员口状态。接入后仍作为现有交换机对象，无需为 S12700H、S16700 等机型新建监控对象。

## 支持机型

同一插件覆盖下列华为交换机系列。独立框、iStack、CSS 集群与 M-LAG 双活都使用该监控对象，无需再建新对象。

- 园区与汇聚 S 系列：S5700、S6700、S7700、S8700（S8704/S8706/S8710）、S9300
- 框式园区 / CSS：S9700、S12700、S12700E、S12700H、S16700（S16704/S16708）
- CloudEngine CE 系列，含 CE16800-X4/X8/X16、CE16804/CE16808/CE16816，以及 CE6881、CE5881 等 SKU

S12700H 与 S16700 为 V600 代框式机型，仍走本插件与交换机对象。未启用堆叠、CSS 或 M-LAG 的设备对应表为空，不会阻断 CPU、内存、风扇、电源或光模块指标。堆叠/CSS 的 link-up/down 以及 M-LAG 一致性检查是 trap，不是可轮询状态表；链路健康看堆叠口 / CSS 口 / M-LAG 口状态与成员心跳。

## 前置要求

- 选定节点能够访问目标设备的 SNMP 端口（默认 `161/UDP`）。
- 设备已启用 SNMPv2c 或 SNMPv3，并授权只读访问。
- 建议使用 SNMPv3（认证+加密）。若使用 v2c，团体名仅填写在页面专用字段中。
- 只读视图应授权标准 IF-MIB，以及 `1.3.6.1.4.1.2011.5.25.31`（实体健康含电压与单板功耗、风扇转速/在位、整机功耗、电源在位/状态/电参、光模块 DDM）、`1.3.6.1.4.1.2011.6.157`（整机与板卡能耗，毫瓦）、`1.3.6.1.4.1.2011.5.25.183`（堆叠对象 `183.1` 与 CSS 对象 `183.3`）和 `1.3.6.1.4.1.2011.5.25.178.8`（M-LAG 成员口与心跳）。

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

`sysUpTime`（`1.3.6.1.2.1.1.3.0`）应返回 TimeTicks。`sysObjectID`（`1.3.6.1.2.1.1.2.0`）按下列机框字典识别（接口计数走内置 IF-MIB 表，本插件不扩展 IF-MIB）：

## sysObjectID 型号字典

仅机框身份识别。不新建交换机监控对象，不新增私有指标。

| sysObjectID | 展示名 |
| --- | --- |
| `1.3.6.1.4.1.2011.2.239` | CloudEngine CE / dcswitch 家族 |
| `1.3.6.1.4.1.2011.2.239.58` | CE16804 |
| `1.3.6.1.4.1.2011.2.239.59` | CE16808 |
| `1.3.6.1.4.1.2011.2.239.60` | CE16816 |
| `1.3.6.1.4.1.2011.2.239.120` | CE16800-X4 |
| `1.3.6.1.4.1.2011.2.239.121` | CE16800-X8 |
| `1.3.6.1.4.1.2011.2.239.122` | CE16800-X16 |
| `1.3.6.1.4.1.2011.2.383` | S8700 |
| `1.3.6.1.4.1.2011.2.383.3` | S8704 |
| `1.3.6.1.4.1.2011.2.383.1` | S8706 |
| `1.3.6.1.4.1.2011.2.383.2` | S8710 |
| `1.3.6.1.4.1.2011.2.409` | S16700 |
| `1.3.6.1.4.1.2011.2.409.1` | S16704 |
| `1.3.6.1.4.1.2011.2.409.2` | S16708 |

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
- `device_voltage_volts` 按实体报告输入电压（`hwEntityVoltage`，毫伏换算为伏特；维度 `descr` 为 `entPhysicalName`）。与光模块 `device_optical_voltage`（`hwEntityOpticalVoltage`）不同。
- `device_fan_state` 能看到各风扇状态（`hwEntityFanState`：正常/异常）。`device_fan_speed` 为已在位风扇的满速百分比；空槽位看 `device_fan_present`。
- `device_power_used` / `device_power_total` 报告整机已用与总功耗（瓦特，`hwDevicePowerInfoUsedPower` / `hwDevicePowerInfoTotalPower`）。
- `device_entity_board_power` 按实体报告单板功耗（瓦特，`hwEntityBoardPower`；维度 `descr` 为 `entPhysicalName`）。与 ENERGYMNGT 毫瓦序列 `device_board_current_power_mw` / `device_board_rated_power_mw` 单位不同。
- `device_energy_current_power_mw` / `device_energy_average_power_mw` / `device_energy_rated_power_mw` 报告整机能耗（毫瓦，`hwCurrentPower` / `hwAveragePower` / `hwRatedPower`；展示可 ÷1000 为瓦特）。板卡序列为 `device_board_current_power_mw` / `device_board_rated_power_mw`，维度 `hwBoardName`。
- `device_psu_state` 能看到已在位电源模块（`hwEntityPwrState`：供电/未供电/休眠/未知）。空槽位看 `device_psu_present`。已在位模块同时报告 `device_psu_current_mA`（毫安）、`device_psu_voltage_mV`（毫伏）和 `device_psu_rated_power_watts`（模块额定瓦特，不是整机瞬时功耗）。
- 有光模块时，`device_optical_rx_power` / `device_optical_tx_power`（µW 换算为 dBm）以及温度（°C）、电压（mV→V）、偏置电流（µA）有读数。无效哨兵 `2147483647` 会被丢弃。
- 启用 iStack 或 CE 堆叠时，`device_stack_member_role`（`hwMemberStackRole`）和 `device_stack_port_state`（`hwStackPortStatus`，up=1/down=2）有数据。
- 启用 CSS（S12700/S12700H/S9700 类）时，`device_css_member_role`（`hwCssMemberRole`）和 `device_css_port_state`（`hwCssPortOperStatus`，down=0/up=1）有数据。
- 启用 M-LAG 时，`device_mlag_port_state`（`hwPortState`，down=0/up=1）和 `device_mlag_member_heartbeat`（`hwLocalHeartBeatState`，ok=1/lost=2）有数据。

## 常见问题

### 只有 uptime 和接口，没有 CPU/内存

设备 SNMP 视图可能未授权实体健康对象。请确认只读视图包含 `1.3.6.1.4.1.2011.5.25.31`。

### 没有电源或仅有收/发光功率、没有完整 DDM

请确认视图包含 `hwEntityPwrState` / `hwEntityPwrPresent` / `hwEntityPwrCurrent` / `hwEntityPwrVoltage` / `hwEntityPwrPower` 以及 `hwOpticalModuleInfoTable`。空槽位和无模块不会产生序列。电源电流单位为毫安，电压单位为毫伏。

### 没有堆叠、CSS 或 M-LAG 指标

堆叠/CSS/M-LAG 未启用、设备为独立框，或视图未授权对应对象。iStack/CE 使用 `183.1.20` / `183.1.21`；CSS 使用 `183.3.2` / `183.3.4`；M-LAG 使用 `178.8.1.4` / `178.8.1.5`。`183.1.4`/`183.1.5`/`183.1.6`/`183.1.22` 以及 M-LAG 一致性检查是标量或 trap，不是成员/端口/链路表。这不代表整机采集失败。

### 没有毫瓦能耗指标

请确认视图包含 `1.3.6.1.4.1.2011.6.157`。这些序列单位是毫瓦，与 `device_power_used` / `device_power_total`（瓦特）并存。缺少能耗表不代表瓦特整机功耗采集失败。

### 高速口流量为 0 或不准

请确认采集到的仍是现有 64 位 `ifHCInOctets` / `ifHCOutOctets`。本模板不再新增 IF-MIB 计数器。
