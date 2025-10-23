### Metricbeat Docker Introduction

- &zwnj;**Basic Functions**&zwnj;
  - Container-level metrics collection

  - Docker Daemon level metrics collection

  - Event and status monitoring

  - Integration with Elastic Stack


- &zwnj;**Key Features**&zwnj;
  - Lightweight

  - Modular collection

  - Visualization and monitoring integration

  - Suitable for large-scale container environments

  - Scalability and flexibility

### Metricbeat Docker Output Fields


|Group|Field Name|Description|Type|
|--------|------|------|--------|
|Built-in Fields|collect_type|Collection type|-|
|Built-in Fields|collector|Collector|-|
|Built-in Fields|instance_id|Instance ID|-|
|docker.container|docker.container.id|Alias for container.id|alias|
|docker.container|docker.container.image|Alias for container.image.name|alias|
|docker.container|docker.container.name|Alias for container.name|alias|
|docker.container|docker.container.labels|Image labels|object|
|docker.container|docker.container.command|Command executed in Docker container|keyword|
|docker.container|docker.container.created|Date when container was created|date|
|docker.container|docker.container.status|Container status|keyword|
|docker.container|docker.container.ip_addresses|IP addresses of the container|ip|
|docker.container.size|docker.container.size.root_fs|Total size of all files in the container|long|
|docker.container.size|docker.container.size.rw|Size of files that have been created or changed since container creation|long|
|docker.container|docker.container.tags|Image tags|keyword|
|docker.cpu|docker.cpu.kernel.pct|Percentage of CPU time spent in kernel mode (0-1)|scaled_float|
|docker.cpu|docker.cpu.kernel.norm.pct|Percentage of CPU time spent in kernel mode (normalized by CPU cores, 0-1)|scaled_float|
|docker.cpu|docker.cpu.kernel.ticks|CPU ticks spent in kernel mode|long|
|docker.cpu|docker.cpu.system.pct|Total percentage of system CPU time (0-1)|scaled_float|
|docker.cpu|docker.cpu.system.norm.pct|Total percentage of system CPU time (normalized by CPU cores, 0-1)|scaled_float|
|docker.cpu|docker.cpu.system.ticks|System CPU ticks|long|
|docker.cpu|docker.cpu.user.pct|Percentage of CPU time spent in user mode (0-1)|scaled_float|
|docker.cpu|docker.cpu.user.norm.pct|Percentage of CPU time spent in user mode (normalized by CPU cores, 0-1)|scaled_float|
|docker.cpu|docker.cpu.user.ticks|CPU ticks spent in user mode|long|
|docker.cpu|docker.cpu.total.pct|Total CPU usage percentage|scaled_float|
|docker.cpu|docker.cpu.total.norm.pct|Total CPU usage percentage (normalized by CPU cores)|scaled_float|
|docker.cpu.core|docker.cpu.core.*.pct|CPU time percentage for individual cores (0-1)|object|
|docker.cpu.core|docker.cpu.core.*.norm.pct|CPU time percentage for individual cores (normalized by CPU cores, 0-1)|object|
|docker.cpu.core|docker.cpu.core.*.ticks|CPU ticks for individual cores|object|
|docker.diskio.read|docker.diskio.read.ops|Number of read operations during container lifetime|long|
|docker.diskio.read|docker.diskio.read.bytes|Number of bytes read during container lifetime|long (bytes)|
|docker.diskio.read|docker.diskio.read.rate|Number of read operations per second|long|
|docker.diskio.read|docker.diskio.read.service_time|Total time spent servicing IO requests (nanoseconds)|long|
|docker.diskio.read|docker.diskio.read.wait_time|Total time IO requests spent waiting in queue (nanoseconds)|long|
|docker.diskio.read|docker.diskio.read.queued|Total number of IO requests in queue|long|
|docker.diskio.write|docker.diskio.write.ops|Number of write operations during container lifetime|long|
|docker.diskio.write|docker.diskio.write.bytes|Number of bytes written during container lifetime|long (bytes)|
|docker.diskio.write|docker.diskio.write.rate|Number of write operations per second|long|
|docker.diskio.write|docker.diskio.write.service_time|Total time spent servicing IO requests (nanoseconds)|long|
|docker.diskio.write|docker.diskio.write.wait_time|Total time IO requests spent waiting in queue (nanoseconds)|long|
|docker.diskio.write|docker.diskio.write.queued|Total number of write requests in queue|long|
|docker.diskio.summary|docker.diskio.summary.ops|Number of I/O operations during container lifetime|long|
|docker.diskio.summary|docker.diskio.summary.bytes|Number of bytes read and written during container lifetime|long (bytes)|
|docker.diskio.summary|docker.diskio.summary.rate|Number of I/O operations per second|long|
|docker.diskio.summary|docker.diskio.summary.service_time|Total time spent servicing IO requests (nanoseconds)|long|
|docker.diskio.summary|docker.diskio.summary.wait_time|Total time IO requests spent waiting in queue (nanoseconds)|long|
|docker.diskio.summary|docker.diskio.summary.queued|Total number of I/O requests in queue|long|
|docker.event|docker.event.status|Event status|keyword|
|docker.event|docker.event.id|Event ID (if available)|keyword|
|docker.event|docker.event.from|Event source|keyword|
|docker.event|docker.event.type|Type of object that triggered the event|keyword|
|docker.event|docker.event.action|Event type|keyword|
|docker.event.actor|docker.event.actor.id|ID of object that triggered the event|keyword|
|docker.event.actor|docker.event.actor.attributes|Key-value pairs of attributes for the object that triggered the event (depends on object type)|object|
|docker.healthcheck|docker.healthcheck.failingstreak|Number of consecutive failed checks|integer|
|docker.healthcheck|docker.healthcheck.status|Health check status code|keyword|
|docker.healthcheck.event|docker.healthcheck.event.end_date|Health check end time|date|
|docker.healthcheck.event|docker.healthcheck.event.start_date|Health check start time|date|
|docker.healthcheck.event|docker.healthcheck.event.output|Health check output|keyword|
|docker.healthcheck.event|docker.healthcheck.event.exit_code|Health check exit code|integer|
|docker.image.id|docker.image.id.current|Unique identifier when the image was created|keyword|
|docker.image.id|docker.image.id.parent|Parent identifier of the image (if exists)|keyword|
|docker.image|docker.image.created|Image creation time|date|
|docker.image.size|docker.image.size.virtual|Image size|long|
|docker.image.size|docker.image.size.regular|Total size of all cached images related to the current image|long|
|docker.image|docker.image.labels|Image labels|object|
|docker.image|docker.image.tags|Image tag list|keyword|
|docker.info.containers|docker.info.containers.paused|Total number of paused containers|long|
|docker.info.containers|docker.info.containers.running|Total number of running containers|long|
|docker.info.containers|docker.info.containers.stopped|Total number of stopped containers|long|
|docker.info.containers|docker.info.containers.total|Total number of existing containers|long|
|docker.info|docker.info.id|Docker host unique identifier|keyword|
|docker.info|docker.info.images|Total number of existing images|long|
|docker.memory.stats|docker.memory.stats.*|Raw memory statistics from cgroups memory.stat interface|object|
|docker.memory.commit|docker.memory.commit.total|Total committed bytes on Windows platform|long (bytes)|
|docker.memory.commit|docker.memory.commit.peak|Peak committed bytes on Windows platform|long (bytes)|
|docker.memory|docker.memory.private_working_set.total|Private working set on Windows platform|long (bytes)|
|docker.memory|docker.memory.fail.count|Memory allocation failure counter|scaled_float|
|docker.memory|docker.memory.limit|Memory limit|long (bytes)|
|docker.memory.rss|docker.memory.rss.total|Total size of resident set size (RSS)|long (bytes)|
|docker.memory.rss|docker.memory.rss.pct|RSS percentage of total memory (0-1)|scaled_float|
|docker.memory.usage|docker.memory.usage.max|Maximum memory usage|long (bytes)|
|docker.memory.usage|docker.memory.usage.pct|Memory usage percentage (0-1)|scaled_float|
|docker.memory.usage|docker.memory.usage.total|Total memory usage|long (bytes)|
|docker.network|docker.network.interface|Network interface name|keyword|
|docker.network.in|docker.network.in.bytes|Bytes received per second|long (bytes)|
|docker.network.in|docker.network.in.dropped|Inbound packets dropped per second|scaled_float|
|docker.network.in|docker.network.in.errors|Packets received with errors per second|long|
|docker.network.in|docker.network.in.packets|Packets received per second|long|
|docker.network.out|docker.network.out.bytes|Bytes sent per second|long (bytes)|
|docker.network.out|docker.network.out.dropped|Outbound packets dropped per second|scaled_float|
|docker.network.out|docker.network.out.errors|Packets sent with errors per second|long|
|docker.network.out|docker.network.out.packets|Packets sent per second|long|
|docker.network.inbound|docker.network.inbound.bytes|Total bytes received since container startup|long (bytes)|
|docker.network.inbound|docker.network.inbound.dropped|Total inbound packets dropped since container startup|long|
|docker.network.inbound|docker.network.inbound.errors|Total packets received with errors since container startup|long|
|docker.network.inbound|docker.network.inbound.packets|Total packets received since container startup|long|
|docker.network.outbound|docker.network.outbound.bytes|Total bytes sent since container startup|long (bytes)|
|docker.network.outbound|docker.network.outbound.dropped|Total outbound packets dropped since container startup|long|
|docker.network.outbound|docker.network.outbound.errors|Total packets sent with errors since container startup|long|
|docker.network.outbound|docker.network.outbound.packets|Total packets sent since container startup|long|
|docker.network_summary|docker.network_summary.ip.*|IP counters|object|
|docker.network_summary|docker.network_summary.tcp.*|TCP counters|object|
|docker.network_summary|docker.network_summary.udp.*|UDP counters|object|
|docker.network_summary|docker.network_summary.udp_lite.*|UDP Lite counters|object|
|docker.network_summary|docker.network_summary.icmp.*|ICMP counters|object|
|docker.network_summary|docker.network_summary.namespace.pid|Root PID of container, corresponding to /proc/[pid]/net|long|
|docker.network_summary|docker.network_summary.namespace.id|Network namespace ID used by container, corresponding to /proc/[pid]/ns/net|long|