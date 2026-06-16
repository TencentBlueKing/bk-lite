# 模块 ARD：OpsPilot（AI 助手）

> 路径 `server/apps/opspilot` ｜ API 前缀 `api/v1/opspilot/`

## 1. 职责【已实现/已存在】
AI 助手平台：RAG 检索增强、知识库管理、Bot 编排、LLM 厂商接入、工作流自动化与记忆管理。

## 2. 数据模型与存储【已实现/已存在】

模型可按子域分组（文件即子域边界）。下表覆盖各子域全部模型类。

**模型供应商 / 技能子域（`models/model_provider_mgmt.py`）**

| 模型 | 行 | 说明 |
|------|----|------|
| ModelVendor | `:27` | 厂商（OpenAI/Azure/Aliyun/Zhipu/Baidu/Anthropic/DeepSeek/other）；`api_key` 加密；含持久化字段 `protocol_type`（CharField，choices=openai/anthropic，迁移 `0049_modelvendor_protocol_type.py`，默认 openai）（`:30`） |
| LLMModel | `:68` | LLM 模型（关联厂商）。`protocol_type` 为只读 property（`:100-110`）：anthropic 厂商→anthropic；deepseek/other→读取 `vendor.protocol_type`；其余→openai，支撑非 OpenAI 协议接入 |
| EmbedProvider / RerankProvider | `:118,154` | Embed / Rerank 模型（密钥经厂商解密） |
| OCRProvider | `:190` | OCR 解析提供方（EncryptMixin，供 KnowledgeDocument 解析） |
| LLMSkill | `:232` | 智能体/技能（LLM 模型、提示词、RAG 配置、工具列表、技能类型、对话历史窗口、知识库路由等） |
| SkillTools | `:295` | 工具集（参数、标签、tools 列表，可复用注册） |
| SkillRequestLog | `:309` | 技能调用请求日志（请求/响应明细、来源 IP、成败状态） |

**Bot / 工作流子域（`models/bot_mgmt.py`）**

| 模型 | 行 | 说明 |
|------|----|------|
| Bot / BotChannel | `:22,70` | Bot（Rasa 模型/技能/渠道/部署）、渠道（GitLab/钉钉/企微/企微机器人/公众号，渠道密钥加密） |
| BotConversationHistory | `:172` | Bot 对话历史（用户/机器人角色、引用知识、通道用户） |
| ConversationTag | `:189` | 对话标注（问题/答案关联到知识库与文档） |
| RasaModel | `:200` | Rasa 模型文件（MinIO `munchkin-private`） |
| ChannelUser / ChannelGroup / UserGroup | `:220,239,248` | 消息通道用户、通道群组、用户-群组关联 |
| BotWorkFlow | `:256` | 机器人工作流（flow/web JSON，保存时同步 ChatApplication） |
| ChatApplication | `:421` | 聊天应用（按工作流入口节点自动生成，mobile/web_chat 两类） |
| WorkflowAttachmentAsset | `:290` | 工作流附件资产（关联 FileKnowledge，下载令牌、execution/attachment 去重约束） |
| WorkFlowTaskResult | `:278` | 工作流执行主记录（执行实例、状态、输入/输出） |
| WorkFlowTaskNodeResult | `:325` | 工作流节点执行明细（节点输入/输出、状态、耗时） |
| WorkFlowConversationHistory | `:361` | ChatFlow 对话历史（用户输入 + 系统输出两条/次，入口类型分流，定时触发不记录） |

**知识库子域（`models/knowledge_mgmt.py`）**

| 模型 | 行 | 说明 |
|------|----|------|
| KnowledgeBase | `:28` | 知识库（embed/rerank、naive/QA/graph RAG 开关、阈值/召回模式） |
| KnowledgeDocument | `:56` | 知识文档（解析模式、分块类型、OCR、训练状态） |
| FileKnowledge / WebPageKnowledge / ManualKnowledge | `:120,149,177` | 文件知识（MinIO `munchkin-private`）、网页知识（可定时同步）、手工录入知识 |
| QAPairs | `:192` | 问答对（生成模型、问/答提示词、状态） |
| KnowledgeGraph / GraphChunkMap / KnowledgeTask | `:218,228,234` | 知识图谱（一对一知识库）、Chunk↔Graph 映射、知识训练任务（进度/状态） |

