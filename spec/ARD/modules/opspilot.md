# 模块 ARD：OpsPilot（AI 助手）

> 路径 `server/apps/opspilot` ｜ API 前缀 `api/v1/opspilot/`

## 1. 职责【已实现/已存在】
AI 助手平台：RAG 检索增强、知识库管理、Bot 编排、LLM 厂商接入、工作流自动化与记忆管理。

## 2. 数据模型与存储【已实现/已存在】
| 模型 | 文件 | 说明 |
|------|------|------|
| Bot / BotChannel | `models/bot_mgmt.py` | Bot（Rasa 模型/技能/渠道/部署）、渠道（GitLab/钉钉/企微/公众号） |
| KnowledgeBase / KnowledgeDocument / FileKnowledge | `models/knowledge_mgmt.py` | 知识库（embed/rerank/RAG 模式）、文档、文件（MinIO `munchkin-private`） |
| ModelVendor / LLMModel / EmbedProvider / RerankProvider | `models/model_provider_mgmt.py` | 厂商（OpenAI/Azure/Aliyun/Zhipu/Baidu/Anthropic/DeepSeek）、LLM/Embed/Rerank（密钥加密）。LLMModel 有 `protocol_type` 属性按厂商推断协议（Anthropic→anthropic，其余可选），支撑非 OpenAI 协议接入 |
| MemorySpace / MemoryWriteCache | `models/memory_mgmt.py:9,137` | 记忆空间（local/Mem0/Zep/custom，个人/团队范围）；记忆批量写缓存（workflow/node/target 去重，PENDING/PROCESSING 状态机） |
| OCRProvider | `models/model_provider_mgmt.py:190` | OCR 解析提供方（EncryptMixin，供 KnowledgeDocument 解析） |

**存储**：PostgreSQL + **pgvector**（向量）；MinIO（知识文件）；Elasticsearch（metis 工具检索）。

## 3. 接口【已实现/已存在】
`model_provider_mgmt/*`、`bot_mgmt/*`（含 OpenAI 兼容 `/v1/chat/completions`、`/lobe_chat/v1/chat/completions`）、`channel_mgmt/*`、`knowledge_mgmt/*`、`memory_mgmt/*`。

## 4. AI / RAG 集成【已实现/已存在】
- LangChain（`langchain_core.messages`）；`metis/llm/` 引擎（工具：ES/K8s/Python/Monitor/Redis；分块：fixed/semantic/recursive；embedding manager）。
- RAG 模式：naive（**本地 pgvector**）/QA/graph（`services/{rag_service,knowledge_search_service,chat_service}.py`）。
- **外部依赖更正**（基于代码核对）：
  - Kubernetes：**已使用**，但经运行时 `kubeconfig_data` 参数加载（`metis/llm/tools/kubernetes/{utils,connection}.py`），**非** `KUBE_CONFIG_FILE` 环境变量。
  - `METIS_SERVER_URL`、`MUNCHKIN_BASE_URL`、`CONVERSATION_MQ_*`：仅在 `config.py` 中定义，**代码中未被引用**（占位/预留，当前 RAG 走本地 pgvector）。【待确认是否为历史遗留】

## 5. 任务与 NATS【已实现/已存在】
- 定时（`config.py`）：`cleanup-expired-workflow-attachments`（每日 3 点）、`flush-pending-memory-write-cache`（每日 0 点）。
- NATS：`nats_api.py:get_opspilot_module_{list,data}`、`get_guest_provider`。

## 6. 风险 / 待确认
- `METIS_SERVER_URL`/`MUNCHKIN_BASE_URL`/`CONVERSATION_MQ_*` 在 config.py 定义但未被代码引用——是历史遗留还是外部联动入口【待确认】。
- LLM 调用的成本/限流/审计【待确认】。

## 7. 证据来源
`server/apps/opspilot/{urls.py,models/*,services/*,metis/llm/*,tasks.py,config.py,nats_api.py}`。
