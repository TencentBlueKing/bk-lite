### Metricbeat System Introduc### Metricbeat System Output Fields


### Metricbeat System Introduction

**Basic Functions**
  - CPU usage
  - Memory usage
  - Disk metrics
  - File system monitoring
  - Network metrics
  - Process monitoring
  - System runtime status

**Key Features**
  - Comprehensive coverage
  - Modular design
  - Lightweight & real-time
  - Cross-platform support
  - Visualization and integration
  - Suitable for various application scenarios

### Metricbeat System Output Fields


|Group|Field Name|Description|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|process|process.state|Process state, e.g., "running"|keyword|
|process|process.cpu.pct|Percentage of CPU time used by the process since the last event (normalized by CPU cores, 0-1)|scaled_float|
|process|process.cpu.start_time|Process start time|date|
|process|process.memory.pct|Percentage of main memory (RAM) used by the process|scaled_float|j;**Basic Functions**&zwnj;
  - CPU usage

  - Memory usage

  - Disk metrics

  - File system monitoring

  - Network metrics

  - Process monitoring

  - System runtime status

- &zwnj;**Key Features**&zwnj;
  - Comprehensive coverage

  - Modular design

  - Lightweight & real-time

  - Cross-platform support

  - Visualization and integration

  - Suitable for various application scenarios

### Metricbeat system Output Fields


