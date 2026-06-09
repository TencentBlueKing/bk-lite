### 说明
采集物理服务器的硬件清单信息（序列号、CPU、主板、内存、磁盘、网卡、GPU），标准化同步至 CMDB。采集为**只读**。本插件提供两种采集方式，你可按环境选择：

1. **物理服务器 SSH（JOB）**：通过主机侧命令采集完整硬件资产信息。
2. **【BETA】物理服务器 IPMI（protocol）**：经 BMC 管理口采集基础身份信息，用于带外资产补充。

> `physcial_server.ip_addr` 在 IPMI 采集场景下表示 **BMC 管理口 IP**，不是业务网口地址。

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
