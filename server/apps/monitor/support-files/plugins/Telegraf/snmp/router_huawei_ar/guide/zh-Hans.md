# 华为 AR 路由器 SNMP 接入指南

本插件使用 Telegraf `inputs.snmp`，从选定节点采集 Huawei AR 系列路由器的设备健康、实体电压、单板瓦特功耗、整机/板卡毫瓦能耗与接口流量。

## 前置要求

- 选定节点能够访问目标设备的 SNMP 端口（默认 `161/UDP`）。
- 设备已启用 SNMPv2c 或 SNMPv3，并授权只读访问。
- 建议使用 SNMPv3（认证+加密）。若使用 v2c，团体名仅填写在页面专用字段中，不要写入其他文本框。
- 目标设备需暴露标准 IF-MIB 以及本模板声明的华为私有对象；部分机型或未授权视图可能缺少个别表项，缺失对象不会阻断其余指标。

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

`sysUpTime`（`1.3.6.1.2.1.1.3.0`）应返回 TimeTicks。AR 路由器的 `sysObjectID`（`1.3.6.1.2.1.1.2.0`）属于 `1.3.6.1.4.1.2011.2.224`（hwAR）。

## sysObjectID 型号字典

根节点 `1.3.6.1.4.1.2011.2.224`。下表叶子号是本插件使用的产品身份。

| 叶子 | 展示名称 |
| --- | --- |
| 340 | AR8140-12G10XG |
| 341 | AR8140-T-12G10XG |
| 349 | AR720 |
| 350 | AR730 |
| 363 | AR6710-L50T2X4 |
| 364 | AR6710-L50T2X4-T |
| 365 | AR6710-L26T2X4 |
| 366 | AR6710-L26T2X4-T |
| 368 | AR5710-H8T2TS1 |
| 369 | AR5710-H8T2TS1-T |
| 370 | AR6710-L8T3TS1X2 |
| 371 | AR6710-L8T3TS1X2-T |
| 378 | AR8700-8 |
| 379 | AR6510-L11T1X2 |
| 380 | AR6510-L5T4S4 |
| 381 | AR5510-H8P2TW1 |
| 382 | AR5510-H10T1 |
| 383 | AR5510-L5T-LTE4EA |
| 384 | AR5510-L5T |
| 385 | AR6500-10 |

同一根下的其他叶子仍属 AR 系列。型号字典保持不变，不新建 AR 监控对象。本插件在既有健康指标上增加实体电压（毫伏换算为伏特）、单板功耗（瓦特）与整机/板卡能耗（毫瓦）。

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
- `device_cpu_usage`、`device_memory_usage` 有读数。
- 实体健康指标 `device_voltage_volts`（毫伏换算为伏特）有读数；支持该叶子的机型上 `device_entity_board_power`（瓦特）有读数。二者与 CPU/内存/温度同属 `hwEntityStateTable`，与光模块电压不同。
- 有风扇的机型上 `device_fan_state` / `device_fan_speed`（满速百分比）有读数。
- 有光模块时，`device_optical_rx_power` / `device_optical_tx_power`（µW 换算为 dBm）以及温度（°C）、模块电压（mV→V）、偏置电流（µA）有读数。无效哨兵 `2147483647` 会被丢弃。
- `device_energy_current_power_mw` / `device_energy_average_power_mw` / `device_energy_rated_power_mw` 报告整机能耗（毫瓦，`hwCurrentPower` / `hwAveragePower` / `hwRatedPower`；展示可 ÷1000 为瓦特）。板卡序列为 `device_board_current_power_mw` / `device_board_rated_power_mw`，维度 `hwBoardName`；空名称与 `-1` 会被丢弃。与 `device_entity_board_power`（瓦特）并存，勿混单位。
- `interface_ifHCInOctets` / `interface_ifHCOutOctets` 在业务口上有速率。

接口流量走内置 IF-MIB（`ifTable` / `ifXTable`）。本模板不扩展 IF，不额外采集 `ifHC*` 或 `ifOperStatus` 叶子。

## 常见问题

### 只有 uptime 和接口，没有 CPU/内存

设备 SNMP 视图可能未授权实体健康对象。请确认只读视图包含 `1.3.6.1.4.1.2011.5.25.31`。

### 没有毫瓦能耗指标

请确认视图包含 `1.3.6.1.4.1.2011.6.157`。这些序列单位是毫瓦，与 `device_entity_board_power`（瓦特）并存。缺少能耗表不代表实体电压、单板功耗、CPU/内存或 IF-MIB 采集失败。

### 高速口流量为 0 或不准

请确认采集到的是内置 IF-MIB 表中的 64 位 `ifHCInOctets` / `ifHCOutOctets`。

### sysObjectID 不在上表中

只要 OID 落在 `1.3.6.1.4.1.2011.2.224` 下，设备仍属 AR 系列。采集不依赖上表叶子；字典仅用于型号识别。
