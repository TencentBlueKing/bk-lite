### Metricbeat docker简介

- &zwnj;**基本功能**&zwnj;
  - 容器级别指标采集

  - Docker Daemon 级别指标采集

  - 事件与状态监控

  - 与 Elastic Stack 集成


- &zwnj;**主要特点**&zwnj;
  - 轻量化

  - 模块化采集

  - 可视化与监控联动

  - 适合大规模容器环境

  - 可扩展性和灵活性

### Metricbeat docker 输出字段


|分组|字段名|描述|类型|
|--------|------|------|--------|
|内置字段|collect_type|采集类型|-|
|内置字段|collector|采集器|-|
|内置字段|instance_id|实例id|-|
|docker.container|docker.container.id|作为 container.id 的别名|alias|
|docker.container|docker.container.image|作为 container.image.name 的别名|alias|
|docker.container|docker.container.name|作为 container.name 的别名|alias|
|docker.container|docker.container.labels|镜像标签|object|
|docker.container|docker.container.command|在 Docker 容器中执行的命令|keyword|
|docker.container|docker.container.created|容器创建的日期|date|
|docker.container|docker.container.status|容器状态|keyword|
|docker.container|docker.container.ip_addresses|容器的 IP 地址|ip|
|docker.container.size|docker.container.size.root_fs|容器中所有文件的总大小|long|
|docker.container.size|docker.container.size.rw|自容器创建以来新增或修改的文件大小|long|
|docker.container|docker.container.tags|镜像标签|keyword|
|docker.cpu|docker.cpu.kernel.pct|内核态占用的 CPU 时间百分比（0-1）|scaled_float|
|docker.cpu|docker.cpu.kernel.norm.pct|内核态占用的 CPU 时间百分比（按 CPU 核数归一化，0-1）|scaled_float|
|docker.cpu|docker.cpu.kernel.ticks|内核态 CPU 时钟周期数|long|
|docker.cpu|docker.cpu.system.pct|系统态总 CPU 时间百分比（0-1）|scaled_float|
|docker.cpu|docker.cpu.system.norm.pct|系统态总 CPU 时间百分比（按 CPU 核数归一化，0-1）|scaled_float|
|docker.cpu|docker.cpu.system.ticks|系统态 CPU 时钟周期数|long|
|docker.cpu|docker.cpu.user.pct|用户态占用的 CPU 时间百分比（0-1）|scaled_float|
|docker.cpu|docker.cpu.user.norm.pct|用户态占用的 CPU 时间百分比（按 CPU 核数归一化，0-1）|scaled_float|
|docker.cpu|docker.cpu.user.ticks|用户态 CPU 时钟周期数|long|
|docker.cpu|docker.cpu.total.pct|CPU 总使用率|scaled_float|
|docker.cpu|docker.cpu.total.norm.pct|CPU 总使用率（按 CPU 核数归一化）|scaled_float|
|docker.cpu.core|docker.cpu.core.*.pct|单个核心 CPU 时间百分比（0-1）|object|
|docker.cpu.core|docker.cpu.core.*.norm.pct|单个核心 CPU 时间百分比（按 CPU 核数归一化，0-1）|object|
|docker.cpu.core|docker.cpu.core.*.ticks|单个核心的 CPU 时钟周期数|object|
|docker.diskio.read|docker.diskio.read.ops|容器生命周期内的读操作次数|long|
|docker.diskio.read|docker.diskio.read.bytes|容器生命周期内读取的字节数|long (bytes)|
|docker.diskio.read|docker.diskio.read.rate|每秒读操作数|long|
|docker.diskio.read|docker.diskio.read.service_time|IO 请求服务的总时间（纳秒）|long|
|docker.diskio.read|docker.diskio.read.wait_time|IO 请求在队列中等待的总时间（纳秒）|long|
|docker.diskio.read|docker.diskio.read.queued|队列中的 IO 请求总数|long|
|docker.diskio.write|docker.diskio.write.ops|容器生命周期内的写操作次数|long|
|docker.diskio.write|docker.diskio.write.bytes|容器生命周期内写入的字节数|long (bytes)|
|docker.diskio.write|docker.diskio.write.rate|每秒写操作数|long|
|docker.diskio.write|docker.diskio.write.service_time|IO 请求服务的总时间（纳秒）|long|
|docker.diskio.write|docker.diskio.write.wait_time|IO 请求在队列中等待的总时间（纳秒）|long|
|docker.diskio.write|docker.diskio.write.queued|队列中的写请求总数|long|
|docker.diskio.summary|docker.diskio.summary.ops|容器生命周期内的 I/O 操作次数|long|
|docker.diskio.summary|docker.diskio.summary.bytes|容器生命周期内读写的字节数|long (bytes)|
|docker.diskio.summary|docker.diskio.summary.rate|每秒 I/O 操作数|long|
|docker.diskio.summary|docker.diskio.summary.service_time|IO 请求服务的总时间（纳秒）|long|
|docker.diskio.summary|docker.diskio.summary.wait_time|IO 请求在队列中等待的总时间（纳秒）|long|
|docker.diskio.summary|docker.diskio.summary.queued|队列中的 I/O 请求总数|long|
|docker.event|docker.event.status|事件状态|keyword|
|docker.event|docker.event.id|事件 ID（如果可用）|keyword|
|docker.event|docker.event.from|事件来源|keyword|
|docker.event|docker.event.type|触发事件的对象类型|keyword|
|docker.event|docker.event.action|事件类型|keyword|
|docker.event.actor|docker.event.actor.id|触发事件的对象 ID|keyword|
|docker.event.actor|docker.event.actor.attributes|触发事件对象的属性键值对（依对象类型而定）|object|
|docker.healthcheck|docker.healthcheck.failingstreak|连续失败的检查次数|integer|
|docker.healthcheck|docker.healthcheck.status|健康检查状态码|keyword|
|docker.healthcheck.event|docker.healthcheck.event.end_date|健康检查结束时间|date|
|docker.healthcheck.event|docker.healthcheck.event.start_date|健康检查开始时间|date|
|docker.healthcheck.event|docker.healthcheck.event.output|健康检查输出|keyword|
|docker.healthcheck.event|docker.healthcheck.event.exit_code|健康检查退出码|integer|
|docker.image.id|docker.image.id.current|镜像创建时的唯一标识符|keyword|
|docker.image.id|docker.image.id.parent|镜像的父标识符（如果存在）|keyword|
|docker.image|docker.image.created|镜像的创建时间|date|
|docker.image.size|docker.image.size.virtual|镜像大小|long|
|docker.image.size|docker.image.size.regular|与当前镜像相关的所有缓存镜像的总大小|long|
|docker.image|docker.image.labels|镜像标签|object|
|docker.image|docker.image.tags|镜像标签列表|keyword|
|docker.info.containers|docker.info.containers.paused|暂停的容器总数|long|
|docker.info.containers|docker.info.containers.running|运行中的容器总数|long|
|docker.info.containers|docker.info.containers.stopped|已停止的容器总数|long|
|docker.info.containers|docker.info.containers.total|存在的容器总数|long|
|docker.info|docker.info.id|Docker 主机唯一标识符|keyword|
|docker.info|docker.info.images|存在的镜像总数|long|
|docker.memory.stats|docker.memory.stats.*|来自 cgroups memory.stat 接口的原始内存统计信息|object|
|docker.memory.commit|docker.memory.commit.total|Windows 平台上的提交字节总数|long (bytes)|
|docker.memory.commit|docker.memory.commit.peak|Windows 平台上的提交字节峰值|long (bytes)|
|docker.memory|docker.memory.private_working_set.total|Windows 平台上的私有工作集|long (bytes)|
|docker.memory|docker.memory.fail.count|内存分配失败计数器|scaled_float|
|docker.memory|docker.memory.limit|内存限制|long (bytes)|
|docker.memory.rss|docker.memory.rss.total|常驻内存集（RSS）的总大小|long (bytes)|
|docker.memory.rss|docker.memory.rss.pct|RSS 占总内存百分比（0-1）|scaled_float|
|docker.memory.usage|docker.memory.usage.max|最大内存使用量|long (bytes)|
|docker.memory.usage|docker.memory.usage.pct|内存使用率（0-1）|scaled_float|
|docker.memory.usage|docker.memory.usage.total|总内存使用量|long (bytes)|
|docker.network|docker.network.interface|网络接口名称|keyword|
|docker.network.in|docker.network.in.bytes|每秒接收的字节数|long (bytes)|
|docker.network.in|docker.network.in.dropped|每秒丢弃的入站数据包数|scaled_float|
|docker.network.in|docker.network.in.errors|每秒接收错误的数据包数|long|
|docker.network.in|docker.network.in.packets|每秒接收的数据包数|long|
|docker.network.out|docker.network.out.bytes|每秒发送的字节数|long (bytes)|
|docker.network.out|docker.network.out.dropped|每秒丢弃的出站数据包数|scaled_float|
|docker.network.out|docker.network.out.errors|每秒发送错误的数据包数|long|
|docker.network.out|docker.network.out.packets|每秒发送的数据包数|long|
|docker.network.inbound|docker.network.inbound.bytes|自容器启动以来接收的字节总数|long (bytes)|
|docker.network.inbound|docker.network.inbound.dropped|自容器启动以来丢弃的入站数据包总数|long|
|docker.network.inbound|docker.network.inbound.errors|自容器启动以来接收错误的数据包总数|long|
|docker.network.inbound|docker.network.inbound.packets|自容器启动以来接收的数据包总数|long|
|docker.network.outbound|docker.network.outbound.bytes|自容器启动以来发送的字节总数|long (bytes)|
|docker.network.outbound|docker.network.outbound.dropped|自容器启动以来丢弃的出站数据包总数|long|
|docker.network.outbound|docker.network.outbound.errors|自容器启动以来发送错误的数据包总数|long|
|docker.network.outbound|docker.network.outbound.packets|自容器启动以来发送的数据包总数|long|
|docker.network_summary|docker.network_summary.ip.*|IP 计数器|object|
|docker.network_summary|docker.network_summary.tcp.*|TCP 计数器|object|
|docker.network_summary|docker.network_summary.udp.*|UDP 计数器|object|
|docker.network_summary|docker.network_summary.udp_lite.*|UDP Lite 计数器|object|
|docker.network_summary|docker.network_summary.icmp.*|ICMP 计数器|object|
|docker.network_summary|docker.network_summary.namespace.pid|容器的根 PID，对应 /proc/[pid]/net|long|
|docker.network_summary|docker.network_summary.namespace.id|容器使用的网络命名空间 ID，对应 /proc/[pid]/ns/net|long|