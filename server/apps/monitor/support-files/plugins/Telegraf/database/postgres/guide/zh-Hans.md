# PostgreSQL 监控接入指南

本能力通过 Telegraf `inputs.postgresql` 连接指定 PostgreSQL 主机、端口和数据库。

## 前置要求

- 采集节点能够访问目标 PostgreSQL 主机和实际端口。
- 准备可登录指定数据库并读取 `pg_stat_database`、`pg_stat_bgwriter` 的账号。PostgreSQL 10 及以上授予 `pg_read_all_stats`。同一授权也可读取当前会话等待。
- 「Top SQL 采集」默认关闭。打开前，由 DBA 在页面填写的数据库中执行 `CREATE EXTENSION IF NOT EXISTS pg_stat_statements`（并已把它加入 `shared_preload_libraries`）。监控账号需能读取该视图。
- 「等待事件采集」默认关闭。打开后采样当前正在等待的会话，不是累计等待时长。
- 恢复状态、流复制连接数和复制槽个数随基础连接采集。备库，或连接数、槽个数大于 0，顶栏形态为「主从」。未处于恢复且两者都是 0，形态为「单机」。没有这些读数时不显示形态，也不把未处于恢复单独写成「单机」。同一查询还采集已连接副本的写入、刷盘和回放延迟，以及复制槽仍保留的 WAL。没有流复制连接时延迟为 0；没有槽在保留 WAL 时积压为 0。
- 目标的 `pg_hba.conf` 允许来自采集节点的该账号连接。
- 页面可选 SSL 模式 `disable`、`prefer`、`require`；本模板不支持证书路径，`verify-ca` / `verify-full` 暂不可用。
- 模板固定忽略 `template0` 和 `template1`。

## 接入步骤

1. 由 DBA 创建专用账号。当前采集器是 Telegraf `inputs.postgresql`，读取 `pg_stat_database` 和 `pg_stat_bgwriter`。PostgreSQL 10 及以上授予 `pg_read_all_stats`。将 `<monitor_user>`、`<password>`、`<dbname>` 换成现场值，不要把密码写入命令历史：

```sql
CREATE ROLE <monitor_user> WITH LOGIN PASSWORD '<password>';
GRANT CONNECT ON DATABASE <dbname> TO <monitor_user>;
GRANT pg_read_all_stats TO <monitor_user>;
```

`<dbname>` 与页面数据库名一致，默认可用 `postgres`。不要授予超级用户，也不要改用 `postgres_exporter` 的 `SECURITY DEFINER` 包装视图；当前模板不查询那些视图。来源地址仍由 `pg_hba.conf` 限制。

2. 从实际采集节点验证目标地址、账号、数据库名、SSL 模式和统计视图权限。
3. 填写用户名、密码、主机、实际端口、数据库名、SSL 模式和采集间隔（默认 `60` 秒）。
4. 在监控对象表格中选择节点，填写主机、端口、实例名称和可选分组。
5. 保存后等待至少一个采集周期。

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
| Top SQL 采集 | 否 | 高级选项，默认关闭。打开后可在专业盘查看语句耗时、执行次数和返回行。 |
| 等待事件采集 | 否 | 高级选项，默认关闭。打开后可查看当前等待会话。 |
| 节点 | 是 | 能够访问 PostgreSQL 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `postgresql_numbackends`
- `postgresql_xact_commit_rate`
- `postgresql_deadlocks_rate`
- `postgresql_cache_hit_ratio`
- `postgresql_recovery_in_recovery`（0 为接受写入，1 为备库）
- `postgresql_replication_streaming_replicas`（当前流复制连接数）
- `postgresql_replication_replication_slots`（复制槽个数）
- `postgresql_replication_write_lag_seconds`（已连接副本的写入延迟，秒）
- `postgresql_replication_flush_lag_seconds`（已连接副本的刷盘延迟，秒）
- `postgresql_replication_replay_lag_seconds`（已连接副本的回放延迟，秒）
- `postgresql_replication_slot_restart_lag_bytes`（复制槽仍保留的 WAL，字节）

打开「Top SQL 采集」并完成至少一个采集周期后，还可确认 `postgresql_statement_total_time_seconds`。打开「等待事件采集」后，有会话正在等待时可确认 `postgresql_wait_sessions`。

## 常见问题

### 认证或来源地址被拒绝

- 核对 `pg_hba.conf` 是否允许采集节点来源地址、账号和目标数据库。
- 核对服务器实际使用的密码认证方式与账号配置。

### 登录成功但数据不完整

- 确认账号能读取 `pg_stat_database` 和 `pg_stat_bgwriter`。PostgreSQL 10 及以上使用 `pg_read_all_stats`。
- `template0` 和 `template1` 被模板明确忽略，不会产生数据。

### 目标强制 SSL

- 将 SSL 模式设为 `require`（或 `prefer`）。本模板不支持证书路径；需要 `verify-ca` / `verify-full` 的目标暂无法直接接入。
