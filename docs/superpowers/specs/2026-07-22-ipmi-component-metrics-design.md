# IPMI 部件化指标设计

日期：2026-07-22
状态：已确认，待实施

## 1. 背景

当前硬件服务器 IPMI 插件直接使用 Telegraf `inputs.ipmi_sensor` 上报 `ipmi_sensor_value` 和 `ipmi_sensor_status`，监控指标主要按 Power、Environment 分类。实际环境中的 IPMI SDR 名称包含 PSU、CPU、DIMM、Drive、RAID、硬盘背板和风扇等部件信息，但当前指标没有形成稳定的部件模型。

同时存在两个已确认问题：

1. 当前 PSU 状态查询使用宽泛的 `psu|power supply` 正则，会把 PSU 温度、功率、电压、风扇和故障子项同时当成 PSU 状态。
2. `ipmi_sensor_status{name="host_power"}` 的值表示传感器健康状态，不等于服务器开关机状态；部分服务器也不提供 `Host Power` SDR。

本设计在保留原始指标的前提下，增加厂商无关的部件标准化层。

## 2. 目标

- 监控中心按部件建立一级指标分类，分类下直接展示指标，具体物理部件通过维度区分。
- 保留所有原始 `ipmi_sensor_*` 序列，新增标准化的 `ipmi_<部件>_<指标>` 序列。
- 支持 PSU、CPU、内存、硬盘、RAID 控制器、硬盘背板、风扇和整机。
- 统一健康状态、详细状态和故障检测项的数值表达。
- 使用通用 IPMI SDR 规则；无法可靠解释的厂商专有状态不得猜测。
- 新增逻辑只作用于 IPMI 链路，任何失败不得影响 Telegraf 启动、其他采集插件或原始 IPMI 指标。

## 3. 非目标

- 首版不增加 Lenovo XCC、Dell iDRAC、HPE iLO 等厂商配置。
- 首版不保证解析所有厂商专有离散事件码。
- 不新增持久化的汇总指标；汇总由 PromQL 在查询时完成。
- 不通过 IPMI 替代操作系统 Agent 的 CPU、内存利用率监控。
- 不在本次设计中引入 Redfish、RAID CLI 或 SNMP 作为硬盘状态补充来源。

## 4. 监控中心结构

监控中心维持现有两层结构：

```text
一级：指标分类
二级：指标
指标内部：维度
```

一级分类为：

- 整机
- PSU
- CPU
- 内存
- 硬盘
- RAID 控制器
- 硬盘背板
- 风扇

`PSU 1`、`CPU 0`、`DIMM A1`、`Drive 3`、`Fan 4` 等作为 `component_id` 维度，不注册为独立指标。

## 5. 总体架构

采用 Telegraf 采集端标准化方案：

```text
inputs.ipmi_sensor
        ├── 原始 ipmi_sensor_* 原样上报
        └── processors.starlark 标准化副本
                  ↓
           ipmi_<部件>_<指标>

标准 IPMI chassis power status
        └── 隔离的轻量采集脚本
                  ↓
           ipmi_chassis_power_state
```

Starlark 处理器只接收 IPMI measurement，并为匹配成功的原始样本生成标准化副本。处理器不得改名、删除或修改原始样本。

## 6. 公共维度

| 维度 | 必需 | 含义 |
|---|---|---|
| `instance_id` | 是 | 服务器实例标识，沿用现有值 |
| `component_id` | 是 | 标准化部件标识，如 `psu_1`、`drive_3`、`dimm_a1` |
| `raw_name` | 是 | 原始 IPMI SDR 传感器名称 |
| `profile` | 是 | 首版固定为 `generic` |
| `sensor_id` | 否 | 同一部件下同类传感器的稳定标识 |
| `slot` | 否 | 能可靠提取时记录物理槽位 |
| `direction` | 否 | `input`、`output` 等方向 |
| `fault_type` | 否 | 稳定的故障检测项类型 |
| `location` | 否 | `inlet`、`exhaust`、`ambient` 等位置 |

状态、故障原因等会变化的信息不得直接作为标签。详细状态使用数值枚举，具体故障使用稳定的 `fault_type` 检测项加数值表达。

`component_type` 不作为公共维度，因为指标名称和指标分类已经明确表达部件类型。

## 7. 状态模型

### 7.1 通用健康状态

所有 `*_status` 使用：

```text
 1 = 正常
 0 = 异常
-1 = 未知、无读数、不支持或无法判断
```

### 7.2 详细状态

所有 `*_state` 使用部件专属数值枚举。厂商专有状态码无法由通用规则可靠解释时，详细状态输出 `-1`。

硬盘详细状态首版枚举：

```text
-1 = 未知
 1 = 在线/正常
 2 = 不在位
 3 = 预测故障
 4 = 故障
 5 = 重建中
 6 = 热备
 7 = 离线
```

不在位不能自动判为异常，因为采集端不知道槽位是否应安装硬盘，对应健康状态为 `-1`。

### 7.3 故障检测项

