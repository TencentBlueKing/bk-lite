### 说明
基于脚本方式采集版本与主配置信息，同步至 CMDB。

### 前置要求
1. 主机已安装Agent（下发安装agent请访问：节点管理）
2. nginx已启动

### 版本兼容性
- 支持官方 Nginx 1.10+ 版本（包括：1.28.x、1.29.x、1.26.x、1.24.x等）

### 采集内容
| Key 名称    | 含义                                                              |
| :---------- | :---------------------------------------------------------------- |
| inst_name   | 实例展示名：`{内网IP}-nginx-{端口}`                               |
| bk_obj_id   | 固定对象标识：nginx                                               |
| ip_addr     | 主机内网 IP       |
| port        | 该进程监听端口集合
| version     | Nginx 版本                  |
| bin_path    | 可执行文件绝对路径
| conf_path   | 主配置文件绝对路径 |
| log_path    | error_log 指令配置的日志文件绝对路径                              |
| server_name | server_name 指令提取的域名
| include     | include 指令引用的配置路径
| ssl_version | 系统 OpenSSL 版本（                             |

> 补充说明：`log_path` 在未配置 error_log 或写法非常规时可能为空；