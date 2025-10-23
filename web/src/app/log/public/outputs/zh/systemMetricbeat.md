### Metricbeat system简介

- &zwnj;**基本功能**&zwnj;
  - CPU 使用情况

  - 内存使用情况

  - 磁盘指标

  - 文件系统监控

  - 网络指标

  - 进程监控

  - 系统运行状态

- &zwnj;**主要特点**&zwnj;
  - 覆盖面广

  - 模块化设计

  - 轻量化 & 实时性

  - 跨平台支持

  - 可视化与集成

  - 适合多种应用场景

### Metricbeat system 输出字段


|分组|字段名|描述|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|process|process.state|进程状态，例如 “running”|keyword|
|process|process.cpu.pct|自上次事件以来进程占用的 CPU 时间百分比（按 CPU 核数归一化，0-1）|scaled_float|
|process|process.cpu.start_time|进程启动时间|date|
|process|process.memory.pct|进程占用主内存（RAM）的百分比|scaled_float|
|system.core|system.core.id|CPU 核心编号|long|
|system.core|system.core.total.pct|核心总活跃时间百分比|scaled_float|
|system.core|system.core.user.pct|用户态 CPU 时间百分比|scaled_float|
|system.core|system.core.user.ticks|用户态 CPU 时钟周期数|long|
|system.core|system.core.system.pct|内核态 CPU 时间百分比|scaled_float|
|system.core|system.core.system.ticks|内核态 CPU 时钟周期数|long|
|system.core|system.core.nice.pct|低优先级进程 CPU 时间百分比|scaled_float|
|system.core|system.core.nice.ticks|低优先级进程 CPU 时钟周期数|long|
|system.core|system.core.idle.pct|空闲 CPU 时间百分比|scaled_float|
|system.core|system.core.idle.ticks|空闲 CPU 时钟周期数|long|
|system.core|system.core.iowait.pct|等待（磁盘 I/O）CPU 时间百分比|scaled_float|
|system.core|system.core.iowait.ticks|等待（磁盘 I/O）CPU 时钟周期数|long|
|system.core|system.core.irq.pct|硬件中断 CPU 时间百分比|scaled_float|
|system.core|system.core.irq.ticks|硬件中断 CPU 时钟周期数|long|
|system.core|system.core.softirq.pct|软件中断 CPU 时间百分比|scaled_float|
|system.core|system.core.softirq.ticks|软件中断 CPU 时钟周期数|long|
|system.core|system.core.steal.pct|虚拟 CPU 被抢占等待时间百分比（仅 Unix）|scaled_float|
|system.core|system.core.steal.ticks|虚拟 CPU 被抢占等待 CPU 时钟周期数（仅 Unix）|long|
|system.core|system.core.model_number|CPU 型号编号（仅 Linux）|keyword|
|system.core|system.core.model_name|CPU 型号名称（仅 Linux）|keyword|
|system.core|system.core.mhz|CPU 当前时钟频率（仅 Linux）|float|
|system.core|system.core.core_id|CPU 物理核心 ID（仅 Linux）|keyword|
|system.core|system.core.physical_id|CPU 核物理 ID（仅 Linux）|keyword|
|system.cpu|system.cpu.cores|主机上 CPU 核数|long|
|system.cpu|system.cpu.user.pct|用户态 CPU 时间百分比| |
|system.cpu|system.cpu.system.pct|内核态 CPU 时间百分比|scaled_float|
|system.cpu|system.cpu.nice.pct|低优先级进程 CPU 时间百分比|scaled_float|
|system.cpu|system.cpu.idle.pct|空闲 CPU 时间百分比|scaled_float|
|system.cpu|system.cpu.iowait.pct|等待（磁盘 I/O）CPU 时间百分比|scaled_float|
|system.cpu|system.cpu.irq.pct|硬件中断 CPU 时间百分比|scaled_float|
|system.cpu|system.cpu.softirq.pct|软件中断 CPU 时间百分比|scaled_float|
|system.cpu|system.cpu.steal.pct|虚拟 CPU 被抢占等待 CPU 时间百分比（仅 Unix）|scaled_float|
|system.cpu|system.cpu.total.pct|除 Idle 和 IOWait 外的 CPU 时间百分比|scaled_float|
|system.cpu|system.cpu.user.norm.pct|用户态 CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.system.norm.pct|内核态 CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.nice.norm.pct|低优先级进程 CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.idle.norm.pct|空闲 CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.iowait.norm.pct|等待（磁盘 I/O）CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.irq.norm.pct|硬件中断 CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.softirq.norm.pct|软件中断 CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.steal.norm.pct|虚拟 CPU 被抢占等待 CPU 时间百分比（归一化，仅 Unix）|scaled_float|
|system.cpu|system.cpu.total.norm.pct|除 Idle 和 IOWait 外的 CPU 时间百分比（归一化）|scaled_float|
|system.cpu|system.cpu.user.ticks|用户态 CPU 时钟周期数|long|
|system.cpu|system.cpu.system.ticks|内核态 CPU 时钟周期数|long|
|system.cpu|system.cpu.nice.ticks|低优先级进程 CPU 时钟周期数|long|
|system.cpu|system.cpu.idle.ticks|空闲 CPU 时钟周期数|long|
|system.cpu|system.cpu.iowait.ticks|等待（磁盘 I/O）CPU 时钟周期数|long|
|system.cpu|system.cpu.irq.ticks|硬件中断 CPU 时钟周期数|long|
|system.cpu|system.cpu.softirq.ticks|软件中断 CPU 时钟周期数|long|
|system.cpu|system.cpu.steal.ticks|虚拟 CPU 被抢占等待 CPU 时钟周期数（仅 Unix）|long|
|system.diskio|system.diskio.name|磁盘名称，例如 sda1|keyword|
|system.diskio|system.diskio.serial_number|磁盘序列号（并非所有系统都提供）|keyword|
|system.diskio|system.diskio.read.count|成功完成的读取次数|long|
|system.diskio|system.diskio.write.count|成功完成的写入次数|long|
|system.diskio|system.diskio.read.bytes|成功读取的字节总数（Linux 为扇区数乘以假定扇区大小 512）|long (bytes)|
|system.diskio|system.diskio.write.bytes|成功写入的字节总数（Linux 为扇区数乘以假定扇区大小 512）|long (bytes)|
|system.diskio|system.diskio.read.time|所有读取操作耗费的总毫秒数|long|
|system.diskio|system.diskio.write.time|所有写入操作耗费的总毫秒数|long|
|system.diskio|system.diskio.io.time|执行 I/O 操作耗费的总毫秒数|long|
|system.diskio|system.diskio.io.ops|当前正在进行的 I/O 操作数|long|
|system.entropy|system.entropy.available_bits|可用熵位数|long|
|system.entropy|system.entropy.pct|可用熵占比（相对于 4096 大小的熵池）|scaled_float|
|system.filesystem|system.filesystem.available|非特权用户可用的磁盘空间（字节）|long (bytes)|
|system.filesystem|system.filesystem.device_name|磁盘名称，例如 /dev/disk1|keyword|
|system.filesystem|system.filesystem.type|磁盘类型，例如 ext4；在 Windows 上有时不可用（外部磁盘）|keyword|
|system.filesystem|system.filesystem.mount_point|挂载点，例如 /|keyword|
|system.filesystem|system.filesystem.files|系统上 inode 总数，包括文件、文件夹、符号链接和设备|long|
|system.filesystem|system.filesystem.options|文件系统挂载选项|keyword|
|system.filesystem|system.filesystem.free|可用磁盘空间（字节）|long (bytes)|
|system.filesystem|system.filesystem.free_files|文件系统中可用的 inode 数量|long|
|system.filesystem|system.filesystem.total|磁盘总空间（字节）|long (bytes)|
|system.filesystem|system.filesystem.used.bytes|已使用的磁盘空间（字节）|long (bytes)|
|system.filesystem|system.filesystem.used.pct|已使用磁盘空间百分比|scaled_float|
|system.fsstat|system.fsstat.count|文件系统数量|long|
|system.fsstat|system.fsstat.total_files|系统上 inode 总数，包括文件、文件夹、符号链接和设备（Windows 不适用）|long|
|system.fsstat.total_size|system.fsstat.total_size.free|总可用空间|long (bytes)|
|system.fsstat.total_size|system.fsstat.total_size.used|总已用空间|long (bytes)|
|system.fsstat.total_size|system.fsstat.total_size.total|总空间（已用 + 可用）|long (bytes)|
|system.load|system.load.1|最近 1 分钟的 CPU 负载平均值|scaled_float|
|system.load|system.load.5|最近 5 分钟的 CPU 负载平均值|scaled_float|
|system.load|system.load.15|最近 15 分钟的 CPU 负载平均值|scaled_float|
|system.load|system.load.norm.1|最近 1 分钟的 CPU 负载平均值（除以 CPU 核数）|scaled_float|
|system.load|system.load.norm.5|最近 5 分钟的 CPU 负载平均值（除以 CPU 核数）|scaled_float|
|system.load|system.load.norm.15|最近 15 分钟的 CPU 负载平均值（除以 CPU 核数）|scaled_float|
|system.load|system.load.cores|主机 CPU 核心数|long|
|system.memory|system.memory.total|内存总量（字节）|long (bytes)|
|system.memory|system.memory.used.bytes|已使用的内存（字节）|long (bytes)|
|system.memory|system.memory.free|空闲内存总量（字节），不包括系统缓存和缓冲区|long (bytes)|
|system.memory|system.memory.cached|系统缓存的内存总量（字节）|long (bytes)|
|system.memory|system.memory.used.pct|已使用内存百分比|scaled_float|
|system.memory.actual|system.memory.actual.used.bytes|实际已使用内存（字节），表示总内存与可用内存的差值|long (bytes)|
|system.memory.actual|system.memory.actual.free|实际空闲内存（字节），根据操作系统计算|long (bytes)|
|system.memory.actual|system.memory.actual.used.pct|实际已使用内存百分比|scaled_float|
|system.memory.swap|system.memory.swap.total|交换内存总量（字节）|long (bytes)|
|system.memory.swap|system.memory.swap.used.bytes|已使用交换内存（字节）|long (bytes)|
|system.memory.swap|system.memory.swap.free|可用交换内存（字节）|long (bytes)|
|system.memory.swap|system.memory.swap.used.pct|已使用交换内存百分比|scaled_float|
|system.network|system.network.name|网络接口名称|keyword|
|system.network|system.network.out.bytes|发送字节数|long (bytes)|
|system.network|system.network.in.bytes|接收字节数|long (bytes)|
|system.network|system.network.out.packets|发送数据包数量|long|
|system.network|system.network.in.packets|接收数据包数量|long|
|system.network|system.network.in.errors|接收时的错误数量|long|
|system.network|system.network.out.errors|发送时的错误数量|long|
|system.network|system.network.in.dropped|被丢弃的接收数据包数量|long|
|system.network|system.network.out.dropped|被丢弃的发送数据包数量（Darwin/BSD 始终为 0）|long|
|system.network_summary|system.network_summary.ip.*|IP 计数器|object|
|system.network_summary|system.network_summary.tcp.*|TCP 计数器|object|
|system.network_summary|system.network_summary.udp.*|UDP 计数器|object|
|system.network_summary|system.network_summary.udp_lite.*|UDP Lite 计数器|object|
|system.network_summary|system.network_summary.icmp.*|ICMP 计数器|object|
|system.process|system.process.name|进程名称（别名）|alias|
|system.process|system.process.state|进程状态，例如 "running"|keyword|
|system.process|system.process.pid|进程 ID（别名）|alias|
|system.process|system.process.ppid|父进程 ID（别名）|alias|
|system.process|system.process.pgid|进程组 ID（别名）|alias|
|system.process|system.process.num_threads|进程线程数量|integer|
|system.process|system.process.cmdline|启动进程的完整命令行，包括用空格分隔的参数|keyword|
|system.process|system.process.username|进程所属用户（别名）|alias|
|system.process|system.process.cwd|进程当前工作目录（别名）|alias|
|system.process|system.process.env|启动进程时使用的环境变量（FreeBSD、Linux、OS X 可用）|object|
|system.process.cpu|system.process.cpu.user.ticks|进程在用户空间消耗的 CPU 时间|long|
|system.process.cpu|system.process.cpu.total.value|进程自启动以来的 CPU 使用值|long|
|system.process.cpu|system.process.cpu.total.pct|进程自上次更新以来的 CPU 使用百分比，类似 Unix top 命令 %CPU|scaled_float|
|system.process.cpu|system.process.cpu.total.norm.pct|进程自上次事件以来的 CPU 使用百分比（已按 CPU 核数归一化）|scaled_float|
|system.process.cpu|system.process.cpu.system.ticks|进程在内核空间消耗的 CPU 时间|long|
|system.process.cpu|system.process.cpu.total.ticks|进程消耗的总 CPU 时间|long|
|system.process.cpu|system.process.cpu.start_time|进程启动时间|date|
|system.process.memory|system.process.memory.size|进程虚拟内存总量（字节），Windows 表示 Commit Charge|long (bytes)|
|system.process.memory|system.process.memory.rss.bytes|进程占用的实际内存（RAM）（字节），Windows 表示当前工作集大小|long (bytes)|
|system.process.memory|system.process.memory.rss.pct|进程占用的实际内存百分比|scaled_float|
|system.process.memory|system.process.memory.share|进程使用的共享内存（字节）|long (bytes)|
|system.process.io|system.process.io.cancelled_write_bytes|进程取消写入或未写入的字节数|long|
|system.process.io|system.process.io.read_bytes|从存储层读取的字节数|long|
|system.process.io|system.process.io.write_bytes|写入到存储层的字节数|long|
|system.process.io|system.process.io.read_char|通过 read(2) 等系统调用读取的字节数|long|
|system.process.io|system.process.io.write_char|通过系统调用写入的字节数|long|
|system.process.io|system.process.io.read_ops|读相关系统调用次数|long|
|system.process.io|system.process.io.write_ops|写相关系统调用次数|long|
|system.process.fd|system.process.fd.open|进程打开的文件描述符数量|long|
|system.process.fd|system.process.fd.limit.soft|文件描述符软限制，进程可随时更改|long|
|system.process.fd|system.process.fd.limit.hard|文件描述符硬限制，仅 root 可提升|long|
|system.process.cgroup|system.process.cgroup.id|任务所属 cgroup 的公共 ID|keyword|
|system.process.cgroup|system.process.cgroup.path|相对于 cgroup 子系统挂载点的 cgroup 路径|keyword|
|system.process.cgroup|system.process.cgroup.cgroups_version|进程所属 cgroup 版本|long|
|system.process.cgroup.cpu|system.process.cgroup.cpu.id|cgroup 的 CPU 子系统 ID|keyword|
|system.process.cgroup.cpu|system.process.cgroup.cpu.path|相对于 cgroup 子系统挂载点的 CPU cgroup 路径|keyword|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.usage.ns|cgroup v2 使用的 CPU 时间（纳秒）|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.usage.pct|cgroup v2 使用的 CPU 百分比|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.usage.norm.pct|cgroup v2 归一化使用百分比|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.user.ns|cgroup v2 用户态 CPU 时间（纳秒）|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.user.pct|cgroup v2 用户态 CPU 百分比|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.user.norm.pct|cgroup v2 归一化用户态 CPU 百分比|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.system.ns|cgroup v2 内核态 CPU 时间（纳秒）|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.system.pct|cgroup v2 内核态 CPU 百分比|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.system.norm.pct|cgroup v2 归一化内核态 CPU 百分比|float|
|system.process.cgroup.cpu.cfs|system.process.cgroup.cpu.cfs.period.us|CFS 调度周期（微秒）|long|
|system.process.cgroup.cpu.cfs|system.process.cgroup.cpu.cfs.quota.us|CFS 时间配额（微秒），cgroup 可运行 CPU 总时间|long|
|system.process.cgroup.cpu.cfs|system.process.cgroup.cpu.cfs.shares|CPU 共享权重，必须 >=2|long|
|system.process.cgroup.cpu.rt|system.process.cgroup.cpu.rt.period.us|RT 调度周期（微秒）|long|
|system.process.cgroup.cpu.rt|system.process.cgroup.cpu.rt.runtime.us|RT 调度最长连续运行时间（微秒）|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.periods|已经过的调度周期数量|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.throttled.periods|cgroup 被限流的次数|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.throttled.us|cgroup 被限流的总时间（微秒）|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.throttled.ns|cgroup 被限流的总时间（纳秒）|long|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.10.pct|CPU 部分任务被阻塞的压力（10 秒）|float (%)|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.60.pct|CPU 部分任务被阻塞的压力（60 秒）|float (%)|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.300.pct|CPU 部分任务被阻塞的压力（300 秒）|float (%)|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.total|CPU 部分任务被阻塞总时间|long|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.10.pct|CPU 全部非空闲任务被阻塞的压力（10 秒）|float (%)|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.60.pct|CPU 全部非空闲任务被阻塞的压力（60 秒）|float (%)|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.300.pct|CPU 全部非空闲任务被阻塞的压力（300 秒）|float (%)|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.total|CPU 全部非空闲任务被阻塞总时间|long|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.id|cgroup CPU 会计 ID|keyword|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.path|CPU cgroup 路径|keyword|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.total.ns|cgroup 总 CPU 时间（纳秒）|long|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.total.pct|cgroup CPU 时间百分比|scaled_float|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.total.norm.pct|cgroup CPU 时间归一化百分比|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.user.ns|用户态 CPU 时间（纳秒）|long|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.user.pct|用户态 CPU 百分比|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.user.norm.pct|用户态 CPU 归一化百分比|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.system.ns|内核态 CPU 时间（纳秒）|long|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.system.pct|内核态 CPU 百分比|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.system.norm.pct|内核态 CPU 归一化百分比|scaled_float|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.percpu|每个 CPU 的 cgroup CPU 时间|object|
|system.process.cgroup.memory|system.process.cgroup.memory.id|cgroup 内存 ID|keyword|
|system.process.cgroup.memory|system.process.cgroup.memory.path|cgroup 内存路径|keyword|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.usage.bytes|cgroup 当前内存使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.usage.max.bytes|cgroup 内存最大使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.limit.bytes|内存限制（包括文件缓存）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.failures|达到内存限制次数|long|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.low.bytes|内存低阈值（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.high.bytes|内存高阈值（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.max.bytes|内存最大阈值（字节）|long (bytes)|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.low|低阈值触发次数|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.high|高阈值触发次数|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.max|最大阈值触发次数|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.oom|OOM 阈值触发次数|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.oom_kill|OOM killer 阈值触发次数|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.fail|失败阈值触发次数|long|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.usage.bytes|当前内存 + swap 使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.usage.max.bytes|内存 + swap 最大使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.limit.bytes|内存 + swap 限制|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.low.bytes|内存 + swap 低阈值|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.high.bytes|内存 + swap 高阈值|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.max.bytes|内存 + swap 最大阈值|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.failures|达到内存 + swap 限制次数|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.low|达到内存+swap低阈值触发次数|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.high|达到内存+swap高阈值触发次数|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.max|达到内存+swap最大阈值触发次数|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.oom|达到内存+swap OOM阈值触发次数|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.oom_kill|达到内存+swap OOM killer阈值触发次数|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.fail|达到内存+swap失败阈值触发次数|long|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.usage.bytes|当前内核内存使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.usage.max.bytes|最大内核内存使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.limit.bytes|内核内存限制（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.failures|达到内核内存限制次数|long|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.usage.bytes|TCP 缓冲区内存使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.usage.max.bytes|TCP 缓冲区最大内存使用（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.limit.bytes|TCP 缓冲区内存限制（字节）|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.failures|达到 TCP 缓冲区内存限制次数|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.*|详细内存 IO 统计|object|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.*.bytes|详细内存 IO 统计|object|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.active_anon.bytes|活跃匿名和 swap 缓存（LRU）字节数，包括 tmpfs|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.active_file.bytes|活跃文件-backed 内存字节数|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.cache.bytes|页面缓存，包括 tmpfs|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.hierarchical_memory_limit.bytes|包含此内存 cgroup 的层级内存限制（字节）|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.hierarchical_memsw_limit.bytes|包含此内存 cgroup 的层级内存+swap 限制（字节）|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.inactive_anon.bytes|非活跃匿名和 swap 缓存（LRU）字节数|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.inactive_file.bytes|非活跃文件-backed 内存字节数|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.mapped_file.bytes|内存映射文件大小（包括 tmpfs）|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.page_faults|cgroup 内进程触发页面错误次数|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.major_page_faults|cgroup 内进程触发主页面错误次数|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.pages_in|读入内存的页数|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.pages_out|写出内存的页数|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.rss.bytes|匿名 + swap 缓存（不含 tmpfs）|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.rss_huge.bytes|匿名透明大页字节数|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.swap.bytes|swap 使用字节数|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.unevictable.bytes|不可回收内存（字节）|long (bytes)|
|system.process.cgroup.blkio|system.process.cgroup.blkio.id|cgroup blkio ID|keyword|
|system.process.cgroup.blkio|system.process.cgroup.blkio.path|cgroup blkio 路径|keyword|
|system.process.cgroup.blkio|system.process.cgroup.blkio.total.bytes|blkio 总传输字节数|long (bytes)|
|system.process.cgroup.blkio|system.process.cgroup.blkio.total.ios|blkio 总 I/O 操作次数|long|
|system.process.cgroup.io|system.process.cgroup.io.id|cgroup IO ID|keyword|
|system.process.cgroup.io|system.process.cgroup.io.path|cgroup IO 路径|keyword|
|system.process.cgroup.io|system.process.cgroup.io.stats.*|每设备 IO 使用统计|object|
|system.process.cgroup.io|system.process.cgroup.io.stats..|每设备 IO 使用统计|object|
|system.process.cgroup.io|system.process.cgroup.io.stats...bytes|每设备 IO 字节使用|object|
|system.process.cgroup.io|system.process.cgroup.io.stats...ios|每设备 IO 操作数|object|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.10.pct|全部任务被阻塞压力（10 秒）|float (%)|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.60.pct|全部任务被阻塞压力（60 秒）|float (%)|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.300.pct|全部任务被阻塞压力（300 秒）|float (%)|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.total|全部任务被阻塞总时间|long|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.10.pct|部分任务被阻塞压力（10 秒）|float (%)|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.60.pct|部分任务被阻塞压力（60 秒）|float (%)|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.300.pct|部分任务被阻塞压力（300 秒）|float (%)|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.total|部分任务被阻塞总时间|long|
|system.process.summary|system.process.summary.total|主机进程总数|long|
|system.process.summary|system.process.summary.running|正在运行的进程数|long|
|system.process.summary|system.process.summary.idle|空闲进程数|long|
|system.process.summary|system.process.summary.sleeping|睡眠进程数|long|
|system.process.summary|system.process.summary.stopped|停止进程数|long|
|system.process.summary|system.process.summary.zombie|僵尸进程数|long|
|system.process.summary|system.process.summary.dead|死亡进程数|long|
|system.process.summary|system.process.summary.wakekill|wakekill 状态进程数（老内核）|long|
|system.process.summary|system.process.summary.wake|wake 状态进程数（老内核）|long|
|system.process.summary|system.process.summary.parked|parked| |
|system.process.summary|system.process.summary.unknown|状态无法获取或未知的进程数量|long|
|system.process.summary.threads|system.process.summary.threads.running|当前正在运行的线程数量|long|
|system.process.summary.threads|system.process.summary.threads.blocked|被 I/O 阻塞的线程数量|long|
|system.raid|system.raid.name|RAID 设备名称|keyword|
|system.raid|system.raid.status|设备的活动状态|keyword|
|system.raid|system.raid.level|RAID 级别|keyword|
|system.raid|system.raid.sync_action|RAID 数组当前同步动作，如果是冗余 RAID|keyword|
|system.raid|system.raid.disks.active|活动磁盘数量|long|
|system.raid|system.raid.disks.total|设备包含的总磁盘数量|long|
|system.raid|system.raid.disks.spare|备用磁盘数量|long|
|system.raid|system.raid.disks.failed|失败磁盘数量|long|
|system.raid|system.raid.disks.states.*|原始磁盘状态映射|object|
|system.raid|system.raid.blocks.total|设备块总数（1024 字节块）|long|
|system.raid|system.raid.blocks.synced|已同步块数量（1024 字节块）|long|
|system.service|[system.service.name](http://system.service.name)|服务名称|keyword|
|system.service|system.service.load_state|服务加载状态|keyword|
|system.service|system.service.state|服务活动状态|keyword|
|system.service|system.service.sub_state|服务子状态|keyword|
|system.service|system.service.state_since|上次状态变更时间戳，若服务处于活动运行状态，则为服务上线时间|date|
|system.service|system.service.exec_code|服务主进程的 SIGCHLD 代码|keyword|
|system.service.unit_file|system.service.unit_file.state|单元文件状态|keyword|
|system.service.unit_file|system.service.unit_file.vendor_preset|单元文件默认状态|keyword|
|system.service.resources|system.service.resources.cpu.usage.ns|CPU 使用量（纳秒）|long|
|system.service.resources|system.service.resources.memory.usage.bytes|内存使用量（字节）|long|
|system.service.resources|system.service.resources.tasks.count|与服务相关的任务数|long|
|system.service.resources.network|system.service.resources.network.in.bytes|网络接收字节数|long (bytes)|
|system.service.resources.network|system.service.resources.network.in.packets|网络接收包数|long|
|system.service.resources.network|system.service.resources.network.out.packets|网络发送包数|long|
|system.service.resources.network|system.service.resources.network.out.bytes|网络发送字节数|long (bytes)|
|system.socket|system.socket.direction|套接字方向（别名）|alias|
|system.socket|system.socket.family|套接字类型（别名）|alias|
|system.socket|system.socket.local.ip|本地 IP 地址，可为 IPv4 或 IPv6|ip|
|system.socket|system.socket.local.port|本地端口|long|
|system.socket|system.socket.remote.ip|远端 IP 地址，可为 IPv4 或 IPv6|ip|
|system.socket|system.socket.remote.port|远端端口|long|
|system.socket|system.socket.remote.host|PTR 记录，通过反向 IP 查找获取|keyword|
|system.socket|system.socket.remote.etld_plus_one|远程主机的 eTLD+1|keyword|
|system.socket|system.socket.remote.host_error|反向查找失败的错误描述|keyword|
|system.socket|system.socket.process.pid|套接字所属进程 PID（别名）|alias|
|system.socket|system.socket.process.command|套接字所属进程名（别名）|alias|
|system.socket|system.socket.process.cmdline|套接字所属进程完整命令行|keyword|
|system.socket|system.socket.process.exe|套接字所属进程可执行文件（别名）|alias|
|system.socket|system.socket.user.id|用户 ID（别名）|alias|
|system.socket|system.socket.user.name|用户全名（别名）|alias|
|system.socket.summary.all|system.socket.summary.all.count|所有打开的连接数量|integer|
|system.socket.summary.all|system.socket.summary.all.listening|所有监听端口数量|integer|
|system.socket.summary.tcp|system.socket.summary.tcp.memory|TCP 套接字使用内存（字节），基于分配页数和系统页大小，仅 Linux 可用|integer (bytes)|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.orphan|所有孤立的 TCP 套接字数量（仅 Linux 可用）|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.count|所有打开的 TCP 连接数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.listening|所有 TCP 监听端口数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.established|已建立的 TCP 连接数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.close_wait|TCP 连接处于 close_wait 状态的数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.time_wait|TCP 连接处于 time_wait 状态的数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.syn_sent|TCP 连接处于 syn_sent 状态的数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.syn_recv|TCP 连接处于 syn_recv 状态的数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.fin_wait1|TCP 连接处于 fin_wait1 状态的数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.fin_wait2|TCP 连接处于 fin_wait2 状态的数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.last_ack|TCP 连接处于 last_ack 状态的数量|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.closing|TCP 连接处于 closing 状态的数量|integer|
|system.socket.summary.udp|system.socket.summary.udp.memory|UDP 套接字使用内存（字节），基于分配页数和系统页大小，仅 Linux 可用|integer (bytes)|
|system.socket.summary.udp.all|system.socket.summary.udp.all.count|所有打开的 UDP 连接数量|integer|
|system.uptime|system.uptime.duration.ms|操作系统运行时间（毫秒）|long (duration)|
|system.users|system.users.id|会话 ID|keyword|
|system.users|system.users.seat|关联的 logind seat|keyword|
|system.users|system.users.path|会话的 DBus 对象路径|keyword|
|system.users|system.users.type|用户会话类型|keyword|
|system.users|system.users.service|与服务关联的会话|keyword|
|system.users|system.users.remote|布尔值，指示是否为远程会话|boolean|
|system.users|system.users.state|会话当前状态|keyword|
|system.users|system.users.scope|关联的 systemd scope|keyword|
|system.users|system.users.leader|会话的 root PID|long|
|system.users|system.users.remote_host|会话的远程主机地址|keyword|