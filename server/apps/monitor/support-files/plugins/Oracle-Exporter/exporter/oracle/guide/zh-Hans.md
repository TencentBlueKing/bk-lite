# Oracle 监控接入指南

本能力在所选节点运行 Oracle-Exporter，并由 Telegraf 从其本地 `/metrics` 端点拉取指标。

## 前置要求

- 采集节点能够访问 Oracle 数据库主机和实际监听端口。
- 准备专用监控账号；账号需能登录指定 `service_name`，并读取 exporter 默认指标和已开启的 RAC、ASM、归档、Data Guard 查询。授权对象使用底层名 `V_$` / `DBA_`，不要授予 `DBA` 或 `SELECT ANY DICTIONARY`。
- 页面要求填写 Oracle `service_name`，不是 SID。
- 在采集节点上准备一个未占用的 exporter 监听端口。该端口与 Oracle 数据库端口是两个独立字段。
- 当前页面不提供 SID、TCPS、Wallet 或自定义连接串字段。

## 接入步骤

1. 由 DBA 在采集器实际连接的容器中创建专用账号。`GRANT` 的对象是 `V_$` / `DBA_`，不能对同义词 `V$` 授权。将 `<monitor_user>`、`<password>` 换成现场值。不要授予 `DBA` 或 `SELECT ANY DICTIONARY`：

```sql
CREATE USER <monitor_user> IDENTIFIED BY "<password>";
GRANT CREATE SESSION TO <monitor_user>;

-- 默认指标
GRANT SELECT ON V_$INSTANCE TO <monitor_user>;
GRANT SELECT ON V_$SESSION TO <monitor_user>;
GRANT SELECT ON V_$RESOURCE_LIMIT TO <monitor_user>;
GRANT SELECT ON V_$SYSSTAT TO <monitor_user>;
GRANT SELECT ON V_$PROCESS TO <monitor_user>;
GRANT SELECT ON V_$SYSMETRIC TO <monitor_user>;
GRANT SELECT ON V_$WAITCLASSMETRIC TO <monitor_user>;
GRANT SELECT ON V_$SYSTEM_WAIT_CLASS TO <monitor_user>;
GRANT SELECT ON V_$SGA TO <monitor_user>;
GRANT SELECT ON V_$SGASTAT TO <monitor_user>;
GRANT SELECT ON V_$PGASTAT TO <monitor_user>;
GRANT SELECT ON V_$PARAMETER TO <monitor_user>;
GRANT SELECT ON V_$DATAFILE TO <monitor_user>;
GRANT SELECT ON V_$LOG_HISTORY TO <monitor_user>;
GRANT SELECT ON V_$EVENTMETRIC TO <monitor_user>;
GRANT SELECT ON V_$EVENT_NAME TO <monitor_user>;
GRANT SELECT ON V_$LOCKED_OBJECT TO <monitor_user>;
GRANT SELECT ON V_$ASM_DISKGROUP_STAT TO <monitor_user>;
GRANT SELECT ON DBA_TABLESPACE_USAGE_METRICS TO <monitor_user>;
GRANT SELECT ON DBA_TABLESPACES TO <monitor_user>;
GRANT SELECT ON DBA_INDEXES TO <monitor_user>;
GRANT SELECT ON DBA_OBJECTS TO <monitor_user>;
GRANT SELECT ON DBA_USERS TO <monitor_user>;

-- 当前采集器固定启用 --isRAC --isASM --isArchiveLog --isDataGuard
GRANT SELECT ON GV_$INSTANCE TO <monitor_user>;
GRANT SELECT ON V_$ASM_DISK_STAT TO <monitor_user>;
GRANT SELECT ON V_$ASM_ALIAS TO <monitor_user>;
GRANT SELECT ON V_$ASM_DISKGROUP TO <monitor_user>;
GRANT SELECT ON V_$ASM_FILE TO <monitor_user>;
GRANT SELECT ON V_$DATAGUARD_STATS TO <monitor_user>;
GRANT SELECT ON V_$DATABASE TO <monitor_user>;
GRANT SELECT ON V_$ARCHIVE_DEST TO <monitor_user>;
```

这些对象与 exporter 的 `default_metrics.toml`、`rac_metrics.toml`、`asm_metrics.toml`、`dg_metrics.toml` 和归档查询一致。非 CDB 或单个 PDB 使用本地用户；只有从 CDB 根容器监控多个容器时才改用 `C##` 公共用户。

2. 从实际采集节点验证数据库主机、端口、`service_name` 和监控账号。
3. 填写用户名、密码、服务名称、数据库主机和端口。
4. 填写未占用的 exporter 监听端口和采集间隔（默认 `60` 秒）。
5. 在监控对象表格中选择节点，填写监听端口、主机、端口、实例名称和可选分组。
6. 保存后等待至少一个采集周期。

## 接入前校验

使用 `sqlplus` 连接具体服务；命令会交互式询问密码，不要把密码写入命令行：

```bash
sqlplus monitor@//db.example.com:1521/ORCLPDB1
```

登录后确认账号能够查询所需动态性能视图。也可先验证 TCP 端口：

```bash
nc -vz db.example.com 1521
```

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | Oracle 监控账号。 |
| 密码 | 是 | 对应账号密码。 |
| 服务名称 | 是 | Oracle `service_name`，不是 SID。 |
| 监听端口 | 是 | Oracle-Exporter 在采集节点本地暴露 `/metrics` 的端口。 |
| 主机 | 是 | Oracle 数据库主机地址。 |
| 端口 | 是 | Oracle 数据库实际监听端口。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 运行 Oracle-Exporter 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，可按实际监听端口检查本地端点，例如：

```bash
curl --fail --silent --show-error "http://127.0.0.1:9161/metrics"
```

随后在平台确认以下指标可查询：

- `oracledb_up_gauge`
- `oracledb_uptime_seconds_gauge`
- `oracledb_sessions_value_gauge`
- `oracledb_tablespace_used_percent_gauge`

## 常见问题

### 登录失败

- 区分 `service_name` 与 SID，并核对主机、数据库端口和账号状态。
- 通过交互式密码提示验证，避免因 shell 转义造成误判。

### exporter 本地端点不可访问

- 不要把数据库端口填入「监听端口」。
- 检查本地端口冲突，并查看 Oracle-Exporter 的进程参数与日志。

### 只有部分指标

- 登录成功不等于具备全部动态性能视图权限；按 exporter 日志中的实际查询错误补齐最小读取权限。
- 表空间、会话和资源指标依赖的视图不同，需分别核对权限与目标实例是否提供数据。
