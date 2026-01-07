# Local Executor

本地命令执行器，支持在不同操作系统上执行命令和脚本。

## 功能特性

- ✅ 跨平台命令执行
- ✅ 支持多种脚本类型（sh, bash, bat, PowerShell 等）
- ✅ 命令执行超时控制
- ✅ 详细的日志记录
- ✅ 错误信息捕获

## 支持的脚本类型

| 脚本类型 | 常量 | 说明 | 适用系统 |
|---------|------|------|---------|
| `sh` | `ShellTypeSh` | Unix Shell（默认） | Linux, macOS |
| `bash` | `ShellTypeBash` | Bash Shell | Linux, macOS |
| `bat` | `ShellTypeBat` | Windows 批处理 | Windows |
| `cmd` | `ShellTypeCmd` | Windows 命令提示符（同 bat） | Windows |
| `powershell` | `ShellTypePowerShell` | Windows PowerShell | Windows |
| `pwsh` | `ShellTypePwsh` | PowerShell Core | 跨平台 |

> **注意：** 不指定 `shell` 参数时，默认使用 `sh`（兼容旧版本行为）

## 使用示例

### 1. Linux/macOS - 使用默认 Shell

```json
{
  "command": "ls -la /tmp",
  "execute_timeout": 30
}
```

### 2. Linux/macOS - 使用 Bash

```json
{
  "command": "ps aux | grep nginx",
  "execute_timeout": 30,
  "shell": "bash"
}
```

### 3. Windows - 使用批处理命令

```json
{
  "command": "dir C:\\Windows\\System32",
  "execute_timeout": 30,
  "shell": "bat"
}
```

### 4. Windows - 执行批处理文件

```json
{
  "command": "C:\\scripts\\deploy.bat prod",
  "execute_timeout": 120,
  "shell": "bat"
}
```

### 5. Windows - 使用 PowerShell

```json
{
  "command": "Get-Process | Where-Object {$_.CPU -gt 100}",
  "execute_timeout": 30,
  "shell": "powershell"
}
```

### 6. Windows - 执行 PowerShell 脚本

```json
{
  "command": "C:\\scripts\\backup.ps1 -Environment prod -Verbose",
  "execute_timeout": 300,
  "shell": "powershell"
}
```

## Go 代码示例

```go
package main

import (
    "fmt"
    "nats-executor/local"
)

func main() {
    // 使用默认 shell (sh)
    req1 := local.ExecuteRequest{
        Command:        "echo 'Hello World'",
        ExecuteTimeout: 30,
    }
    
    // 使用 bash
    req2 := local.ExecuteRequest{
        Command:        "echo 'Hello from Bash'",
        ExecuteTimeout: 30,
        Shell:          local.ShellTypeBash,
    }
    
    // Windows 批处理
    req3 := local.ExecuteRequest{
        Command:        "echo Hello from Windows",
        ExecuteTimeout: 30,
        Shell:          local.ShellTypeBat,
    }
    
    // PowerShell
    req4 := local.ExecuteRequest{
        Command:        "Write-Output 'Hello from PowerShell'",
        ExecuteTimeout: 30,
        Shell:          local.ShellTypePowerShell,
    }
    
    // 执行命令
    response := local.Execute(req1, "instance-001")
    if response.Success {
        fmt.Println("Output:", response.Output)
    } else {
        fmt.Println("Error:", response.Error)
    }
}
```

## 请求参数

### ExecuteRequest

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `command` | string | 是 | 要执行的命令或脚本 |
| `execute_timeout` | int | 是 | 执行超时时间（秒） |
| `shell` | string | 否 | 脚本类型，默认 `sh` |

## 响应参数

### ExecuteResponse

| 字段 | 类型 | 说明 |
|------|------|------|
| `result` | string | 命令输出（stdout + stderr） |
| `instance_id` | string | 实例 ID |
| `success` | boolean | 执行是否成功 |
| `error` | string | 错误信息（失败时） |

## 注意事项

### 命令语法差异

不同脚本类型的命令语法不同，调用方需要根据目标系统编写对应的命令：

**文件列表：**
- Unix/Linux: `ls -la`
- Windows CMD: `dir`
- PowerShell: `Get-ChildItem`

**环境变量：**
- Unix/Linux: `$HOME`, `${PATH}`
- Windows CMD: `%USERPROFILE%`, `%PATH%`
- PowerShell: `$env:USERPROFILE`, `$env:PATH`

**路径分隔符：**
- Unix/Linux: `/home/user/file.txt`
- Windows: `C:\Users\user\file.txt` 或 `C:/Users/user/file.txt`

### PowerShell 特殊字符

在 JSON 中使用 PowerShell 命令时，注意转义特殊字符：

```json
{
  "command": "Get-Process | Where-Object {$_.Name -eq 'nginx'}",
  "shell": "powershell"
}
```

### 超时控制

- 命令执行超过 `execute_timeout` 会被强制终止
- 建议根据命令复杂度合理设置超时时间
- 长时间运行的任务建议使用后台进程方式

### 权限要求

- Unix/Linux: 某些命令需要 sudo 权限
- Windows: 某些操作需要管理员权限
- 确保 executor 进程有足够的权限执行目标命令

## 错误处理

执行失败时，`success` 为 `false`，`error` 字段包含错误信息：

- **超时错误**: `Command timed out after Xs (timeout: Ys)`
- **命令不存在**: `executable file not found`
- **权限错误**: `permission denied`
- **语法错误**: 根据具体 shell 返回不同的错误信息

## 测试

运行单元测试：

```bash
cd agents/nats-executor
go test -v ./local/
```

测试特定脚本类型：

```bash
# 测试默认 shell
go test -v ./local/ -run TestExecuteDefaultShell

# 测试 bash
go test -v ./local/ -run TestExecuteBash

# 测试超时
go test -v ./local/ -run TestExecuteTimeout
```

## NATS 订阅主题

### 本地命令执行
- **主题**: `local.execute.{instance_id}`
- **功能**: 执行本地命令或脚本

### 健康检查
- **主题**: `health.check.{instance_id}`
- **功能**: 检查实例是否在线

### 文件下载
- **主题**: `download.local.{instance_id}`
- **功能**: 从 NATS Object Store 下载文件到本地

### 文件解压
- **主题**: `unzip.local.{instance_id}`
- **功能**: 解压 ZIP 文件到本地目录
