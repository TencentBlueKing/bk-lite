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
