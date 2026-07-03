# OpsPilot 智能运维助手 · 功能清单

**文档版本：** V1.1
**发布日期：** 2026-07-03
**适用范围：** BK-Lite OpsPilot 智能运维助手模块
**编制依据：** OpsPilot PRD v1.1（2026-05-28）与 `server/apps/opspilot`、`web/src/app/opspilot` 源代码核对

---

## 一、模块定位

OpsPilot 是 BK-Lite 的智能应用构建与运营平台，提供从基础模型接入、工具与知识库管理、记忆管理、智能体与 ChatFlow 工作流编排，到多渠道对话交付与日志统计的全链路能力。模型密钥、工具密码、渠道密钥等敏感配置全程加密或脱敏，资源可见范围以**团队分组（即系统管理中的组织/组，详见编制规范 SOP 2.2）**为边界。本清单仅列已实现能力；演进展望类内容不纳入。

## 二、功能清单

### 1. 模型管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 模型类型管理 | 四类基础模型的统一管理 | LLM、Embed（嵌入）、Rerank（重排）、OCR | GA |
| 模型 CRUD 与启停 | 模型新增、编辑、删除、启用 / 停用与分组展示 | — | GA |
| 模型分组 | 模型分组维护与排序调整 | — | GA |
| 供应商管理 | 模型供应商维护与详情查看 | 供应商类型：OpenAI、Azure、阿里云、智谱、百度、Anthropic、DeepSeek、其它 | GA |
| 协议类型 | 供应商协议类型选择 | OpenAI 兼容、Anthropic 兼容；DeepSeek 与"其它"类型可选协议，Anthropic 固定 anthropic，其余按 openai 推导 | GA |
| 密钥加密存储 | 供应商 API Key 等密钥配置加密存储 | 读取时不明文展示 | GA |
| 团队可见范围 | 按团队分组控制模型可见范围 | 非超级管理员仅可访问有权限团队内资源 | GA |

### 2. 工具管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 工具列表与检索 | 工具列表展示，按名称 / 标签检索 | — | GA |
| 工具 CRUD | 工具的新增、编辑、删除 | 工具名称唯一 | GA |
| MCP 链接配置 | 配置 MCP 链接与变量 | — | GA |
| 变量类型 | 工具变量支持类型区分 | 含文本与密码类型；密码类型字段加密保存 | GA |
| MCP 子工具拉取 | 从 MCP 拉取可用子工具能力 | — | GA |
| 团队可见范围 | 按团队分组控制工具可见范围 | — | GA |

### 3. 知识库管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 知识库 CRUD | 知识库的新增、编辑、删除、详情查看 | 名称唯一；删除前检查是否被智能体引用 | GA |
| 知识来源 | 支持三类知识来源 | 本地文件、网页链接、自定义文本 | GA |
| 文档预处理 | 文本提取、分块预览与训练 | 默认分块大小 256、重叠 32，分块方式默认 fixed_size | GA |
| OCR 解析 | 文档可选启用 OCR 解析 | 依赖已配置的 OCR 模型 | GA |
| 文档训练状态 | 文档训练状态展示 | 5 态：待处理(Pending)、分块中(Chunking)、训练中(Training)、就绪(Ready)、错误(Error) | GA |
| 检索配置 | 配置检索模式、阈值、返回规模 | 默认检索类型 similarity_score_threshold，默认分数阈值 0.7 | GA |
| Rerank 与召回 | 配置 Rerank 模型与召回 | 默认启用 Rerank，默认 Top K 10；召回模式默认 chunk | GA |
| RAG 模式 | 支持多种 RAG 模式开关 | 朴素 RAG（默认开）、问答对 RAG（默认开）、知识图谱 RAG（默认关） | GA |
| 问答对管理 | 问答对生成、导入、编辑、删除、预览 | — | GA |
| 知识图谱 | 知识图谱创建、查看、更新与社区重建 | — | GA |
| 基础模型变更约束 | 变更知识库基础模型后须对文档重训练 | — | GA |

