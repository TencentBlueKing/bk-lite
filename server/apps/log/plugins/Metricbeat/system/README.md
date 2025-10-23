# Metricbeat System 模块配置说明

## 概述

System 模块用于收集系统级别的性能指标，包括 CPU、内存、网络、进程等核心监控数据，是系统监控的基础模块。

## 配置参数

### 核心配置（官网推荐默认值）

以下参数已采用官网推荐的最佳实践，大多数情况下无需用户配置：

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `period` | `10s` | 采集周期 |
| `processes` | `['.*']` | 监控所有进程 |
| `cpu.metrics` | `["percentages", "normalized_percentages"]` | CPU 指标类型 |
| `core.metrics` | `["percentages"]` | CPU 核心指标类型 |

### 用户可配置参数

#### 1. 指标集配置

##### `metricsets` (可选)
- **类型**: `list[string]`
- **默认值**: 
  ```yaml
  - cpu
  - load
  - memory
  - network
  - process
  - process_summary
  - uptime
  - socket_summary
  ```
- **说明**: 需要收集的指标集列表
- **可选值**: `cpu`, `load`, `memory`, `network`, `process`, `process_summary`, `uptime`, `socket_summary`, `core`, `diskio`, `filesystem`, `fsstat`, `raid`, `socket`, `service`
- **示例**:
```yaml
metricsets:
  - cpu
  - memory
  - filesystem
```

#### 2. 采集配置

##### `period` (可选)
- **类型**: `string`
- **默认值**: `"10s"`
- **说明**: 指标采集周期
- **示例**:
```yaml
period: "30s"  # 30秒采集一次
```

##### `processes` (可选)
- **类型**: `list[string]`
- **默认值**: `['.*']`
- **说明**: 进程过滤正则表达式列表
- **示例**:
```yaml
processes: ['nginx.*', 'mysql.*', 'java.*']
```

#### 3. 容器环境配置

##### `hostfs` (可选)
- **类型**: `string`
- **说明**: 容器中监控宿主机时的文件系统挂载点
- **示例**:
```yaml
hostfs: "/hostfs"
```

#### 4. 文件系统配置

##### `filesystem_ignore_types` (可选)
- **类型**: `list[string]`
- **说明**: 忽略的文件系统类型列表
- **示例**:
```yaml
filesystem_ignore_types: ["tmpfs", "devtmpfs", "proc"]
```

#### 5. 进程 Top N 配置

##### `process_include_top_n` (可选)
- **类型**: `object`
- **说明**: 只包含 CPU 或内存使用率前 N 的进程
- **子参数**:
  - `enabled` (boolean): 是否启用，默认 `true`
  - `by_cpu` (int): 按 CPU 使用率排序的进程数量
  - `by_memory` (int): 按内存使用率排序的进程数量
- **示例**:
```yaml
process_include_top_n:
  enabled: true
  by_cpu: 10
  by_memory: 10
```

#### 6. 实例标识

##### `instance_id` (必需)
- **类型**: `string`
- **说明**: 实例唯一标识，用于区分不同的采集实例
- **示例**:
```yaml
instance_id: "web-server-01"
```

## 配置示例

### 基础系统监控
```yaml
instance_id: "basic-system"
```

### 服务器性能监控
```yaml
metricsets:
  - cpu
  - memory
  - filesystem
  - network
  - process
period: "30s"
process_include_top_n:
  enabled: true
  by_cpu: 15
  by_memory: 15
instance_id: "production-server"
```

### 容器环境监控
```yaml
metricsets:
  - cpu
  - memory
  - network
hostfs: "/hostfs"
filesystem_ignore_types: ["tmpfs", "devtmpfs"]
instance_id: "container-host"
```

### 应用服务监控
```yaml
metricsets:
  - cpu
  - memory
  - process
processes: ['nginx.*', 'java.*', 'mysql.*']
period: "15s"
instance_id: "app-services"
```

## 指标集说明

| 指标集 | 说明 | 适用场景 |
|--------|------|----------|
| `cpu` | CPU 使用率 | 基础监控 |
| `memory` | 内存使用情况 | 基础监控 |
| `load` | 系统负载 | 基础监控 |
| `network` | 网络流量统计 | 网络分析 |
| `process` | 进程详细信息 | 应用监控 |
| `process_summary` | 进程汇总统计 | 系统概览 |
| `filesystem` | 磁盘使用情况 | 存储监控 |
| `diskio` | 磁盘 I/O 统计 | 性能分析 |
| `socket` | 网络连接信息 | 网络诊断 |
| `service` | 系统服务状态 | 服务监控 |

## 注意事项

1. **性能考虑**:
   - 采集周期不宜过短，建议不少于 10 秒
   - 启用过多指标集会增加系统负载
   - 使用 `process_include_top_n` 限制进程数量

2. **存储优化**:
   - 不需要的指标集可以禁用以减少存储
   - 合理设置进程过滤规则

3. **容器环境**:
   - 在容器中监控宿主机时必须配置 `hostfs`
   - 需要正确挂载宿主机文件系统

4. **权限要求**:
   - 某些指标需要特定权限（如 root）
   - 确保有权限读取 `/proc` 和 `/sys` 目录
