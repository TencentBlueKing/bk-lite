# RabbitMQ 监控接入指南

本能力通过 Telegraf `inputs.rabbitmq` 访问 RabbitMQ Management Plugin HTTP API；管理端口与 AMQP 端口不同。

## 前置要求

- 目标 RabbitMQ 已启用 Management Plugin，并暴露采集节点可访问的 HTTP(S) 管理地址。
- 准备可读取 Management API 的账号；远程采集不要使用默认仅限本机的 `guest` 账号。
- 用户名和密码在当前页面均为必填。
- 带认证的 Management API 应优先使用 HTTPS，并部署证书链受采集节点信任的服务端证书。
- 若目标只能使用 HTTP，仅可部署在隔离且可信的链路中；Basic Auth 凭据只是可逆编码，会在网络中以未加密形式传输。
- 以 Management API 的实际可访问状态作为接入前提。

## 接入步骤

1. 从实际采集节点验证 Management API 地址和监控账号。
2. 填写 URL、用户名、密码和采集间隔（默认 `60` 秒，不要低于 `30` 秒）。URL 填 Management 根地址，例如 `http://127.0.0.1:15672`，不要带 `/api/queues`。
3. 「采集队列」默认关闭，只采集 overview 与 node，不请求 `/api/queues`。
4. 需要队列指标时再打开「采集队列」，并填写必填的队列包含规则（不填不能保存，避免全量拉取 `/api/queues`）；超时默认 `20` 秒。
5. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
6. 保存后等待至少一个采集周期。

## 接入前校验

下列 HTTPS 命令会交互式询问密码，并保留 HTTP 失败状态。交互提示只避免密码进入命令行参数或历史记录，不能保护网络传输；证书链必须受采集节点信任。不要将 `-k` 或 `--insecure` 作为常规方案：

```bash
curl --fail --silent --show-error --user monitor "https://rabbitmq.example.com:15671/api/overview"
```

请求应返回 `200` 和 JSON。使用页面要填写的同一完整基地址验证，不要混用 AMQP 端口。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | RabbitMQ Management HTTP(S) 根地址，例如 `http://127.0.0.1:15672`，不要带 `/api/queues` 等路径。保存时去掉末尾斜杠并折叠重复斜杠。 |
| 用户名 | 是 | 可读取 Management API 的账号。 |
| 密码 | 是 | 对应账号密码。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`，不要低于 `30`。 |
| 采集队列 | 否 | 默认关闭。开启后才会请求 `/api/queues`。关闭是停止 Management 全表拉取压力的唯一办法。 |
| 队列包含 | 开启采集队列时必填 | 开启后必须填包含规则，不填不能保存，避免全量拉取 `/api/queues`。名称过滤仍会先拉全表，只减少入库。 |
| 队列排除 | 否 | Telegraf `queue_name_exclude` glob，可选。 |
| 超时 | 开启采集队列时建议填写 | Telegraf `client_timeout`，默认 `20` 秒，范围 `15–30`。 |
| 节点 | 是 | 能够访问 Management API 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

名称过滤仍会先拉取完整 `/api/queues` 表，只减少入库；include glob 不能减轻 Management 拉取压力。要停止该压力，只能关闭「采集队列」。Telegraf 1.29 没有 vhost 包含/排除字段；队列序列已带 `queue` 与 `vhost` 标签，可在看板按标签过滤。

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `rabbitmq_node_running`
- `rabbitmq_overview_connections`
- `rabbitmq_overview_messages`
- `rabbitmq_node_mem_used`

开启「采集队列」后再确认 `rabbitmq_queue_messages`。

## 常见问题

### 返回 `401` 或 `403`

- 核对账号是否具有 Management API 的监控读取权限。
- `guest` 默认不能远程登录；为采集准备专用账号。

### 端口可达但无数据

- 确认 URL 指向 Management HTTP(S) API，而不是 AMQP 服务端口。
- 查看 Telegraf 日志中的具体 API、HTTP 状态和响应解析错误。

### 队列采集超时或拖慢节点

- 名称过滤仍会拉取完整 `/api/queues` 表；include glob 只减少入库序列，不能减轻 Management 拉取压力。停止该压力的唯一办法是关闭「采集队列」。若请求较慢，可将超时调到 `15–30` 秒，但这不会减少全表拉取。
