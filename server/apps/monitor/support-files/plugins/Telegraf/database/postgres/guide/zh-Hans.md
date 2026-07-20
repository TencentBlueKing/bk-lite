# PostgreSQL 监控接入指南

## 前置要求

- 目标实例已启动 PostgreSQL 服务，默认监听 `5432` 端口。
- 采集节点到 PostgreSQL 地址网络可达（含安全组 / 防火墙放通 5432 端口）。
- 已准备具备数据库登录与查询统计视图权限的账号和密码。
- 监控账号建议具备 `pg_monitor` 角色，用于读取 `pg_stat_*` 视图。

## 推荐账号权限

参考 Telegraf `inputs.postgresql` 官方推荐，使用专用只读监控账号并授予 `pg_read_all_stats` 预定义角色（PostgreSQL 10+ 提供，可读取所有 `pg_stat_*` / `pg_stat_database` 视图）：

```sql
CREATE USER monitor WITH PASSWORD '<your_password>';
GRANT pg_read_all_stats TO monitor;
```

> 旧版本可授予 `pg_monitor`（PostgreSQL 10-15 的角色），并按需 `GRANT SELECT ON ALL TABLES IN SCHEMA pg_catalog TO monitor;`。无需 SUPERUSER。

模板已默认忽略 `template0`、`template1` 系统库，不会对监控账号的访问范围造成干扰。

## 接入步骤

1. 在采集节点上使用 `psql` 验证可登录目标 PostgreSQL。
2. 在监控对象接入页填写用户名、密码、主机、端口（默认 `5432`）和采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写采集节点、主机、端口、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

在采集节点上使用监控账号登录数据库，校验连通性与基本查询权限：

```bash
psql "host=<host> port=<port> user=<user> dbname=postgres" -c "SELECT version();"
```

满足以下条件可认为接入基本可用：

- 命令成功返回 PostgreSQL 版本号，无 `FATAL: could not connect` 等错误。
- 监控账号可执行 `SELECT * FROM pg_stat_database;` 等 `pg_stat_*` 视图查询。

可选的连通性探测：

```bash
nc -vz <host> 5432
```

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | 访问 PostgreSQL 的账号，建议授予 `pg_monitor` |
| 密码 | 是 | 对应账号密码 |
| 主机 | 是 | PostgreSQL 服务所在主机，例如 `10.0.0.10` |
| 端口 | 是 | PostgreSQL 端口，默认 `5432` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名（默认 `主机:端口`） |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 在采集节点用 `psql` 重连测试，确认不仅控制台可达。
- 确认 `pg_hba.conf` 允许来自采集节点 IP 的连接（`host all all <collector_ip>/32 md5`）。
- 等待至少一个采集间隔（默认 60 秒）后再查看。
- 检查 Telegraf / 采集任务在目标节点是否正常运行。

### 2. 认证失败

- 确认用户名密码无首尾空格与特殊字符未正确转义。
- 确认账号已通过 `GRANT pg_monitor TO <user>;` 授权。
- 检查 PostgreSQL 是否启用 `pg_hba.conf` 中的 `md5`/`scram-sha-256` 认证方式。

### 3. 仅部分指标缺失或权限不足

- 缺少 `pg_stat_*` 类指标通常是监控账号权限不足，授予 `pg_monitor` 后重试。
- 数据库连接数、锁等待、复制延迟等指标依赖对应视图的查询权限。
- 模板默认忽略 `template0`、`template1`，其余数据库若无权限也会被静默跳过。

### 4. SSL / 连接相关异常

- 模板默认 `sslmode=disable`，若目标库强制 SSL，请改用兼容的连接串并配置 `pg_hba.conf`。
- 如出现 `FATAL: no pg_hba.conf entry`，通常是 `pg_hba.conf` 未放通采集节点 IP。
