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
