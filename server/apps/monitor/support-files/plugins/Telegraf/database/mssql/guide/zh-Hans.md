# MSSQL 监控接入指南

本能力通过 Telegraf `inputs.sqlserver` 使用 SQL Server 账号连接指定主机与 TCP 端口。

## 前置要求

- 采集节点能够访问 SQL Server 的实际 TCP 主机和端口。
- 准备可登录 `master` 数据库并读取所需动态管理视图的账号；通常需要 `VIEW SERVER STATE`。
- 当前页面只接收主机和 TCP 端口。命名实例应先确定并固定实际 TCP 端口，不能填写实例名语法。
- 当前连接固定 `encrypt=disable`，页面没有加密或证书字段。
- 模板明确排除 `SQLServerAvailabilityReplicaStates` 和 `SQLServerDatabaseReplicaStates` 查询，因此不会采集相应的副本状态数据。

## 接入步骤

1. 从实际采集节点验证目标 TCP 端口和监控账号。
2. 填写用户名、密码、主机、实际 TCP 端口和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写主机、端口、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

使用 `tcp:` 地址和固定端口；省略 `-P` 后 `sqlcmd` 会交互式询问密码：

```bash
sqlcmd -S tcp:sql.example.com,1433 -U monitor -Q "SELECT @@VERSION"
```

命令应成功返回版本。页面要求分别填写 TCP 主机和实际端口。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | SQL Server 登录名。 |
| 密码 | 是 | 对应账号密码。 |
| 主机 | 是 | SQL Server 主机名或 IP，不包含实例名。 |
| 端口 | 是 | 实际 TCP 端口。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问目标 TCP 端口的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称，默认可由主机和端口组合。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `sqlserver_cpu_sqlserver_process_cpu_avg`
- `sqlserver_server_properties_uptime`
- `sqlserver_memory_total_server_memory_kb`
- `sqlserver_page_life_expectancy`

## 常见问题

### 命名实例无法连接

- 先在 SQL Server 侧确认命名实例实际使用的 TCP 端口，再在页面分别填写主机和端口。
- 当前连接不通过 SQL Server Browser 解析实例名。

### 登录成功但数据不完整

- 核对账号对动态管理视图的 `VIEW SERVER STATE` 权限。
- 两个副本状态查询由模板明确排除，缺少对应数据是当前配置边界。

### 目标要求加密

- 当前模板固定禁用加密，页面也没有证书字段；强制加密的目标无法用此配置直接接入。
