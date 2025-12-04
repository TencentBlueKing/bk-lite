## 说明
基于 MySQL 原生协议直连实例，采集版本与关键信息，标准化同步至 CMDB。

## 前置要求
1. 网络放通端口（默认3306），与接入点网络通畅
2. 账号最小权限：SHOW GLOBAL VARIABLES，information_schema 只读；不需写入。
3. 提供连接参数：host、port、user、password。

## 采集内容
| Key 名称 | 含义 |
| :----------- | :--- |
| mysql.ip_addr | 实例 IP |
| mysql.port | 监听端口 |
| mysql.version | MySQL 版本 |
| mysql.enable_binlog | 是否开启 binlog (log_bin) |
| mysql.sync_binlog | binlog 同步策略 (sync_binlog) |
| mysql.max_conn | 最大连接数 (max_connections) |
| mysql.max_mem | 单包最大大小 (max_allowed_packet) |
| mysql.basedir | 安装目录 (basedir) |
| mysql.datadir | 数据目录 (datadir) |
| mysql.socket | 本地 socket 文件 |
| mysql.bind_address | 绑定地址 (bind_address) |
| mysql.slow_query_log | 慢查询日志是否开启 |
| mysql.slow_query_log_file | 慢查询日志文件路径 |
| mysql.log_error | 错误日志文件路径 |
| mysql.wait_timeout | 空闲连接等待超时 (wait_timeout) |