# ActiveMQ 监控接入指南

本能力通过 Telegraf `inputs.activemq` 使用页面提供的 URL、用户名和密码访问 ActiveMQ HTTP 管理端点。

## 前置要求

- 目标 ActiveMQ 已启用与 Telegraf `inputs.activemq` 兼容的 HTTP 管理端点。
- 采集节点能够访问所填完整 URL。
- 准备能通过该 HTTP 端点认证并读取监控数据的账号；具体角色名称与权限由目标 ActiveMQ 的实际安全配置决定。
- 当前页面只提供 URL、用户名、密码和间隔，不提供管理路径、队列过滤器或其他插件参数。

## 接入步骤

1. 从实际采集节点验证完整 URL 和监控账号。
2. 填写 URL、用户名、密码和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

下列命令会交互式询问密码，并保留 HTTP 失败状态：

```bash
curl --fail --silent --show-error --location --user monitor "http://activemq.example.com:8161"
```

请求应完成且不能返回认证或访问拒绝。最终是否兼容采集接口，以保存后的 Telegraf 日志和指标为准。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | ActiveMQ HTTP 管理端点的完整基地址。 |
| 用户名 | 是 | 目标端点接受的登录账号。 |
| 密码 | 是 | 对应账号密码。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问该 URL 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `activemq_topics_consumer_count`
- `activemq_topics_dequeue_count`
- `activemq_topics_enqueue_count`
- `activemq_topics_size`

## 常见问题

### 认证或访问被拒绝

- 核对 URL、账号和目标 ActiveMQ 当前实际权限配置。
- 使用交互式密码提示复核，不要把密码写入命令行。

### 自定义管理路径或过滤需求

- 当前页面和模板没有管理路径或队列过滤字段，不能通过页面配置这些能力。
- 超出当前字段范围的目标需先实现对应能力，不能依靠接入文档补充未暴露参数。

### 保存后无数据

- 查看 Telegraf 日志中的实际 HTTP 状态、响应解析或认证错误。
- 浏览器能登录管理页面不一定代表其响应与 `inputs.activemq` 采集接口兼容。
