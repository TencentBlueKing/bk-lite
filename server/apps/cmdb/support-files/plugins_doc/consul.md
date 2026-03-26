### 说明
基于脚本采集本机 Consul 进程，解析启动参数与 consul info 输出，采集版本、端口、路径、数据目录与配置路径，同步至 CMDB。

### 前置要求
1. Consul 已启动（以 `consul agent` 进程为准）。
2. 采集账号具备执行 `ps`、读取 `/proc`、执行 `consul info/version` 的权限。

### 版本兼容性
- 支持官方 Consul 1.x+ 版本（包括：1.15.x、1.18.x、1.21.x 等）。


### 采集内容
| Key 名称     | 含义                                 |
| :----------- | :----------------------------------- |
| inst_name    | 实例展示名：`{内网IP}-consul-{端口}` |
| bk_obj_id    | 固定对象标识 consul                  |
| ip_addr      | 主机内网 IP                          |
| port         | 监听端口                             |
| install_path | consul 可执行文件所在目录            |
| version      | Consul 版本                          |
| data_dir     | 数据目录                             |
| conf_path    | 配置文件或配置目录                   |
| role         | Consul 当前状态                      |

> 补充说明：`data_dir`、`conf_path`、`role` 等字段依赖进程启动参数与 `consul info` 输出，在未配置对应参数或 `consul info` 输出缺失/格式异常时可能为空；