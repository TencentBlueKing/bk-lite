# Webhookd Infra API

## 概述

通过 webhookd 渲染 K8s 采集器配置 YAML。

**基础 URL**: `http://your-server:8080/infra`

## API 列表

### Render - 渲染 K8s 配置

根据 NATS 连接信息渲染 K8s 采集器配置 YAML（包含 Collector 和 Secret）。

**端点**: `POST /infra/render`

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
  "cluster_name": "my-cluster",
  "type": "metric",
  "nats_url": "tls://192.168.1.100:4222",
  "nats_username": "admin",
  "nats_password": "secret123",
  "nats_ca": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----"
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cluster_name | string | 是 | 集群名称，用于标识。只允许字母、数字、下划线和连字符 |
| type | string | 是 | 采集器类型，枚举值：`metric`（指标采集）或 `log`（日志采集） |
| nats_url | string | 是 | NATS 服务器地址，格式：`nats://host:port` |
| nats_username | string | 是 | NATS 用户名 |
| nats_password | string | 是 | NATS 密码 |
| nats_ca | string | 是 | NATS CA 证书内容（PEM 格式） |

**成功响应**:
```json
{
  "status": "success",
  "id": "my-cluster",
  "message": "K8s configuration rendered successfully",
  "yaml": "apiVersion: v1\nkind: ConfigMap\n..."
}
```

**错误响应**:
```json
{
  "status": "error",
  "id": "my-cluster",
  "message": "Missing required field: nats_url"
}
```

---

## 使用示例

### 渲染指标采集器配置

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "prod-cluster",
    "type": "metric",
    "nats_url": "nats://192.168.1.100:4222",
    "nats_username": "admin",
    "nats_password": "secret123",
    "nats_ca": "-----BEGIN CERTIFICATE-----\nMIIDXTCCAkWgAwIBAgIJAJC1...\n-----END CERTIFICATE-----"
  }' \
  http://localhost:8080/infra/render
```

### 渲染日志采集器配置

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "prod-cluster",
    "type": "log",
    "nats_url": "nats://192.168.1.100:4222",
    "nats_username": "admin",
    "nats_password": "secret123",
    "nats_ca": "-----BEGIN CERTIFICATE-----\nMIIDXTCCAkWgAwIBAgIJAJC1...\n-----END CERTIFICATE-----"
  }' \
  http://localhost:8080/infra/render
```

### 提取 YAML 内容并保存到文件

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "cluster_name": "prod-cluster",
    "type": "metric",
    "nats_url": "nats://192.168.1.100:4222",
    "nats_username": "admin",
    "nats_password": "secret123",
    "nats_ca": "..."
  }' \
  http://localhost:8080/infra/render | jq -r '.yaml' > k8s-collector.yaml
```

---

## 输出说明

返回的 `yaml` 字段包含完整的 K8s 配置，由两部分组成：

1. **Collector 配置**：根据 `type` 选择 metric 或 log 采集器模板
2. **Secret 配置**：包含 NATS 连接信息（已 Base64 编码）

可直接用于 `kubectl apply -f` 部署。

---

## 错误码

- `exit 0`: 成功
- `exit 1`: 失败（参数缺失、格式错误等）

---

## 注意事项

1. **cluster_name 命名规则**: 只允许字母、数字、下划线和连字符
2. **type 取值**: 必须是 `metric` 或 `log`
3. **nats_ca 格式**: 需要完整的 PEM 格式证书
4. **Content-Type**: 请求必须设置 `Content-Type: application/json`
