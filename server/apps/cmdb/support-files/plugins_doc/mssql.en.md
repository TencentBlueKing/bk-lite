### Overview
[BETA] This plugin connects directly to a SQL Server instance via ODBC, reads the version and key configuration items, and syncs them to CMDB in a standardized form.


### Entry Point and Execution Location
Complete the configuration in the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select **MSSQL** on the plugin cards.
3. Click "Add Task".

Note: the task actually runs on the "access point" you select; all connectivity self-check commands in this document should be run on the access point host.


### Version Compatibility
- Compatible with common mainstream official SQL Server versions; use the actually deployed version as the reference.

### Prerequisites
Before you start, confirm the following:

1. **Target information is known**
   - SQL Server address: IP or domain name.
   - Port: default `1433`; use the actual port if it was changed.
   - Database name: fill in as actually used.
2. **Network connectivity is open**
   - `TCP/<port>` from the access point → SQL Server is reachable (security group / firewall / routing all allow it).
   - If SQL Server is in the cloud, confirm that the access point network can reach its private/public address and has been added to the whitelist.
3. **ODBC driver is installed on the access point (important)**
   - The collector (access point) host must have "ODBC Driver 17 for SQL Server" installed, otherwise a connection cannot be established.
   - On the access point, run `odbcinst -j` or `odbcinst -q -d` to confirm the driver is installed; if not, follow Microsoft official documentation to install it.
4. **SQL Server allows remote connections**
   - TCP/IP is enabled and listening on the target port, allowing connections from the access point.
5. **A dedicated collection account is ready (read-only / query primarily)**
   - Do not reuse a business account or administrator account.
   - The account needs the `db_datareader` role and `VIEW SERVER STATE` (used to read `sys.dm_*` dynamic views).
6. **The access point has self-check tools (optional but strongly recommended)**
   - Windows: PowerShell `Test-NetConnection`.
   - Linux: `nc`.


### Procedure
### Step 1: Network connectivity self-check (run on the access point)
Use either method:

- Linux：
  - `nc -vz <mssql_ip> 1433`

- Windows PowerShell：
  - `Test-NetConnection <mssql_ip> -Port 1433`

**Pass criterion**: the port is reachable.

### Step 2: Create a collection account (run on the target SQL Server)
You need an administrator account with user-management privileges (such as `sa` or a DBA-provided admin account) to run the commands below. Replace the username, password, and database name in the script with your real values:

```sql
-- 1) 创建登录名
CREATE LOGIN cmdb_collector WITH PASSWORD = 'YourStrongPassword';

-- 2) 授予读取动态管理视图所需的服务器级权限
GRANT VIEW SERVER STATE TO cmdb_collector;

-- 3) 在目标数据库中创建用户并赋予只读角色
USE [YourDatabase];
CREATE USER cmdb_collector FOR LOGIN cmdb_collector;
ALTER ROLE db_datareader ADD MEMBER cmdb_collector;
```

Notes:
- The grants above do not include write or DDL privileges.
- `VIEW SERVER STATE` is used to read dynamic views such as `sys.dm_os_*` (for example memory usage). Missing it causes related fields to be incomplete.

### Step 3: Verify that the collection account works
On the access point (with the ODBC driver installed), connect with this account and run `SELECT 1;`. A normal return means network/account/driver are basically usable. For example on Linux:

```bash
sqlcmd -S <ip>,1433 -U cmdb_collector -P '<password>' -Q "SELECT 1"
```

(or test the connection with any SQL Server client)

### Step 4: (Optional) Revoke/clean up the account
```sql
USE [YourDatabase];
DROP USER cmdb_collector;
DROP LOGIN cmdb_collector;
```


### Credential Fields
- `host`: IP or domain name of the target SQL Server.
- `port`: Service port of the target instance (default `1433`). If the port was changed, enter the actual port.
- `user`: Account name used to log in to the target SQL Server. Prefer a separately created collection account (for example `cmdb_collector`); do not use a business or administrator account.
- `password`: Password for that account. Encrypted at rest and injected as an environment variable when dispatched.
- `database`: Database name used when connecting.
- `timeout`: Connect/read timeout.


### Collected Data
**SQL Server (mssql)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name |
| ip_addr | Instance IP |
| port | Listen port |
| version | Product version (`SERVERPROPERTY('ProductVersion')`) |
| max_conn | Max connections (user connections) |
| fill_factor | Index fill factor |
| max_mem | Physical memory in use (`physical_memory_in_use_kb` converted to MB) |
| order_rule | Collation |
| db_name | Database name |

> Note: fields such as `max_mem` from `sys.dm_*` dynamic views depend on `VIEW SERVER STATE`. They may be empty when the privilege is missing or the target does not return the corresponding item.
