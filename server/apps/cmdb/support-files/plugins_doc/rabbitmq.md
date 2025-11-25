## 说明
基于脚本调用 rabbitmqctl status 解析运行信息，采集版本、端口、节点名、日志与配置路径等核心参数，同步至 CMDB。

## 前置要求
1. 已安装并运行 RabbitMQ，rabbitmqctl 可执行。
2. 采集账号可执行 rabbitmqctl status 且可读取日志与配置文件路径。

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| inst_name | 实例展示名：`{内网IP}-rabbitmq-{主端口}` |
| obj_id | 固定对象标识 rabbitmq |
| ip_addr | 主机内网 IP |
| port | 主监听端口（AMQP 协议端口） |
| allport | 所有监听端口及协议汇总，逗号分隔 |
| node_name | 节点名称（集群标识） |
| log_path | 日志文件路径列表（逗号分隔） |
| conf_path | 配置文件路径列表（缺省补 `/etc/rabbitmq/rabbitmq.conf`） |
| version | RabbitMQ 版本 |
| enabled_plugin_file | 已启用插件文件路径 |
| erlang_version | Erlang 运行环境版本 |