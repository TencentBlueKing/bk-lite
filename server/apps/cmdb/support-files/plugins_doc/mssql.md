### 说明
【BETA】该插件通过 ODBC 直连 SQL Server 实例，读取版本与关键配置项，并标准化同步至 CMDB。


### 操作入口与执行位置
你需要在 CMDB Web 页面完成配置：
1. 进入“CMDB → 管理 → 自动发现 → 采集 → 专业采集”。
2. 在插件卡片中选择 **MSSQL**。
3. 点击“新增任务”。

说明：任务实际执行发生在你选择的“接入点”上；文档中的连通性自测命令，均应在接入点机器上执行。


### 版本兼容性
- 兼容官方 SQL Server 常见主流版本；建议以实际部署版本为准。

### 前置要求
在开始之前，请先确认以下条件：

1. **目标信息已明确**
   - SQL Server 地址：IP 或域名。
   - 端口：默认 `1433`，如有改动以实际为准。
   - 数据库名：按实际填写。
2. **网络连通已放通**
   - 接入点 → SQL Server 的 `TCP/<port>` 可达（安全组/防火墙/路由均放通）。
   - 若 SQL Server 在云上，需确认：接入点所在网络可以访问其内网/公网地址，并已加入白名单。
3. **接入点已安装 ODBC 驱动（重要）**
   - 采集器（接入点）主机需安装 “ODBC Driver 17 for SQL Server”，否则无法建立连接。
   - 可在接入点执行 `odbcinst -j` 或 `odbcinst -q -d` 确认驱动已安装；未安装请参考微软官方文档安装。
4. **SQL Server 允许远程连接**
   - 已启用 TCP/IP 协议并监听目标端口，允许来自接入点的连接。
5. **已准备采集专用账号（只读/查询为主）**
   - 不要复用业务账号/管理员账号。
   - 账号需具备 `db_datareader` 角色，并授予 `VIEW SERVER STATE`（用于读取 `sys.dm_*` 动态视图）。
6. **接入点具备自测工具（可选但强烈建议）**
   - Windows：PowerShell 的 `Test-NetConnection`。
   - Linux：`nc`。


### 操作步骤
### 步骤 1：网络连通性自测（在接入点执行）
任选一种方式进行验证：

- Linux：
  - `nc -vz <mssql_ip> 1433`

- Windows PowerShell：
  - `Test-NetConnection <mssql_ip> -Port 1433`

**判断标准**：端口连通即可。

### 步骤 2：创建采集账号（在目标 SQL Server 上执行）
你需要一个具备账号管理权限的管理员账号（如 `sa` 或 DBA 提供的管理账号）来执行下面的命令。把脚本中的用户名、密码、数据库名替换为你的真实值：

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

说明：
- 上述授权不包含写入或 DDL 权限。
- `VIEW SERVER STATE` 用于读取 `sys.dm_os_*` 等动态视图（如内存使用），缺失会导致相关字段采集不全。

### 步骤 3：验证采集账号是否可用
在接入点（已安装 ODBC 驱动）上，使用该账号建立连接并执行 `SELECT 1;`，能正常返回即说明网络/账号/驱动基本可用。例如 Linux 下可执行：

```bash
sqlcmd -S <ip>,1433 -U cmdb_collector -P '<password>' -Q "SELECT 1"
```

（或用任意 SQL Server 客户端测试连接）

### 步骤 4：（可选）撤回/清理账号
```sql
USE [YourDatabase];
DROP USER cmdb_collector;
DROP LOGIN cmdb_collector;
```


### 凭据字段说明
- `host`：目标 SQL Server 的 IP 或域名。
- `port`：目标实例对外提供服务的端口号（默认 `1433`）。如改过端口请填写实际端口。
- `user`：用于登录目标 SQL Server 的账号名称。建议使用单独创建的采集账号（例如 `cmdb_collector`），不要使用业务账号或管理员账号。
- `password`：上述账号对应的密码。落库自动加密，下发时以环境变量注入。
- `database`：连接时使用的数据库名。
- `timeout`：连接/读取的超时时间。


### 采集内容
**SQL Server（mssql）**

| Key 名称 | 含义 |
| :--- | :--- |
| inst_name | 实例展示名 |
| ip_addr | 实例 IP |
| port | 监听端口 |
| version | 产品版本（`SERVERPROPERTY('ProductVersion')`） |
| max_conn | 最大连接数（user connections） |
| fill_factor | 索引填充因子 |
| max_mem | 物理内存使用（`physical_memory_in_use_kb` 换算为 MB） |
| order_rule | 排序规则（collation） |
| db_name | 数据库名 |

> 补充说明：`max_mem` 等来自 `sys.dm_*` 动态视图的字段依赖 `VIEW SERVER STATE` 权限，权限缺失或目标未返回对应项时，采集结果中可能为空。
