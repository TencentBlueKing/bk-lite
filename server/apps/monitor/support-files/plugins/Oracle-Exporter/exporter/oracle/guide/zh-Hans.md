# Oracle 监控接入指南

## 前置要求

- 目标 Oracle 数据库已启动，并可通过网络访问，默认监听端口为 `1521`。
- 采集节点到 Oracle 数据库网络可达（含安全组 / 防火墙放通）。
- 已准备具备 Oracle 监控所需视图读取权限的账号和密码。
- 本插件通过本地运行的 Oracle-Exporter（Prometheus exporter）采集指标，再由 Telegraf 的 `inputs.prometheus` 从 `http://127.0.0.1:<监听端口>/metrics` 抓取数据。需在采集节点保证 Oracle-Exporter 已部署或可启动。

## 推荐账号权限

监控账号至少具备对下列动态性能视图的 `SELECT` 权限：

- `v$session`
- `v$sysstat`
- `v$database`

可在 Oracle 中按需授予对应权限，例如：

```sql
GRANT SELECT ANY DICTIONARY TO <monitor_user>;
```

或按需精确授予（更安全）：

```sql
GRANT SELECT ON v_$session TO <monitor_user>;
GRANT SELECT ON v_$sysstat TO <monitor_user>;
GRANT SELECT ON v_$database TO <monitor_user>;
```

建议使用专用只读监控账号，避免使用 `SYS`、`SYSTEM` 等高权限账号。

## 接入步骤

1. 在采集节点上确认可访问目标 Oracle 数据库：使用 `sqlplus` 验证账号可正常登录。
2. 在采集节点上确认 Oracle-Exporter 已启动，并能通过 `http://127.0.0.1:<监听端口>/metrics` 抓到指标。
3. 在监控对象接入页填写用户名、密码、服务名称、监听端口、主机、端口和采集间隔（默认 `60s`）。
4. 在「监控对象」表格中填写节点、监听端口、主机、端口、实例名称和所属组。
5. 点击「确认」保存配置，等待至少一个采集周期。
6. 到资产或指标页确认实例已上报数据。

## 接入前校验

在采集节点验证 Oracle 数据库连通性：

```bash
sqlplus <user>/<pass>@//<host>:<port>/<service_name>
```

验证 Oracle-Exporter 已正常监听并暴露 `/metrics`（注意这是 exporter 本地端口，不是 Oracle 端口）：

```bash
curl -sS "http://127.0.0.1:<监听端口>/metrics" | head
```

满足以下条件可认为接入基本可用：

- `sqlplus` 能成功登录目标 Oracle 实例
- `curl http://127.0.0.1:<监听端口>/metrics` 返回 `200` 且包含 `oracledb_*` 指标行

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | 访问 Oracle 数据库的监控账号 |
| 密码 | 是 | 对应账号密码 |
| 服务名称 | 是 | Oracle 的 `service_name`，需与实际运行的服务一致 |
| 监听端口 | 是 | Oracle-Exporter 本地暴露 `/metrics` 的端口（不是 Oracle 端口） |
| 主机 | 是 | Oracle 数据库所在主机地址 |
| 端口 | 是 | Oracle 数据库监听端口，默认 `1521` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 在采集节点重新执行 `sqlplus` 与 `curl http://127.0.0.1:<监听端口>/metrics`，确认数据库与 exporter 都可达。
- 确认 Oracle-Exporter 进程是否正常运行（`ps`、`docker ps` 或 `systemctl status`）。
- 等待至少一个采集间隔（默认 60 秒）后再查看。
- 检查节点上 Telegraf / Oracle-Exporter 采集任务是否正常运行。

### 2. 认证失败（ORA-01017 / ORA-28000）

- 确认用户名、密码、服务名称无首尾空格，注意 Oracle 用户名通常会被自动转为大写。
- 确认账号未被锁定（`ALTER USER <user> ACCOUNT UNLOCK;`），密码未过期。
- 确认账号具备 `v$session`、`v$sysstat`、`v$database` 等视图的 `SELECT` 权限。

### 3. exporter 未监听 / 端口冲突

- 本插件中「监听端口」是 Oracle-Exporter 在采集节点本地暴露 `/metrics` 的端口，区别于「端口」（Oracle 数据库本身，默认 `1521`）。两者不可混用。
- 在采集节点执行 `curl -v http://127.0.0.1:<监听端口>/metrics`，确认返回 `200` 且包含 `oracledb_*` 指标行。
- 若端口被占用，调整 Oracle-Exporter 的监听端口并同步更新本插件配置中的「监听端口」。
- 查看 Oracle-Exporter 日志，定位启动失败原因（如数据库连接串错误、账号权限不足）。

### 4. 仅部分指标缺失或权限不足

- 指标依赖 `v$session`、`v$sysstat`、`v$database` 等动态性能视图，权限不足会导致部分指标为空。
- 优先以 `GRANT SELECT ANY DICTIONARY` 验证是否为权限问题，再按需收敛授权范围。
- 若仅有 `tablespace` 相关指标缺失，确认账号是否被授予对应表空间的查询权限。
