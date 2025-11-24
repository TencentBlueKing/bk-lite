# Auditbeat File Integrity 模块配置说明

## 概述

File Integrity 模块用于监控文件系统完整性，检测文件的创建、修改、删除等操作，是安全审计的重要组件。

## 配置参数

### 核心配置（官网推荐默认值）

以下参数已采用官网推荐的最佳实践，无需用户配置：

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `recursive` | `false` | 非递归监控，避免性能问题 |
| `scan_at_start` | `true` | 启动时执行初始扫描 |
| `scan_rate_per_sec` | `50 MiB` | 每秒扫描速率限制 |
| `max_file_size` | `100 MiB` | 最大文件大小限制 |
| `hash_types` | `["sha1"]` | 哈希算法类型 |

### 用户可配置参数

#### 1. 监控路径配置

##### `paths` (可选)
- **类型**: `list[string]`
- **默认值**: `["/bin", "/usr/bin", "/sbin", "/usr/sbin", "/etc"]`
- **说明**: 需要监控的目录路径列表
- **示例**:
```yaml
paths:
  - "/opt/app/config"
  - "/var/www/html"
  - "/home/user/important"
```

#### 2. 文件过滤配置

##### `exclude_files` (可选)
- **类型**: `list[string]`
- **默认值**: 
  ```yaml
  - '(?i)\.sw[nop]$'  # vim swap files
  - '~$'              # backup files  
  - '/\.git($|/)'     # git directories
  ```
- **说明**: 排除文件的正则表达式列表
- **示例**:
```yaml
exclude_files:
  - '\.log$'          # 日志文件
  - '\.tmp$'          # 临时文件
  - '/cache/'         # 缓存目录
```

##### `include_files` (可选)
- **类型**: `list[string]`
- **默认值**: `[]`
- **说明**: 仅包含匹配的文件正则表达式列表（为空表示包含所有）
- **示例**:
```yaml
include_files:
  - '\.conf$'         # 仅监控配置文件
  - '\.yaml$'         # YAML 文件
```

#### 3. 实例标识

##### `instance_id` (必需)
- **类型**: `string`
- **说明**: 实例唯一标识，用于区分不同的采集实例
- **示例**:
```yaml
instance_id: "web-server-config"
```

## 配置示例

### 基础配置
```yaml
instance_id: "system-integrity"
```

### 应用配置监控
```yaml
paths:
  - "/opt/myapp/config"
  - "/etc/nginx"
  - "/etc/ssl"
exclude_files:
  - '\.bak$'
  - '\.log$'
instance_id: "app-config-monitor"
```

### 严格安全监控
```yaml
paths:
  - "/etc/passwd"
  - "/etc/shadow"
  - "/etc/sudoers"
  - "/root/.ssh"
include_files:
  - 'passwd|shadow|sudoers|authorized_keys'
instance_id: "security-critical"
```

## 注意事项

1. **性能影响**: 监控大目录会影响系统性能，建议：
   - 使用 `recursive: false` 避免深度递归
   - 合理设置 `exclude_files` 排除不必要的文件
   - 限制监控路径数量

2. **存储考虑**: 
   - 文件变更频繁的目录会产生大量事件
   - 建议排除日志、缓存等频繁变更的目录

3. **权限要求**: 
   - 需要足够权限读取监控目录
   - 某些系统目录可能需要 root 权限

4. **最佳实践**:
   - 重点监控配置文件、可执行文件等关键资源
   - 排除临时文件、备份文件等噪音
   - 根据安全需求调整监控范围
