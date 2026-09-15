# 华为交换机 SNMP 接入指南

本插件使用 Telegraf `inputs.snmp`，从选定节点采集华为园区、框式及 CloudEngine 交换机的设备健康指标。采集仍走现有交换机 / 网络设备路径（`snmp_huawei`）。接口计数保持当前 IF-MIB 64 位 HC 入/出对，本模板不再新增 IF-MIB 对象。

## 支持机型

同一插件覆盖下列华为交换机系列。独立框、iStack 与 CSS 集群都使用该监控对象，无需再建新对象。

- 园区与汇聚 S 系列：S5700、S6700、S7700、S8700、S9300
- 框式园区 / CSS：S9700、S12700、S12700E、S16700
- CloudEngine CE 系列，含 CE6881、CE5881 等 SKU

未启用堆叠或 CSS 的设备对应表为空，不会阻断 CPU、内存、风扇、电源、光模块或接口指标。堆叠/CSS 的 link-up/down 是 trap，不是可轮询状态表；链路健康看堆叠口 / CSS 口状态。

## 前置要求

- 选定节点能够访问目标设备的 SNMP 端口（默认 `161/UDP`）。
- 设备已启用 SNMPv2c 或 SNMPv3，并授权只读访问。
- 建议使用 SNMPv3（认证+加密）。若使用 v2c，团体名仅填写在页面专用字段中。
- 只读视图应授权标准 IF-MIB，以及 `1.3.6.1.4.1.2011.5.25.31`（实体健康、电源、光模块 DDM）和 `1.3.6.1.4.1.2011.5.25.183`（HUAWEI-STACK-MIB 堆叠对象 `183.1` 与 CSS 对象 `183.3`）。

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

`sysUpTime`（`1.3.6.1.2.1.1.3.0`）应返回 TimeTicks。华为交换机的 `sysObjectID`（`1.3.6.1.2.1.1.2.0`）属于企业号 `2011`。

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
- `device_psu_state` 能看到已在位电源模块（`hwEntityPwrState`：供电/未供电/休眠/未知）。空槽位看 `device_psu_present`。
- 有光模块时，`device_optical_rx_power` / `device_optical_tx_power`（µW 换算为 dBm）以及温度（°C）、电压（mV→V）、偏置电流（µA）有读数。无效哨兵 `2147483647` 会被丢弃。
- 启用 iStack 或 CE 堆叠时，`device_stack_member_role`（`hwMemberStackRole`）和 `device_stack_port_state`（`hwStackPortStatus`，up=1/down=2）有数据。
- 启用 CSS（S12700/S9700 类）时，`device_css_member_role`（`hwCssMemberRole`）和 `device_css_port_state`（`hwCssPortOperStatus`，down=0/up=1）有数据。

## 常见问题

### 只有 uptime 和接口，没有 CPU/内存

设备 SNMP 视图可能未授权实体健康对象。请确认只读视图包含 `1.3.6.1.4.1.2011.5.25.31`。

### 没有电源或仅有收/发光功率、没有完整 DDM

请确认视图包含 `hwEntityPwrState` / `hwEntityPwrPresent` 以及 `hwOpticalModuleInfoTable`。空槽位和无模块不会产生序列。

### 没有堆叠或 CSS 指标

堆叠/CSS 未启用、设备为独立框，或视图未授权 `1.3.6.1.4.1.2011.5.25.183`。iStack/CE 使用 `183.1.20` / `183.1.21`；CSS 使用 `183.3.2` / `183.3.4`。`183.1.4`/`183.1.5`/`183.1.6`/`183.1.22` 是标量或 trap，不是成员/端口/链路表。这不代表整机采集失败。

### 高速口流量为 0 或不准

请确认采集到的仍是现有 64 位 `ifHCInOctets` / `ifHCOutOctets`。本模板不再新增 IF-MIB 计数器。
