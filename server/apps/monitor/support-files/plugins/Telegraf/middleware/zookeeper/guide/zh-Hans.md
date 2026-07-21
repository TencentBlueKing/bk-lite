# ZooKeeper 监控接入指南

本插件通过 Telegraf `inputs.zookeeper` 周期性向 ZooKeeper 的客户端端口（默认 `2181`）发送 `mntr` 命令，采集集群节点数、平均延迟、连接数、watch / znode 数量等运行时指标。如果目标 ZooKeeper 已开启 Prometheus Metric Provider（`metricsProvider.httpPort=7000`），建议改用 `inputs.prometheus` 直接抓 `/metrics`。

## 前置要求

- 目标 ZooKeeper 服务已启动，客户端端口默认 `2181`。
- 采集节点到 ZooKeeper 主机网络可达（含安全组 / 防火墙放通）。
- `mntr` 命令需要 ZooKeeper 服务端启用四字命令（默认已启用；如果配置 `4lw.commands.whitelist` 请确认包含 `mntr`）。
- 当前模板支持多个 `servers`（集群场景下采集所有 follower / leader 状态）。

> Telegraf 通过 TCP 向 `2181` 发送 `mntr\n`，解析每行 `zk_xxx value` 输出，得到 `zookeeper` 单表，维度包含 `server`、`port`、`state`，并能区分 leader / follower 的 `followers` / `synced_followers` / `pending_syncs`。

## 推荐账号权限

ZooKeeper 的 `mntr` 命令无需账号即可调用，但通过 ACL 可限制网络层访问。建议：

```properties
# conf/zoo.cfg
4lw.commands.whitelist=mntr,conf,envi,ruok,srvr,stat
# 或只允许 mntr
4lw.commands.whitelist=mntr

# 仅监听内网
clientPortAddress=10.0.0.5
clientPort=2181
```

如启用 SASL / Digest 鉴权，监控账号需具备 `read` 权限（通常仅 ACL 验证，mntr 不需要登录）。

## 接入步骤

1. 在采集节点验证 `mntr` 命令可用：

   ```bash
   echo mntr | nc <host> 2181
   ```

   返回多行 `zk_xxx value` 即视为正常。

2. 在监控接入页填写「服务器地址」（`host:port`，例如 `10.0.0.5:2181`）、超时时间（默认 `10s`）、采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、服务器地址、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

`mntr` 可达性：

```bash
echo mntr | nc <host> 2181
```

正常返回 14-17 行 `zk_xxx value` 文本。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| 服务器地址 | 是 | ZooKeeper 客户端地址，格式 `host:port`，例如 `10.0.0.5:2181` |
| 超时时间 | 是 | 单次 mntr 命令的最大等待秒数，默认 `10` |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由服务器地址自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 ZooKeeper 服务已启动，`nc <host> 2181` 后执行 `mntr` 能看到输出。
- 确认 `4lw.commands.whitelist` 包含 `mntr`；如果使用 ZK 3.5+ 且配置白名单只允许 `stat`、`ruok`，将返回拒绝。
- 等待至少一个采集间隔后再查看；检查节点上 Telegraf / 采集任务是否正常运行。

### 2. 连接超时

- 调整「超时时间」字段到合适值（推荐 `5s~30s`），过短会被集群繁忙时误判失败。
- 防火墙 / 安全组是否放通 `2181` TCP 端口。

### 3. 部分指标缺失

- `followers` / `synced_followers` / `pending_syncs` 仅 leader 节点输出，follower 节点相应字段为 0。
- `zk_ephemerals_count` 仅在节点启用 ephemeral 节点时统计。
- `version` 字段在不同版本中字符串略有差异，属正常现象。
- 如果集群启用了 Prometheus Metric Provider，建议改用 `inputs.prometheus` 抓 `http://<host>:7000/metrics`，指标更丰富。