# Oracle 监控接入指南

本能力在所选节点运行 Oracle-Exporter，并由 Telegraf 从其本地 `/metrics` 端点拉取指标。

## 前置要求

- 采集节点能够访问 Oracle 数据库主机和实际监听端口。
- 准备专用监控账号；账号需能登录指定 `service_name`，并读取 exporter 查询涉及的动态性能视图，例如 `v$session`、`v$sysstat` 和 `v$database`。
- 页面要求填写 Oracle `service_name`，不是 SID。
- 在采集节点上准备一个未占用的 exporter 监听端口。该端口与 Oracle 数据库端口是两个独立字段。
- 当前页面不提供 SID、TCPS、Wallet 或自定义连接串字段。

## 接入步骤

1. 从实际采集节点验证数据库主机、端口、`service_name` 和监控账号。
2. 填写用户名、密码、服务名称、数据库主机和端口。
3. 填写未占用的 exporter 监听端口和采集间隔（默认 `60` 秒）。
4. 在监控对象表格中选择节点，填写监听端口、主机、端口、实例名称和可选分组。
5. 保存后等待至少一个采集周期。

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
