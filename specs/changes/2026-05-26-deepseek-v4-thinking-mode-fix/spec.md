# 2026 05 26 Deepseek V4 Thinking Mode Fix

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-26-deepseek-v4-thinking-mode-fix/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

DeepSeek V4 和 Qwen 等模型在启用 thinking mode（深度思考模式）时存在多个兼容性问题，导致工具调用失败：

1. **`show_think` 配置不生效**：数据库中配置的 `show_think` 值无法正确传递到 LLM 调用层
2. **`tool_choice` 不兼容**：thinking mode 仅支持 `tool_choice="auto"` 或 `"none"`，使用 `"any"` 或 `"required"` 会返回 HTTP 400 错误
3. **Windows 编码错误**：日志中的 emoji 字符导致 GBK 编码失败
4. **代码质量问题**：`node.py` 中存在大量重复的内联 import，影响可维护性

## What Changes

- **修复 `show_think` 传递链**：确保从数据库 → API → LLM 调用的完整传递
- **自动转换 `tool_choice`**：检测 thinking mode 并将不兼容的 `tool_choice` 值转换为 `"auto"`
- **安全日志输出**：添加 `_safe_log_preview()` 辅助函数处理特殊字符
- **重构 import 结构**：将所有内联 import 移至文件头部，统一使用标准模块名

## Capabilities

### New Capabilities

（无新增能力，本次为 bug 修复和代码重构）

### Modified Capabilities

（无规格级别的行为变更，仅修复实现层面的问题）

## Impact

### 受影响的代码

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `server/apps/opspilot/viewsets/llm_view.py` | 修复 | 添加 `show_think` 从 `skill_obj` 的 fallback 逻辑 |
| `server/apps/opspilot/utils/agui_chat.py` | 修复 | `params.pop()` → `params.get()` 保留 `show_think` |
| `server/apps/opspilot/utils/sse_chat.py` | 修复 | `params.pop()` → `params.get()` 保留 `show_think` |
| `server/apps/opspilot/metis/llm/chain/node.py` | 修复+重构 | thinking mode 兼容、日志安全、import 整理 |

### 受影响的模型

- DeepSeek V4（`extra_body.thinking.type == "enabled"`）
- Qwen（`extra_body.enable_thinking == True`）
- 其他模型不受影响（无 thinking mode 检测时保持原有行为）

### 向后兼容性

- ✅ 完全向后兼容
- ✅ 非 thinking mode 模型（GPT-4、Claude 等）行为不变
- ✅ 无 API 变更

## Implementation Decisions

## Context

### 背景

OpsPilot 的 LLM 调用链支持多种模型，包括 DeepSeek V4 和 Qwen 等国产模型。这些模型提供了 "thinking mode"（深度思考模式），通过 `extra_body` 参数启用：

- DeepSeek: `extra_body.thinking.type = "enabled"`
- Qwen: `extra_body.enable_thinking = True`

### 当前问题

1. **配置传递断裂**：`show_think` 在 `agui_chat.py` 和 `sse_chat.py` 中被 `pop()` 移除，导致下游无法获取
2. **API 限制**：DeepSeek V4 thinking mode 仅支持 `tool_choice="auto"` 或 `"none"`，其他值返回 400 错误
3. **编码问题**：Windows 默认 GBK 编码无法处理日志中的 emoji 字符
4. **技术债务**：`node.py` 有 14 处内联 import，违反 Python 最佳实践

### 约束

- 必须保持非 thinking mode 模型的行为不变
- 不能引入 breaking changes
- 修复必须对用户透明

## Goals / Non-Goals

**Goals:**

- 修复 `show_think` 配置从数据库到 LLM 调用的完整传递链
- 使 DeepSeek V4 和 Qwen 在 thinking mode 下能正常使用工具调用
- 消除 Windows 环境下的编码错误
- 提升 `node.py` 代码质量和可维护性

**Non-Goals:**

- 不修改 thinking mode 的核心逻辑
- 不添加新的 thinking mode 功能
- 不重构整个 LLM 调用链架构
- 不处理其他模型的兼容性问题（除非顺带解决）

## Decisions

### Decision 1: `show_think` 传递方式

**选择**：使用 `params.get()` 替代 `params.pop()`

**理由**：
- `pop()` 会从字典中移除键，导致下游函数无法访问
- `get()` 保留原值，允许多层函数共享同一配置
- 最小改动，风险最低

**替代方案**：
- 在调用链开始时复制 params → 增加内存开销，改动范围大
- 使用 context 对象传递 → 需要重构整个调用链

### Decision 2: `tool_choice` 兼容性处理

**选择**：在 `bind_tools()` 调用前检测 thinking mode，自动将不兼容的 `tool_choice` 转换为 `"auto"`

**理由**：
- 对调用方透明，无需修改上层代码
- 仅在必要时转换，不影响其他模型
- 记录日志便于调试

**检测逻辑**：
```python
extra_body = getattr(llm, 'extra_body', None) or {}
deepseek_thinking = extra_body.get("thinking", {}).get("type") == "enabled"
qwen_thinking = extra_body.get("enable_thinking") is True
if deepseek_thinking or qwen_thinking:
    if tool_choice in ("any", "required"):
        tool_choice = "auto"
```

