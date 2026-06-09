### 说明
采集主机操作系统的基础清单信息（主机名、操作系统、CPU、内存、磁盘、网卡 MAC、运行进程及监听端口），标准化同步至 CMDB，用于资产盘点与容量评估。采集为**只读**，不修改目标任何配置。

> 说明：本插件采集的是“配置/清单”类静态信息（如 CPU 型号、核数、内存容量），不采集 CPU 使用率、负载等性能指标（性能指标属于“监控”模块）。

### 执行方式
本插件为 **JOB（脚本）** 类型，按目标 IP 自动选择执行方式：

| 目标情况 | 执行方式 | 是否需要 SSH 凭据 |
| :--- | :--- | :--- |
| 目标主机**已安装 Agent**（在节点管理的节点列表中） | **本地执行**：Agent 直接在该主机上运行采集脚本 | 不需要 |
| 目标主机**未安装 Agent**（不在节点列表中） | **SSH 远程回退**：由接入点节点 SSH 连入目标执行脚本 | 需要 |

> 一句话：装了 Agent 的机器零凭据即可采集；未装的依赖你填写的 SSH 账号远程采集。

### 版本兼容性
#### Linux 系统（支持内核 4.x+）
- 兼容 openEuler 22.03/24.03 LTS 系列版本
- 兼容 银河麒麟 V10/V11 系列版本
- 兼容 统信 UOS V20/V25 系列版本
- 兼容 RHEL 7/8/9/10 系列版本

#### Windows 系统
- 兼容 Windows Server 2016 LTSB、2019 LTSC、2022 LTSC、2025 LTSC 版本

### 前置要求
1. **网络与连通**
   - SSH 目标：接入点到目标的 SSH 端口（默认 `22`，可自定义）连通。
   - 本地执行目标：该主机的 Agent/Executor 在节点管理中正常在线即可。
2. **采集账号与权限（仅 SSH 远程时需要）**
   - **基础信息**（主机名、OS、CPU、内存、磁盘、MAC）：普通登录账号即可，无需 root/sudo。脚本仅读取 `lscpu`、`free`、`df`、`ip link`、`/etc/os-release`、`/proc` 等全局可读信息。
   - **进程与监听端口（`proc` 字段）**：如需采全所有进程的可执行路径与端口归属，需 **root（或等价权限）**；普通账号只能看到自身进程，进程清单会不完整。
3. **目标依赖**
   - Linux：`/bin/sh` 及 `lscpu`、`free`、`df`、`ip`、`ss`、`ps`、`awk`、`readlink` 等常见命令（多数发行版自带）。JSON 转义由 `awk` 完成，**无需 python3**。
   - Windows：PowerShell 5+。

### 操作步骤
#### 步骤 0：操作入口
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 选择插件 **主机**，点击“新增任务”。

> 任务实际执行发生在你选择的“接入点”上；下面的自测命令应在接入点机器上执行。

#### 步骤 1：网络连通性自测（接入点执行，仅 SSH 目标）
- Linux：`nc -vz <host_ip> 22`
- Windows PowerShell：`Test-NetConnection <host_ip> -Port 22`

判断标准：端口连通即可。

#### 步骤 2：填写任务
- **采集目标**：填写目标 IP 段（支持 CIDR、逗号分隔、区间，如 `10.0.0.1-10.0.0.50`）。
- **凭据**：为“未装 Agent”的目标准备 SSH 凭据（可配置多组，逐个轮试并记录命中）。
- 设置超时与采集周期，保存并执行。

#### 步骤 3：验证结果
- 在任务详情查看 `新增 / 更新 / 删除` 摘要与原始数据；在 CMDB 主机模型下应能查询到对应实例。

### 凭据字段说明
- `username`：SSH 登录用户名（仅 SSH 目标需要），如 `root` 或具备读取权限的普通账号。
- `password`：上述账号的密码。落库自动加密，下发时以环境变量注入，不写入明文配置文件。
- `port`：SSH 端口，默认 `22`。

### 采集内容
**主机（host）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名 |
| ip_addr | 主机 IP |
| hostname | 主机名（`hostname -f`，回退 `hostname`） |
| os_type | 操作系统类型（`uname -s`） |
| os_name | 操作系统名称（`/etc/os-release` NAME） |
| os_version | 操作系统版本（`/etc/os-release` VERSION_ID） |
| os_bit | 系统位数（按架构推导） |
| cpu_arch | CPU 指令架构（`uname -m`） |
| cpu_model | CPU 型号（`lscpu`，回退 `/proc/cpuinfo`） |
| cpu_core | CPU 逻辑核心数 |
| memory | 物理内存总量（GB） |
| disk | 汇总磁盘容量（GB） |
| inner_mac | 首块网卡 MAC 地址（`ip link`） |
| proc | 运行进程清单（含监听端口），写入关联模型 host_proc_usage |

**进程（host_proc_usage，host 的关联子项）**

| Key 名称 | 含义 |
| :--- | :--- |
| pid | 进程 ID |
| name | 进程名 |
| arg | 启动命令行 |
| exe | 可执行文件路径（`readlink /proc/<pid>/exe`） |
| cwd | 工作目录（`readlink /proc/<pid>/cwd`） |
| ports | 该进程监听端口集合（`ss -lntp`） |

> 补充说明：`cpu_model`、`cpu_core` 在 `lscpu`/`/proc/cpuinfo` 权限不足时会被置为 `unknown`；`memory`、`disk` 在统计命令异常时退化为 `0.0`；`inner_mac` 在容器等无法解析首块网卡的环境下置为 `unknown`。`cpu_arch` 源自 `uname -m`，龙芯/申威/RISC-V 等国产架构可正常采集，但 `os_bit` 仅识别 `x86_64`/`aarch64`/`i386`/`i686`，其余架构会标记为 `unknown`。`proc` 中其他用户进程的 `exe`/`cwd`/`ports` 需 root 才能采全。
