### Overview
This plugin connects directly to a PostgreSQL instance over the native protocol, reads the version and key configuration items, and syncs them to CMDB in a standardized form.


### Entry Point and Execution Location
Complete the configuration in the CMDB Web UI:
1. Go to "CMDB → Management → Auto Discovery → Collection → Professional Collection".
2. Select **PostgreSQL** on the plugin cards.
3. Click "Add Task".

Note: the task actually runs on the "access point" you select; all connectivity self-check commands in this document should be run on the access point host.


### Version Compatibility
- Compatible with common mainstream official PostgreSQL versions; both older and newer major versions generally collect normally. Use the actually deployed version as the reference.

### Prerequisites
Before you start, confirm the following:

1. **Target information is known**
   - PostgreSQL address: IP or domain name.
   - Port: default `5432`; use the actual port if it was changed.
   - Database name: default `postgres`; fill in as actually used.
2. **Network connectivity is open**
   - `TCP/<port>` from the access point → PostgreSQL is reachable (security group / firewall / routing all allow it).
   - If PostgreSQL is in the cloud (for example RDS), confirm that the access point network can reach its private/public address and has been added to the whitelist.
3. **PostgreSQL allows remote connections**
   - The service listens on the target NIC (`listen_addresses` is not only `127.0.0.1`).
   - `pg_hba.conf` already allows login from the access point source IP/subnet (for example add `host <database> <user> 10.0.0.10/32 md5`); reload after changing.
4. **A dedicated collection account is ready (read-only / query primarily)**
   - Do not reuse a business account or superuser account.
   - This plugin reads information via `SHOW` commands. Any authenticated account can run them; no special grants are needed, so the account only needs to be able to log in.
5. **The access point has self-check tools (optional but strongly recommended)**
   - Linux: `nc`, `psql` client (for `SELECT 1` verification).
   - Windows: PowerShell `Test-NetConnection`.


### Procedure
### Step 1: Network connectivity self-check (run on the access point)
Use either method:

- Linux：
  - `nc -vz <pg_ip> 5432`
  - `psql "host=<pg_ip> port=5432 user=<user> dbname=postgres" -c "SELECT 1;"`

- Windows PowerShell：
  - `Test-NetConnection <pg_ip> -Port 5432`

**Pass criterion**: the port is reachable, and `SELECT 1` succeeds.


### Step 2: Create a collection account (run on the target PostgreSQL)
This plugin reads version and configuration via `SHOW` commands. Any authenticated account can run them; no extra grants are needed. You only need a minimal account that can log in. You need an administrator account with user-management privileges (such as `postgres` or a DBA-provided admin account) to run the commands below.

#### 2.1 Log in to PostgreSQL with an administrator account (example)
On the PostgreSQL host, or any host that can reach PostgreSQL (replace `pg_ip/port` with real values):

```bash
psql "host=<pg_ip> port=<port> user=<admin_user> dbname=postgres"
```

After login you will see the psql prompt (such as `postgres=#`).

#### 2.2 Create a minimal collection account
Replace the username and password in the script below with your real values:

```sql
-- 创建一个仅能登录的采集账号（采集所需的 SHOW 命令无需额外授权）
CREATE ROLE cmdb_collector LOGIN PASSWORD 'YourStrongPassword';
```

Notes:
- The statement above only creates a login role and does not grant any object write or DDL privileges.
- Also confirm that `pg_hba.conf` already allows this account to log in from the access point source IP (see Prerequisites item 3); otherwise the account exists but cannot connect.

#### 2.3 Verify that the collection account works
On the access point (or any host that can reach PostgreSQL):

```bash
psql "host=<pg_ip> port=<port> user=cmdb_collector dbname=postgres" -c "SELECT 1;"
```

If it returns `1`, network/account are basically usable.

#### 2.4 (Optional) Revoke/clean up the account
If you want to revoke/clean up the account (for example delete it after testing):

```sql
DROP ROLE cmdb_collector;
```


### Credential Fields
- `host`: IP or domain name of the target PostgreSQL.
- `port`: Service port of the target PostgreSQL instance (default `5432`). If the port was changed or a cloud database exposes a different port, enter the actual port.
- `user`: Account name used to log in to the target PostgreSQL. Prefer a separately created collection account (for example `cmdb_collector`); do not use a business account or superuser.
- `password`: Password for that account. Encrypted at rest and injected as an environment variable when dispatched. This is unrelated to the "administrator account"; the administrator account is only used to create the collection account.
- `database`: Database name used when connecting (default `postgres`).
- `timeout`: Connect/read timeout.


### Collected Data
**PostgreSQL (postgresql)**

| Key | Description |
| :--- | :--- |
| inst_name | Instance display name (`{ip}-pg-{port}`) |
| ip_addr | Instance IP |
| port | Listen port |
| version | PostgreSQL version (`SHOW server_version`) |
| conf_path | Configuration file path (`SHOW config_file`) |
| data_path | Data directory (`SHOW data_directory`) |
| max_conn | Max connections (`SHOW max_connections`) |
| cache_memory_mb | Shared buffers (`SHOW shared_buffers` converted to MB) |
| log_path | Log directory (`SHOW log_directory`) |

> Note: the fields above all come from `SHOW` commands. They may be empty if the target instance does not configure the corresponding item or returns empty. `cache_memory_mb` is converted from `shared_buffers` and is expressed in MB.
