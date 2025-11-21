## 说明

基于 **TCP 协议**（TCP 传输，支持 SSL 加密），自动化采集 MySQL 实例数据并同步至 CMDB，支撑资源盘点、权限审计与故障排查。


## 前置要求

### 1. 账号权限

*   创建专用账号（如cmdb\_collector），授予最小权限：SELECT（系统库）、SHOW系列、PROCESS、SHOW STATUS，及mysql.user/mysql.db的查询权限。

*   限制访问 IP（如@'192.168.1.%'）。

### 2. 凭据准备

*   核心：实例 IP、端口（默认 3306）、账号、密码。
*   可选：SSL 证书路径（ca.pem等）、字符集（推荐utf8mb4）。

### 3. 环境检查
*   网络：开放 3306 端口，用telnet/nc验证连通性。
*   依赖：JDBC 驱动（mysql-connector-java 8.0.30+）。
*   数据库：max\_connections预留 5 个连接，skip\_networking=OFF。

## 采集内容

### 1. 实例基础信息

| Key 名称                     | 含义                          |
| :------------------------- | :-------------------------- |
| mysql.instance.ip          | 实例 IP（如 192.168.1.200）      |
| mysql.instance.port        | 端口（默认 3306）                 |
| mysql.instance.version     | 版本（如 8.0.32）                |
| mysql.instance.status      | 状态（Running/Down）            |
| mysql.instance.start\_time | 启动时间（YYYY-MM-DD HH\:MM\:SS） |
