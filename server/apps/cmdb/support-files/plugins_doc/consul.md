## 说明
基于脚本采集本机 Consul 进程，解析启动参数与 consul info 输出，采集版本、端口、路径、数据目录与配置路径，同步至 CMDB。

## 前置要求
1. Consul 已启动（以 `consul agent` 进程为准）。
2. 采集账号具备执行 `ps`、读取 `/proc`、执行 `consul info/version` 的权限。

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| inst_name | 实例展示名：`{内网IP}-consul-{端口}` |
| bk_obj_id | 固定对象标识 consul |
| ip_addr | 主机内网 IP（hostname -I 第一个） |
| port | 监听端口（优先从 `-server-port`，否则从成员列表推断本机端口） |
| install_path | consul 可执行文件所在目录（/proc/<pid>/exe 解析） |
| version | Consul 版本（consul version） |
| data_dir | 数据目录（-data-dir） |
| conf_path | 配置文件或配置目录（-config-file 或 -config-dir；多项以冒号拼接） |
| role | Consul 当前状态（consul info 的 state 字段） |