### 4. 记忆管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 记忆空间 CRUD | 记忆空间的新增、编辑、删除、详情查看 | — | GA |
| 可见范围 | 记忆空间可见范围设置 | 2 种：个人记忆(personal)、团队记忆(team) | GA |
| 空间配置 | 配置简介、写入规则与默认模型 | — | GA |
| 写入测试 | 基于写入规则与默认模型由 LLM 处理输入并返回结果 | 缺少写入规则时直接返回原始输入 | GA |
| 记忆条目管理 | 记忆条目的新增、编辑、删除、查看 | 含标题与内容；条目归属记忆空间，空间删除时条目一并删除 | GA |
| 条目可见性 | 个人记忆空间内条目仅创建者可见；团队记忆空间按团队可见性共享 | — | GA |
| 条目筛选 | 记忆条目按记忆空间筛选 | — | GA |
| ChatFlow 记忆节点 | 在 ChatFlow 中通过记忆节点引用记忆能力 | 含记忆读取(memory_read)、记忆写入(memory_write)节点 | GA |

### 5. 智能体管理

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 智能体列表 | 列表展示、搜索与置顶 | 支持置顶状态切换 | GA |
| 智能体 CRUD | 智能体的创建、编辑、删除 | — | GA |
| 模板化创建 | 智能体模板列表与模板化创建 | — | GA |
| 基础配置 | 配置模型、提示词、温度、简介、分组 | 默认温度 0.7 | GA |
| 增强配置 | 聊天历史、RAG、工具增强 | 默认对话窗口大小 10 | GA |
| 知识库阈值与严格模式 | 每知识库独立阈值配置与 RAG 严格模式配置 | 关闭 RAG 时清空关联知识库与阈值映射 | GA |
| 技能类型 | 智能体技能类型 | 4 种：基础工具、知识工具、Plan-Execute、LATS | GA |
| 流式执行 | 智能体执行（流式响应）与 AG-UI 协议执行 | — | GA |

### 6. 工作台（Studio）与 ChatFlow

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 应用机器人管理 | 应用机器人列表管理与上线 / 下线 | 上线后可对外服务，下线后停止对外响应 | GA |
| 应用类型 | 支持三类应用 | Pilot、LobeChat、ChatFlow | GA |
| ChatFlow 画布编排 | ChatFlow 画布编排与节点配置 | 应用由工作流保存时自动同步，不通过应用接口直接创建 | GA |
| 企业微信智能机器人入口 | ChatFlow 支持企业微信智能机器人入口节点 | 支持 webhook / websocket 两种连接配置形态；当前消息处理以文本输入为主 | GA |
| 节点类别 | ChatFlow 支持的节点类别 | 触发、应用、智能体、记忆、逻辑判断（条件/意图分类）、动作（HTTP/通知）等 | GA |
| 节点执行测试 | 节点执行测试与执行过程查看 | 节点状态：pending/running/completed/failed | GA |
| 流程中断与提交 | 执行流程中断、审批提交与选择提交 | 任务状态：running/interrupt_requested/interrupted/success/fail | GA |
| 执行与会话日志 | 执行日志检索、会话日志查看、输出数据查看 | 主任务与节点级结果均保留 | GA |
| 统计视图 | 会话量、活跃用户、Token 消耗等统计 | — | GA |

