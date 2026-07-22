# 2026 05 14 Fix Playbook Zip Extraction Security

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-14-fix-playbook-zip-extraction-security/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

`ansible-executor` 的 `prepare_playbook()` 函数在处理 Playbook ZIP 文件时，第 759 行直接调用 `zf.extractall(workspace)` 而未使用已有的安全函数 `_safe_extract_zip()`。这导致攻击者可以通过上传包含路径遍历条目（如 `../../../etc/cron.d/malicious`）的恶意 ZIP 文件，实现任意文件写入，进而可能导致远程代码执行。

此问题由 GitHub Issue #2804 报告。

## What Changes

- 将 `ansible_runner.py` 第 759 行的 `zf.extractall(workspace)` 替换为 `_safe_extract_zip(zf, workspace)`
- 复用已有的安全解压函数，该函数会检查：
  - 路径遍历攻击（`..` 组件）
  - 绝对路径
  - 符号链接攻击
  - 解压目标是否在 workspace 内

## Capabilities

### New Capabilities

（无新增能力，仅修复安全漏洞）

### Modified Capabilities

（无需修改现有规格，这是实现层面的 bug 修复）

## Impact

- **代码**: `agents/ansible-executor/service/ansible_runner.py` 第 759 行
- **安全**: 修复 Zip Slip 漏洞，防止任意文件写入
- **API**: 无变化
- **依赖**: 无变化
- **测试**: 现有测试 `test_ansible_runner.py` 已覆盖 `_safe_extract_zip` 的安全检查逻辑

## Implementation Decisions

## Context

`ansible-executor` 服务负责执行 Ansible Playbook 任务。用户可以通过上传 ZIP 文件的方式提供 Playbook。当前代码中存在两处 ZIP 解压逻辑：

1. **Line 756-759**: Playbook ZIP 解压 - 直接调用 `extractall()`，**无安全检查**
2. **Line 784-785**: File distribution ZIP 解压 - 使用 `_safe_extract_zip()`，**有安全检查**

代码中已存在完善的安全函数：
- `_safe_workspace_path()` (Line 268-282): 验证路径在 workspace 内
- `_safe_extract_zip()` (Line 285-295): 检查路径遍历、符号链接等攻击

问题在于 Playbook ZIP 解压路径遗漏了安全函数调用。

## Goals / Non-Goals

**Goals:**
- 修复 Playbook ZIP 解压的 Zip Slip 漏洞
- 复用已有的安全函数，保持代码一致性
- 不引入新的依赖或复杂逻辑

**Non-Goals:**
- 不重构整体 ZIP 处理架构
- 不修改 `_safe_extract_zip()` 函数本身
- 不处理 mlops 模块中的类似模式（那些在临时目录中操作，风险较低）

## Decisions

### Decision 1: 复用 `_safe_extract_zip()` 而非新建函数

**选择**: 直接调用已有的 `_safe_extract_zip(zf, workspace)`

**理由**:
- 函数已经过测试验证（`test_ansible_runner.py` 有完整测试用例）
- 保持代码一致性（同一文件中的另一处 ZIP 解压已使用此函数）
- 最小改动原则

**替代方案**:
- 创建新的安全函数 → 不必要，已有函数完全满足需求
- 内联安全检查逻辑 → 代码重复，维护成本高

### Decision 2: 单行修改

**选择**: 仅修改 Line 759，将 `zf.extractall(workspace)` 改为 `_safe_extract_zip(zf, workspace)`

**理由**:
- 最小化变更范围
- 降低引入新 bug 的风险
- 便于代码审查

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 修改后可能影响正常 ZIP 解压 | `_safe_extract_zip()` 已在 file_distribution 路径使用，经过生产验证 |
| 恶意 ZIP 被拒绝时的错误信息不够友好 | 当前 `_safe_extract_zip()` 会抛出 `ValueError`，已有的错误处理机制会捕获并返回给用户 |

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-14
```

## Capability Deltas

### playbook-zip-security

## ADDED Requirements

### Requirement: Playbook ZIP 解压必须使用安全函数

Playbook ZIP 文件解压时，系统 SHALL 使用 `_safe_extract_zip()` 函数进行安全检查，防止路径遍历攻击。

#### Scenario: 正常 ZIP 文件解压成功
- **WHEN** 用户上传包含合法路径的 Playbook ZIP 文件
- **THEN** 系统成功解压文件到 workspace 目录

#### Scenario: 恶意路径遍历 ZIP 被拒绝
- **WHEN** 用户上传包含 `../` 路径遍历条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: 符号链接 ZIP 条目被拒绝
- **WHEN** 用户上传包含符号链接条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

#### Scenario: 绝对路径 ZIP 条目被拒绝
- **WHEN** 用户上传包含绝对路径条目的 ZIP 文件
- **THEN** 系统拒绝解压并抛出 ValueError

## Work Checklist

## 1. 代码修复

- [x] 1.1 修改 `agents/ansible-executor/service/ansible_runner.py` 第 759 行，将 `zf.extractall(workspace)` 替换为 `_safe_extract_zip(zf, workspace)`

## 2. 验证

- [x] 2.1 运行 `cd agents/ansible-executor && make lint` 确保代码风格通过
- [x] 2.2 运行现有测试 `test_ansible_runner.py` 确保安全函数测试通过
- [x] 2.3 手动验证：确认修改后的代码路径与 file_distribution 路径（Line 785）使用相同的安全函数
