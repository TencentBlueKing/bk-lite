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

- [ ] 6.1 运行 `lsp_diagnostics` 确认无新增错误
- [ ] 6.2 重启服务器测试 DeepSeek V4 thinking mode 工具调用
- [ ] 6.3 验证 `show_think` 配置从数据库正确传递
