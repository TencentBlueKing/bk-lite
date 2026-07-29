# RabbitMQ 监控接入指南

本能力通过 Telegraf `inputs.rabbitmq` 访问 RabbitMQ Management Plugin HTTP API；管理端口与 AMQP 端口不同。

## 前置要求

- 目标 RabbitMQ 已启用 Management Plugin，并暴露采集节点可访问的 HTTP(S) 管理地址。
- 准备可读取 Management API 的账号；远程采集不要使用默认仅限本机的 `guest` 账号。
- 用户名和密码在当前页面均为必填。
- 带认证的 Management API 应优先使用 HTTPS，并部署证书链受采集节点信任的服务端证书。
- 若目标只能使用 HTTP，仅可部署在隔离且可信的链路中；Basic Auth 凭据只是可逆编码，会在网络中以未加密形式传输。
- 当前页面和模板没有队列包含/排除过滤字段，也不提供 Management Plugin 启停操作。
- 以 Management API 的实际可访问状态作为接入前提。

## 接入步骤

1. 从实际采集节点验证 Management API 地址和监控账号。
2. 填写 URL、用户名、密码和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

下列 HTTPS 命令会交互式询问密码，并保留 HTTP 失败状态。交互提示只避免密码进入命令行参数或历史记录，不能保护网络传输；证书链必须受采集节点信任。不要将 `-k` 或 `--insecure` 作为常规方案：

```bash
curl --fail --silent --show-error --user monitor "https://rabbitmq.example.com:15671/api/overview"
```

请求应返回 `200` 和 JSON。使用页面要填写的同一完整基地址验证，不要混用 AMQP 端口。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | RabbitMQ Management HTTP(S) API 基地址。 |
| 用户名 | 是 | 可读取 Management API 的账号。 |
| 密码 | 是 | 对应账号密码。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 Management API 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `rabbitmq_node_running`
- `rabbitmq_overview_connections`
- `rabbitmq_overview_messages`
- `rabbitmq_node_mem_used`

## 常见问题

### 返回 `401` 或 `403`

- 核对账号是否具有 Management API 的监控读取权限。
- `guest` 默认不能远程登录；为采集准备专用账号。

### 端口可达但无数据

- 确认 URL 指向 Management HTTP(S) API，而不是 AMQP 服务端口。
- 查看 Telegraf 日志中的具体 API、HTTP 状态和响应解析错误。

### 需要过滤队列

- 当前 UI 和模板没有队列过滤字段；文档不承诺或要求配置该能力。
