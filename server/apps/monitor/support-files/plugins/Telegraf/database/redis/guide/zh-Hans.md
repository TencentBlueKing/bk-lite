# Redis 监控接入指南

本能力通过 Telegraf `inputs.redis` 使用 TCP 连接指定 Redis 主机和端口，并读取 `INFO` 统计。

## 前置要求

- 采集节点能够访问目标 Redis 主机和实际端口。
- 未启用认证时用户名和密码均留空；只使用 `requirepass` 时可仅填写密码；Redis 6+ ACL 场景填写用户名和密码。
- 监控账号需要执行 `INFO` 的权限。
- 当前模板固定生成 `tcp://` 地址，页面没有 TLS、Unix socket、数据库编号或 Sentinel 字段。

## 接入步骤

1. 从实际采集节点验证目标地址以及 `INFO` 权限。
2. 按目标认证方式填写可选用户名、可选密码、主机、端口和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写主机、端口、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

无认证实例：

```bash
redis-cli -h redis.example.com -p 6379 INFO server
```

需要认证时使用交互式密码提示：

```bash
redis-cli -h redis.example.com -p 6379 --user monitor --askpass INFO server
```

响应应包含 `redis_version` 和 `uptime_in_seconds`，且不能出现 `NOAUTH` 或 `WRONGPASS`。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 否 | Redis 6+ ACL 用户名；不使用 ACL 时留空。 |
| 密码 | 否 | `requirepass` 或 ACL 密码；无认证时留空。 |
| 主机 | 是 | Redis 主机名或 IP，不包含协议。 |
| 端口 | 是 | Redis 实际监听端口。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 Redis 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `redis_uptime`
- `redis_used_memory`
- `redis_instantaneous_ops_per_sec`
- `redis_clients`

## 常见问题

### 返回 `NOAUTH` 或 `WRONGPASS`

- 核对目标使用的是仅密码认证还是 Redis 6+ ACL，并按对应方式填写字段。
- 使用交互式密码提示复核，不要把密码写入命令行。

### 只有部分数据

- 确认账号可以执行完整 `INFO`，而不只是某个受限子命令。
- 某些字段取决于 Redis 版本和当前功能是否启用。

### TLS 或 Sentinel 地址无法接入

- 当前页面和模板只支持一个 TCP 主机与端口，不提供 TLS 或 Sentinel 参数。