相关 PRD：[[spec/prd/OpsPilot/工作台.md#3. 关键能力]]；相关架构：[[spec/ARD/modules/opspilot.md#5. 任务与 NATS【已实现/已存在】]]
> 证据来源：server/apps/opspilot/tasks.py:1257-1299，server/apps/opspilot/utils/workflow_sensitive_config.py:8-118，web/src/app/opspilot/constants/chatflow.ts:15-47,175-188　|　同步基线：83091efe　|　【已实现】

### 7. 渠道与会话

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| 渠道类型 | 支持的渠道类型 | 6 种：企业微信、企业微信机器人、微信公众号、钉钉、Web、GitLab | GA |
| 渠道参数配置 | 渠道参数配置，敏感字段脱敏展示 | 密钥字段加密存储，对外返回以掩码显示 | GA |
| 会话列表 | Web / Mobile 会话列表查询 | 按用户维度返回，按最近会话时间倒序 | GA |
| 会话历史消息 | 会话历史消息查询 | 支持 Web 与 Mobile 入口类型 | GA |
| 引导语查询 | 技能引导语查询 | — | GA |
| 会话删除 | 按会话删除历史记录 | 仅作用于当前用户指定会话 | GA |

### 8. 对外接口与触发

| 功能项 | 功能说明 | 规格 / 约束 | 状态 |
|---|---|---|---|
| OpenAI 风格接口 | OpenAI 风格聊天补全接口 | — | GA |
| LobeChat 兼容接口 | LobeChat 兼容聊天补全接口 | — | GA |
| ChatFlow 执行接口 | 按 bot_id / node_id 执行 ChatFlow | — | GA |
| 企业渠道触发 | 企业微信智能机器人、企业微信、微信公众号、钉钉触发入口 | 企业微信智能机器人当前仅处理文本消息 | GA |
| 工作流执行类型 | 支持的工作流执行类型 | OpenAI、RESTful、Celery（定时）、NATS、企业微信、企业微信智能机器人、微信公众号、钉钉、嵌入式对话、Web、Mobile、AG-UI | GA |

## 三、能力边界与约束

资源可见范围以团队分组为边界，非超级管理员仅可访问有权限团队内资源，关键资源编辑需通过模块权限点校验。知识库名称唯一，删除前须检查智能体引用，变更基础模型后须重训练文档；文档须经"上传—处理—训练—可检索"全状态机方可使用。个人记忆条目仅创建者可见，记忆空间删除时其条目一并删除。应用由 ChatFlow 工作流保存时自动同步，不经应用接口直接创建。模型密钥、工具密码、渠道密钥全程加密存储且对外脱敏展示。本模块不含非 OpsPilot 模块的资产管理、作业编排与监控能力，不定义第三方平台的组织权限模型。

## 四、平台协同

OpsPilot 的知识库与智能体可结合 CMDB 资产事实数据回答运维问询；ChatFlow 的触发节点支持 Web、移动端、企业微信 / 钉钉 / 微信公众号、GitLab 等渠道，与控制台及外部协作工具对接；定时触发依赖 Celery 调度。团队分组与权限语义与系统管理的组织及 RBAC 体系一致；执行日志、会话日志与统计数据支撑审计追溯。

## 五、支持的模型、知识与工具范围

以下枚举均以后端 `apps/opspilot/enum.py`、`models/*` 与前端 `web/src/app/opspilot/constants` 为准。

> **状态：本节 5.1–5.x 所列模型类型、供应商、知识来源/文件类型、渠道、工具类目、ChatFlow 节点等枚举均为 GA。** 例外说明：CMDB、monitor 两类工具模块在工具目录中存在但当前未在加载器 `TOOL_MODULES` 中启用（CMDB 已注释临时关闭），不计入可用工具范围（见 5.x 工具节备注）；其余无 Beta/试验项。

### 5.1 模型类型

| 模型类型 | 后端模型 | 说明 |
|---|---|---|
| LLM 大语言模型 | `LLMModel` | 对话/推理基础模型 |
| Embed 向量模型 | `EmbedProvider` | 文档向量化 |
| Rerank 重排模型 | `RerankProvider` | 检索结果重排 |
| OCR 模型 | `OCRProvider` | 图片/扫描件文字识别 |

共 4 类模型，各自支持内置（`is_build_in`）与自定义。

### 5.2 模型供应商类型（VENDOR_TYPE_CHOICES）与协议类型（PROTOCOL_TYPE_CHOICES）

| 供应商类型 | 取值 |
|---|---|
| OpenAI | `openai` |
| Azure | `azure` |
| 阿里云 | `aliyun` |
| 智谱 | `zhipu` |
| 百度 | `baidu` |
| Anthropic | `anthropic` |
| DeepSeek | `deepseek` |
| 其它 | `other` |

供应商类型共 8 种；协议类型 2 种：OpenAI 兼容（`openai`）、Anthropic 兼容（`anthropic`）。Anthropic 类供应商固定 Anthropic 协议，DeepSeek/其它类型支持协议选择。

### 5.3 知识库文档来源类型（knowledge_source_type）

| 来源类型 | 取值 |
|---|---|
| 文件上传 | `file` |
| 网页 | `web_page` |
| 手动录入 | `manual` |

共 3 种来源（另含 QA 问答对衍生数据）。文件来源支持扩展名 10 种：md、docx、xlsx、csv、pptx、pdf、txt、png、jpg、jpeg（`KNOWLEDGE_TYPES`）。

### 5.4 知识库检索能力

| 能力 | 字段 | 默认 |
|---|---|---|
| 朴素 RAG（分块检索） | `enable_naive_rag` | 开 |
| QA 问答对 RAG | `enable_qa_rag` | 开 |
| 图谱 RAG（GraphRAG） | `enable_graph_rag` | 关 |
| 重排（Rerank） | `enable_rerank` | 开（默认 Top K 10） |

检索方式默认 `similarity_score_threshold`（相似度阈值）；召回模式默认按 chunk。共 3 类 RAG 检索能力可组合启用。

### 5.5 内置可用工具（ToolsLoader 注册类目）

后端 `metis/llm/tools/tools_loader.py` 静态注册以下工具类目（每类含多个具体工具，按 `@tool` 装饰函数发现并写入 SkillTools 表）：

| 工具类目 | 标识 | 说明 |
|---|---|---|
| 浏览器代理 | `agent_browser` / `browser_use` | 智能浏览 |
| 当前时间 | `current_time` | 时间获取 |
| DuckDuckGo 搜索 | `duckduckgo` | 联网搜索 |
| 网页抓取 | `fetch` | HTML/文本/Markdown 抓取 |
| GitHub | `github` | 代码仓库查询 |
| Jenkins | `jenkins` | 流水线查询 |
| Kubernetes | `kubernetes` / `kubernetes_data_collection` | 集群巡检/数据采集 |
| Elasticsearch | `elasticsearch` | 索引/查询 |
| MySQL | `mysql` | 数据库分析 |
| PostgreSQL | `postgres` | 数据库分析 |
| Oracle | `oracle` | 数据库分析 |
| MSSQL | `mssql` | 数据库分析 |
| Redis | `redis` | 缓存分析 |
| Shell | `shell` | 命令执行 |
| SSH | `ssh` | 远程批量执行/上传 |
| Python | `python` | 代码执行 |

加载器 `TOOL_MODULES` 实际启用 18 个工具模块键（上表 16 个功能类目，其中浏览器类含 `agent_browser` / `browser_use`、Kubernetes 类含 `kubernetes` / `kubernetes_data_collection` 各为 2 个键）；CMDB、monitor 类目在工具目录中存在但当前未在加载器中启用（CMDB 已在 `TOOL_MODULES` 中注释临时关闭）。

### 5.6 智能体技能类型（SkillTypeChoices）与机器人类型（BotTypeChoice）

| 类别 | 枚举值 | 数量 |
|---|---|---|
| 技能类型 | 基础工具（Basic Tool）、知识工具（Knowledge Tool）、Plan-Execute、Lats | 4 |
| 机器人类型 | Pilot、LobeChat、ChatFlow | 3 |

### 5.7 ChatFlow 节点类型（前端 chatflow 节点库）

| 节点分类 | 节点类型 |
|---|---|
| 触发器（Triggers） | celery（定时）、nats、restful、openai、agui |
| 应用（Applications） | embedded_chat、web_chat、mobile、enterprise_wechat、enterprise_wechat_aibot、dingtalk、wechat_official |
| 智能体（Agents） | agents |
| 逻辑（Logic） | condition（条件分支）、intent_classification（意图分类） |
| 记忆（Memory） | memory_read、memory_write |
| 动作（Actions） | http、notification |

共 6 个分类、20 种节点类型（`constants/chatflow.ts`、`components/studio/chatflowSettings.tsx`）。工作流执行类型（WorkFlowExecuteType）后端枚举 12 种：openai、restful、celery、nats、enterprise_wechat、enterprise_wechat_aibot、wechat_official、dingtalk、embedded_chat、web_chat、mobile、agui。

### 5.8 对话渠道类型（ChannelChoices）

| 渠道 | 取值 |
|---|---|
| 企业微信 | `enterprise_wechat` |
| 企业微信机器人 | `enterprise_wechat_bot` |
| 微信公众号 | `wechat_official_account` |
| 钉钉 | `ding_talk` |
| Web | `web` |
| GitLab | `gitlab` |

共 6 种对话渠道。

> 说明：上述枚举均直接来自源代码常量、模型字段或前端节点库注册，不含演进展望项。工具类目以 ToolsLoader 实际注册为准（`TOOL_MODULES` 启用 18 个模块键、16 个功能类目），目录中存在但未启用的 CMDB / monitor 类不计入；ChatFlow 节点 17 种以前端节点库为准，后端 WorkFlowExecuteType（10 种）为执行入口/渠道层枚举，二者口径不同。


## 六、枚举与对象取值明细附录

> 本附录列出 OpsPilot 模块的关键枚举与对象取值，取自源码常量定义。共 13 类、84 项取值。

### 内置LLM模型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| OpenAI | `chat-gpt` | OpenAI ChatGPT 模型 |
| 智谱AI | `zhipu` | 智谱 AI 模型 |
| Hugging Face | `hugging_face` | Hugging Face 模型 |
| DeepSeek | `deep-seek` | DeepSeek 模型 |
| 百川 | `Baichuan` | 百川大语言模型 |

### 协议类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| OpenAI 兼容 | `openai` | OpenAI 兼容协议 |
| Anthropic 兼容 | `anthropic` | Anthropic 兼容协议 |

### 对话渠道

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 企业微信 | `enterprise_wechat` | 企业微信渠道 |
| 企业微信机器人 | `enterprise_wechat_bot` | 企业微信机器人渠道 |
| 微信公众号 | `wechat_official_account` | 微信公众号渠道 |
| 钉钉 | `ding_talk` | 钉钉对话渠道 |
| Web | `web` | Web 网页渠道 |
| GitLab | `gitlab` | GitLab 渠道 |

### 工作流任务状态

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 运行中 | `running` | 工作流任务运行中 |
| 请求中断 | `interrupt_requested` | 已请求中断工作流任务 |
| 已中断 | `interrupted` | 工作流任务已中断 |
| 成功 | `success` | 工作流任务成功 |
| 失败 | `fail` | 工作流任务失败 |

### 工作流执行类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| OpenAI | `openai` | 通过 OpenAI 接口执行工作流 |
| RESTful | `restful` | 通过 RESTful 接口执行工作流 |
| Celery | `celery` | 通过 Celery 异步执行工作流 |
| NATS | `nats` | 通过 NATS 触发执行工作流 |
| 企业微信 | `enterprise_wechat` | 企业微信触发执行工作流 |
| 企业微信智能机器人 | `enterprise_wechat_aibot` | 企业微信智能机器人触发执行工作流 |
| 微信公众号 | `wechat_official` | 微信公众号触发执行工作流 |
| 钉钉 | `dingtalk` | 钉钉触发执行工作流 |
| 嵌入式对话 | `embedded_chat` | 嵌入式对话触发执行工作流 |
| Web 对话 | `web_chat` | Web 对话触发执行工作流 |
| 移动端 | `mobile` | 移动端触发执行工作流 |
| AG-UI | `agui` | AG-UI 触发执行工作流 |

### 工具类目

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| agent_browser | `agent_browser` | 智能体浏览器工具 |
| browser_use | `browser_use` | 浏览器操作工具 |
| current_time | `current_time` | 当前时间工具 |
| duckduckgo | `duckduckgo` | DuckDuckGo 搜索工具 |
| elasticsearch | `elasticsearch` | Elasticsearch 查询工具 |
| fetch | `fetch` | 网页抓取工具 |
| github | `github` | GitHub 工具 |
| jenkins | `jenkins` | Jenkins 工具 |
| kubernetes | `kubernetes` | Kubernetes 工具 |
| kubernetes_data_collection | `kubernetes_data_collection` | Kubernetes 数据采集工具 |
| mssql | `mssql` | SQL Server 数据库工具 |
| mysql | `mysql` | MySQL 数据库工具 |
| oracle | `oracle` | Oracle 数据库工具 |
| postgres | `postgres` | PostgreSQL 数据库工具 |
| python | `python` | Python 执行工具 |
| redis | `redis` | Redis 工具 |
| shell | `shell` | Shell 命令工具 |
| ssh | `ssh` | SSH 远程工具 |
| cmdb | `cmdb` | CMDB 工具（源码中已注释关闭，未启用） |

### 技能类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| Basic Tool | `1` | 基础工具技能 |
| Knowledge Tool | `2` | 知识库工具技能 |
| Plan Execute | `3` | 计划-执行型技能 |
| Lats | `4` | LATS 推理型技能 |

### 文档状态

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 训练中 | `0` | 知识文档训练中 |
| 就绪 | `1` | 知识文档就绪可用 |
| 错误 | `2` | 知识文档处理出错 |
| 等待中 | `3` | 知识文档等待处理 |
| 分块中 | `4` | 知识文档分块处理中 |

### 机器人类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| Pilot | `1` | Pilot 类型机器人 |
| LobeChat | `2` | LobeChat 类型机器人 |
| ChatFlow | `3` | ChatFlow 类型机器人 |

### 模型供应商类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| OpenAI | `openai` | OpenAI 供应商 |
| Azure | `azure` | 微软 Azure 供应商 |
| 阿里云 | `aliyun` | 阿里云供应商 |
| 智谱 | `zhipu` | 智谱 AI 供应商 |
| 百度 | `baidu` | 百度（千帆）供应商 |
| Anthropic | `anthropic` | Anthropic 供应商 |
| DeepSeek | `deepseek` | DeepSeek 供应商 |
| 其它 | `other` | 其它自定义供应商 |

### 模型类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| LLM Model | `llm_model` | 大语言模型（LLM） |
| Embed Model | `embed_provider` | 文本向量化（嵌入）模型 |
| Rerank Model | `rerank_provider` | 检索结果重排序模型 |
| OCR Model | `ocr_provider` | OCR 光学字符识别模型 |

### 知识文件类型

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| md | `md` | 支持的知识文件格式：.md |
| docx | `docx` | 支持的知识文件格式：.docx |
| xlsx | `xlsx` | 支持的知识文件格式：.xlsx |
| csv | `csv` | 支持的知识文件格式：.csv |
| pptx | `pptx` | 支持的知识文件格式：.pptx |
| pdf | `pdf` | 支持的知识文件格式：.pdf |
| txt | `txt` | 支持的知识文件格式：.txt |
| png | `png` | 支持的知识文件格式：.png |
| jpg | `jpg` | 支持的知识文件格式：.jpg |
| jpeg | `jpeg` | 支持的知识文件格式：.jpeg |

### 知识来源

| 枚举项 | 取值 | 中文含义 |
|---|---|---|
| 文件 | `file` | 来自上传文件的知识 |
| 网页 | `web_page` | 来自网页抓取的知识 |
| 手动 | `manual` | 手动录入的知识 |
