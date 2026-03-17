### 说明
支持基于 SSH 远程执行形式，采集主机操作系统、CPU、内存、磁盘、网络及运行状态核心参数并同步至 CMDB，用于资产盘点与容量评估。

### 前置要求
1. 已开通 SSH 访问（默认端口 22，可自定义），网络连通。
2. 采集账号具备只读执行权限：uname、cat /etc/os-release、lscpu、free、df、ip/ifconfig、uptime。
3. 允许读取 /etc/os-release、/proc/cpuinfo、/proc/meminfo、/proc 下基本信息（间接通过命令）。

### 版本兼容性
#### Linux 系统（支持内核4.x+）
- 兼容 openEuler 22.03/24.03 LTS 系列版本
- 兼容 银河麒麟 V10/V11 系列版本
- 兼容 统信 UOS V20/V25 系列版本
- 兼容 RHEL 7/8/9/10 系列版本

#### Windows 系统
- 兼容 Windows Server 2016 LTSB、Windows Server 2019 LTSC 、Windows Server 2022 LTSC、Windows Server 2025 LTSC 版本
  

### 采集内容
| Key 名称             | 含义                |
| :------------------- | :------------------ |
| host.os_type         | 操作系统类型        |
| host.os_version      | 操作系统版本        |
| host.architecture    | CPU 指令架构        |
| host.hostname        | 主机名              |
| host.cpu_model       | CPU 型号            |
| host.cpu_cores       | CPU 逻辑核心数量    |
| host.mem_total       | 物理内存总量        |
| host.disk_total      | 汇总磁盘容量        |
| host.mac_address     | 第一块网卡 MAC 地址 |
| host.uptime          | 系统运行时长        |
| host.load_avg        | 系统平均负载        |
| host.collection_time | 采集耗时            |
| host.error           | 失败时的错误信息    |

> 补充说明：`host.architecture` 源自 `uname -m`，在龙芯、申威、RISC-V等国产架构上可正常采集；但由于脚本仅对 `x86_64`/`aarch64`/`i386`/`i686` 识别位数，这些架构下内部推导的 `os_bits` 会被标记为 `"unknown"`。`host.cpu_model`、`host.cpu_cores` 在 `lscpu` 和 `/proc/cpuinfo` 权限不足时也会被置为 `"unknown"`；`host.mem_total`、`host.disk_total` 在内存/磁盘统计命令异常时会退化为 `0.0`；`host.mac_address` 在容器等环境下无法解析首块网卡 MAC 时会被置为 `"unknown"`。