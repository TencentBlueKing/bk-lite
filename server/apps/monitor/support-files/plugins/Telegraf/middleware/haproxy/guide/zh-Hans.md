# HAProxy 监控接入指南

本能力通过 Telegraf `inputs.haproxy` 访问页面填写的 HAProxy HTTP(S) stats 地址。

## 前置要求

- HAProxy 已暴露 HTTP 或 HTTPS stats 页面，采集节点能够访问完整地址。
- 当前页面只允许填写 HTTP(S) stats URL。
- stats 页面未启用认证时，用户名和密码均留空；启用 Basic Auth 时成对填写。
- 当前模板保留 HAProxy 原始字段名。

## 接入步骤

1. 从实际采集节点验证 HTTP(S) stats 地址及可选 Basic Auth。
2. 填写 Stats 地址、可选用户名/密码和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写 Stats 地址、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

无认证 CSV stats 端点：

```bash
curl --fail --silent --show-error "http://haproxy.example.com:8404/haproxy?stats;csv"
```

启用 Basic Auth 时由 `curl` 交互式询问密码：

```bash
curl --fail --silent --show-error --user monitor "https://haproxy.example.com:8404/haproxy?stats;csv"
```

响应应为 HAProxy stats CSV；`--fail` 会保留 `4xx/5xx` 失败状态。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| Stats 地址 | 是 | HAProxy HTTP(S) stats 完整 URL。 |
| 用户名 | 否 | Basic Auth 用户名；未启用认证时留空。 |
| 密码 | 否 | 与用户名成对填写；未启用认证时留空。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够访问 stats URL 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `haproxy_scur`
- `haproxy_rate`
- `haproxy_hrsp_5xx`
- `haproxy_chkfail`

## 常见问题

### 返回 `401`

- 核对用户名和密码是否成对填写，并避免把凭据拼入 URL。
- 使用交互式密码提示复现，避免明文密码和 shell 转义问题。

### Stats 地址格式错误

- 填写包含协议、主机、端口和 stats 路径的完整 HTTP(S) URL。

### 字段名与预期不同

- 当前模板固定保留 HAProxy 原始字段名。
