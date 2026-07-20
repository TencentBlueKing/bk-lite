# SQL Server（MSSQL）监控接入指南

## 前置要求

- 目标实例已启动 SQL Server 数据库服务，默认监听 `1433` 端口（命名实例可能使用动态端口，请以实际为准）。
- 采集节点到 SQL Server 地址网络可达（含安全组 / 防火墙放通 `1433` 或对应端口）。
- 已准备具备 `VIEW SERVER STATE` 权限的监控账号和密码。
- 主机地址可直接填写 IP 或主机名；端口默认为 `1433`，按实例情况调整。

## 推荐账号权限

监控账号至少需要 `VIEW SERVER STATE`（以及在采集复制/可用性组指标时补充 `VIEW ANY DEFINITION`）权限以读取 SQL Server 动态管理视图。可由管理员在目标实例上执行（参考 Telegraf `inputs.sqlserver` 官方推荐步骤）：

```sql
USE master;
GO
CREATE LOGIN [monitor] WITH PASSWORD = N'<your_password>';
GO
GRANT VIEW SERVER STATE TO [monitor];
GO
GRANT VIEW ANY DEFINITION TO [monitor];
GO
```

如需采集每个用户数据库内部指标，需在每个业务库中创建对应 user 并授予 `VIEW DATABASE STATE`：

```sql
USE <your_database>;
GO
CREATE USER [monitor] FOR LOGIN [monitor];
GO
GRANT VIEW DATABASE STATE TO [monitor];
GO
```

Azure SQL Database / Elastic Pool 等场景请参见上游 README 中的 `## Additional Setup` 章节，使用 `##MS_ServerStateReader##` 服务器角色或 `VIEW DATABASE STATE`。

- 建议使用专用只读监控账号，避免使用 `sa` 等高权限管理员账号。
- 若启用混合身份验证，请确认 SQL Server 配置允许 SQL 登录，并已启用对应登录名。
- 模板默认使用 `encrypt=disable`，无需额外证书配置。

## 接入步骤

1. 在采集节点上确认可访问目标 SQL Server（推荐先执行下方「接入前校验」命令）。
2. 在监控对象接入页填写用户名、密码、主机、端口和采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、主机、端口、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

在采集节点使用 `sqlcmd` 进行连通性与账号校验：

```bash
sqlcmd -S <host>,<port> -U <user> -P '<password>' -Q "SELECT @@VERSION"
```

满足以下条件可认为账号与网络基本可用：

- 命令无认证错误，能正常返回 `SELECT @@VERSION` 结果（含 SQL Server 版本号）。
- 若使用命名实例，请使用 `-S <host>\\<instance_name>` 形式连接。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | 访问 SQL Server 的登录名，例如 `monitor` |
| 密码 | 是 | 对应账号的登录密码 |
| 主机 | 是 | SQL Server 地址，IP 或主机名 |
| 端口 | 是 | SQL Server 端口，默认 `1433` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 `主机:端口` 自动组合 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 在采集节点上重新执行 `sqlcmd` 校验，确认主机、端口可达且账号可用。
- 确认 `1433`（或对应端口）在安全组 / 防火墙已放通。
- 等待至少一个采集间隔后再查看。
- 检查节点上 Telegraf / 采集任务是否正常运行，是否有 `sqlserver` 插件报错。

### 2. 认证失败（登录失败 / Login failed）

- 确认 SQL Server 启用了 SQL Server 身份验证（混合身份验证）。
- 确认用户名密码无首尾空格与特殊字符转义问题，`sqlcmd -P` 加单引号可避免 shell 转义。
- 确认账号具备 `VIEW SERVER STATE` 权限。
- 确认账号未被锁定或禁用，密码策略未过期。

### 3. 仅部分指标缺失或权限不足

- Telegraf `sqlserver` 输入依赖 `sys.dm_*` 动态管理视图，权限不足时会出现连接成功但指标缺失。
- 部分指标（如可用性组、复制状态）依赖额外权限或未启用 AlwaysOn，请按需放开 `VIEW SERVER STATE` 及对应 DMV 权限。
- 若数据库使用了非默认 schema 或列名差异，请确认 SQL Server 版本与 Telegraf `sqlserver` 插件版本兼容。

### 4. 命名实例或动态端口

- SQL Server 命名实例默认使用动态端口，建议在实例上固定 TCP 端口或使用 SQL Server Browser（`UDP 1434`）。
- 若采集节点无法访问 SQL Server Browser，需明确填写命名实例对应的实际 TCP 端口。
- 连接字符串默认 `encrypt=disable`，若目标强制加密请同步调整模板参数。