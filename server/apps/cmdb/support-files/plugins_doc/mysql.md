### 说明
该插件通过 MySQL 原生协议直连实例，读取版本与关键配置项，并标准化同步至 CMDB。


### 操作入口与执行位置
你需要在 CMDB Web 页面完成配置：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 在插件卡片中选择 **MySQL**。
3. 点击“新增任务”。

说明：任务实际执行发生在你选择的“接入点”上；文档中的连通性自测命令，均应在接入点机器上执行。


### 前置要求
在开始之前，请先确认以下条件：

1. **目标信息已明确**
   - MySQL 地址：IP 或域名。
   - 端口：默认 `3306`，如有改动以实际为准。
2. **网络连通已放通**
   - 接入点 → MySQL 的 `TCP/<port>` 可达（安全组/防火墙/路由均放通）。
   - 若 MySQL 在云上（如 RDS），需确认：接入点所在网络可以访问 RDS 的内网/公网地址，并已加入白名单。
3. **MySQL 允许远程连接**
   - MySQL 服务监听在目标网卡（不是只监听 `127.0.0.1`）。
   - 账号的 `Host` 匹配接入点来源（例如 `@'10.0.0.10'` 或网段；不建议长期使用 `@'%'`）。
4. **已准备采集专用账号（只读/查询为主）**
   - 不要复用业务账号/管理员账号。
   - 建议按“最小权限”创建；如遇权限不足再按需补齐。
5. **接入点具备自测工具（可选但强烈建议）**
   - Linux：`nc`、`mysql` 客户端（用于执行 `SELECT 1` 验证）。
   - Windows：PowerShell 的 `Test-NetConnection`。



### 操作步骤
### 步骤 1：网络连通性自测（在接入点执行）
任选一种方式进行验证：

- Linux：
  - `nc -vz <mysql_ip> 3306`
  - `mysql -h <mysql_ip> -P 3306 -u <user> -p -e "SELECT 1;"`

- Windows PowerShell：
  - `Test-NetConnection <mysql_ip> -Port 3306`

**判断标准**：端口连通，且能够成功执行 `SELECT 1`。


### 步骤 2：创建采集账号（在目标 MySQL 上执行）
下面以“一个 MySQL 小白也能照着做”为目标，给出**完整可执行**的示例流程。你需要一个具备账号管理权限的管理员账号（如 `root` 或 DBA 提供的管理账号）来执行这些命令。

#### 2.1 用管理员账号登录 MySQL（示例）
在 MySQL 所在机器上，或任何能连到 MySQL 的机器上执行（把 `mysql_ip/port` 换成真实值）：

```bash
mysql -h <mysql_ip> -P <port> -u <admin_user> -p
```

登录后你会进入 MySQL 提示符（形如 `mysql>`）。

#### 2.2 创建只读采集账号并授权
把下面脚本中的 IP、用户名、密码替换为你的真实值：

```sql
-- 0) 建议：先确认当前连接用户（可选）
SELECT USER(), CURRENT_USER();

-- 1) 创建账号（示例：仅允许接入点 10.0.0.10 登录）
CREATE USER 'cmdb_collector'@'10.0.0.10' IDENTIFIED BY 'YourStrongPassword';

-- 2) 允许读取 information_schema / performance_schema（用于获取版本、变量、状态等信息）
GRANT SELECT ON information_schema.* TO 'cmdb_collector'@'10.0.0.10';
GRANT SELECT ON performance_schema.* TO 'cmdb_collector'@'10.0.0.10';
-- Host（登录来源）说明：
-- - 'cmdb_collector'@'10.0.0.10'：仅允许某台接入点 IP 登录（推荐，更安全）
-- - 'cmdb_collector'@'10.0.0.%'：允许一个网段登录（按需使用）
-- - 不建议长期使用 @'%'（任何来源都可登录），除非你明确知道风险并有额外网络隔离

-- 3) 可能用到的全局只读能力（不涉及写入业务数据）
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'cmdb_collector'@'10.0.0.10';

-- 4) 生效
FLUSH PRIVILEGES;
```

说明：
- 上述授权不包含 `INSERT/UPDATE/DELETE/CREATE/DROP` 等写入/DDL 权限。
- 如果你的安全规范不允许 `PROCESS` 等全局权限，可先不授予；若后续采集报“权限不足”再按需追加（见下文“最小权限补齐”）。

#### 2.3 验证采集账号是否可用
在接入点（或任意能访问 MySQL 的机器）执行：

```bash
mysql -h <mysql_ip> -P <port> -u cmdb_collector -p -e "SELECT 1;"
```

如果能返回 `1`，说明网络/账号基本可用。

（可选）登录后检查账号到底有什么权限：

```sql
SHOW GRANTS FOR 'cmdb_collector'@'10.0.0.10';
```

#### 2.4 常见“权限不足”时的最小补齐方式
如果采集执行报错提示缺少某个系统库读取权限，优先按“只读”补齐：

```sql
-- 示例：如果报 performance_schema 相关权限问题
GRANT SELECT ON performance_schema.* TO 'cmdb_collector'@'10.0.0.10';
FLUSH PRIVILEGES;
```

#### 2.5 （可选）撤回/清理账号
如果你希望“撤回/清理账号”（例如测试后删除），执行：

```sql
DROP USER 'cmdb_collector'@'10.0.0.10';
FLUSH PRIVILEGES;
```


### 凭据字段说明
- 凭据字段：用户名（`user`）、密码（`password`）、端口（`port`）。
- `user`：用于登录目标 MySQL 的账号名称。建议使用单独创建的采集账号（例如 `cmdb_collector`），不要使用业务账号或管理员账号。
- `password`：上述账号对应的密码。注意该密码与“管理员账号”无关；管理员账号仅用于创建采集账号。
- `port`：目标 MySQL 实例对外提供服务的端口号（默认 `3306`）。如果 MySQL 改过端口或是云数据库提供了不同端口，请填写实际端口。


### 采集内容
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