### Overview
This plugin connects directly to a MySQL instance over the native protocol, reads the version and key configuration items, and syncs them to CMDB in a standardized form.


### Entry Point and Execution Location
Complete the configuration in the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select **MySQL** on the plugin cards.
3. Click "Add Task".

Note: the task actually runs on the "access point" you select; all connectivity self-check commands in this document should be run on the access point host.


### Version Compatibility
- Compatible with official MySQL 5.5+ (including 5.6.x, 5.7.x, 8.0.x, 8.4.x, etc.)

### Prerequisites
Before you start, confirm the following:

1. **Target information is known**
   - MySQL address: IP or domain name.
   - Port: default `3306`; use the actual port if it was changed.
2. **Network connectivity is open**
   - `TCP/<port>` from the access point → MySQL is reachable (security group / firewall / routing all allow it).
   - If MySQL is in the cloud (for example RDS), confirm that the access point network can reach the RDS private/public address and has been added to the whitelist.
3. **MySQL allows remote connections**
   - The MySQL service listens on the target NIC (not only `127.0.0.1`).
   - The account `Host` matches the access point source (for example `@'10.0.0.10'` or a subnet; long-term use of `@'%'` is not recommended).
4. **A dedicated collection account is ready (read-only / query primarily)**
   - Do not reuse a business account or administrator account.
   - Create it with least privilege; add more only if permission is insufficient.
5. **The access point has self-check tools (optional but strongly recommended)**
   - Linux: `nc`, `mysql` client (for `SELECT 1` verification).
   - Windows: PowerShell `Test-NetConnection`.



### Procedure
### Step 1: Network connectivity self-check (run on the access point)
Use either method:

- Linux：
  - `nc -vz <mysql_ip> 3306`
  - `mysql -h <mysql_ip> -P 3306 -u <user> -p -e "SELECT 1;"`

- Windows PowerShell：
  - `Test-NetConnection <mysql_ip> -Port 3306`

**Pass criterion**: the port is reachable, and `SELECT 1` succeeds.


### Step 2: Create a collection account (run on the target MySQL)
The following is a complete, executable example aimed at someone new to MySQL. You need an administrator account with user-management privileges (such as `root` or a DBA-provided admin account) to run these commands.

#### 2.1 Log in to MySQL with an administrator account (example)
On the MySQL host, or any host that can reach MySQL (replace `mysql_ip/port` with real values):

```bash
mysql -h <mysql_ip> -P <port> -u <admin_user> -p
```

After login you will see the MySQL prompt (such as `mysql>`).

#### 2.2 Create a read-only collection account and grant privileges
Replace the IP, username, and password in the script below with your real values:

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

Notes:
- The grants above do not include write/DDL privileges such as `INSERT/UPDATE/DELETE/CREATE/DROP`.
- If your security policy does not allow global privileges such as `PROCESS`, skip them first; if collection later reports "insufficient privilege", add them as needed (see "Least-privilege supplement" below).

#### 2.3 Verify that the collection account works
On the access point (or any host that can reach MySQL):

```bash
mysql -h <mysql_ip> -P <port> -u cmdb_collector -p -e "SELECT 1;"
```

If it returns `1`, network/account are basically usable.

(Optional) After login, check the account privileges:

```sql
SHOW GRANTS FOR 'cmdb_collector'@'10.0.0.10';
```

#### 2.4 Least-privilege supplement when "insufficient privilege" occurs
If collection fails because a system-schema read privilege is missing, add read-only grants first:

```sql
-- 示例：如果报 performance_schema 相关权限问题
GRANT SELECT ON performance_schema.* TO 'cmdb_collector'@'10.0.0.10';
FLUSH PRIVILEGES;
```

#### 2.5 (Optional) Revoke/clean up the account
If you want to revoke/clean up the account (for example delete it after testing):

```sql
DROP USER 'cmdb_collector'@'10.0.0.10';
FLUSH PRIVILEGES;
```


### Credential Fields
- Credential fields: username (`user`), password (`password`), port (`port`).
- `user`: Account name used to log in to the target MySQL. Prefer a separately created collection account (for example `cmdb_collector`); do not use a business or administrator account.
- `password`: Password for that account. This is unrelated to the "administrator account"; the administrator account is only used to create the collection account.
- `port`: Service port of the target MySQL instance (default `3306`). If MySQL uses a different port or a cloud database exposes a different port, enter the actual port.


### Collected Data
| Key                       | Description        |
| :------------------------ | :----------------- |
| mysql.ip_addr             | Instance IP        |
| mysql.port                | Listen port        |
| mysql.version             | MySQL version      |
| mysql.enable_binlog       | Whether binlog is enabled |
| mysql.sync_binlog         | binlog sync policy |
| mysql.max_conn            | Max connections    |
| mysql.max_mem             | Max packet size    |
| mysql.basedir             | Install directory  |
| mysql.datadir             | Data directory     |
| mysql.socket              | Local socket file  |
| mysql.bind_address        | Bind address       |
| mysql.slow_query_log      | Whether slow query log is enabled |
| mysql.slow_query_log_file | Slow query log file path |
| mysql.log_error           | Error log file path |
| mysql.wait_timeout        | Idle connection wait timeout |

> Note: `mysql.basedir`, `mysql.datadir`, `mysql.socket`, `mysql.bind_address`, `mysql.slow_query_log`, `mysql.slow_query_log_file`, `mysql.log_error` all come from `SHOW GLOBAL VARIABLES`. They may be empty (NULL or empty string) if the target instance does not set the corresponding variable or the value is empty. `mysql.enable_binlog` / `mysql.sync_binlog` depend on `log_bin` and `sync_binlog`; if binlog is not enabled or the version does not support them, the fields may be empty or default.
