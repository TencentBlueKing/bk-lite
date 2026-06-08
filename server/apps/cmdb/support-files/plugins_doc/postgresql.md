### 说明
该插件通过 PostgreSQL 原生协议直连实例，读取版本与关键配置项，并标准化同步至 CMDB。


### 操作入口与执行位置
你需要在 CMDB Web 页面完成配置：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 在插件卡片中选择 **PostgreSQL**。
3. 点击“新增任务”。

说明：任务实际执行发生在你选择的“接入点”上；文档中的连通性自测命令，均应在接入点机器上执行。


### 版本兼容性
- 兼容官方 PostgreSQL 常见主流版本；新旧大版本一般均可正常采集，建议以实际部署版本为准。

### 前置要求
在开始之前，请先确认以下条件：

1. **目标信息已明确**
   - PostgreSQL 地址：IP 或域名。
   - 端口：默认 `5432`，如有改动以实际为准。
   - 数据库名：默认 `postgres`，可按实际填写。
2. **网络连通已放通**
   - 接入点 → PostgreSQL 的 `TCP/<port>` 可达（安全组/防火墙/路由均放通）。
   - 若 PostgreSQL 在云上（如 RDS），需确认：接入点所在网络可以访问其内网/公网地址，并已加入白名单。
3. **PostgreSQL 允许远程连接**
   - 服务监听在目标网卡（`listen_addresses` 不是只监听 `127.0.0.1`）。
   - `pg_hba.conf` 已允许接入点来源 IP/网段登录（例如新增一条 `host <database> <user> 10.0.0.10/32 md5`），修改后需 `reload` 生效。
4. **已准备采集专用账号（只读/查询为主）**
   - 不要复用业务账号/超级用户账号。
   - 本插件读取的信息通过 `SHOW` 命令获取，任何已认证账号即可执行，无需特殊授权，因此账号“能登录”即可。
5. **接入点具备自测工具（可选但强烈建议）**
   - Linux：`nc`、`psql` 客户端（用于执行 `SELECT 1` 验证）。
   - Windows：PowerShell 的 `Test-NetConnection`。


### 操作步骤
### 步骤 1：网络连通性自测（在接入点执行）
任选一种方式进行验证：

- Linux：
  - `nc -vz <pg_ip> 5432`
  - `psql "host=<pg_ip> port=5432 user=<user> dbname=postgres" -c "SELECT 1;"`

- Windows PowerShell：
  - `Test-NetConnection <pg_ip> -Port 5432`

**判断标准**：端口连通，且能够成功执行 `SELECT 1`。


### 步骤 2：创建采集账号（在目标 PostgreSQL 上执行）
本插件读取的版本与配置项均通过 `SHOW` 命令完成，这些命令任何已认证账号都能执行，无需额外授权。因此你只需要创建一个“能登录”的最小账号即可。你需要一个具备账号管理权限的管理员账号（如 `postgres` 或 DBA 提供的管理账号）来执行下面的命令。

#### 2.1 用管理员账号登录 PostgreSQL（示例）
在 PostgreSQL 所在机器上，或任何能连到 PostgreSQL 的机器上执行（把 `pg_ip/port` 换成真实值）：

```bash
psql "host=<pg_ip> port=<port> user=<admin_user> dbname=postgres"
```

登录后你会进入 psql 提示符（形如 `postgres=#`）。

#### 2.2 创建最小采集账号
把下面脚本中的用户名、密码替换为你的真实值：

```sql
-- 创建一个仅能登录的采集账号（采集所需的 SHOW 命令无需额外授权）
CREATE ROLE cmdb_collector LOGIN PASSWORD 'YourStrongPassword';
```

说明：
- 上述语句仅创建一个可登录角色，不授予任何对象写入或 DDL 权限。
- 还需确认 `pg_hba.conf` 已允许接入点来源 IP 使用该账号登录（见“前置要求”第 3 条），否则即使账号存在也无法连接。

#### 2.3 验证采集账号是否可用
在接入点（或任意能访问 PostgreSQL 的机器）执行：

```bash
psql "host=<pg_ip> port=<port> user=cmdb_collector dbname=postgres" -c "SELECT 1;"
```

如果能返回 `1`，说明网络/账号基本可用。

#### 2.4 （可选）撤回/清理账号
如果你希望“撤回/清理账号”（例如测试后删除），执行：

```sql
DROP ROLE cmdb_collector;
```


### 凭据字段说明
- `host`：目标 PostgreSQL 的 IP 或域名。
- `port`：目标 PostgreSQL 实例对外提供服务的端口号（默认 `5432`）。如改过端口或云数据库提供了不同端口，请填写实际端口。
- `user`：用于登录目标 PostgreSQL 的账号名称。建议使用单独创建的采集账号（例如 `cmdb_collector`），不要使用业务账号或超级用户。
- `password`：上述账号对应的密码。落库自动加密，下发时以环境变量注入。该密码与“管理员账号”无关；管理员账号仅用于创建采集账号。
- `database`：连接时使用的数据库名（默认 `postgres`）。
- `timeout`：连接/读取的超时时间。


### 采集内容
**PostgreSQL（postgresql）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名（`{ip}-pg-{port}`） |
| ip_addr | 实例 IP |
| port | 监听端口 |
| version | PostgreSQL 版本（`SHOW server_version`） |
| conf_path | 配置文件路径（`SHOW config_file`） |
| data_path | 数据目录（`SHOW data_directory`） |
| max_conn | 最大连接数（`SHOW max_connections`） |
| cache_memory_mb | 共享缓冲区（`SHOW shared_buffers` 换算为 MB） |
| log_path | 日志目录（`SHOW log_directory`） |

> 补充说明：上述字段均来自 `SHOW` 命令，在目标实例未配置对应项或返回为空时，采集结果中可能为空；`cache_memory_mb` 由 `shared_buffers` 换算而来，单位以 MB 表示。
