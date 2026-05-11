## 1. 修改 ChatService.invoke_chat 返回结构

- [x] 1.1 修改 `server/apps/opspilot/services/chat_service.py` 的 `invoke_chat` 方法，在 `except Exception` 分支返回完整错误结构：`{"message": ..., "success": False, "error": str(e), "error_type": type(e).__name__, "total_tokens": 0, "prompt_tokens": 0, "completion_tokens": 0, "browser_steps": []}`
- [x] 1.2 在成功路径的返回结构中添加 `"success": True` 字段（可选，用于显式标记）

## 2. 修改 AgentNode 添加错误检查

- [x] 2.1 修改 `server/apps/opspilot/utils/chat_flow_utils/nodes/agent/agent.py` 的 `execute` 方法，检查 `data.get("success")` 是否为 `False`
- [x] 2.2 失败时返回 `{"success": False, "error": data.get("error"), output_key: data["message"]}`

## 3. 修改 IntentClassifierNode 移除静默回退

- [x] 3.1 修改 `server/apps/opspilot/utils/chat_flow_utils/nodes/intent/intent_classifier.py` 的 `execute` 方法，检查 `result.get("success")` 是否为 `False`
- [x] 3.2 当 `invoke_chat` 失败时，返回 `{"success": False, "intent_result": "error", "error": result.get("error")}`
- [x] 3.3 当意图不在配置列表中时，返回 `{"success": False, "intent_result": "error", "error": f"意图 '{intent_text}' 不在配置列表中: {intent_names}"}` 而非静默回退到第一个意图
- [x] 3.4 移除 `except Exception` 分支中的静默回退逻辑，改为返回显式错误

## 4. 修改 OpenAI 兼容接口返回错误响应

- [x] 4.1 修改 `server/apps/opspilot/views.py` 的 `get_chat_msg` 函数，检查 `data.get("success")` 是否为 `False`
- [x] 4.2 失败时返回 `JsonResponse({"error": {"message": ..., "type": ..., "code": "execution_failed"}}, status=500)`
- [x] 4.3 检查 `openai_completions` 和其他调用 `invoke_chat` 的视图函数，确保错误处理一致

## 5. 添加单元测试

- [x] 5.1 为 `ChatService.invoke_chat` 添加测试：验证异常时返回 `success=False` 结构
- [x] 5.2 为 `AgentNode.execute` 添加测试：验证 `invoke_chat` 失败时返回错误结构
- [x] 5.3 为 `IntentClassifierNode.execute` 添加测试：验证意图不匹配时返回错误而非回退
- [x] 5.4 为 OpenAI 兼容接口添加测试：验证失败时返回 HTTP 500

## 6. 验证与清理

- [x] 6.1 运行 `cd server && make test` 确保所有测试通过
- [x] 6.2 运行 `cd server && make lint` 确保代码风格符合规范
- [x] 6.3 手动测试：触发 LLM 调用失败场景，验证错误正确传播
