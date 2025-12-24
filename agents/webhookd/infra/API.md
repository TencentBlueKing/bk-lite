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

---

## Sidecar - 生成采集器 Sidecar 安装脚本

根据节点信息生成 Collector Sidecar 的安装脚本（支持 Windows 和 Linux）。

**端点**: `POST /infra/sidecar`

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
  "os": "windows",
  "api_token": "your-api-token",
  "server_url": "http://10.10.10.10:20005/node_mgmt/open_api/node",
  "node_id": "192.168.1.100",
  "zone_id": "1",
  "group_id": "1",
  "file_url": "http://download.example.com/collector-windows.zip"
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| os | string | 是 | - | 操作系统类型，枚举值：`windows` 或 `linux` |
| api_token | string | 是 | - | Sidecar 用于获取配置的认证 Token |
| server_url | string | 是 | - | BKLite 访问端点 URL，必须以 `http://` 或 `https://` 开头 |
| node_id | string | 是 | - | 节点 ID（通常是机器 IP 或主机名） |
| zone_id | string | 否 | "1" | Zone ID，必须是正整数 |
| group_id | string | 否 | "1" | Group ID，必须是正整数 |
| file_url | string | 否 | "" | 采集器安装包下载地址（zip 文件），留空表示使用已解压的安装包 |

**成功响应**:
```json
{
  "status": "success",
  "id": "192.168.1.100",
  "message": "Installation script generated successfully",
  "install_script": "#Requires -RunAsAdministrator\n<#\n.SYNOPSIS\n..."
}
```

**错误响应**:
```json
{
  "status": "error",
  "id": "192.168.1.100",
  "message": "Missing required parameter: api_token"
}
```

---

## Sidecar 使用示例

### 生成 Windows 安装脚本

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "os": "windows",
    "api_token": "abc123def456",
    "server_url": "http://192.168.1.10:20005/node_mgmt/open_api/node",
    "node_id": "WIN-SERVER-01",
    "zone_id": "1",
    "group_id": "1",
    "file_url": "http://cdn.example.com/collector-windows.zip"
  }' \
  http://localhost:8080/infra/sidecar
```

### 生成 Linux 安装脚本

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "os": "linux",
    "api_token": "prod-token-xyz",
    "server_url": "https://bklite.example.com/node_mgmt/open_api/node",
    "node_id": "node-001",
    "zone_id": "2",
    "group_id": "5"
  }' \
  http://localhost:8080/infra/sidecar
```

### 提取安装脚本并保存到文件

**Windows PowerShell 脚本**:
```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "os": "windows",
    "api_token": "token",
    "server_url": "http://server:20005/api/node",
    "node_id": "node-01",
    "file_url": "http://cdn.example.com/collector.zip"
  }' \
  http://localhost:8080/infra/sidecar | jq -r '.install_script' > install-sidecar.ps1
```

**Linux Shell 脚本**:
```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "os": "linux",
    "api_token": "token",
    "server_url": "http://server:20005/api/node",
    "node_id": "node-01"
  }' \
  http://localhost:8080/infra/sidecar | jq -r '.install_script' > install-sidecar.sh

chmod +x install-sidecar.sh
```

### 使用变量构建请求

```bash
# 使用 jq 构建 JSON（推荐，更安全）
jq -n \
  --arg os "windows" \
  --arg api_token "secure-token-123" \
  --arg server_url "https://bklite.internal/api/node" \
  --arg node_id "$(hostname)" \
  --arg zone_id "1" \
  --arg group_id "1" \
  '{
    os: $os,
    api_token: $api_token,
    server_url: $server_url,
    node_id: $node_id,
    zone_id: $zone_id,
    group_id: $group_id
  }' | curl -X POST -H "Content-Type: application/json" -d @- \
  http://localhost:8080/infra/sidecar
```

---

## Sidecar 参数校验规则

1. **os**: 必填，只能是 `windows` 或 `linux`
2. **api_token**: 必填，用于 Sidecar 认证
3. **server_url**: 必填，必须以 `http://` 或 `https://` 开头
4. **node_id**: 必填，节点唯一标识
5. **zone_id**: 可选，默认为 "1"，必须是正整数
6. **group_id**: 可选，默认为 "1"，必须是正整数
7. **file_url**: 可选，如果提供必须以 `http://` 或 `https://` 开头

---

## Sidecar 安装说明

### Windows 安装流程

生成的 PowerShell 脚本会自动完成：

1. 下载采集器安装包（如果提供了 `file_url`）
2. 解压到安装目录（默认：`C:\fusion-collector\`）
3. 生成 `sidecar.yml` 配置文件
4. 注册为 Windows 服务（服务名：`sidecar`）
5. 启动服务

**执行脚本**:
```powershell
# 以管理员身份运行
.\install-sidecar.ps1
```

**管理服务**:
```powershell
# 查看服务状态
Get-Service -Name sidecar

# 停止服务
Stop-Service -Name sidecar

# 启动服务
Start-Service -Name sidecar

# 查看日志
Get-Content C:\fusion-collector\logs\sidecar.log -Tail 50
```

### Linux 安装流程

生成的 Shell 脚本会自动完成：

1. 下载采集器安装包（如果提供了 `file_url`）
2. 解压到安装目录（默认：`/opt/fusion-collector/`）
3. 生成 `sidecar.yml` 配置文件
4. 注册为系统服务（systemd）
5. 启动服务

**执行脚本**:
```bash
# 以 root 身份运行
sudo bash install-sidecar.sh
```

**管理服务**:
```bash
# 查看服务状态
systemctl status sidecar

# 停止服务
systemctl stop sidecar

# 启动服务
systemctl start sidecar

# 查看日志
tail -f /opt/fusion-collector/logs/sidecar.log
```