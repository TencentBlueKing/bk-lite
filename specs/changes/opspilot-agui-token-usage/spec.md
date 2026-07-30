# OpsPilot Agent 测试 token 用量日志

Status: proposed

## 目标

OpsPilot 的 `execute_agui` skill 测试接口必须记录一次完整 Agent 问答的 token
消耗，使调用日志能够反映包含工具调用和多轮模型推理在内的实际模型用量。

## 行为契约

- `execute_agui` 必须把当前 skill 的 ID 传入 AG-UI 流式执行链路，使成功完成的
  测试调用能够创建对应的 `SkillRequestLog`。
- 一次问答的 token 用量是该次 Agent 运行中所有真实 LLM 调用用量之和，而不是
  只统计最终回答对应的最后一次调用。
- 每次 LLM 调用优先读取 LangChain 消息的 `usage_metadata`，并兼容
  `response_metadata.token_usage`。
- 同一个 LLM run 只能累计一次，避免父子图或重复结束事件造成重复计数。
- 模型供应商未返回用量时不自行估算；该次调用按 0 计入，并输出可定位的警告日志。
- token 统计只用于日志与观测，不改变现有 AG-UI SSE 事件及前端协议。
- token 日志记录失败不得中断或改变已经完成的 Agent 流式回答。

## 日志结构

成功完成流式执行后，`SkillRequestLog.response_detail` 使用现有统计接口可识别的
OpenAI 风格结构：

```json
{
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50,
    "total_tokens": 150
  },
  "response": []
}
```

其中：

- `prompt_tokens` 是整轮所有 LLM 调用的输入 token 总和。
- `completion_tokens` 是整轮所有 LLM 调用的输出 token 总和。
- `total_tokens` 优先使用供应商返回的总量；未返回时按输入与输出之和计算。
- `response` 保持现有 AG-UI 事件记录格式。

服务运行日志同时记录 skill ID、skill 名称及三个 token 数值，不记录提示词、
凭据、工具参数或完整回答。

## 实现接缝

- `LLMViewSet.execute_agui` 将 `skill_obj.id` 传给 `stream_agui_chat`。
- AG-UI Agent 流在 `on_chat_model_end` 事件中提取并聚合 token 用量，通过仅在
  当前请求内部使用的统计对象或回调传回 `agui_chat`，不新增对外 SSE 事件。
- `_log_and_update_tokens_agui` 将聚合结果写入
  `SkillRequestLog.response_detail.usage`；沿用现有后台持久化和错误隔离逻辑。
- token 提取与累计逻辑保持为可独立测试的纯函数或小型聚合器。

## 异常与兼容

- 缺少 `usage_metadata` 和 `response_metadata.token_usage` 时记录 0，并继续正常
  返回回答。
- 非数字、负数和布尔值不得进入统计，按 0 处理。
- `total_tokens` 缺失或无效时回退为 `prompt_tokens + completion_tokens`。
- 现有 skill 调用日志查询及 token 消耗统计接口无需修改数据契约。
- 不增加数据库字段或迁移。

## 验证

- 单次 LLM 调用正确记录输入、输出和总 token。
- 工具调用引发的多轮 LLM 请求能够累计为一次 Agent 问答用量。
- 相同 run ID 的重复结束事件不会重复累计。
- `usage_metadata` 与 `response_metadata.token_usage` 两种形状均可解析。
- 缺少或包含非法 usage 时记录 0，流式响应不受影响。
- `execute_agui` 把真实 skill ID 传入日志链路并成功创建 `SkillRequestLog`。
- 结构化运行日志包含 skill 标识和 token 数值，不包含敏感请求内容。
