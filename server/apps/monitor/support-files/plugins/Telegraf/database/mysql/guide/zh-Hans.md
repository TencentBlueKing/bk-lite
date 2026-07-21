# MySQL 监控接入指南

## 前置要求

- 目标 MySQL 实例已启动并监听 `3306` 端口（默认）。
- 采集节点到 MySQL 网络可达（含安全组 / 防火墙放通 3306）。
- 已准备具备监控所需权限的 MySQL 账号和密码。
- 已准备好一台 Telegraf 采集节点，并已加入平台节点管理。

## 推荐账号权限

监控账号至少具备以下权限，用于覆盖 `SHOW GLOBAL STATUS`、`SHOW GLOBAL VARIABLES`、`SHOW SLAVE STATUS` 以及 `performance_schema` / `information_schema` 读取：

- `PROCESS`
- `REPLICATION CLIENT`
- `SELECT`（针对 `performance_schema` 与 `information_schema`）
- 可选：`SUPER` 或 `BACKUP_ADMIN`（用于 `SHOW SLAVE STATUS` 在 8.0 上的兼容性，建议按实际版本与最小化原则授权）

示例（最小化授权）：

```sql
CREATE USER 'monitor'@'%' IDENTIFIED BY '<password>';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'monitor'@'%';
GRANT SELECT ON performance_schema.* TO 'monitor'@'%';
GRANT SELECT ON information_schema.* TO 'monitor'@'%';
FLUSH PRIVILEGES;
```

建议使用专用只读监控账号，避免使用业务高权限账号。

## 接入步骤

1. 在采集节点上确认可访问目标 MySQL，例如 `mysql -h <host> -P 3306 -u <username> -p` 能正常登录。
2. 在监控对象接入页填写用户名、密码、主机、端口和采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、主机、端口、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据（如 `mysql_uptime`、`mysql_threads_connected` 等）。

## 接入前校验

使用 MySQL 客户端登录并执行以下命令：

```bash
mysql -h <host> -P 3306 -u <username> -p -e "SHOW GLOBAL STATUS LIKE 'Uptime';"
```

预期返回包含 `Uptime` 变量及数值（单位：秒），表示账号具备 `SHOW GLOBAL STATUS` 权限。

主从相关（如果开启了 `gather_slave_status`）：

```bash
mysql -h <host> -P 3306 -u <username> -p -e "SHOW SLAVE STATUS\\G"
```

满足以下条件可认为采集链路基本可用：

- 命令可成功执行，无需额外交互。
- `Uptime` 返回非零数值。
- 网络连通，无 `ERROR 1045 (28000)`、`ERROR 1130` 等认证或网络拒绝错误。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 是 | 用于连接 MySQL 的账号 |
| 密码 | 是 | 对应账号密码 |
| 主机 | 是 | MySQL 实例地址（IP 或域名） |
| 端口 | 是 | MySQL 监听端口，默认 `3306` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认采集节点能 Telnet/TCP 连通目标 MySQL 的 3306 端口。
- 确认采集节点上 Telegraf / 采集任务是否正常运行。
- 等待至少一个采集间隔（默认 60 秒）后再查看。
- 在采集节点上用 `mysql` 客户端重放下面的命令，确认账号可用。

### 2. 认证失败（`ERROR 1045` / `Access denied`）

- 检查用户名密码是否带入首尾空格或多余换行。
- 确认账号允许从采集节点 IP 登录（`user@'%'` 或 `user@'<collector_ip>'`）。
- 确认账号至少具备 `PROCESS` 与 `REPLICATION CLIENT` 权限，否则采集会立即失败。
- MySQL 8.0 默认使用 `caching_sha2_password`，确认采集端驱动兼容。

### 3. 仅部分指标缺失或权限不足

- InnoDB 指标依赖 `performance_schema` 或 `SHOW ENGINE INNODB STATUS`；账号缺少 `PROCESS` 时该组指标为空。
- 主从指标依赖 `REPLICATION CLIENT` 权限；`SHOW SLAVE STATUS` 返回空时需检查授权。
- `gather_slave_status = true` 而实例并非从库时，相关指标为空属正常现象。
- 临时表、缓冲池等指标依赖 `SHOW GLOBAL STATUS`，需保证监控账号具备相应权限。

### 4. 主从延迟指标异常

- 当前模板默认 `gather_slave_status = true`、`gather_replica_status = false`，如使用 MySQL 8.0.22+ 的 `SHOW REPLICA STATUS`，需在模板中切换到 `gather_replica_status`。
- 单实例（非主从）环境下，`slave_*` 字段为空属预期。

> 注：本插件采用 Telegraf 原生 `inputs.mysql`，无需额外部署 exporter；如需扩展指标，请直接调整模板中的 `fieldinclude` 与 `gather_*` 开关。