`*_fault` 的样本值使用 `1/0/-1` 表示该故障是否存在：

```text
 1 = 检测到该故障
 0 = 未检测到该故障
-1 = 无法判断
```

这与 `*_status` 的健康语义不同：`status=1` 表示正常，`fault=1` 表示对应故障存在。`fault_type` 表示稳定的检测项，如 `input_failure`、`predictive_failure`，不是当前状态描述。

### 7.4 原始状态码

可获得原始离散状态码时，转换为十进制写入 `*_raw_state_code`。例如 `0x81` 写为 `129`。原始码不直接作为标准健康结论。

## 8. 指标清单

### 8.1 整机

- `ipmi_chassis_power_state`
- `ipmi_chassis_status`
- `ipmi_chassis_fault`
- `ipmi_chassis_power_watts`
- `ipmi_chassis_temperature_celsius`
- `ipmi_chassis_voltage_volts`
- `ipmi_chassis_airflow_cfm`

整机统一使用 `component_id="chassis"`。温度位置使用 `location=inlet|exhaust|ambient|bmc|pch|system_board|other`。

整机故障类型首版支持 `sel_full`、`watchdog`、`intrusion`、`power_fault`、`firmware_error`、`boot_error`、`ntp_sync_failure` 和 `other`。

### 8.2 PSU

- `ipmi_psu_status`
- `ipmi_psu_state`
- `ipmi_psu_fault`
- `ipmi_psu_temperature_celsius`
- `ipmi_psu_power_watts`
- `ipmi_psu_voltage_volts`
- `ipmi_psu_fan_speed_rpm`

`direction=input|output` 区分输入、输出功率和电压。故障类型首版支持 `failure`、`input_failure`、`output_failure`、`power_failure`、`communication_failure`、`mismatch`、`overload` 和 `other`。

### 8.3 CPU

- `ipmi_cpu_status`
- `ipmi_cpu_state`
- `ipmi_cpu_fault`
- `ipmi_cpu_temperature_celsius`
- `ipmi_cpu_power_watts`
- `ipmi_cpu_voltage_volts`
- `ipmi_cpu_utilization_percent`

CPU 编号按原设备保留，不把 `CPU0` 强制改为 `CPU1`。

### 8.4 内存

- `ipmi_memory_status`
- `ipmi_memory_state`
- `ipmi_memory_fault`
- `ipmi_memory_temperature_celsius`
- `ipmi_memory_power_watts`
- `ipmi_memory_voltage_volts`
- `ipmi_memory_utilization_percent`

DIMM 使用 `component_id=dimm_<槽位>` 和 `slot`。整组内存传感器使用 `component_id="memory"`，不得伪装成单根 DIMM。

### 8.5 硬盘

- `ipmi_disk_status`
- `ipmi_disk_state`
- `ipmi_disk_fault`
- `ipmi_disk_temperature_celsius`
- `ipmi_disk_power_watts`
- `ipmi_disk_wear_percent`
- `ipmi_disk_raw_state_code`

`Drive 3`、`Disk 3`、`HDD 3` 和能够可靠确认的 `BPDISK3` 统一为 `component_id="drive_3"`。

磨损度只有原始数据明确为百分比时才上报。离散十六进制值不能当作磨损百分比。

### 8.6 RAID 控制器

- `ipmi_raid_status`
- `ipmi_raid_state`
- `ipmi_raid_fault`
- `ipmi_raid_temperature_celsius`
- `ipmi_raid_battery_status`
- `ipmi_raid_battery_temperature_celsius`

没有控制器编号的 RAID 传感器使用 `component_id="raid"`。RAID BBU 使用稳定的 `battery_id="bbu"`。

### 8.7 硬盘背板

- `ipmi_backplane_status`
- `ipmi_backplane_state`
- `ipmi_backplane_fault`
- `ipmi_backplane_temperature_celsius`

`Rear HDD BP`、`Mid HDD BP` 分别归一为 `backplane_rear`、`backplane_mid`。`BPDISK<n>` 优先识别为对应硬盘，不归入背板整体状态。

### 8.8 风扇

- `ipmi_fan_status`
- `ipmi_fan_state`
- `ipmi_fan_fault`
- `ipmi_fan_speed_rpm`
- `ipmi_fan_power_watts`

双转子风扇使用相同 `component_id`，通过 `sensor_id=front|rear` 区分。PSU 内部风扇优先归入 PSU，不重复进入普通风扇分类。

不得根据 RPM 为零直接判定风扇故障；关机状态下 RPM 为零可能正常。状态来自明确的 IPMI 状态传感器，转速阈值交给告警策略。

## 9. 名称解析和优先级

标准化规则同时使用原始名称、单位和字段类型，不允许仅凭 `psu`、`fan` 等单一关键词确定指标。

规则优先级：

1. 精确特殊规则；
2. 带编号部件规则；
3. 通用部件规则；
4. 无法分类时只保留原始指标。

典型转换：

