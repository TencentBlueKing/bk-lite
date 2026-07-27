# 网站拨测 监控接入指南

通过 Telegraf `inputs.http_response`，从选定节点对目标 HTTP/HTTPS URL 发起拨测，采集可用性、响应时间与状态码等指标。

## 基础配置

- **节点**：选择可访问目标的采集节点。
- **URL**：填写不含 query 的 HTTP/HTTPS 地址；IPv6 需使用方括号，例如 `https://[2001:db8::1]/`。
- **间隔**：采集周期，单位秒。
- **请求方式**：仅支持 GET、HEAD、POST。

## 高级配置

按需展开「高级配置」，未填写的项不会写入 Telegraf 配置，沿用原生默认行为。

### 请求内容

- **请求参数**：URL 字段不可包含 query；参数按填写顺序编码后追加，允许同名参数。
- **请求头**：仅填写非敏感头（如 `Content-Type`）；不要填写 `Authorization`。
- **请求体**：仅 POST 可用；通过 `Content-Type` 声明 JSON、XML 或表单等格式。

### 认证凭据

支持无认证、Basic Auth、Bearer Token。凭据经环境变量注入，不会写入 Telegraf 配置正文。

### 期望响应

可按需设置期望状态码、期望响应内容、请求超时、跟随重定向；留空则保留 Telegraf 默认（请求超时默认 5 秒）。

### 证书校验

HTTPS 场景可开启「跳过证书校验」。
