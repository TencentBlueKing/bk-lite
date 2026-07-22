# 2026 06 05 Intent Classification Llm Config

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-intent-classification-llm-config/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前工作台中的意图分类节点要求用户先选择一个智能体，再借助该智能体绑定的模型完成分类。这与目标产品语义不一致：意图分类节点本身只需要一个 LLM 模型和一段分类规则，不需要复用完整智能体配置。

现有设计还把分类能力隐式绑定到 `LLMSkill`，导致节点配置、执行逻辑和用户认知都围绕“选择智能体”展开。用户无法直观看到具体使用的模型，也无法明确配置仅用于分类的补充规则。

## What Changes

- 将意图分类节点的配置方式从“选择智能体”调整为“选择 LLM 模型”。
- 为意图分类节点新增可选的“分类规则”配置项，作为内置分类 prompt 的补充。
- 保留意图列表配置，但不再通过智能体 skill prompt 驱动分类。
- 后端将意图分类节点改为直接使用所选 LLM 模型执行分类，不兼容旧的 `agent` 配置。

## Capabilities

### New Capabilities
- `intent-classification-llm-config`: 定义意图分类节点直接使用 LLM 模型执行分类，并支持用户补充分类规则。

### Modified Capabilities
- `intent-classification-llm-config`: 意图分类节点的前端配置结构、后端执行方式和提示词组装方式整体更新。

## Impact

- Web 聊天流编辑器：节点配置抽屉、节点默认配置、配置摘要展示、国际化文案。
- Server 聊天流引擎：意图分类节点执行器、LLM 参数构造、错误与默认意图回退逻辑。
- 现有工作流数据：旧的 `agent` 型意图分类节点将不再兼容，必须按新配置重新保存。

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-14
```

## Capability Deltas

### intent-classification-llm-config

## ADDED Requirements

### Requirement: 意图分类节点直接选择 LLM 模型

意图分类节点 SHALL 允许用户直接选择一个启用中的 LLM 模型作为分类执行模型，而不是选择智能体。

#### Scenario: 打开意图分类节点配置抽屉

- **WHEN** 用户在工作台打开意图分类节点配置抽屉
- **THEN** 系统 SHALL 显示“LLM模型”选择项
- **AND** 系统 SHALL 不再显示“选择智能体”字段

#### Scenario: 保存意图分类节点配置

- **WHEN** 用户选择一个 LLM 模型并保存节点
- **THEN** 节点配置 SHALL 持久化所选模型标识
- **AND** 后端执行 SHALL 使用该模型完成意图分类

### Requirement: 分类规则作为补充 prompt

意图分类节点 SHALL 提供一个非必填的“分类规则”字段，其内容作为内置分类 prompt 的补充，而不是替代。

#### Scenario: 用户未填写分类规则

- **WHEN** 用户保存节点时未填写分类规则
- **THEN** 系统 SHALL 允许保存
- **AND** 后端 SHALL 仅使用内置分类 prompt 执行分类

#### Scenario: 用户填写分类规则

- **WHEN** 用户填写分类规则并执行工作流
- **THEN** 后端 SHALL 将该内容追加到内置分类 prompt 之后
- **AND** 该补充内容 SHALL 参与本次分类判断

### Requirement: 意图分类节点不再依赖智能体配置

意图分类节点 SHALL 不再要求 `agent` 配置，也不再通过 `LLMSkill` 间接获取模型和 prompt。

#### Scenario: 执行新配置节点

- **WHEN** 意图分类节点包含 `llmModel`、`intents` 和可选的 `classificationRules`
- **THEN** 节点 SHALL 在没有 `agent` 的情况下成功执行分类
- **AND** 节点 SHALL 继续输出用于匹配分支的意图结果

### Requirement: 非兼容旧 agent 型意图分类配置

本次变更后的意图分类节点 SHALL 仅支持新配置协议，不保证兼容旧的 `agent` 型配置。

#### Scenario: 工作流仍使用旧配置

- **WHEN** 工作流中的意图分类节点仅包含旧 `agent` 配置而未按新协议重新保存
- **THEN** 系统 MAY 拒绝按新逻辑执行该节点
- **AND** 产品与实现 SHALL 以新配置协议为唯一支持目标

## Work Checklist

## 1. Web chatflow editor

- [x] 1.1 调整意图分类节点配置组件，移除“选择智能体”，改为加载并展示 LLM 模型下拉。
- [x] 1.2 为意图分类节点新增“分类规则”表单项，设置为非必填，并明确其语义为补充 prompt。
- [x] 1.3 更新节点配置类型、默认值、抽屉数据加载逻辑和配置摘要展示，使其使用 `llmModel` 与 `classificationRules`。
- [x] 1.4 补齐相关中英文文案，确保节点抽屉与列表展示统一使用“LLM模型 / 分类规则”表述。

## 2. Server intent classifier

- [x] 2.1 改造意图分类节点执行器，移除对 `agent` / `LLMSkill` 的依赖，改为直接基于 `llmModel` 构造 LLM 调用参数。
- [x] 2.2 按“内置 prompt + 用户分类规则”组装最终提示词，并保持仅输出意图标签的约束。
- [x] 2.3 保留意图输出校验和默认意图回退逻辑，确保模型输出不在候选列表时仍可稳定路由。

## 3. Validation

- [x] 3.1 执行 `cd web && pnpm lint && pnpm type-check`，确认前端配置变更无类型和 lint 问题。
- [x] 3.2 执行与 server 意图分类节点相关的最小测试或验证命令，确认节点在新配置下可执行。
- [x] 3.3 手动验证工作台中的意图分类节点：可选择 LLM 模型、分类规则可留空、分类结果按意图分支路由。
