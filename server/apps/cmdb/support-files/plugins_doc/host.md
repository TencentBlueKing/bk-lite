## 说明
支持基于 SSH 远程执行形式，采集主机操作系统、CPU、内存、磁盘、网络及运行状态核心参数并同步至 CMDB，用于资产盘点与容量评估。

## 前置要求
1. 已开通 SSH 访问（默认端口 22，可自定义），网络连通。
2. 采集账号具备只读执行权限：uname、cat /etc/os-release、lscpu、free、df、ip/ifconfig、uptime。
3. 允许读取 /etc/os-release、/proc/cpuinfo、/proc/meminfo、/proc 下基本信息（间接通过命令）。

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| host.os_type | 操作系统类型 (uname -o) |
| host.os_version | 操作系统版本 (PRETTY_NAME) |
| host.architecture | CPU 指令架构 (uname -m) |
| host.hostname | 主机名 (FQDN 优先) |
| host.cpu_model | CPU 型号 (lscpu / /proc/cpuinfo) |
| host.cpu_cores | CPU 逻辑核心数量 |
| host.mem_total | 物理内存总量 (MB) |
| host.disk_total | 汇总磁盘容量 (df --total 结果) |
| host.mac_address | 第一块网卡 MAC 地址 |
| host.uptime | 系统运行时长 (uptime -p) |
| host.load_avg | 系统平均负载 (1/5/15 分钟) |
| host.collection_time | 采集耗时 (秒) |
| host.error | 失败时的错误信息（成功为空） |