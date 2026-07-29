# 网站拨测监控接入指南

本插件使用 Telegraf `inputs.http_response`，从选定节点对 HTTP/HTTPS URL 发起 GET、HEAD 或 POST 拨测。

## 前置要求

- 选定节点能够解析目标域名并访问目标 URL；IPv6 地址必须放在方括号中。
- 目标提供适合拨测的只读接口。即使选择 POST，也应使用不会修改业务资源的探活请求。
- 如需 Basic Auth 或 Bearer Token，只在页面专用凭据字段中填写；不要把凭据放进 URL 或普通请求头。
- HTTPS 生产拨测应使用有效证书。仅在已知自签或证书链问题的临时场景开启跳过校验。

## 接入步骤

1. 从计划使用的节点按“接入前校验”验证目标。
2. 填写 URL、采集间隔和请求方式；URL 本身不带 query，参数填写在“请求参数”中。
3. 按需配置 POST 请求体、请求头、认证、期望状态码、期望响应正则、超时和重定向策略。
4. 在监控对象表格中选择节点，填写 URL、实例名称和可选分组。
5. 保存并等待至少一个采集周期。默认采集间隔为 `60` 秒。

## 接入前校验

基础 HTTP 校验：

```bash
PROBE_URL=https://example.com/
curl --fail-with-body --silent --show-error --location \
  --request GET "$PROBE_URL" --output /tmp/website-probe-response.txt
```

如配置“期望响应内容”，可用兼容的扩展正则子集预先检查响应正文：

```bash
grep -E -q 'service[[:space:]]+ready' /tmp/website-probe-response.txt
```

两个命令都应以退出码 `0` 结束。若期望非 2xx 状态，应使用能显示并校验实际状态码的受控测试工具，不要用忽略 HTTP 失败状态的命令当作成功证据。

## 页面字段说明

| 页面字段 | 是否必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| URL | 是 | 无 | 不含 query 的 HTTP/HTTPS 地址；IPv6 示例：`https://[2001:db8::1]/`。编辑时不可修改基础 URL。 |
| 间隔 | 是 | `60` 秒 | 采集周期，最小 `1` 秒；过短会高频访问目标。 |
| 跳过证书校验 | 否 | 关闭 | 不校验 HTTPS 服务端证书，生产环境应保持关闭。 |
| 请求方式 | 是 | `GET` | 支持 `GET`、`HEAD`、`POST`。只有 POST 显示请求体字段。 |
| 请求体 | 否 | 无 | POST 原始正文；通过 `Content-Type` 请求头声明 JSON、XML 或表单格式。 |
| 请求参数 | 否 | 无 | 按填写顺序 URL 编码后附加到 URL，允许同名参数，空行忽略。 |
| 请求头 | 否 | 无 | 非敏感请求头。认证请使用专用认证字段，不要手写 `Authorization`。 |
| 认证方式 | 是 | 无认证 | 支持无认证、Basic Auth、Bearer Token。 |
| 用户名 | 否 | 无 | Basic Auth 用户名，选择 Basic Auth 时填写。 |
| 密码 | 否 | 无 | Basic Auth 密码，经环境变量注入。 |
| Bearer Token | 否 | 无 | 只填写 token 值，不加 `Bearer` 前缀；经环境变量注入。 |
| 期望状态码 | 否 | 无 | `100`–`599`；留空时模板不设置状态码匹配。 |
| 期望响应内容 | 否 | 无 | 对响应正文执行的正则表达式；留空时不做正文匹配。 |
| 请求超时 | 否 | Telegraf 默认 `5` 秒 | 可填 `1`–`600` 秒；超时记为拨测失败。 |
| 跟随重定向 | 否 | Telegraf 默认行为 | 显式开启时检查最终页面；关闭时以首跳响应判断。 |
| 节点 | 是 | 无 | 执行拨测的采集节点。 |
| URL（监控对象） | 是 | 无 | 实例的 HTTP/HTTPS 地址；IPv6 必须使用方括号。 |
| 实例名称 | 是 | 无 | 平台中的展示名称。 |
| 组 | 否 | 无 | 实例所属分组。 |

## 接入后验证

等待至少一个采集周期，在平台确认目标实例出现，并检查以下已注册指标：

- `http_response_result_code`：应为成功枚举值 `0`。
- `http_response_response_time`：应持续上报响应时间。
- `http_response_http_response_code`：应与目标实际返回码一致。
- `http_response_content_length`：在有响应正文时用于核对响应大小。

## 常见问题

### 期望响应内容总是不匹配

该字段由 Telegraf 按正则表达式匹配，不是普通包含字符串。可先用兼容的 `grep -E -q` 表达式检查保存的响应正文，并核对转义、大小写和换行；最终以实际拨测结果为准。

### Basic Auth 或 Bearer 认证失败

确认认证方式与凭据字段匹配。Bearer Token 字段不加 `Bearer` 前缀；不要同时手写 `Authorization` 请求头。

### 重定向后状态码不符合预期

开启跟随重定向时校验最终响应；关闭时校验首跳响应。根据要监控的契约选择策略。

### HTTPS 证书失败

修复证书链、有效期或主机名。跳过校验只用于受控临时场景。
