# MySQL 监控接入指南

本能力直连 MySQL，采集连接、查询、InnoDB、复制等统计。

## 前置要求

- 采集节点能够访问目标 MySQL 主机和实际端口。
- 当前接入不启用 TLS，页面没有 TLS、数据库名或自定义连接参数字段。

### 基础监控权限

基础监控即可跑健康概览和性能常规图（连接、查询、InnoDB、复制等）。

- 专用监控账号可登录实例，主机限制为采集节点来源。
- 查看进程（`PROCESS`）：进程列表与部分实例状态。
- 查看复制（`REPLICATION CLIENT`）：复制状态与 Binary Log。
- 建议同时授予 `SELECT ON performance_schema.*`：Performance Schema 相关统计（含表等待；也是语句/等待进阶的前提）。
- 不要授予业务库 `SELECT`。若个别 InnoDB 指标因 `information_schema` 被拒，仅对该表补 `SELECT`。

### Top SQL 与等待（进阶）

在基础监控权限已满足的前提下，Top SQL 页和等待页还需要：

- 实例已启用 Performance Schema。未启用则语句和等待采不到。
- 监控账号已有 `SELECT ON performance_schema.*`，与基础监控建议的同一授权即可。
- 在采集配置中打开对应开关，这两项默认关闭：「Top SQL 采集」对应 Top SQL 页；「等待/会话采集」对应等待页。
- 与「表 IO Wait」「表锁 Wait」相互独立。打开表等待不会自动出现语句或等待数据，反过来也一样。

## 接入步骤

1. 由 DBA 创建专用账号。将 `<monitor_user>`、`<password>`、`<collector_host>` 换成现场值；主机限制为采集节点地址，不要使用 `%`，也不要把密码写入命令历史：

```sql
CREATE USER '<monitor_user>'@'<collector_host>' IDENTIFIED BY '<password>';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO '<monitor_user>'@'<collector_host>';
GRANT SELECT ON performance_schema.* TO '<monitor_user>'@'<collector_host>';
```

- `PROCESS`：进程列表与部分实例状态。
- `REPLICATION CLIENT`：复制状态与 Binary Log。
- `SELECT ON performance_schema.*`：Performance Schema 相关统计（含表等待；也是语句/等待进阶的前提）。
- 不要授予业务库 `SELECT`。若个别 InnoDB 指标因 `information_schema` 被拒，仅对该表补 `SELECT`。

2. 从实际采集节点验证目标地址、账号和基本状态查询权限。
3. 填写用户名、密码、主机、实际端口和采集间隔（默认 `60` 秒）。
4. 在监控对象表格中选择节点，填写主机、端口、实例名称和可选分组。
5. 保存后等待至少一个采集周期。

## 接入前校验

`--password` 会交互式询问密码：

```bash
mysql --host db.example.com --port 3306 --user monitor --password --execute "SHOW GLOBAL STATUS LIKE 'Uptime';"
```

命令应成功返回 `Uptime`。如需复制数据，再用同一账号验证目标版本支持且账号有权执行相应复制状态查询。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | MySQL 监控账号。 |
| 密码 | 是 | 对应账号密码。 |
| 主机 | 是 | MySQL 主机名或 IP，不包含协议。 |
| 端口 | 是 | MySQL 实际监听端口。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 MySQL 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认可以查到运行时长、当前连接数、查询速率和 InnoDB 缓冲池等基础指标。

## 常见问题

### 登录失败

- 核对账号允许从采集节点来源地址登录。
- 使用交互式密码提示复核，避免 shell 对特殊字符的解释造成误判。

### 只有部分数据

- 缺 `PROCESS`：进程列表和部分实例状态没有数据。
- 缺 `REPLICATION CLIENT`：复制状态和 Binary Log 没有数据。
- 缺 `SELECT ON performance_schema.*`：Performance Schema 相关统计没有数据，表等待以及语句、等待进阶也会空。
- 未打开「Top SQL 采集」或「等待/会话采集」：对应页没有数据。这两项默认关闭，且需要实例已启用 Performance Schema。
- 非复制实例没有复制数据，属于正常情况。
- 仍对不上时，查看采集任务失败原因或采集日志。

### 目标强制 TLS

- 当前接入不启用 TLS，页面没有证书或 TLS 模式字段；强制 TLS 的目标不能用此配置直接接入。