**记忆子域（`models/memory_mgmt.py`）**

| 模型 | 行 | 说明 |
|------|----|------|
| MemorySpace | `:9` | 记忆空间（storage_type 枚举 local/mem0/zep/custom，个人/团队范围，配置敏感字段加密） |
| Memory | `:104` | 记忆条目（按用户/组织隔离，标题 + 内容） |
| MemoryWriteCache | `:137` | 记忆批量写缓存（workflow/node/target 去重，PENDING/PROCESSING 状态机） |

**其他（`models/user_pin.py`）**

| 模型 | 行 | 说明 |
|------|----|------|
| UserPin | `:4` | 用户置顶记录（按用户隔离，置顶 Bot 或 LLMSkill） |

**存储**：PostgreSQL + **pgvector**（向量）；MinIO（知识文件/Rasa 模型/工作流附件，桶 `munchkin-private`）；Elasticsearch（metis 工具检索）。

## 3. 接口【已实现/已存在】
`model_provider_mgmt/*`、`bot_mgmt/*`（含 OpenAI 兼容 `/v1/chat/completions`、`/lobe_chat/v1/chat/completions`）、`channel_mgmt/*`、`knowledge_mgmt/*`、`memory_mgmt/*`。

## 4. AI / RAG 集成【已实现/已存在】
- LangChain（`langchain_core.messages`）；`metis/llm/` 引擎（分块：fixed/semantic/recursive；embedding manager）。
- 内置工具（`metis/llm/tools/tools_loader.py:31-52` 的 `ToolsLoader.TOOL_MODULES`，约 19 类）：attachment_file、agent_browser、browser_use、current_time（date）、duckduckgo（search）、elasticsearch、fetch、github、jenkins、kubernetes、kubernetes_data_collection、mssql、mysql、oracle、postgres、python、redis、shell、ssh；cmdb 已注释临时关闭（`:35`）。
- monitor 工具不在 `TOOL_MODULES`，由 `services/builtin_tools.py:4,58` 单独装配（与 redis/mysql/oracle/mssql/attachment_file 一并作为内置工具暴露）。
- RAG 模式：naive（**本地 pgvector**）/QA/graph（`services/{rag_service,knowledge_search_service,chat_service}.py`）。
- **外部依赖更正**（基于代码核对）：
  - Kubernetes：**已使用**，但经运行时 `kubeconfig_data` 参数加载（`metis/llm/tools/kubernetes/{utils,connection}.py`），**非** `KUBE_CONFIG_FILE` 环境变量。
  - `METIS_SERVER_URL`、`MUNCHKIN_BASE_URL`、`CONVERSATION_MQ_*`：仅在 `config.py` 中定义，**代码中未被引用**（占位/预留，当前 RAG 走本地 pgvector）。【待确认是否为历史遗留】

## 5. 任务与 NATS【已实现/已存在】
- 定时（`config.py`）：`cleanup-expired-workflow-attachments`（每日 3 点）、`flush-pending-memory-write-cache`（每日 0 点）。
- NATS（`nats_api.py` 中 `@nats_client.register` 注册，共 5 个）：`get_opspilot_module_list`（`:65`）、`get_opspilot_module_data`（`:85`）、`get_guest_provider`（`:118`）、`consume_bot_event`（`:162`）、`trigger_workflow_by_nats`（`:212`）。

## 6. 风险 / 待确认
- `METIS_SERVER_URL`/`MUNCHKIN_BASE_URL`/`CONVERSATION_MQ_*` 在 config.py 定义但未被代码引用——是历史遗留还是外部联动入口【待确认】。
- LLM 调用的成本/限流/审计【待确认】。

## 7. 证据来源
`server/apps/opspilot/{urls.py,models/*,services/*,metis/llm/*,tasks.py,config.py,nats_api.py}`；模型表见 `models/{model_provider_mgmt.py,bot_mgmt.py,knowledge_mgmt.py,memory_mgmt.py,user_pin.py}`；内置工具见 `metis/llm/tools/tools_loader.py:31-52`、`services/builtin_tools.py`；protocol_type 持久化见 `migrations/0049_modelvendor_protocol_type.py`。
