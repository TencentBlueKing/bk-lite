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
