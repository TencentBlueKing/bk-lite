# MongoDB 监控接入指南

本能力通过 Telegraf `inputs.mongodb` 直连一个 MongoDB `host:port`，连接串固定使用 `connect=direct`。

## 前置要求

- 采集节点能够访问目标 MongoDB 主机和端口。
- 未启用认证时用户名和密码均留空；启用认证时两项成对填写。
- 监控账号至少能够读取 `serverStatus` 所需数据；建议使用专用、最小权限账号。
- 当前模板固定直连单个地址，不提供副本集名称、多个服务器、TLS、认证库或自定义连接参数。

## 接入步骤

1. 从实际采集节点验证目标地址和可选认证账号。
2. 填写可选用户名/密码、主机、端口和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写主机、端口、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

无认证实例可直接验证：

```bash
mongosh "mongodb://db.example.com:27017/?connect=direct" --eval "db.serverStatus().ok"
```

启用认证时使用交互式密码提示：

```bash
mongosh "mongodb://db.example.com:27017/?connect=direct" --username monitor --authenticationDatabase admin --password
```

登录后执行 `db.serverStatus().ok`，结果应为 `1`。若目标认证库不是默认值，当前模板无法在页面指定。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 用户名 | 否 | 启用认证时填写，否则留空。 |
| 密码 | 否 | 与用户名成对填写，否则留空。 |
| 主机 | 是 | MongoDB 主机，不包含协议或连接参数。 |
| 端口 | 是 | MongoDB 实际监听端口。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 MongoDB 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `mongodb_uptime_ns`
- `mongodb_connections_current`
- `mongodb_active_reads`
- `mongodb_wtcache_current_bytes`

## 常见问题

### 认证失败

- 确认用户名和密码成对填写，并核对账号实际认证库。
- 当前页面不能设置 `authSource` 或 x.509/TLS 参数；依赖这些参数的目标不能直接接入。

### 副本集地址无法工作

- 模板固定 `connect=direct` 且只接收一个主机和端口，不会在页面配置副本集发现。
- 请选择采集节点可直接访问的具体 MongoDB 成员。

### 只有部分数据

- 登录成功不等于拥有 `serverStatus` 所需权限；结合 Telegraf 日志确认具体命令被拒绝。
- 某些统计字段取决于 MongoDB 版本和使用的存储引擎。
