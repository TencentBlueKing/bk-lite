# Consul 监控接入指南

本能力通过 Telegraf `inputs.consul` 访问 Consul HTTP API，当前指标范围是健康检查状态。

## 前置要求

- 采集节点能够访问 Consul HTTP API 的完整基地址。
- 目标已注册需要观察的健康检查。
- 当前页面和模板只有 URL 与间隔字段，不会发送认证凭据，也没有其他插件选项。
- 因此 API 必须允许采集节点直接读取健康检查；要求认证的目标无法用当前配置直接接入。

## 接入步骤

1. 从实际采集节点验证 Consul 基地址和健康检查接口可直接读取。
2. 填写完整 URL 和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

```bash
curl --fail --silent --show-error "http://consul.example.com:8500/v1/agent/checks"
```

请求应返回 `200` 和 JSON；`--fail` 会保留 `4xx/5xx` 失败状态。空对象表示当前 Agent 没有已注册检查，不代表采集器故障。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | Consul HTTP API 完整基地址，例如 `http://consul.example.com:8500`。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够直接访问 API 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `consul_health_checks_passing`
- `consul_health_checks_critical`
- `consul_health_checks_warning`
- `consul_health_checks_status`

## 常见问题

### 返回 `403` 或要求认证

- 当前页面和模板不能配置或发送认证凭据。
- 不要把敏感凭据拼进 URL；要求认证的目标需等能力实现对应安全字段后再接入。

### 没有健康检查数据

- 确认目标 Agent 实际注册了健康检查，并用接入前命令查看返回体。
- 当前能力只覆盖健康检查状态，不承诺 Consul telemetry 或运行时指标。

### URL 可达但采集失败

- 核对 URL 是 HTTP API 基地址，不要填写具体健康检查路径。
- 查看 Telegraf 日志中的实际 HTTP 状态和解析错误。
