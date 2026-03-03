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

---

## Proxy - 生成边缘代理节点安装脚本

根据节点信息生成 Proxy 边缘代理节点的安装脚本，包含完整的 Docker Compose 部署包（NATS、Traefik、Collector 等组件）。

**端点**: `POST /infra/proxy`

**请求头**:
```
Content-Type: application/json
```

**请求体**:
```json
{
  "node_id": "proxy-node-01",
  "zone_id": "1",
  "zone_name": "zone-beijing",
  "server_url": "https://bklite.example.com",
  "nats_url": "tls://192.168.1.100:4222",
  "nats_username": "admin",
  "nats_password": "secret123",
  "api_token": "your-api-token",
  "redis_password": "redis-secret",
  "proxy_ip": "192.168.1.50",
  "nats_monitor_username": "monitor_1",
  "nats_monitor_password": "monitor-secret",
  "traefik_web_port": "443",
  "install_path": "/opt/bk-lite/proxy"
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| node_id | string | 是 | - | 节点唯一标识，用于生成证书 CN 和 SAN |
| zone_id | string | 是 | - | Zone ID，用于 JetStream 域名和 NATS 用户配置 |
| zone_name | string | 是 | - | Zone 名称，用于环境配置标识 |
| server_url | string | 是 | - | BKLite 服务端 URL |
| nats_url | string | 是 | - | 上游 NATS Hub 地址，格式：`tls://host:port` 或 `nats://host:port` |
| nats_username | string | 是 | - | NATS 管理员用户名，用于 nats-executor 和 stargazer 服务连接 |
| nats_password | string | 是 | - | NATS 管理员密码 |
| api_token | string | 是 | - | Sidecar 初始化 Token，用于节点认证 |
| redis_password | string | 是 | - | 本地 Redis 密码 |
| proxy_ip | string | 是 | - | Proxy 节点 IP 地址，用于证书 SAN |
| nats_monitor_username | string | 是 | - | NATS 监控用户名，用于本地 NATS 监控认证 |
| nats_monitor_password | string | 是 | - | NATS 监控密码 |
| traefik_web_port | string | 是 | - | Traefik HTTPS 服务端口 |
| install_path | string | 否 | /opt/bk-lite/proxy | Proxy 安装目录 |

**成功响应**:
```json
{
  "status": "success",
  "id": "proxy-node-01",
  "message": "ok",
  "install_script": "#!/bin/bash\nset -euo pipefail\nINSTALL_PATH=\"/opt/bk-lite/proxy\"\n..."
}
```

**错误响应**:
```json
{
  "status": "error",
  "message": "missing node_id"
}
```

---

## Proxy 使用示例

### 生成 Proxy 安装脚本

```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "edge-proxy-01",
    "zone_id": "2",
    "zone_name": "zone-shanghai",
    "server_url": "https://bklite.example.com",
    "nats_url": "tls://192.168.1.100:4222",
    "nats_username": "admin",
    "nats_password": "nats-secret-123",
    "api_token": "init-token-xyz",
    "redis_password": "redis-pwd-456",
    "proxy_ip": "192.168.1.50",
    "nats_monitor_username": "monitor_2",
    "nats_monitor_password": "monitor-secret-789",
    "traefik_web_port": "443"
  }' \
  http://localhost:8080/infra/proxy
```

### 提取安装脚本并保存到文件

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "edge-proxy-01",
    "zone_id": "2",
    "zone_name": "zone-shanghai",
    "server_url": "https://bklite.example.com",
    "nats_url": "tls://192.168.1.100:4222",
    "nats_username": "admin",
    "nats_password": "secret",
    "api_token": "token",
    "redis_password": "redis-pwd",
    "proxy_ip": "192.168.1.50",
    "nats_monitor_username": "monitor_2",
    "nats_monitor_password": "monitor-secret",
    "traefik_web_port": "443"
  }' \
  http://localhost:8080/infra/proxy | jq -r '.install_script' > install-proxy.sh

