# Metricbeat Docker 模块配置说明

## 概述

Docker 模块用于收集 Docker 容器和镜像的性能指标，包括容器资源使用情况、网络流量、磁盘 I/O 等，是容器环境监控的核心模块。

## 配置参数

### 核心配置（官网推荐默认值）

以下参数已采用官网推荐的最佳实践，无需用户配置：

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `period` | `10s` | 采集周期 |
| `hosts` | `["unix:///var/run/docker.sock"]` | Docker API 连接地址 |
| `labels.dedot` | `false` | 不替换标签中的点号 |
| `cpu.cores` | `true` | 收集每个 CPU 核心的指标 |

### 用户可配置参数

#### 1. 指标集配置

##### `metricsets` (可选)
- **类型**: `list[string]`
- **默认值**: 
  ```yaml
  - container
  - cpu
  - diskio
  - event
  - healthcheck
  - info
  - memory
  - network
  ```
- **说明**: 需要收集的 Docker 指标集列表
- **可选值**: `container`, `cpu`, `diskio`, `event`, `healthcheck`, `info`, `image`, `memory`, `network`, `network_summary`
- **示例**:
```yaml
metricsets:
  - container
  - cpu
  - memory
  - network
```

#### 2. 连接配置

##### `hosts` (可选)
- **类型**: `list[string]`
- **默认值**: `["unix:///var/run/docker.sock"]`
- **说明**: Docker API 连接地址列表
- **示例**:
```yaml
hosts: ["tcp://docker-host:2376"]  # 远程 Docker
```

##### `period` (可选)
- **类型**: `string`
- **默认值**: `"10s"`
- **说明**: 指标采集周期
- **示例**:
```yaml
period: "30s"
```

#### 3. TLS 配置

##### `ssl` (可选)
- **类型**: `object`
- **说明**: TLS 连接配置（用于远程 Docker API）
- **子参数**:
  - `certificate_authority`: CA 证书路径
  - `certificate`: 客户端证书路径
  - `key`: 客户端私钥路径
- **示例**:
```yaml
ssl:
  certificate_authority: "/etc/ssl/ca.pem"
  certificate: "/etc/ssl/cert.pem"
  key: "/etc/ssl/key.pem"
```

#### 4. 高级配置

##### `skip_major` (可选)
- **类型**: `list[int]`
- **默认值**: `[9, 253]`
- **说明**: 跳过特定主设备号的磁盘 I/O 指标（用于软 RAID、设备映射等）
- **示例**:
```yaml
skip_major: [9, 253, 254]
```

##### `podman` (可选)
- **类型**: `boolean`
- **默认值**: `false`
- **说明**: 是否连接到 Podman 而非 Docker
- **示例**:
```yaml
podman: true
```

#### 5. 实例标识

##### `instance_id` (必需)
- **类型**: `string`
- **说明**: 实例唯一标识，用于区分不同的采集实例
- **示例**:
```yaml
instance_id: "docker-host-01"
```

## 配置示例

### 基础 Docker 监控
```yaml
instance_id: "local-docker"
```

### 生产环境监控
```yaml
metricsets:
  - container
  - cpu
  - memory
  - network
  - diskio
  - healthcheck
period: "30s"
instance_id: "prod-docker-cluster"
```

### 远程 Docker 监控
```yaml
hosts: ["tcp://docker-api.example.com:2376"]
ssl:
  certificate_authority: "/etc/ssl/docker-ca.pem"
  certificate: "/etc/ssl/docker-cert.pem"
  key: "/etc/ssl/docker-key.pem"
metricsets:
  - container
  - info
  - event
instance_id: "remote-docker"
```

### Podman 环境
```yaml
hosts: ["unix:///run/podman/podman.sock"]
podman: true
metricsets:
  - container
  - cpu
  - memory
instance_id: "podman-host"
```

## 指标集说明

| 指标集 | 说明 | 适用场景 |
|--------|------|----------|
| `container` | 容器基本信息和状态 | 基础监控 |
| `cpu` | 容器 CPU 使用率 | 性能分析 |
| `memory` | 容器内存使用情况 | 资源监控 |
| `network` | 容器网络流量 | 网络分析 |
| `diskio` | 容器磁盘 I/O | 存储性能 |
| `event` | Docker 事件 | 故障排查 |
| `healthcheck` | 容器健康检查 | 健康监控 |
| `info` | Docker 守护进程信息 | 系统状态 |
| `image` | 镜像信息 | 镜像管理 |

## 注意事项

1. **权限要求**:
   - 需要访问 Docker socket 的权限
   - 通常需要将用户加入 `docker` 组或使用 root 权限

2. **网络配置**:
   - 本地监控使用 Unix socket 性能更好
   - 远程监控需要配置 TLS 确保安全

3. **性能考虑**:
   - 容器数量多时建议增加采集周期
   - 某些指标集（如 `diskio`）会增加 I/O 负载

4. **安全考虑**:
   - 远程连接必须使用 TLS
   - 定期轮换 TLS 证书

5. **Podman 兼容性**:
   - Podman 支持 Docker 兼容 API
   - 某些高级功能可能不完全兼容
