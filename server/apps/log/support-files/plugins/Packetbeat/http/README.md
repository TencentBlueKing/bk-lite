# Packetbeat HTTP 协议配置说明

## 概述

HTTP 协议模块用于监控 HTTP 网络流量，捕获 HTTP 请求和响应数据，支持性能分析和安全审计。

## 配置参数

### 核心配置（官网推荐默认值）

以下参数已采用官网推荐的最佳实践，无需用户配置：

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `max_message_size` | `10485760` (10MB) | 单个消息最大大小 |
| `transaction_timeout` | `10s` | 事务超时时间 |
| `split_cookie` | `true` | 分割 Cookie 信息 |
| `include_request_body` | `false` | 不包含请求体，减少存储 |
| `include_response_body` | `false` | 不包含响应体，减少存储 |

### 用户可配置参数

#### 1. 网络配置

##### `ports` (可选)
- **类型**: `list[int]`
- **默认值**: `[80, 8080, 8000, 5000, 8002]`
- **说明**: 监控的 HTTP 端口列表
- **示例**:
```yaml
ports: [80, 443, 8080, 9000]
```

##### `real_ip_header` (可选)
- **类型**: `string`
- **默认值**: `"X-Forwarded-For"`
- **说明**: 获取真实客户端 IP 的 HTTP 头（适用于代理环境）
- **示例**:
```yaml
real_ip_header: "X-Real-IP"
```

#### 2. 安全配置

##### `hide_keywords` (可选)
- **类型**: `list[string]`
- **默认值**: `["pass", "password", "passwd", "token", "auth", "secret"]`
- **说明**: 隐藏的敏感关键词列表，避免敏感信息泄露
- **示例**:
```yaml
hide_keywords: ["password", "token", "apikey", "secret"]
```

#### 3. HTTP 头信息配置

##### `send_headers` (可选)
- **类型**: `list[string]`
- **默认值**: `["User-Agent", "Content-Type", "Authorization"]`
- **说明**: 发送的 HTTP 头信息列表
- **示例**:
```yaml
send_headers: ["User-Agent", "Content-Type", "X-Custom-Header"]
```

##### `send_all_headers` (可选)
- **类型**: `boolean`
- **默认值**: `false`
- **说明**: 是否发送所有 HTTP 头信息
- **注意**: 启用后会忽略 `send_headers` 配置

#### 4. 内容过滤配置

##### `include_body_for` (可选)
- **类型**: `list[string]`
- **默认值**: `["application/json", "application/xml", "text/plain"]`
- **说明**: 包含请求/响应体的内容类型列表
- **示例**:
```yaml
include_body_for: ["application/json", "text/html"]
```

#### 5. 实例标识

##### `instance_id` (必需)
- **类型**: `string`
- **说明**: 实例唯一标识，用于区分不同的采集实例
- **示例**:
```yaml
instance_id: "web-server-01"
```

## 配置示例

### 基础配置
```yaml
ports: [80, 8080]
instance_id: "web-frontend"
```

### 高级配置
```yaml
ports: [80, 443, 8080, 9000]
hide_keywords: ["password", "token", "apikey"]
send_headers: ["User-Agent", "Content-Type", "X-Request-ID"]
real_ip_header: "X-Real-IP"
include_body_for: ["application/json"]
instance_id: "api-gateway"
```

## 注意事项

1. **性能考虑**: 监控过多端口可能影响性能，建议只监控必要的端口
2. **安全考虑**: 确保 `hide_keywords` 包含所有敏感关键词
3. **存储考虑**: 谨慎启用 `include_request_body` 和 `include_response_body`，会大幅增加存储空间
4. **代理环境**: 在负载均衡器或代理后部署时，务必配置正确的 `real_ip_header`
