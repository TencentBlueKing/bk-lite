# Auditbeat Auditd 模块配置说明

## 概述

Auditd 模块用于收集 Linux 系统的审计日志，监控系统安全事件、文件访问、权限变更等关键活动。

## 配置参数

### 基础配置

所有核心配置已采用官网推荐值，无需用户配置：

| 参数 | 默认值 | 说明 |
|------|-------|------|
| `resolve_ids` | `true` | 解析用户/组ID为名称 |
| `failure_mode` | `silent` | 失败模式，避免系统阻塞 |
| `backlog_limit` | `8192` | 审计事件队列大小 |
| `rate_limit` | `0` | 速率限制（0为无限制） |
| `include_raw_message` | `false` | 不包含原始消息，减少存储 |
| `include_warnings` | `false` | 不包含警告信息 |
| `backpressure_strategy` | `auto` | 自动背压策略 |
| `immutable` | `false` | 非不可变模式，避免系统锁定 |

### 用户可配置参数

#### 1. 审计规则配置

##### `audit_rules` (可选)
- **类型**: `list[string]`
- **说明**: 用户自定义审计规则列表
- **示例**:
```yaml
audit_rules:
  - "-w /etc/passwd -p wa -k passwd_changes"
  - "-w /var/log -p wa -k log_access"
```

##### `rule_categories` (可选)
- **类型**: `list[string]`
- **说明**: 预设规则类别，简化配置
- **可选值**:
  - `security`: 安全监控（身份管理 + 权限提升）
  - `system`: 系统监控（关键文件变更）
  - `network`: 网络监控（连接活动）

**示例**:
```yaml
rule_categories:
  - "security"
  - "system"
```

#### 2. 元数据配置

##### `instance_id` (可选)
- **类型**: `string`
- **默认值**: `"default"`
- **说明**: 实例标识符，用于区分不同部署

## 预设规则说明

### Security 类别
监控身份管理和权限提升相关的安全事件：
- `/etc/passwd` - 用户账户变更
- `/etc/shadow` - 密码文件变更  
- `/etc/sudoers` - sudo权限变更
- `/usr/bin/sudo` - sudo命令执行
- `/usr/bin/su` - su命令执行

### System 类别
监控关键系统文件变更：
- `/bin/` - 系统二进制文件
- `/sbin/` - 系统管理工具
- `/boot/` - 启动相关文件

### Network 类别
监控网络连接活动：
- `socket` 系统调用（64位和32位架构）

## 使用示例

### 零配置启用（推荐）
```yaml
auditd: {}
```

### 启用安全监控
```yaml
auditd:
  rule_categories:
    - "security"
```

### 自定义规则
```yaml
auditd:
  audit_rules:
    - "-w /home -p wa -k home_access"
    - "-a always,exit -F arch=b64 -S open -k file_open"
```

### 混合配置
```yaml
auditd:
  rule_categories:
    - "security"
    - "system"
  instance_id: "prod-web-01"
```

## 注意事项

1. **性能影响**: 审计规则过多可能影响系统性能，建议按需配置
2. **权限要求**: 需要 root 权限运行
3. **兼容性**: 仅支持 Linux 系统
4. **规则优先级**: `audit_rules` 和 `rule_categories` 同时存在时，`rule_categories` 会覆盖 `audit_rules`

## 常见问题

**Q: 如何查看当前的审计规则？**
A: 使用命令 `auditctl -l` 查看当前加载的审计规则

**Q: 审计日志在哪里？**
A: 系统审计日志通常在 `/var/log/audit/audit.log`，Auditbeat 会实时收集并转发

**Q: 如何临时禁用某个模块？**
A: 在配置中添加 `enabled: false`
