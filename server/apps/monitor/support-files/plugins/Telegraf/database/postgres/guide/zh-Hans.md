# PostgreSQL 监控接入指南

本能力通过 Telegraf `inputs.postgresql` 连接指定 PostgreSQL 主机、端口和数据库。

## 前置要求

- 采集节点能够访问目标 PostgreSQL 主机和实际端口。
- 准备可登录指定数据库并读取所需统计视图的账号；PostgreSQL 10 及以上可按最小权限授予 `pg_monitor`。
- 目标的 `pg_hba.conf` 允许来自采集节点的该账号连接。
- 页面可选 SSL 模式 `disable`、`prefer`、`require`；本模板不支持证书路径，`verify-ca` / `verify-full` 暂不可用。
- 模板固定忽略 `template0` 和 `template1`。

## 接入步骤

1. 从实际采集节点验证目标地址、账号、数据库名、SSL 模式和统计视图权限。
2. 填写用户名、密码、主机、实际端口、数据库名、SSL 模式和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写主机、端口、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

`--password` 会交互式询问密码：

```bash
psql --host db.example.com --port 5432 --username monitor --dbname postgres --password --command "SELECT count(*) FROM pg_stat_database;"
```

命令应成功返回结果，并且不能出现认证、网络或统计视图权限错误。若目标要求 SSL，请在校验命令中增加相应 SSL 参数。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | PostgreSQL 监控账号。 |
| 密码 | 是 | 对应账号密码。 |
| 主机 | 是 | PostgreSQL 主机名或 IP，不包含协议。 |
| 端口 | 是 | PostgreSQL 实际监听端口。 |
| 数据库名 | 是 | 建立监控连接的数据库，默认 `postgres`。 |
| SSL 模式 | 是 | `disable` / `prefer` / `require`，默认 `disable`。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 PostgreSQL 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `postgresql_numbackends`
- `postgresql_xact_commit_rate`
- `postgresql_deadlocks_rate`
- `postgresql_cache_hit_ratio`

## 常见问题

### 认证或来源地址被拒绝

- 核对 `pg_hba.conf` 是否允许采集节点来源地址、账号和目标数据库。
- 核对服务器实际使用的密码认证方式与账号配置。

### 登录成功但数据不完整

- 确认账号能读取所需 `pg_stat_*` 视图；按版本使用 `pg_monitor` 或等效最小权限。
- `template0` 和 `template1` 被模板明确忽略，不会产生数据。

### 目标强制 SSL

- 将 SSL 模式设为 `require`（或 `prefer`）。本模板不支持证书路径；需要 `verify-ca` / `verify-full` 的目标暂无法直接接入。
