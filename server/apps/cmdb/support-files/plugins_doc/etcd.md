### 说明
基于脚本解析启动参数与配置文件，提取版本、监听端口、数据目录与配置路径，同步至 CMDB。

### 前置要求
1. etcd 已启动
   
### 版本兼容性
- 兼容官方 etcd v3.0.x+ 版本（包括：v3.4.x、v3.5.x、v3.6.x、v3.7.x 等）。

### 采集内容
| Key 名称       | 含义                                               |
| :------------- | :------------------------------------------------- |
| inst_name      | 实例展示名：`{内网IP}-etcd-{客户端端口}`           |
| obj_id         | 固定对象标识 etcd                                  |
| ip_addr        | 主机内网 IP                                        |
| port           | 客户端监听端口                                     |
| peer_port      | 节点间交互端口（listen-peer-urls 解析，默认 2380） |
| install_path   | etcd 可执行文件所在目录                            |
| version        | etcd 版本                                          |
| data_dir       | 数据目录                                           |
| conf_file_path | 使用的配置文件绝对路径                             |

> 补充说明：`conf_file_path` 在未使用 `--config-file` 启动时为空；