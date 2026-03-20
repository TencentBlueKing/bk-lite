### 说明
基于脚本解析启动命令与配置文件，提取版本、端口、路径、JVM 与核心 broker 参数，标准化同步至 CMDB。

### 前置要求
1. Kafka 已启动

### 版本兼容性
- 兼容官方版本 Kafka 2.8x-4.0x 版本（包括：2.8.x、3.3.x、3.5.x、4.0.x 等）。
- 如果在Kafka 3.3.x-4.0.x 版本中使用Kafka模式，会在获取node_id字段后赋值给broker_id字段。

### 采集内容
| Key 名称                    | 含义                                |
| :-------------------------- | :---------------------------------- |
| inst_name                   | 实例展示名：`{内网IP}-kafka-{端口}` |
| obj_id                      | 固定对象标识 kafka                  |
| ip_addr                     | 主机内网 IP                         |
| port                        | 监听端口                            |
| version                     | Kafka 版本                          |
| install_path                | 安装 bin 目录                       |
| conf_path                   | 主配置文件绝对路径                  |
| log_path                    | 日志目录                            |
| java_path                   | Java 可执行文件路径                 |
| java_version                | Java 版本                           |
| xms                         | JVM 初始堆大小                      |
| xmx                         | JVM 最大堆大小                      |
| broker_id                   | Broker 唯一标识                     |
| io_threads                  | I/O 线程数                          |
| network_threads             | 网络线程数                          |
| socket_receive_buffer_bytes | 接收缓冲大小                        |
| socket_request_max_bytes    | 请求最大大小                        |
| socket_send_buffer_bytes    | 发送缓冲大小                        |

> 补充说明：`install_path`、`conf_path`、`log_path` 依赖启动参数与配置文件（classpath、server.properties、-Dkafka.logs.dir/log.dirs），未指定时可能为空；`java_path`、`java_version` 在无法定位 java 可执行文件或执行失败时可能为空或为 `unknown`；`xms`、`xmx` 仅在 JVM 启动参数中显式设置时才有值；`broker_id`、`io_threads`、`network_threads`、`socket_*` 等配置项在配置文件中缺失时输出 `unknown`。