**替代方案**：
- 在 LLMClientFactory 中处理 → 需要传递 tool_choice 到工厂，改动范围大
- 抛出异常让用户手动配置 → 用户体验差
- 完全禁用 thinking mode 的工具调用 → 功能损失

### Decision 3: 日志编码安全

**选择**：添加 `_safe_log_preview()` 辅助函数，使用 `encode('ascii', 'replace').decode('ascii')` 处理

**理由**：
- 集中处理，避免分散的 try-except
- 保留日志可读性（用 `?` 替代无法编码的字符）
- 不影响实际数据处理，仅影响日志输出

**替代方案**：
- 设置全局编码为 UTF-8 → 可能影响其他系统组件
- 完全移除 emoji → 降低日志可读性
- 使用 logging 的 encoding 参数 → 需要修改 logger 配置

### Decision 4: Import 重构策略

**选择**：将所有内联 import 移至文件头部，使用标准模块名

**理由**：
- 符合 PEP 8 规范
- 提升代码可读性和 IDE 支持
- 避免重复 import 的性能开销
- 便于依赖分析

**移除的内联 import**：
- `from collections import Counter` (1 处)
- `from langchain_core.messages import ToolMessage` (4 处)
- `from langchain_core.messages import SystemMessage as _SysMsg` (3 处)
- `from langchain_core.callbacks import dispatch_custom_event` (2 处)
- `from apps.opspilot.utils.rollback import ...` (2 处)
- `from apps.opspilot.utils.verification import ...` (1 处)

## Risks / Trade-offs

### Risk 1: `tool_choice` 自动转换可能影响工具调用行为

**风险**：`"auto"` 允许模型选择不调用工具，而 `"any"/"required"` 强制调用

**缓解**：
- 仅在 thinking mode 下转换
- 保留二次重试机制（nudge message）
- 记录详细日志便于排查

### Risk 2: 日志字符替换可能丢失调试信息

**风险**：被替换的字符可能包含有用的调试信息

**缓解**：
- 仅替换无法编码的字符
- 实际数据处理不受影响
- 可通过其他方式（如数据库记录）获取完整信息

### Risk 3: Import 重构可能引入循环依赖

**风险**：将 import 移至文件头部可能暴露循环依赖问题

**缓解**：
- 已验证所有 import 在文件头部正常工作
- LSP 诊断未报告新的 import 错误
- 保留原有的模块结构

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-26
```

## Work Checklist

## 1. 修复 `show_think` 配置传递

- [x] 1.1 在 `llm_view.py` 的 `execute` 方法中添加 `show_think` 从 `skill_obj.show_think` 的 fallback 逻辑
- [x] 1.2 在 `llm_view.py` 的 `execute_agui` 方法中添加相同的 fallback 逻辑
- [x] 1.3 将 `agui_chat.py` 中的 `params.pop("show_think", True)` 改为 `params.get("show_think", True)`
- [x] 1.4 将 `sse_chat.py` 中的 `params.pop("show_think", True)` 改为 `params.get("show_think", True)`

## 2. 修复 DeepSeek V4 Thinking Mode 工具调用兼容性

- [x] 2.1 在 `node.py` 的 `agent_node` 中添加 thinking mode 检测逻辑（检测 `extra_body.thinking.type` 和 `extra_body.enable_thinking`）
- [x] 2.2 在首次 `bind_tools()` 调用前，将不兼容的 `tool_choice` 值（`"any"`, `"required"`）转换为 `"auto"`
- [x] 2.3 在二次重试（choice continuation）的 `bind_tools()` 调用前添加相同的转换逻辑
- [x] 2.4 添加日志记录 thinking mode 下的 `tool_choice` 转换

## 3. 修复 Windows GBK 编码错误

- [x] 3.1 在 `node.py` 中添加 `_safe_log_preview()` 辅助函数
- [x] 3.2 将日志输出中可能包含 emoji 的内容通过 `_safe_log_preview()` 处理

## 4. 重构 `node.py` Import 结构

- [x] 4.1 将 `from collections import Counter` 移至文件头部
- [x] 4.2 移除内联的 `from langchain_core.messages import ToolMessage`（4 处）
- [x] 4.3 移除内联的 `from langchain_core.messages import SystemMessage as _SysMsg`（3 处），改用 `SystemMessage`
- [x] 4.4 移除内联的 `from langchain_core.callbacks import dispatch_custom_event`（2 处）
- [x] 4.5 移除内联的 `from apps.opspilot.utils.rollback import ...`（2 处）
- [x] 4.6 移除内联的 `from apps.opspilot.utils.verification import ...`（1 处）
- [x] 4.7 将 `_json` 和 `_asyncio` 别名改为标准模块名 `json` 和 `asyncio`

## 5. 清理调试代码

- [x] 5.1 移除 `choice_debug.log` 文件写入代码
- [x] 5.2 移除 `show_think resolution` 调试日志

## 6. 验证

- [x] 6.1 运行 `lsp_diagnostics` 确认无新增错误
- [x] 6.2 重启服务器测试 DeepSeek V4 thinking mode 工具调用
- [x] 6.3 验证 `show_think` 配置从数据库正确传递
