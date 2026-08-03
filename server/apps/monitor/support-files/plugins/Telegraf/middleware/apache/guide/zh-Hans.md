# Apache 监控接入指南

本能力通过 Telegraf `inputs.apache` 拉取 Apache HTTPD `mod_status` 的可机读输出。

## 前置要求

- 目标 Apache 已加载 `mod_status`，并暴露带 `?auto` 的状态端点。
- 采集节点能够访问该完整 URL。
- 当前页面和模板没有用户名或密码字段，因此状态端点必须允许采集节点在无 Basic Auth 的情况下读取。
- 建议在 Apache 侧按采集节点 IP 限制访问范围；是否启用 `ExtendedStatus On` 决定可获得的统计丰富度。

## 接入步骤

1. 从实际采集节点验证带 `?auto` 的状态 URL。
2. 填写完整 URL 和采集间隔（默认 `60` 秒）。
3. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
4. 保存后等待至少一个采集周期。

## 接入前校验

```bash
curl --fail --silent --show-error "http://apache.example.com/server-status?auto"
```

响应应为 `Key: Value` 形式的文本，并包含 `Total Accesses`。`--fail` 会保留 `4xx/5xx` 失败状态；返回 HTML 通常表示缺少 `?auto`。

## 页面字段说明

| 页面字段 | 是否必填 | 说明 |
| --- | --- | --- |
| URL | 是 | `mod_status` 可机读端点的完整 URL，需包含 `?auto`。 |
| 间隔 | 是 | 采集周期，单位秒，默认 `60`。 |
| 节点 | 是 | 能够无认证访问该 URL 的采集节点。 |
| 实例名称 | 是 | 平台内展示的实例名称。 |
| 组 | 否 | 实例所属分组。 |

## 接入后验证

保存并等待一个采集周期后，在平台确认以下指标可查询：

- `apache_ServerUptimeSeconds`
- `apache_TotalAccesses`
- `apache_BusyWorkers`
- `apache_IdleWorkers`

## 常见问题

### 返回 `401` 或要求 Basic Auth

- 当前页面和模板不支持 Basic Auth，不能填写账号密码。
- 在受控网络中允许采集节点匿名读取该状态端点，并用 IP 白名单限制来源。

### 返回 HTML 或无法解析

- 确认 URL 包含 `?auto`，并检查反向代理是否保留查询串。
- 从实际采集节点复现，不要只在 Apache 本机验证。

### 只有部分数据

- 检查 `ExtendedStatus` 的实际配置以及 `mod_status` 返回体中是否存在相应字段。
