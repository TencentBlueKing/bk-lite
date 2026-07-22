# RabbitMQ 监控接入指南

本插件通过 Telegraf `inputs.rabbitmq` 周期性拉取 RabbitMQ Management Plugin 的 HTTP API，采集概览、节点、队列、交换机、联邦链路等指标。Management Plugin 默认端口 `15672`，与 AMQP（`5672`）不同，请勿混淆。

## 前置要求

- 目标 RabbitMQ 服务已启动，并启用 Management Plugin：

  ```bash
  rabbitmq-plugins enable rabbitmq_management
  ```

- Management 默认端口 `15672`，账号通常使用 `guest / guest`（仅本机访问）或自定义管理员账号。
- 采集节点到 RabbitMQ 主机网络可达（含安全组 / 防火墙放通）。
- 如启用 LDAP / 内部账号鉴权，准备好只读账号（仅可访问 Management HTTP API）。

> Telegraf 输出 5 张主要指标表：`rabbitmq_overview`、`rabbitmq_node`、`rabbitmq_queue`、`rabbitmq_exchange`、`rabbitmq_federation`，并以 `url` / `node` / `queue` / `vhost` 等为维度。

## 推荐账号权限

Management 账号在 RabbitMQ 中通过内置 tag 控制（`administrator` / `monitoring` / `management` / `policymaker`）。监控账号建议授予 `monitoring` 标签，只读：

```bash
rabbitmqctl add_user monitor monitor-pwd
rabbitmqctl set_user_tags monitor monitoring
rabbitmqctl set_permissions -p / monitor "^$" "^$" "^$"   # monitoring 仅 API 读，不需要 AMQP 权限
```

`monitoring` 标签自带 Management HTTP API 只读访问能力，已满足 Telegraf 采集需求。

## 接入步骤

1. 在采集节点验证 Management API 可达：

   ```bash
   curl -u monitor:monitor-pwd http://<host>:15672/api/overview
   ```

2. 在监控接入页填写 URL（默认 `http://<host>:15672`）、用户名、密码、采集间隔（默认 `60s`）。
3. 在「监控对象」表格中填写节点、URL、实例名称和所属组。
4. 点击「确认」保存配置，等待至少一个采集周期。
5. 到资产或指标页确认实例已上报数据。

## 接入前校验

Management API 可达性：

```bash
curl -u <user>:<pwd> http://<host>:15672/api/nodes
```

返回 200 + JSON 数组即视为正常。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | RabbitMQ Management API 地址，例如 `http://10.0.0.5:15672` |
| 用户名 | 是 | Management 登录账号，建议使用 `monitoring` 标签的只读账号 |
| 密码 | 是 | 对应账号密码 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60` |
| 节点 | 是 | 负责采集的探针节点 |
| 实例名称 | 是 | 平台内展示的实例名，默认由 URL 自动填充 |
| 组 | 否 | 组织分组，便于权限与资产归属 |

## 常见问题

### 1. 保存后长时间无数据

- 确认 Management Plugin 已 `enable`；启用后必须重启 RabbitMQ 节点或等待下一次节点启动。
- 确认端口 `15672` 可达，注意与 AMQP `5672` 区分。
- 在采集节点用 `curl` 直接验证 `/api/overview`。

### 2. 认证失败

- `guest` 账号默认仅允许 `localhost` 登录；远程采集请新建账号。
- 检查账号的 `set_user_tags` 是否包含 `monitoring` 或 `management`；只设 `set_permissions` 不够。
- 密码含特殊字符无需转义，Telegraf 会通过 Authorization 头发认证。

### 3. 部分指标缺失

- `rabbitmq_node` 仅暴露当前查询可达的节点；若集群有节点掉线，需等待节点恢复或检查集群状态。
- 某些字段（`gc_num`、`io_read_bytes` 等）依赖 RabbitMQ 3.6+ 的新统计；老版本会出现字段缺失。
- 通过 `queue_name_include` / `queue_name_exclude` 可按通配符过滤；空数组表示全部（默认值）。