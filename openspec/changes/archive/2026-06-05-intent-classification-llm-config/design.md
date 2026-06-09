## Context

当前意图分类节点前端配置为 `agent + intents`，抽屉中直接加载智能体列表。后端 `IntentClassifierNode` 继承 `AgentNode`，执行时强制读取 `config.agent`，再通过 `LLMSkill` 间接拿到 `llm_model` 和 `skill_prompt`。分类专用的系统提示词只是追加在 skill prompt 后面。

这条链路的问题是：

- 配置语义错误：用户看到的是“选择智能体”，而不是“选择 LLM 模型”。
- 执行依赖过重：一个纯分类节点却依赖完整的智能体实体。
- Prompt 来源混杂：分类逻辑既有内置 prompt，又受 skill prompt 影响，不利于形成稳定分类行为。

## Goals / Non-Goals

**Goals:**
- 让意图分类节点直接选择 LLM 模型，而不是选择智能体。
- 新增“分类规则”字段，允许用户补充分类约束，但不要求必填。
- 将意图分类 prompt 统一为“内置 prompt + 用户补充规则”。
- 后端直接基于 `llmModel` 调用 LLM，彻底移除对 `agent` / `LLMSkill` 的依赖。
- 明确旧配置不兼容，避免为双协议长期保留分支。

**Non-Goals:**
- 不改造普通智能体节点的配置和执行方式。
- 不引入新的模型管理接口，复用现有 LLM 模型列表接口。
- 不扩展意图分类节点的高级模型参数面板，本次仅覆盖模型选择和分类规则。

## Decisions

### 1. 意图分类节点采用独立配置协议

意图分类节点配置将改为以 `llmModel`、`classificationRules`、`intents` 为核心字段，不再保留 `agent`。

选择原因：这与节点真实职责一致，也能让前后端围绕统一协议实现，不再额外映射 skill。

### 2. 前端复用现有 LLM 模型数据源

节点抽屉不再调用智能体列表接口，而是改为加载 `/opspilot/model_provider_mgmt/llm_model/` 返回的启用模型列表，并沿用现有模型下拉文案与筛选渲染工具。

选择原因：仓库里已经有成熟的模型列表接口和下拉渲染方式，复用后能降低改动面并保持 UI 一致性。

### 3. Prompt 组装改为“内置分类 prompt + 用户分类规则”

后端执行时固定使用分类节点内置 prompt 作为主提示词；如果用户填写了分类规则，则将其追加到内置 prompt 之后，作为补充约束。用户输入的分类规则不覆盖内置 prompt。

选择原因：内置 prompt 可以保证分类输出格式稳定，用户规则只负责补充业务约束，避免因自定义内容破坏基础分类协议。

### 4. 后端直接构造最小 LLM 调用参数

`IntentClassifierNode` 不再继承或复用 `AgentNode` 的 skill 装载过程，而是直接基于所选 `llmModel` 构造 `ChatService.invoke_chat()` 所需最小参数，包括：

- `llm_model`
- `skill_prompt`
- `temperature`
- `chat_history`
- `user_message`
- `skill_type`
- 与执行上下文相关的 `user_id`、`locale`、`execution_id`

选择原因：意图分类节点本身不需要知识库、工具、上传文件或智能体模板。直接构造参数更清晰，也能减少被 `LLMSkill` 隐式字段影响。

### 5. 旧 agent 配置不兼容

工作流中已有的意图分类节点若仍保留旧 `agent` 配置，本次变更后不保证可执行，用户需要按新配置重新保存。

选择原因：用户已明确选择不兼容旧协议。这样可以避免实现阶段加入兼容桥接、双字段回退和长期维护负担。

## Data Shape

### Frontend node config

```json
{
  "inputParams": "last_message",
  "outputParams": "last_message",
  "llmModel": 1,
  "classificationRules": "",
  "intents": [
    { "name": "默认意图" }
  ]
}
```

### Prompt composition

```text
[内置意图分类 prompt]

[用户填写的分类规则（可选）]
```

## Risks / Trade-offs

- 旧工作流中的意图分类节点会失效，需要重新配置。
- 直接使用模型后，分类节点不再自动继承某个智能体已有的 prompt、知识库或工具；这是有意收紧能力边界。
- 若不同模型对“仅输出标签”遵循程度不同，可能需要在实现中保留默认意图回退和输出校验。

## Migration Plan

1. 更新前端意图分类节点配置 UI、类型和默认值。
2. 更新后端意图分类节点执行器，切断 `agent` 依赖。
3. 对现有工作流不做自动迁移，交由用户重新编辑并保存该节点。
4. 发布说明中明确意图分类节点配置方式已变更。

## Open Questions

- 是否需要在抽屉中对“分类规则”增加示例文案或帮助提示，帮助用户理解其是补充 prompt 而非完整 prompt。