```text
PSU1_Status       → ipmi_psu_status{component_id="psu_1"}
PSU1_Inlet_Temp   → ipmi_psu_temperature_celsius{component_id="psu_1",sensor_id="inlet"}
PSU1_PIn          → ipmi_psu_power_watts{component_id="psu_1",direction="input"}
PSU1_VOut         → ipmi_psu_voltage_volts{component_id="psu_1",direction="output"}
CPU0_Status       → ipmi_cpu_status{component_id="cpu_0"}
DIMM A1 Temp      → ipmi_memory_temperature_celsius{component_id="dimm_a1",slot="A1"}
Drive 3           → ipmi_disk_status{component_id="drive_3",slot="3"}
Fan 1 Front Tach  → ipmi_fan_speed_rpm{component_id="fan_1",sensor_id="front"}
```

只有能确认部件、稳定编号、指标角色和单位时才生成标准化序列。若多个原始样本会生成相同的指标和标签组合，冲突的标准化副本必须丢弃并记录脱敏日志，原始数据不受影响。

## 10. 整机电源状态采集

`ipmi_chassis_power_state` 使用标准命令：

```bash
ipmitool chassis power status
```

转换规则：

```text
Power is on  → 1
Power is off → 0
命令失败     → -1
```

采集由隔离的轻量包装脚本完成。包装脚本从环境变量读取密码，不允许把密码写入命令参数、标准输出或日志。命令失败必须仍输出 `-1`，不得让 Telegraf 退出或阻断其他输入插件。

SDR 中存在的 `Host Power` 继续作为原始数据保存，但不作为标准开关机结论。

## 11. 链路隔离和可靠性

- Starlark 使用 measurement 过滤，仅处理 IPMI 数据。
- 原始 IPMI metric 必须先保留，标准化采用复制输出，不原地修改。
- Starlark 单条规则失败时丢弃对应标准化副本，不能影响其他规则和原始序列。
- chassis 采集为非关键数据源，超时、认证失败或输出变化统一降级为 `-1`。
- 新增脚本和处理器不得进入服务启动的阻断路径。
- 不修改其他 Telegraf 插件模板、共享处理器或输出配置。
- 不增加无限取值标签；所有可选维度均来自有限规则或原始稳定标识。
- 日志必须脱敏，禁止输出用户名密码组合、密码环境变量值和完整服务器连接串。
- 上线初期保留现有原始查询能力，标准化指标异常时可直接用 `ipmi_sensor_*` 排查和回退。

## 12. 测试设计

实现阶段执行 TDD，先建立失败测试，再实现功能。

1. 名称归一化测试：覆盖三份实际数据中的 PSU、CPU、DIMM、Drive、BPDISK、RAID、背板和前后转子风扇代表样本。
2. 分类优先级测试：确保 PSU 风扇不进入普通风扇、RAID BBU 不进入普通温度、BPDISK 进入硬盘。
3. 指标角色测试：验证状态、温度、输入/输出功率、电压、转速和气流识别。
4. 状态转换测试：覆盖 `1/0/-1`、详细枚举、未知状态码和原始码保留。
5. 模板测试：验证生成的 Telegraf TOML 合法、原始 `inputs.ipmi_sensor` 保留、处理器只作用于 IPMI。
6. chassis 测试：覆盖开机、关机、超时、认证失败、输出格式变化和密码不泄露。
7. 指标清单测试：验证八个分类、指标名、枚举、维度和中英文文案。
8. 链路隔离测试：关闭或破坏标准化处理器、chassis 命令时，其他 Telegraf 输入和原始 IPMI 指标仍能正常输出。
9. 实际样本回归：从用户提供的三个原始文件提取脱敏代表性行作为 fixture，并生成标准化预期结果对照。

改动代码覆盖率不低于仓库要求的 75%，并运行 Server 对应最小门禁。

## 13. 实施顺序

1. 建立脱敏 fixture 和失败测试。
2. 实现通用名称解析和部件识别。
3. 实现 Starlark 标准化副本与链路隔离。
4. 实现 chassis power 状态采集和失败降级。
5. 更新指标分类、指标定义和中英文文案。
6. 修复 PSU 宽泛匹配和 Host Power 状态语义。
7. 运行插件测试、模板验证和 Server 最小门禁。
8. 用三份实际样本生成标准化结果对照表。

## 14. 验收标准

- 三份实际样本中可可靠识别的部件均生成正确的标准化指标和 `component_id`。
- 原始 `ipmi_sensor_*` 指标与改动前保持一致。
- `Drive 3`、`PSU 2`、`DIMM A1` 等体现为维度，不产生按编号拆分的指标名。
- `ns`、disabled 和无法解释的状态不会被误报为正常或异常。
- PSU 温度、功率、电压、风扇和故障项不会再混入 PSU 状态指标。
- 主机开关机状态来自标准 chassis 命令，不再使用 SDR 健康状态代替。
- 标准化或 chassis 采集失败时，其他采集链路和原始 IPMI 数据不受影响。
- 不泄露 IPMI 凭据，不引入高基数动态标签。
