### 说明
采集物理服务器的硬件清单信息，标准化同步至 CMDB。采集为**只读**。本插件提供三种采集方式，你可按环境选择：

1. **物理服务器 SSH（JOB）**：通过主机侧命令采集完整硬件资产信息。
2. **【BETA】物理服务器 IPMI（protocol）**：经 BMC 管理口采集基础身份信息，用于带外资产补充。
3. **【BETA】物理服务器 Redfish（protocol）**：经 BMC 的标准 HTTPS API 采集基础身份信息。

三种方式统一以采集目标 IP 构建 `physcial_server.inst_name`。同一 IP 首次成功写入的任务拥有该实例；其他任务受 `collect_task` 过滤和实例名唯一约束，不会更新或重复创建该实例。

---

## 方式一：物理服务器 SSH（JOB）

### 执行方式
本方式为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 前置要求（SSH 方式）
1. **网络连通**：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
2. **采集账号与权限**：**需 root / sudo**。脚本用 `dmidecode` 读取序列号/主板/内存槽，用 `hdparm` / `smartctl` / `nvme` 读取磁盘序列号等，均需 root。
3. **目标依赖**：`dmidecode`、`lscpu`、`lsblk`、`lspci`、`smartctl` 或 `hdparm`、`nvme`；GPU 信息可选依赖 `nvidia-smi`。

### 凭据字段说明（SSH 方式）
- `username`：SSH 登录用户名，需具备 root / sudo 权限。
- `password`：上述账号的密码。落库自动加密，下发时以环境变量注入，不写入明文配置文件。
- `port`：SSH 端口，默认 `22`。

### 采集内容（SSH 方式）
**物理服务器（physcial_server）**

| Key 名称 | 含义 |
| :--- | :--- |
| serial_number | 整机序列号 |
| cpu_vendor | CPU 厂商 |
| cpu_model | CPU 型号 |
| cpu_cores | CPU 物理核心数 |
| cpu_threads | CPU 线程数 |
| cpu_arch | CPU 架构 |
| board_vendor | 主板厂商 |
| board_model | 主板型号 |
| board_serial | 主板序列号 |

**关联子项（以包含/关联挂在物理服务器下）**
- 内存 `memory`：`mem_*` 系列字段。
- 磁盘 `disk`：`disk_*` 系列字段。
- 网卡 `nic`：`nic_*` 系列字段。
- GPU `gpu`：`gpu_*` 系列字段。

---

## 方式二：物理服务器 IPMI（protocol，BETA）

### 说明
经 BMC 管理口采集物理服务器的基础身份信息，agentless（无代理）方式，由接入点直连 BMC。

### 前置要求（IPMI 方式）
1. **网络连通**：接入点到 BMC 的 `623` 端口连通。
2. **账号权限**：IPMI 账号有读权限即可。

### 凭据字段说明（IPMI 方式）
- `host`：BMC 管理口 IP。
- `port`：IPMI 端口，默认 `623`。
- `username`：IPMI 用户名。
- `password`：IPMI 密码。落库自动加密。
- `privilege`：IPMI 权限级别。

### 采集内容（IPMI 方式）
| Key 名称 | 含义 |
| :--- | :--- |
| ip_addr | BMC 管理口 IP |
| serial_number | 整机序列号 |
| model | 产品型号 |
| brand | 厂商 |
| asset_code | 资产标签 |
| board_vendor | 主板厂商 |
| board_model | 主板型号 |
| board_serial | 主板序列号 |

> 补充说明：IPMI 方式仅补充基础身份字段，不创建 `memory` / `disk` / `nic` / `gpu` 关联实例；`asset_code`、`board_serial` 等字段依赖厂商 FRU 实现，可能为空。

---

## 方式三：物理服务器 Redfish（protocol，BETA）

### 说明
Redfish 是服务器 BMC 提供的标准 REST API。本方式通过 HTTPS Basic Auth 读取 `/redfish/v1/` 与唯一的 `ComputerSystem` 资源，不依赖目标操作系统，也不执行写操作。

### 前置要求（Redfish 方式）
1. **网络连通**：接入点到 BMC 的 HTTPS 端口连通，默认 `443`。
2. **账号权限**：使用可读取 Redfish 资产清单的只读或最小权限 BMC 账号。
3. **证书要求**：默认校验服务端 TLS 证书；BMC 使用自签名证书且无法建立可信证书链时，可在任务凭据中明确关闭校验。关闭后仍使用 HTTPS 加密，但无法验证 BMC 身份，存在中间人风险。
4. **目标约束**：一个目标 IP 必须只暴露一台 `ComputerSystem`，以符合“一 IP 一物理服务器资产”的实例规则。

### 凭据字段说明（Redfish 方式）
- `host`：BMC 管理口 IP，也是统一实例名的来源。
- `port`：Redfish HTTPS 端口，默认 `443`。
- `username`：Redfish/BMC 用户名。
- `password`：Redfish/BMC 密码。落库自动加密，下发时通过环境变量引用。
- `verify_tls`：是否校验服务端证书，默认 `true`；仅在受信任管理网络中接入自签名证书时关闭。

### 采集内容（Redfish 方式）
| Key 名称 | Redfish 来源 | 含义 |
| :--- | :--- | :--- |
| ip_addr | 采集目标 | BMC 管理口 IP |
| port | 采集配置 | Redfish HTTPS 端口 |
| serial_number | ComputerSystem.SerialNumber | 整机序列号 |
| model | ComputerSystem.Model | 产品型号 |
| brand | ComputerSystem.Manufacturer | 厂商 |
| asset_code | ComputerSystem.AssetTag | 资产标签 |

> 当前 Redfish MVP 只写入 `physcial_server` 主实例，不创建内存、磁盘、网卡、GPU 等子实例。华为 iBMC 等设备只要正确实现上述标准 Redfish 资源即可接入；厂商 OEM 扩展不作为首版依赖。