|Group|Field Name|Description|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|process|process.state|Process state, e.g. "running"|keyword|
|process|process.cpu.pct|Percentage of CPU time used by the process since the last event (normalized by CPU cores, 0-1)|scaled_float|
|process|process.cpu.start_time|Process start time|date|
|process|process.memory.pct|Percentage of main memory (RAM) used by the process|scaled_float|
|system.core|system.core.id|CPU core number|long|
|system.core|system.core.total.pct|Total active time percentage of the core|scaled_float|
|system.core|system.core.user.pct|User mode CPU time percentage|scaled_float|
|system.core|system.core.user.ticks|User mode CPU clock cycles|long|
|system.core|system.core.system.pct|Kernel mode CPU time percentage|scaled_float|
|system.core|system.core.system.ticks|Kernel mode CPU clock cycles|long|
|system.core|system.core.nice.pct|Low priority process CPU time percentage|scaled_float|
|system.core|system.core.nice.ticks|Low priority process CPU clock cycles|long|
|system.core|system.core.idle.pct|Idle CPU time percentage|scaled_float|
|system.core|system.core.idle.ticks|Idle CPU clock cycles|long|
|system.core|system.core.iowait.pct|CPU time percentage waiting for disk I/O|scaled_float|
|system.core|system.core.iowait.ticks|CPU clock cycles waiting for disk I/O|long|
|system.core|system.core.irq.pct|Hardware interrupt CPU time percentage|scaled_float|
|system.core|system.core.irq.ticks|Hardware interrupt CPU clock cycles|long|
|system.core|system.core.softirq.pct|Software interrupt CPU time percentage|scaled_float|
|system.core|system.core.softirq.ticks|Software interrupt CPU clock cycles|long|
|system.core|system.core.steal.pct|Virtual CPU preemption wait time percentage (Unix only)|scaled_float|
|system.core|system.core.steal.ticks|Virtual CPU preemption wait CPU clock cycles (Unix only)|long|
|system.core|system.core.model_number|CPU model number (Linux only)|keyword|
|system.core|system.core.model_name|CPU model name (Linux only)|keyword|
|system.core|system.core.mhz|CPU current clock frequency (Linux only)|float|
|system.core|system.core.core_id|CPU physical core ID (Linux only)|keyword|
|system.core|system.core.physical_id|CPU core physical ID (Linux only)|keyword|
|system.cpu|system.cpu.cores|Number of CPU cores on the host|long|
|system.cpu|system.cpu.user.pct|User mode CPU time percentage|scaled_float|
|system.cpu|system.cpu.system.pct|Kernel mode CPU time percentage|scaled_float|
|system.cpu|system.cpu.nice.pct|Low priority process CPU time percentage|scaled_float|
|system.cpu|system.cpu.idle.pct|Idle CPU time percentage|scaled_float|
|system.cpu|system.cpu.iowait.pct|CPU time percentage waiting for disk I/O|scaled_float|
|system.cpu|system.cpu.irq.pct|Hardware interrupt CPU time percentage|scaled_float|
|system.cpu|system.cpu.softirq.pct|Software interrupt CPU time percentage|scaled_float|
|system.cpu|system.cpu.steal.pct|Virtual CPU preemption wait time percentage (Unix only)|scaled_float|
|system.cpu|system.cpu.total.pct|CPU time percentage excluding Idle and IOWait|scaled_float|
|system.cpu|system.cpu.user.norm.pct|User mode CPU time percentage (normalized)|scaled_float|
|system.cpu|system.cpu.system.norm.pct|Kernel mode CPU time percentage (normalized)|scaled_float|
|system.cpu|system.cpu.nice.norm.pct|Low priority process CPU time percentage (normalized)|scaled_float|
|system.cpu|system.cpu.idle.norm.pct|Idle CPU time percentage (normalized)|scaled_float|
|system.cpu|system.cpu.iowait.norm.pct|CPU time percentage waiting for disk I/O (normalized)|scaled_float|
|system.cpu|system.cpu.irq.norm.pct|Hardware interrupt CPU time percentage (normalized)|scaled_float|
|system.cpu|system.cpu.softirq.norm.pct|Software interrupt CPU time percentage (normalized)|scaled_float|
|system.cpu|system.cpu.steal.norm.pct|Virtual CPU preemption wait time percentage (normalized, Unix only)|scaled_float|
|system.cpu|system.cpu.total.norm.pct|CPU time percentage excluding Idle and IOWait (normalized)|scaled_float|
|system.cpu|system.cpu.user.ticks|User mode CPU clock cycles|long|
|system.cpu|system.cpu.system.ticks|Kernel mode CPU clock cycles|long|
|system.cpu|system.cpu.nice.ticks|Low priority process CPU clock cycles|long|
|system.cpu|system.cpu.idle.ticks|Idle CPU clock cycles|long|
|system.cpu|system.cpu.iowait.ticks|CPU clock cycles waiting for disk I/O|long|
|system.cpu|system.cpu.irq.ticks|Hardware interrupt CPU clock cycles|long|
|system.cpu|system.cpu.softirq.ticks|Software interrupt CPU clock cycles|long|
|system.cpu|system.cpu.steal.ticks|Virtual CPU preemption wait CPU clock cycles (Unix only)|long|
|system.diskio|system.diskio.name|Disk name, e.g., sda1|keyword|
|system.diskio|system.diskio.serial_number|Disk serial number (not provided by all systems)|keyword|
|system.diskio|system.diskio.read.count|Number of successful read operations|long|
|system.diskio|system.diskio.write.count|Number of successful write operations|long|
|system.diskio|system.diskio.read.bytes|Total bytes successfully read (Linux: sector count multiplied by assumed sector size 512)|long (bytes)|
|system.diskio|system.diskio.write.bytes|Total bytes successfully written (Linux: sector count multiplied by assumed sector size 512)|long (bytes)|
|system.diskio|system.diskio.read.time|Total milliseconds spent on all read operations|long|
|system.diskio|system.diskio.write.time|Total milliseconds spent on all write operations|long|
|system.diskio|system.diskio.io.time|Total milliseconds spent performing I/O operations|long|
|system.diskio|system.diskio.io.ops|Number of I/O operations currently in progress|long|
|system.entropy|system.entropy.available_bits|Number of available entropy bits|long|
|system.entropy|system.entropy.pct|Available entropy percentage (relative to entropy pool size of 4096)|scaled_float|
|system.filesystem|system.filesystem.available|Disk space available to non-privileged users (bytes)|long (bytes)|
|system.filesystem|system.filesystem.device_name|Disk name, e.g., /dev/disk1|keyword|
|system.filesystem|system.filesystem.type|Disk type, e.g., ext4; sometimes unavailable on Windows (external disks)|keyword|
|system.filesystem|system.filesystem.mount_point|Mount point, e.g., /|keyword|
|system.filesystem|system.filesystem.files|Total number of inodes on the system, including files, folders, symbolic links, and devices|long|
|system.filesystem|system.filesystem.options|File system mount options|keyword|
|system.filesystem|system.filesystem.free|Available disk space (bytes)|long (bytes)|
|system.filesystem|system.filesystem.free_files|Number of available inodes in the file system|long|
|system.filesystem|system.filesystem.total|Total disk space (bytes)|long (bytes)|
|system.filesystem|system.filesystem.used.bytes|Used disk space (bytes)|long (bytes)|
|system.filesystem|system.filesystem.used.pct|Percentage of used disk space|scaled_float|
|system.fsstat|system.fsstat.count|Number of file systems|long|
|system.fsstat|system.fsstat.total_files|Total number of inodes on the system, including files, folders, symbolic links, and devices (not applicable on Windows)|long|
|system.fsstat.total_size|system.fsstat.total_size.free|Total available space|long (bytes)|
|system.fsstat.total_size|system.fsstat.total_size.used|Total used space|long (bytes)|
|system.fsstat.total_size|system.fsstat.total_size.total|Total space (used + available)|long (bytes)|
|system.load|system.load.1|CPU load average for the last 1 minute|scaled_float|
|system.load|system.load.5|CPU load average for the last 5 minutes|scaled_float|
|system.load|system.load.15|CPU load average for the last 15 minutes|scaled_float|
|system.load|system.load.norm.1|CPU load average for the last 1 minute (divided by CPU cores)|scaled_float|
|system.load|system.load.norm.5|CPU load average for the last 5 minutes (divided by CPU cores)|scaled_float|
|system.load|system.load.norm.15|CPU load average for the last 15 minutes (divided by CPU cores)|scaled_float|
|system.load|system.load.cores|Number of CPU cores on the host|long|
|system.memory|system.memory.total|Total memory (bytes)|long (bytes)|
|system.memory|system.memory.used.bytes|Used memory (bytes)|long (bytes)|
|system.memory|system.memory.free|Total free memory (bytes), excluding system cache and buffers|long (bytes)|
|system.memory|system.memory.cached|Total memory cached by the system (bytes)|long (bytes)|
|system.memory|system.memory.used.pct|Percentage of used memory|scaled_float|
|system.memory.actual|system.memory.actual.used.bytes|Actual used memory (bytes), representing the difference between total memory and available memory|long (bytes)|
|system.memory.actual|system.memory.actual.free|Actual free memory (bytes), calculated by the operating system|long (bytes)|
|system.memory.actual|system.memory.actual.used.pct|Percentage of actual used memory|scaled_float|
|system.memory.swap|system.memory.swap.total|Total swap memory (bytes)|long (bytes)|
|system.memory.swap|system.memory.swap.used.bytes|Used swap memory (bytes)|long (bytes)|
|system.memory.swap|system.memory.swap.free|Available swap memory (bytes)|long (bytes)|
|system.memory.swap|system.memory.swap.used.pct|Percentage of used swap memory|scaled_float|
|system.network|system.network.name|Network interface name|keyword|
|system.network|system.network.out.bytes|Number of bytes sent|long (bytes)|
|system.network|system.network.in.bytes|Number of bytes received|long (bytes)|
|system.network|system.network.out.packets|Number of packets sent|long|
|system.network|system.network.in.packets|Number of packets received|long|
|system.network|system.network.in.errors|Number of errors on receive|long|
|system.network|system.network.out.errors|Number of errors on send|long|
|system.network|system.network.in.dropped|Number of received packets dropped|long|
|system.network|system.network.out.dropped|Number of sent packets dropped (always 0 on Darwin/BSD)|long|
|system.network_summary|system.network_summary.ip.*|IP counters|object|
|system.network_summary|system.network_summary.tcp.*|TCP counters|object|
|system.network_summary|system.network_summary.udp.*|UDP counters|object|
|system.network_summary|system.network_summary.udp_lite.*|UDP Lite counters|object|
|system.network_summary|system.network_summary.icmp.*|ICMP counters|object|
|system.process|system.process.name|Process name (alias)|alias|
|system.process|system.process.state|Process state, e.g., "running"|keyword|
|system.process|system.process.pid|Process ID (alias)|alias|
|system.process|system.process.ppid|Parent process ID (alias)|alias|
|system.process|system.process.pgid|Process group ID (alias)|alias|
|system.process|system.process.num_threads|Number of process threads|integer|
|system.process|system.process.cmdline|Complete command line used to start the process, including space-separated arguments|keyword|
|system.process|system.process.username|User who owns the process (alias)|alias|
|system.process|system.process.cwd|Current working directory of the process (alias)|alias|
|system.process|system.process.env|Environment variables used when starting the process (available on FreeBSD, Linux, OS X)|object|
|system.process.cpu|system.process.cpu.user.ticks|CPU time consumed by the process in user space|long|
|system.process.cpu|system.process.cpu.total.value|CPU usage value of the process since startup|long|
|system.process.cpu|system.process.cpu.total.pct|CPU usage percentage of the process since the last update, similar to Unix top command %CPU|scaled_float|
|system.process.cpu|system.process.cpu.total.norm.pct|CPU usage percentage of the process since the last event (normalized by CPU cores)|scaled_float|
|system.process.cpu|system.process.cpu.system.ticks|CPU time consumed by the process in kernel space|long|
|system.process.cpu|system.process.cpu.total.ticks|Total CPU time consumed by the process|long|
|system.process.cpu|system.process.cpu.start_time|Process start time|date|
|system.process.memory|system.process.memory.size|Total virtual memory of the process (bytes), represents Commit Charge on Windows|long (bytes)|
|system.process.memory|system.process.memory.rss.bytes|Actual memory (RAM) occupied by the process (bytes), represents current working set size on Windows|long (bytes)|
|system.process.memory|system.process.memory.rss.pct|Percentage of actual memory occupied by the process|scaled_float|
|system.process.memory|system.process.memory.share|Shared memory used by the process (bytes)|long (bytes)|
|system.process.io|system.process.io.cancelled_write_bytes|Number of bytes the process cancelled writing or didn't write|long|
|system.process.io|system.process.io.read_bytes|Number of bytes read from the storage layer|long|
|system.process.io|system.process.io.write_bytes|Number of bytes written to the storage layer|long|
|system.process.io|system.process.io.read_char|Number of bytes read through read(2) and other system calls|long|
|system.process.io|system.process.io.write_char|Number of bytes written through system calls|long|
|system.process.io|system.process.io.read_ops|Number of read-related system calls|long|
|system.process.io|system.process.io.write_ops|Number of write-related system calls|long|
|system.process.fd|system.process.fd.open|Number of file descriptors opened by the process|long|
|system.process.fd|system.process.fd.limit.soft|File descriptor soft limit, can be changed by the process at any time|long|
|system.process.fd|system.process.fd.limit.hard|File descriptor hard limit, can only be raised by root|long|
|system.process.cgroup|system.process.cgroup.id|Common ID of cgroup to which the task belongs|keyword|
|system.process.cgroup|system.process.cgroup.path|Cgroup path relative to the cgroup subsystem mount point|keyword|
|system.process.cgroup|system.process.cgroup.cgroups_version|Version of cgroup to which the process belongs|long|
|system.process.cgroup.cpu|system.process.cgroup.cpu.id|CPU subsystem ID of cgroup|keyword|
|system.process.cgroup.cpu|system.process.cgroup.cpu.path|CPU cgroup path relative to the cgroup subsystem mount point|keyword|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.usage.ns|CPU time used by cgroup v2 (nanoseconds)|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.usage.pct|CPU percentage used by cgroup v2|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.usage.norm.pct|Cgroup v2 normalized usage percentage|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.user.ns|Cgroup v2 user mode CPU time (nanoseconds)|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.user.pct|Cgroup v2 user mode CPU percentage|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.user.norm.pct|Cgroup v2 normalized user mode CPU percentage|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.system.ns|Cgroup v2 kernel mode CPU time (nanoseconds)|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.system.pct|Cgroup v2 kernel mode CPU percentage|float|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.system.norm.pct|Cgroup v2 normalized kernel mode CPU percentage|float|
|system.process.cgroup.cpu.cfs|system.process.cgroup.cpu.cfs.period.us|CFS scheduling period (microseconds)|long|
|system.process.cgroup.cpu.cfs|system.process.cgroup.cpu.cfs.quota.us|CFS time quota (microseconds), total CPU time cgroup can run|long|
|system.process.cgroup.cpu.cfs|system.process.cgroup.cpu.cfs.shares|CPU share weight, must be >=2|long|
|system.process.cgroup.cpu.rt|system.process.cgroup.cpu.rt.period.us|RT scheduling period (microseconds)|long|
|system.process.cgroup.cpu.rt|system.process.cgroup.cpu.rt.runtime.us|RT scheduling maximum continuous runtime (microseconds)|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.periods|Number of elapsed scheduling periods|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.throttled.periods|Number of times cgroup was throttled|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.throttled.us|Total time cgroup was throttled (microseconds)|long|
|system.process.cgroup.cpu.stats|system.process.cgroup.cpu.stats.throttled.ns|Total time cgroup was throttled (nanoseconds)|long|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.10.pct|CPU pressure with some tasks blocked (10 seconds)|float (%)|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.60.pct|CPU pressure with some tasks blocked (60 seconds)|float (%)|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.300.pct|CPU pressure with some tasks blocked (300 seconds)|float (%)|
|system.process.cgroup.cpu.pressure.some|system.process.cgroup.cpu.pressure.some.total|Total time with some CPU tasks blocked|long|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.10.pct|CPU pressure with all non-idle tasks blocked (10 seconds)|float (%)|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.60.pct|CPU pressure with all non-idle tasks blocked (60 seconds)|float (%)|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.300.pct|CPU pressure with all non-idle tasks blocked (300 seconds)|float (%)|
|system.process.cgroup.cpu.pressure.full|system.process.cgroup.cpu.pressure.full.total|Total time with all non-idle CPU tasks blocked|long|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.id|Cgroup CPU accounting ID|keyword|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.path|CPU cgroup path|keyword|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.total.ns|Total cgroup CPU time (nanoseconds)|long|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.total.pct|Cgroup CPU time percentage|scaled_float|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.total.norm.pct|Cgroup CPU time normalized percentage|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.user.ns|User mode CPU time (nanoseconds)|long|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.user.pct|User mode CPU percentage|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.user.norm.pct|User mode CPU normalized percentage|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.system.ns|Kernel mode CPU time (nanoseconds)|long|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.system.pct|Kernel mode CPU percentage|scaled_float|
|system.process.cgroup.cpuacct.stats|system.process.cgroup.cpuacct.stats.system.norm.pct|Kernel mode CPU normalized percentage|scaled_float|
|system.process.cgroup.cpuacct|system.process.cgroup.cpuacct.percpu|Cgroup CPU time per CPU|object|
|system.process.cgroup.memory|system.process.cgroup.memory.id|Cgroup memory ID|keyword|
|system.process.cgroup.memory|system.process.cgroup.memory.path|Cgroup memory path|keyword|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.usage.bytes|Current cgroup memory usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.usage.max.bytes|Maximum cgroup memory usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.limit.bytes|Memory limit (including file cache)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.failures|Number of times memory limit was reached|long|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.low.bytes|Memory low threshold (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.high.bytes|Memory high threshold (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.mem.max.bytes|Memory maximum threshold (bytes)|long (bytes)|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.low|Number of low threshold triggers|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.high|Number of high threshold triggers|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.max|Number of maximum threshold triggers|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.oom|Number of OOM threshold triggers|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.oom_kill|Number of OOM killer threshold triggers|long|
|system.process.cgroup.memory.mem.events|system.process.cgroup.memory.mem.events.fail|Number of failure threshold triggers|long|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.usage.bytes|Current memory + swap usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.usage.max.bytes|Maximum memory + swap usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.limit.bytes|Memory + swap limit|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.low.bytes|Memory + swap low threshold|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.high.bytes|Memory + swap high threshold|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.max.bytes|Memory + swap maximum threshold|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.memsw.failures|Number of times memory + swap limit was reached|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.low|Number of times memory+swap low threshold was reached|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.high|Number of times memory+swap high threshold was reached|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.max|Number of times memory+swap maximum threshold was reached|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.oom|Number of times memory+swap OOM threshold was reached|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.oom_kill|Number of times memory+swap OOM killer threshold was reached|long|
|system.process.cgroup.memory.memsw.events|system.process.cgroup.memory.memsw.events.fail|Number of times memory+swap failure threshold was reached|long|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.usage.bytes|Current kernel memory usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.usage.max.bytes|Maximum kernel memory usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.limit.bytes|Kernel memory limit (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem.failures|Number of times kernel memory limit was reached|long|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.usage.bytes|TCP buffer memory usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.usage.max.bytes|Maximum TCP buffer memory usage (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.limit.bytes|TCP buffer memory limit (bytes)|long (bytes)|
|system.process.cgroup.memory|system.process.cgroup.memory.kmem_tcp.failures|Number of times TCP buffer memory limit was reached|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.*|Detailed memory IO statistics|object|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.*.bytes|Detailed memory IO statistics|object|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.active_anon.bytes|Active anonymous and swap cache (LRU) bytes, including tmpfs|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.active_file.bytes|Active file-backed memory bytes|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.cache.bytes|Page cache, including tmpfs|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.hierarchical_memory_limit.bytes|Hierarchical memory limit of memory cgroup containing this one (bytes)|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.hierarchical_memsw_limit.bytes|Hierarchical memory+swap limit of memory cgroup containing this one (bytes)|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.inactive_anon.bytes|Inactive anonymous and swap cache (LRU) bytes|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.inactive_file.bytes|Inactive file-backed memory bytes|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.mapped_file.bytes|Memory-mapped file size (including tmpfs)|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.page_faults|Number of page faults triggered by processes in cgroup|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.major_page_faults|Number of major page faults triggered by processes in cgroup|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.pages_in|Number of pages read into memory|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.pages_out|Number of pages written out of memory|long|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.rss.bytes|Anonymous + swap cache (excluding tmpfs)|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.rss_huge.bytes|Anonymous transparent huge pages bytes|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.swap.bytes|Swap usage bytes|long (bytes)|
|system.process.cgroup.memory.stats|system.process.cgroup.memory.stats.unevictable.bytes|Unevictable memory (bytes)|long (bytes)|
|system.process.cgroup.blkio|system.process.cgroup.blkio.id|Cgroup blkio ID|keyword|
|system.process.cgroup.blkio|system.process.cgroup.blkio.path|Cgroup blkio path|keyword|
|system.process.cgroup.blkio|system.process.cgroup.blkio.total.bytes|Total blkio transfer bytes|long (bytes)|
|system.process.cgroup.blkio|system.process.cgroup.blkio.total.ios|Total blkio I/O operations|long|
|system.process.cgroup.io|system.process.cgroup.io.id|Cgroup IO ID|keyword|
|system.process.cgroup.io|system.process.cgroup.io.path|Cgroup IO path|keyword|
|system.process.cgroup.io|system.process.cgroup.io.stats.*|Per-device IO usage statistics|object|
|system.process.cgroup.io|system.process.cgroup.io.stats..|Per-device IO usage statistics|object|
|system.process.cgroup.io|system.process.cgroup.io.stats...bytes|Per-device IO byte usage|object|
|system.process.cgroup.io|system.process.cgroup.io.stats...ios|Per-device IO operation count|object|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.10.pct|All tasks blocked pressure (10 seconds)|float (%)|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.60.pct|All tasks blocked pressure (60 seconds)|float (%)|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.300.pct|All tasks blocked pressure (300 seconds)|float (%)|
|system.process.cgroup.io.pressure.full|system.process.cgroup.io.pressure.full.total|Total time with all tasks blocked|long|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.10.pct|Some tasks blocked pressure (10 seconds)|float (%)|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.60.pct|Some tasks blocked pressure (60 seconds)|float (%)|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.300.pct|Some tasks blocked pressure (300 seconds)|float (%)|
|system.process.cgroup.io.pressure.some|system.process.cgroup.io.pressure.some.total|Total time with some tasks blocked|long|
|system.process.summary|system.process.summary.total|Total number of processes on the host|long|
|system.process.summary|system.process.summary.running|Number of running processes|long|
|system.process.summary|system.process.summary.idle|Number of idle processes|long|
|system.process.summary|system.process.summary.sleeping|Number of sleeping processes|long|
|system.process.summary|system.process.summary.stopped|Number of stopped processes|long|
|system.process.summary|system.process.summary.zombie|Number of zombie processes|long|
|system.process.summary|system.process.summary.dead|Number of dead processes|long|
|system.process.summary|system.process.summary.wakekill|Number of processes in wakekill state (old kernels)|long|
|system.process.summary|system.process.summary.wake|Number of processes in wake state (old kernels)|long|
|system.process.summary|system.process.summary.parked|Number of processes in parked state|long|
|system.process.summary|system.process.summary.unknown|Number of processes with unknown or unavailable state|long|
|system.process.summary.threads|system.process.summary.threads.running|Number of currently running threads|long|
|system.process.summary.threads|system.process.summary.threads.blocked|Number of threads blocked by I/O|long|
|system.raid|system.raid.name|RAID device name|keyword|
|system.raid|system.raid.status|Active status of the device|keyword|
|system.raid|system.raid.level|RAID level|keyword|
|system.raid|system.raid.sync_action|Current sync action of RAID array, if redundant RAID|keyword|
|system.raid|system.raid.disks.active|Number of active disks|long|
|system.raid|system.raid.disks.total|Total number of disks in the device|long|
|system.raid|system.raid.disks.spare|Number of spare disks|long|
|system.raid|system.raid.disks.failed|Number of failed disks|long|
|system.raid|system.raid.disks.states.*|Raw disk state mapping|object|
|system.raid|system.raid.blocks.total|Total number of blocks in the device (1024-byte blocks)|long|
|system.raid|system.raid.blocks.synced|Number of synced blocks (1024-byte blocks)|long|
|system.service|system.service.name|Service name|keyword|
|system.service|system.service.load_state|Service load state|keyword|
|system.service|system.service.state|Service active state|keyword|
|system.service|system.service.sub_state|Service sub state|keyword|
|system.service|system.service.state_since|Timestamp of last state change, or service online time if in active running state|date|
|system.service|system.service.exec_code|SIGCHLD code of service main process|keyword|
|system.service.unit_file|system.service.unit_file.state|Unit file state|keyword|
|system.service.unit_file|system.service.unit_file.vendor_preset|Unit file default state|keyword|
|system.service.resources|system.service.resources.cpu.usage.ns|CPU usage (nanoseconds)|long|
|system.service.resources|system.service.resources.memory.usage.bytes|Memory usage (bytes)|long|
|system.service.resources|system.service.resources.tasks.count|Number of tasks associated with the service|long|
|system.service.resources.network|system.service.resources.network.in.bytes|Network received bytes|long (bytes)|
|system.service.resources.network|system.service.resources.network.in.packets|Network received packets|long|
|system.service.resources.network|system.service.resources.network.out.packets|Network sent packets|long|
|system.service.resources.network|system.service.resources.network.out.bytes|Network sent bytes|long (bytes)|
|system.socket|system.socket.direction|Socket direction (alias)|alias|
|system.socket|system.socket.family|Socket type (alias)|alias|
|system.socket|system.socket.local.ip|Local IP address, can be IPv4 or IPv6|ip|
|system.socket|system.socket.local.port|Local port|long|
|system.socket|system.socket.remote.ip|Remote IP address, can be IPv4 or IPv6|ip|
|system.socket|system.socket.remote.port|Remote port|long|
|system.socket|system.socket.remote.host|PTR record obtained through reverse IP lookup|keyword|
|system.socket|system.socket.remote.etld_plus_one|eTLD+1 of remote host|keyword|
|system.socket|system.socket.remote.host_error|Error description for failed reverse lookup|keyword|
|system.socket|system.socket.process.pid|PID of process owning the socket (alias)|alias|
|system.socket|system.socket.process.command|Process name owning the socket (alias)|alias|
|system.socket|system.socket.process.cmdline|Complete command line of process owning the socket|keyword|
|system.socket|system.socket.process.exe|Executable file of process owning the socket (alias)|alias|
|system.socket|system.socket.user.id|User ID (alias)|alias|
|system.socket|system.socket.user.name|User full name (alias)|alias|
|system.socket.summary.all|system.socket.summary.all.count|Number of all open connections|integer|
|system.socket.summary.all|system.socket.summary.all.listening|Number of all listening ports|integer|
|system.socket.summary.tcp|system.socket.summary.tcp.memory|Memory used by TCP sockets (bytes), based on allocated pages and system page size, Linux only|integer (bytes)|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.orphan|Number of all orphaned TCP sockets (Linux only)|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.count|Number of all open TCP connections|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.listening|Number of all TCP listening ports|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.established|Number of established TCP connections|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.close_wait|Number of TCP connections in close_wait state|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.time_wait|Number of TCP connections in time_wait state|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.syn_sent|Number of TCP connections in syn_sent state|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.syn_recv|Number of TCP connections in syn_recv state|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.fin_wait1|Number of TCP connections in fin_wait1 state|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.fin_wait2|Number of TCP connections in fin_wait2 state|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.last_ack|Number of TCP connections in last_ack state|integer|
|system.socket.summary.tcp.all|system.socket.summary.tcp.all.closing|Number of TCP connections in closing state|integer|
|system.socket.summary.udp|system.socket.summary.udp.memory|Memory used by UDP sockets (bytes), based on allocated pages and system page size, Linux only|integer (bytes)|
|system.socket.summary.udp.all|system.socket.summary.udp.all.count|Number of all open UDP connections|integer|
|system.uptime|system.uptime.duration.ms|Operating system uptime (milliseconds)|long (duration)|
|system.users|system.users.id|Session ID|keyword|
|system.users|system.users.seat|Associated logind seat|keyword|
|system.users|system.users.path|DBus object path of the session|keyword|
|system.users|system.users.type|User session type|keyword|
|system.users|system.users.service|Session associated with service|keyword|
|system.users|system.users.remote|Boolean indicating if this is a remote session|boolean|
|system.users|system.users.state|Current state of the session|keyword|
|system.users|system.users.scope|Associated systemd scope|keyword|
|system.users|system.users.leader|Root PID of the session|long|
|system.users|system.users.remote_host|Remote host address of the session|keyword|