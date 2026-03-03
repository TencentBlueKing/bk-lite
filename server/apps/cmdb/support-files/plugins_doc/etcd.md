### 说明
基于脚本解析启动参数与配置文件，提取版本、监听端口、数据目录与配置路径，同步至 CMDB。

### 前置要求
1. etcd 已启动

### 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| inst_name | 实例展示名：`{内网IP}-etcd-{客户端端口}` |
| obj_id | 固定对象标识 etcd |
| ip_addr | 主机内网 IP |
| port | 客户端监听端口（listen-client-urls 解析，默认 2379） |
| peer_port | 节点间交互端口（listen-peer-urls 解析，默认 2380） |
| install_path | etcd 可执行文件所在目录 |
| version | etcd 版本（etcd --version） |
| data_dir | 数据目录（--data-dir 或配置文件，缺省 default.etcd） |
| conf_file_path | 使用的配置文件绝对路径（--config-file，可能为空） |