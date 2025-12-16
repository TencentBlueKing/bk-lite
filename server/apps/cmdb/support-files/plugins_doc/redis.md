## 说明
基于脚本（JOB）采集版本、端口与关键配置，同步核心运行参数至 CMDB。

## 前置要求
1. 主机已启动 Redis，安装目录可读，存在 redis-cli。
2. 采集账号可执行 ps、readlink 与 redis-cli config/info 命令。
3. 网络端口（默认 6379 或实际端口）本地可访问；多实例需分别监听独立端口。
4. 若有访问控制（bind / requirepass），需提供对应口令或放通本地。

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| inst_name | 实例展示名：`{主机内网IP}-redis-{端口}` |
| bk_obj_id | 固定对象标识 redis |
| ip_addr | 主机内网 IP（hostname -I 第一个） |
| port | Redis 监听端口 |
| version | Redis 版本（redis-cli --version） |
| install_path | 安装路径（进程可执行文件父目录） |
| max_conn | 最大连接数（config get maxclients） |
| max_mem | 限制最大内存（config get maxmemory，0 表示未限制） |
| database_role | 实例角色（master / slave，来自 info replication） |