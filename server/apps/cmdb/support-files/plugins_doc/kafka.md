### 说明
基于脚本解析启动命令与配置文件，提取版本、端口、路径、JVM 与核心 broker 参数，标准化同步至 CMDB。

### 前置要求
1. Kafka 已启动

### 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| inst_name | 实例展示名：`{内网IP}-kafka-{端口}` |
| obj_id | 固定对象标识 kafka |
| ip_addr | 主机内网 IP（hostname -I 第一个） |
| port | 监听端口（从 listeners/port 提取，默认 9092） |
| version | Kafka 版本（libs 中 kafka_*.jar 解析） |
| install_path | 安装 bin 目录（由 classpath 推导） |
| conf_path | 主配置文件绝对路径（server.properties） |
| log_path | 日志目录（-Dkafka.logs.dir 或 log.dirs） |
| java_path | Java 可执行文件路径（/proc/<pid>/exe 或命令行） |
| java_version | Java 版本（java -version） |
| xms | JVM 初始堆大小 (-Xms) |
| xmx | JVM 最大堆大小 (-Xmx) |
| broker_id | Broker 唯一标识 (broker.id) |
| io_threads | I/O 线程数 (num.io.threads) |
| network_threads | 网络线程数 (num.network.threads) |
| socket_receive_buffer_bytes | 接收缓冲大小 (socket.receive.buffer.bytes) |
| socket_request_max_bytes | 请求最大大小 (socket.request.max.bytes) |
| socket_send_buffer_bytes | 发送缓冲大小 (socket.send.buffer.bytes) |