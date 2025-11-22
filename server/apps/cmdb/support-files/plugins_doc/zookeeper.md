## 说明
基于脚本采集本机 Zookeeper 进程，解析启动参数与配置文件，采集版本、端口、目录与集群核心参数，同步至 CMDB。

## 前置要求
1. Zookeeper 已启动。


## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| inst_name | 实例展示名：`{内网IP}-zk-{端口}` |
| obj_id | 固定对象标识 zookeeper |
| ip_addr | 主机内网 IP |
| port | 客户端监听端口 (clientPort) |
| version | Zookeeper 版本（解析 lib/zookeeper-*.jar） |
| java_version | Java 版本（java -version） |
| install_path | 安装路径（lsof 或 cwd 推断） |
| conf_path | 配置文件绝对路径 (zoo.cfg) |
| log_path | 日志目录 (-Dzookeeper.log.dir) |
| java_path | Java 可执行文件路径 (/proc/<pid>/exe) |
| user | 运行进程的系统用户 |
| data_dir | 数据目录 (dataDir) |
| tick_time | 心跳间隔 (tickTime) |
| init_limit | 初始化同步限制 (initLimit) |
| sync_limit | 正常同步限制 (syncLimit) |
| server | 集群 server 列表（server.X=host:peer:leader 拼接，逗号分隔） |