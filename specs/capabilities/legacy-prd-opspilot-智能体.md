# OpsPilot · 智能体

> Migrated from `spec/prd/OpsPilot/智能体.md` as legacy capability evidence；本轮按代码校正知识绑定为 Wiki。

## 1. 背景与目标

智能体定义大模型的行为：模型选择、提示词、工具与 Wiki 知识库绑定，是机器人对话能力的核心单元。

对应架构：[[legacy-ard-modules-opspilot.md#4. AI / RAG 集成【已实现/已存在】]]
对应功能清单：[[legacy-fuctionlist-10-opspilot-功能清单.md#5. 智能体管理]]

## 2. 范围定义

- 基础配置：模型、提示词、温度、对话窗口。
- 工具绑定：函数调用工具。
- 知识：绑定 Wiki 知识库，由对话链路注入上下文。
- 高级能力：问题优化、追问建议、计划执行等。

不在范围：朴素/问答对/图谱 RAG 开关、按库检索分数阈值、RAG 严格模式。

## 3. 关键能力

- 基础配置：从模型库选择 LLM，配置系统提示词、温度、保留的历史对话条数。
- 工具绑定：绑定函数调用工具（内置或自定义）。
- Wiki 知识库：经 `wiki_knowledge_bases` 绑定一个或多个 Wiki 知识库；回答可带 Wiki 引用。
- 高级能力：`enable_query_rewrite` 问题优化、`enable_suggest` 追问建议、计划-执行等多步技能类型。
- 支持内置与可导入的智能体模板。

## 4. 关键规则

- 智能体按组织/团队隔离。
- 对话历史窗口大小可配置。
- 旧 RAG 阈值与严格模式字段已删除，不得再写成 GA。

## 5. 关键技术架构选择

- 基于 LangChain/LangGraph 编排，支持工具调用与多步推理。
- 知识路径为 Wiki 上下文注入，而不是可配置的分块 RAG 管线。

## 6. 验收标准

- 用户可配置智能体的模型、提示词、工具与 Wiki 知识库。
- 界面与接口不再出现已删除的 RAG 阈值/严格模式配置。
- 问题优化、追问建议、计划执行可按配置生效。

> 证据来源：server/apps/opspilot/models/model_provider_mgmt.py:244-270，server/apps/opspilot/services/chat_service.py:580　|　同步基线：61bace9f　|　【已实现】
