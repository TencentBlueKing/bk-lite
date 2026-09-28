# CMDB 物理服务器 Redfish 子实例采集

Status: approved

存储控制器、电源、整机电源状态/健康，以及磁盘寿命和网卡速率，见 `cmdb-redfish-hardware-p0`。该扩展新增模型和字段，不再受下文「不新增模型」约束。

取代 `cmdb-physical-server-redfish` 里「只采集整机身份、不创建子实例」的范围。
凭据、HTTPS、唯一 `ComputerSystem`、实例名和任务归属规则保持不变。

## 目标

Redfish 采集覆盖 SSH 已经写入的整机 CPU/主板字段，以及 `memory`、`disk`、`nic`、`gpu` 子实例。只读标准 Redfish 资源，不访问 OEM 扩展。标准资源没有的字段留空，空字段不覆盖已有值。

子实例挂在本次采集的 BMC 管理 IP 上。SSH 操作系统 IP 与 BMC IP 不同时，仍然是两台 `physcial_server`，本变更不做序列号合并。

## 已锁定的产品决定

- 不新增模型、字段或数据库结构。写入 SSH 插件已经映射的键。
- IPMI 仍只采集整机身份。协议插件可以识别子实例指标，但 IPMI 结果里没有这些指标时不创建子实例。
- 物理服务器采集继续不是权威快照。某次结果没带上的子实例不删除。部件拔出后，旧子实例会留在 CMDB。
- 子集合读取失败或返回 404 时，成功结果里不出现该模型键。不得用空列表表示「没有部件」。
- 单个成员链接非法、越界或读取失败时跳过该成员。集合首页本身已成功时，其余成员仍写入。
- `ComputerSystem` 读取失败、不是恰好一台，或身份采集失败时，整次目标失败，不写子实例。
- 继续只发同源 `GET /redfish/v1`，不跟随重定向，沿用现有响应大小和分页上限。分页上限按每个集合单独计算。
- 整机身份（服务根、Systems、唯一 ComputerSystem）串行读取。子资源成员 GET 使用有限并发，默认 4 路，且不超过 HTTP 客户端连接上限。失败隔离规则不变。
- 不采集 `EthernetInterfaces`。该资源经常是 BMC 自己的管理网口。

## 资源与字段

采集器在唯一 `ComputerSystem` 成功后，只顺着该系统上的标准链接继续读。

### 整机 `physcial_server`

已有字段不变：`ip_addr`、`port`、`serial_number`、`model`、`brand`、`asset_code`。

| 字段 | 来源 | 规则 |
| :--- | :--- | :--- |
| `cpu_vendor` | 第一颗 CPU 的 `Manufacturer` | `ProcessorType` 缺失视为 CPU。`GPU`、`Accelerator` 不计入 |
| `cpu_model` | 该 CPU 的 `Model` | 多颗 CPU 型号不同时保留成员顺序中的第一颗 |
| `cpu_core` | 全部 CPU 的 `TotalCores` 之和 | 采集结果键为 `cpu_cores`，入库字段沿用 SSH 的 `cpu_core`。缺 `TotalCores` 的处理器不计入，不因此失败 |
| `cpu_threads` | 全部 CPU 的 `TotalThreads` 之和 | 同上 |
| `cpu_arch` | 第一颗 CPU 的 `InstructionSet` | 见下表。无法识别时不写该字段 |
| `board_vendor` | `Assembly` 中 `PhysicalContext=SystemBoard` 的 `Vendor` | 只走系统 `Links.Chassis` 指向的机箱 |
| `board_model` | 该成员的 `Model`，否则 `Name` | 多个 SystemBoard 时取第一个带序列号的，否则取第一个 |
| `board_serial` | 该成员的 `SerialNumber` | 不用机箱序列号顶替 |

`InstructionSet` 映射为现有架构编码能识别的令牌：

| InstructionSet | 写入前的 `cpu_arch` | 入库编码 |
| :--- | :--- | :--- |
| `x86-64` | `x86_64` | `x64` |
| `x86` | `i686` | `x86` |
| `ARM-A64` | `aarch64` | `arm64` |
| `ARM-A32` | `armv7l` | `arm` |

`Processors` 不存在或读取失败时，不写任何 `cpu_*`。没有 SystemBoard 时，不写任何 `board_*`。

### 内存 `memory`

来源：`ComputerSystem.Memory`。`Status.State=Absent` 的成员跳过。没有 `DeviceLocator` 且没有 `Id` 的成员跳过。