chmod +x install-proxy.sh
```

### 使用 jq 构建请求（推荐）

```bash
jq -n \
  --arg node_id "proxy-$(hostname)" \
  --arg zone_id "1" \
  --arg zone_name "zone-prod" \
  --arg server_url "https://bklite.internal" \
  --arg nats_url "tls://nats.internal:4222" \
  --arg nats_username "admin" \
  --arg nats_password "${NATS_PASSWORD}" \
  --arg api_token "${API_TOKEN}" \
  --arg redis_password "${REDIS_PASSWORD}" \
  --arg proxy_ip "${PROXY_IP}" \
  --arg nats_monitor_username "${NATS_MONITOR_USERNAME}" \
  --arg nats_monitor_password "${NATS_MONITOR_PASSWORD}" \
  --arg traefik_web_port "${TRAEFIK_WEB_PORT}" \
  '{
    node_id: $node_id,
    zone_id: $zone_id,
    zone_name: $zone_name,
    server_url: $server_url,
    nats_url: $nats_url,
    nats_username: $nats_username,
    nats_password: $nats_password,
    api_token: $api_token,
    redis_password: $redis_password,
    proxy_ip: $proxy_ip,
    nats_monitor_username: $nats_monitor_username,
    nats_monitor_password: $nats_monitor_password,
    traefik_web_port: $traefik_web_port
  }' | curl -X POST -H "Content-Type: application/json" -d @- \
  http://localhost:8080/infra/proxy
```

### 自定义安装路径

```bash
curl -s -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "proxy-01",
    "zone_id": "1",
    "zone_name": "zone-test",
    "server_url": "http://10.0.0.1:8000",
    "nats_url": "tls://10.0.0.1:4222",
    "nats_username": "admin",
    "nats_password": "password",
    "api_token": "token",
    "redis_password": "redis",
    "proxy_ip": "10.0.0.50",
    "nats_monitor_username": "monitor_1",
    "nats_monitor_password": "monitor-pwd",
    "traefik_web_port": "8443",
    "install_path": "/data/bklite/proxy"
  }' \
  http://localhost:8080/infra/proxy | jq -r '.install_script' > install-proxy.sh
```

---

## Proxy 安装说明

### 前置条件

- Linux 系统（支持 Docker 和 Docker Compose）
- Docker 已安装并运行
- Docker Compose 已安装
- 已配置 CA 证书（服务端需要 `/etc/certs/ca.key` 和 `/etc/certs/ca.crt`）

### 安装流程

生成的安装脚本会自动完成：

1. 创建安装目录
2. 解压部署包（包含 docker-compose.yaml、配置文件、证书）
3. 设置证书文件权限（600）
4. 执行 `bootstrap.sh` 启动服务

**执行脚本**:
```bash
# 以 root 身份运行
sudo bash install-proxy.sh
```

### 部署组件

Proxy 部署包包含以下 Docker 服务：

| 组件 | 说明 |
|------|------|
| nats | NATS 消息队列（Leaf Node 模式连接上游 Hub） |
| traefik | 反向代理，提供 HTTPS 入口（端口 443） |
| nats-executor | NATS 命令执行器 |
| stargazer | 云资源采集器 |
| fusion-collector | 数据采集器 |
| redis | 本地 Redis 缓存 |

### 管理服务

```bash
# 进入安装目录
cd /opt/bk-lite/proxy

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 启动服务
docker compose up -d

# 重启服务
docker compose restart
```

### 证书说明

脚本会自动生成以下证书：

- `proxy.key` / `proxy.crt`: Proxy 节点证书（由服务端 CA 签发）
- `ca.crt`: CA 根证书

证书用于：
1. NATS Leaf Node TLS 连接
2. Traefik HTTPS 服务

---

## Proxy 参数校验规则

1. **node_id**: 必填，作为证书 CN，支持 DNS 解析
2. **zone_id**: 必填，用于 JetStream 域和用户隔离
3. **zone_name**: 必填，环境标识
4. **server_url**: 必填，BKLite 服务端地址
5. **nats_url**: 必填，支持 `tls://` 或 `nats://` 协议
6. **nats_username**: 必填，NATS 管理员用户名
7. **nats_password**: 必填，NATS 管理员密码
8. **api_token**: 必填，Sidecar 初始化认证
9. **redis_password**: 必填，本地 Redis 密码
10. **proxy_ip**: 必填，Proxy 节点 IP 地址
11. **nats_monitor_username**: 必填，NATS 监控用户名
12. **nats_monitor_password**: 必填，NATS 监控密码
13. **traefik_web_port**: 必填，Traefik HTTPS 服务端口
14. **install_path**: 可选，默认 `/opt/bk-lite/proxy`