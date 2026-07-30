# Nginx 监控接入指南

本能力通过 Telegraf `inputs.nginx` 拉取 Nginx `stub_status` 文本。

## 前置要求

- 目标 Nginx 已启用 `ngx_http_stub_status_module` 并暴露状态端点。
- 采集节点能够访问所填完整 URL。
- 当前页面和模板没有用户名或密码字段，因此端点必须允许采集节点在无 Basic Auth 的情况下读取。
- 建议在 Nginx 侧只允许采集节点 IP 访问状态端点。

## 接入步骤

1. 从实际采集节点验证 `stub_status` URL。
2. 填写完整 URL 和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

```bash
curl --fail --silent --show-error "http://nginx.example.com/stub_status"
```

响应应包含 `Active connections`、`Reading`、`Writing` 和 `Waiting`；`--fail` 会保留 `4xx/5xx` 失败状态。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | Nginx `stub_status` 端点的完整 URL。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够无认证访问该 URL 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `nginx_active`
- `nginx_reading`
- `nginx_writing`
- `nginx_requests_rate`

## 常见问题

### 返回 `401` 或要求 Basic Auth

- 当前页面和模板不支持 Basic Auth，不能填写账号密码。
- 在受控网络中允许采集节点匿名读取端点，并用 IP 白名单限制来源。

### 返回 `403`

- 检查 Nginx `allow`/`deny` 规则是否包含实际采集节点来源 IP。
- 从实际采集节点复现，不要只在 Nginx 本机验证。

### 只有基础连接数据

- `stub_status` 只提供有限的连接和请求字段；当前能力仅覆盖模板实际采集范围。
