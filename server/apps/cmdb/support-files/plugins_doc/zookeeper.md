### 说明
基于脚本采集本机 Zookeeper 进程，解析启动参数与配置文件，采集版本、端口、目录与集群核心参数，同步至 CMDB。

### 前置要求
1. Zookeeper 已启动。

### 版本兼容性：
- 支持官方 ZooKeeper 3.4.x+ 版本（包括： 3.6.x、3.7.x、3.8.x、3.9.x 等）。

### 采集内容
| Key 名称     | 含义                             |
| :----------- | :------------------------------- |
| inst_name    | 实例展示名：`{内网IP}-zk-{端口}` |
| obj_id       | 固定对象标识 zookeeper           |
| ip_addr      | 主机内网 IP                      |
| port         | 客户端监听端口                   |
| version      | Zookeeper 版本                   |
| java_version | Java 版本                        |
| install_path | 安装路径                         |
| conf_path    | 配置文件绝对路径                 |
| log_path     | 日志目录                         |
| java_path    | Java 可执行文件路径              |
| user         | 运行进程的系统用户               |
| data_dir     | 数据目录                         |
| tick_time    | 心跳间隔                         |
| init_limit   | 初始化同步限制                   |
| sync_limit   | 正常同步限制                     |
| server       | 集群 server 列表                 |

> 补充说明：`log_path` 在未通过 `-Dzookeeper.log.dir` 显式配置时可能为空；`data_dir`、`tick_time`、`init_limit`、`sync_limit` 在 `zoo.cfg` 中缺失对应配置项时会为空；当以单机模式部署或配置文件中未包含 `server.X` 时，`server` 可能为空；在无法解析实际运行 jar 包路径或版本号时，`install_path` 与 `version` 字段会被置为 `"unknown"`。