| 字段 | 来源 |
| :--- | :--- |
| `mem_locator` | `DeviceLocator`，否则 `Id` |
| `mem_part_number` | `PartNumber` |
| `mem_type` | `MemoryDeviceType` |
| `mem_size` | `CapacityMiB // 1024`，单位为整数 GB。缺失或结果为 0 时不写 |
| `mem_sn` | `SerialNumber` |

实例名沿用 `{mem_locator}-{BMC IP}`。`self_device` 为 BMC IP。

### 磁盘 `disk`

来源：`ComputerSystem.Storage` 每个成员的 `Drives`。同一 `@odata.id` 只保留一条。`Status.State=Absent` 的成员跳过。没有 `Id` 且没有 `Name` 的成员跳过。

| 字段 | 来源 |
| :--- | :--- |
| `disk_name` | `Id`，否则 `Name`。只用于实例名，不新增模型字段 |
| `disk_vendor` | `Manufacturer` |
| `disk` | `CapacityBytes // 1024³`，单位为整数 GB。缺失或结果为 0 时不写 |
| `disk_type` | `MediaType`。不用 `Protocol` 填这个字段 |
| `disk_sn` | `SerialNumber` |

实例名沿用 `{disk_name}-{BMC IP}`。

### 网卡 `nic`

来源：系统所链接机箱上的 `NetworkAdapters`，以及 `ComputerSystem` 自身的 `NetworkAdapters`（若存在）。每个适配器读取 `NetworkDeviceFunctions`。没有合法 MAC 的功能不建实例。MAC 使用现有 `normalize_nic_mac`，全零和非法值丢弃。同一规范化 MAC 只保留一条。

| 字段 | 来源 |
| :--- | :--- |
| `nic_mac` | `Ethernet.MACAddress`，否则 `MACAddress` |
| `nic_vendor` | 适配器 `Manufacturer` |
| `nic_model` | 适配器 `Model` |
| `nic_type` | `NetDevFuncType` |
| `nic_iface` | 不写 |
| `nic_pci_addr` | 不写 |

实例名是规范化后的 MAC。包含关系指向 BMC IP 对应的物理服务器。

### GPU `gpu`

来源：`ProcessorType` 为 `GPU` 或 `Accelerator` 的处理器。没有 `Name` 且没有 `Id` 的成员跳过。不读 `PCIeDevices`。

| 字段 | 来源 |
| :--- | :--- |
| `gpu_name` | `Name`，否则 `Id` |
| `gpu_type` | `ProcessorType` |
| `gpu_desc` | `Model` |

实例名沿用 `{gpu_name}-{BMC IP}`。

## 调用链

`PhyscialServerRedfishInfo` 输出与 SSH 相同的结果桶：`physcial_server`、`memory`、`disk`、`nic`、`gpu`，子实例带 `self_device`。

现有采集服务把每个桶写成 `*_info_gauge`。`PhysicalServerProtocolCollectionPlugin` 增加这四个子指标，并使用与 SSH 插件相同的实例名、整数转换、网卡 MAC 和包含关系。`format_metrics` 要识别主机插件那种 `(转换函数, 源字段)` 映射；源字段缺失时跳过，不得抛错。`cpu_arch` 只在采集结果带有令牌时转换；转换结果为 `other` 时不入库。

## 兼容与影响

- 不改 Redfish 任务表单、凭据和 TLS 行为。
- 插件说明里的 Redfish 章节改为上述字段，并写明采不到的 SSH 字段留空、子实例挂在 BMC IP、缺失部件不自动删除。
- IPMI 文档和 IPMI 采集结果不变。

## 验收

- Agent：一台标准 ComputerSystem 能写出整机 CPU/主板和四类子实例；Absent 内存、无 MAC 网口、重复 Drive 被丢弃；GPU/Accelerator 进入 `gpu`，CPU 聚合不含它们。
- Agent：子集合 404 或读取失败时，整机身份仍成功，且结果中没有该模型键。身份采集失败时不返回子实例。
- Agent：子资源链接仍受同源、`/redfish/v1`、大小和分页限制。非法子链接跳过，不把整机打成失败。
- Server：子指标映射为现有实例名和包含关系；空字段不写；`x86_64` 入库为 `x64`；无法识别的架构不写 `cpu_arch`。
- Server：只有整机指标的 IPMI 结果不创建内存、磁盘、网卡或 GPU。
