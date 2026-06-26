# OpsPilot ReAgent → DeepAgent 全量升级设计

- 日期: 2026-06-26
- 范围: `server/apps/opspilot/`(LangChain/LangGraph 栈仅此一个 app 使用)
- 状态: 设计待评审
- 决策基调: **推倒重来**。产品尚无客户使用,允许破坏性重构;对外保留 `ReAgent` 等命名与 API 形态,内部引擎全部换成 DeepAgents。

## 1. 背景与现状

OpsPilot 当前真正运行的是**手写 ReAct 循环**(`metis/llm/chain/node.py: build_react_nodes`),并衍生出 Plan-Execute、LATS、ChatBot 等图。它附带大量手写生产特性:compaction、retry、reflection、动态工具池、token budget、approval、done-tool、verification、rollback、AG-UI 流式输出。

`deepagents==0.2.5` 虽已在依赖中,且 `node.py: build_deepagent_nodes` 调用了 `create_deep_agent(model, tools, system_prompt)`,但:
- **未传 `skills=` / `backend=`**;
- **未被任何 graph / `agent_factory` 引用**(工厂只映射 ReAct/Plan-Execute/LATS/ChatBot)——基本是死代码。

"skills" 当前是**伪实现**:`services/skill_package/runtime.py` 按触发词把 `skill_markdown` 拼进 system prompt,而非 DeepAgents 的 SKILL.md 渐进式披露(agent 用 `read_file` 按需加载)。

tools / MCP **已是真实可用**:`ToolsNodes.setup` 经 `ToolsLoader` + `MultiServerMCPClient` 注入 `self.tools`。

知识库为**预检索**:`naive_rag_node` 在 agent 启动前跑 RAG 拼进消息,agent 无法在循环中自主检索。

**关键约束发现**:安装的 `deepagents 0.2.5` **没有任何 skills 能力**(无 `skills=` 参数、无 `SkillsMiddleware`)。skills 是更新版(`0.4.x`)特性。`deepagents 0.4.12` 要求 `langchain>=1.3.11`、`langchain-core>=1.4.8`,而当前锁 `langchain==1.0.5`。LangChain/LangGraph 全栈**仅 opspilot 使用(178 个文件)**,其它 app 不受影响,升级爆炸半径被控制在 opspilot 内。

## 2. 目标

1. 用 DeepAgents middleware 栈**统一替换**所有手写 agent 引擎。
2. 对外**保留命名/API**:`SkillTypeChoices`、`ReActAgentGraph` 等类名、`agent_factory.create_agent_instance` 接口、`LLMSkill` 模型字段尽量不变,避免前端/存量技能数据破坏。
3. **真实落地四项能力**:tools、MCP、skills(原生 SKILL.md 渐进式披露)、knowledge base(agent 可调用)。
4. **保住 AG-UI / A2UI 流式输出**(最高优先级,不可回归)。

## 3. 决策记录(已与用户确认)

| # | 决策 | 选择 |
|---|---|---|
| D1 | 迁移野心 | **全量迁移**,所有 agent 类型统一到 DeepAgents |
| D2 | 特性保留 | 仅 **AG-UI/A2UI 流式必保**;其余优先 DeepAgents 原生 |
| D3 | Skills backend | **MinIO 对象存储**(自写 backend 适配器) |
| D4 | 知识库接入 | **双模式**:agent 可调用检索工具(默认) + 可选启动前预检索 |
| D5 | Skills 实现 | **升级 deepagents 到带 skills 的版本(0.4.x)**,用原生 SkillsMiddleware |
| D6 | LATS 及旧 agent | **推倒重来**,删 LATS,所有旧 agent 内部全换 deepagent |
| D7 | retry/reflection/动态工具池/token budget | **确认舍弃**,先用 deepagent 原生行为,有回归再补 |
| D8 | SDK 选型 | **不换 SDK**,继续 deepagents/LangChain(多供应商 + 现有栈同源) |

## 4. 总体架构

```
ChatService.invoke_chat
  └─ create_agent_instance(skill_type, chat_kwargs)      # 工厂保留, 命名不变
       └─ <AgentGraph>.compile_graph(request)            # 各图 compile 改为统一委托
            ├─ prepare_graph: prompt → history → user_msg → [可选 naive_rag_node]
            └─ build_deepagent_nodes(...)                 # 统一入口, 取代 build_react_nodes
                 └─ create_deep_agent(
                      model        = get_llm_client(req),
                      tools        = langchain_tools + mcp_tools + [knowledge_retrieve],
                      backend      = MinIOBackend(skill_namespace, ...),
                      skills       = [<物化的 SKILL.md 路径>],
                      subagents    = [...],                # 复杂任务分解(替代 Plan-Execute/LATS)
                      interrupt_on = {<工具名>: InterruptOnConfig},  # HITL = 原生 approval
                      middleware   = [AGUIStreamMiddleware, ...其余原生由 create_deep_agent 默认装配],
                      system_prompt= rendered_prompt,
                    )
  └─ agui_stream(graph.astream(..., stream_mode="messages"))   # 适配层 → AG-UI/A2UI 事件
```

统一一个 `build_deepagent_nodes`,取代 `build_react_nodes` 及 plan/replan/LATS 节点。`create_deep_agent` 默认自带 `TodoListMiddleware`(规划)、`FilesystemMiddleware`(文件/skills 读写)、`SubAgentMiddleware`、`SummarizationMiddleware`、`AnthropicPromptCachingMiddleware`、`PatchToolCallsMiddleware`。

## 5. 各 Agent 类型映射

| 现有 `SkillTypeChoices` | 处置 | 说明 |
|---|---|---|
| `BASIC_TOOL` (ReAct) | deepagent 主循环 | 直接对应,枚举值/类名保留 |
| `KNOWLEDGE_TOOL` | deepagent + KB 工具/预检索 | 直接对应 |
| `PLAN_EXECUTE` | deepagent 原生 `TodoListMiddleware` | 删手写 planner/replanner |
| `LATS` | **删除** | 无原生对应;无客户使用,直接下线。枚举值保留为 deprecated 别名,落到 deepagent 主循环以防存量数据炸 |
| ChatBot(默认) | deepagent(无/轻量工具) | 直接对应 |

`agent_factory.create_agent_instance` 的分支保留,但所有分支最终构造的 graph 内部都走 `build_deepagent_nodes`;差异仅在传入的 tools/skills/subagents/prompt 配置。

## 6. Tools & MCP

无结构性改动。`ToolsNodes.setup` 已产出 `self.tools`(langchain 工具 + MCP 工具)。迁移后直接 `create_deep_agent(tools=self.tools + [knowledge_retrieve])`。需验证:升级 langchain 后 `langchain-mcp-adapters` / `MultiServerMCPClient` API 兼容(见 §11 依赖矩阵)。

## 7. Skills(核心改动)

### 7.1 依赖升级
`deepagents 0.2.5 → 0.4.12`,连带对齐:`langchain≥1.3.11`、`langchain-core≥1.4.8`,以及 `langchain-openai/-anthropic/-community/-postgres/-experimental`、`langgraph`、`langgraph-prebuilt`、`langgraph-checkpoint-postgres`、`langgraph-supervisor`、`langchain-mcp-adapters` 的兼容版本(§11 给出待定矩阵,实施首阶段锁定)。

### 7.2 源 → 物化(SkillPackage → SKILL.md @ MinIO)
- **源**:`SkillPackage`(DB)继续作为权威源,含 `skill_markdown` / `manifest` / `required_tools` / `triggers` / `storage_path`。
- **物化**:在技能包**发布/启用**时,渲染成标准 DeepAgents skill 目录写入 MinIO:
  ```
  skills/<package_id>/SKILL.md          # YAML frontmatter(name, description≤1024) + 正文
  skills/<package_id>/scripts/...        # 来自 storage_path/extracted
  skills/<package_id>/references/...
  skills/<package_id>/assets/...
  ```
  `description` 由 `manifest.description` + `triggers` 合成,保证激活关键词命中。
- **运行时**:`create_deep_agent(skills=[<本次会话启用的 SKILL.md 路径>], backend=MinIOBackend)`。原生 SkillsMiddleware 启动时注入 frontmatter 摘要到 system prompt,agent 按需 `read_file` 读全文。

### 7.3 下线伪实现
`services/skill_package/runtime.py` 中"按触发词拼 prompt"的注入逻辑下线;`triggers`/匹配评分可保留**仅用于会话级技能预选**(决定本次 `skills=` 传哪些,避免全量注入 frontmatter)。

## 8. MinIO Backend 适配器

新增 `metis/llm/backends/minio_backend.py`,实现 deepagents `BackendProtocol`(6 方法):
`ls_info(path)`、`read(path,...)`、`grep_raw(...)`、`glob_info(pattern, path)`、`write(...)`、`edit(...)`。

- 复用项目现有 `django_minio_backend` / MinIO 客户端配置。
- 作为 **external storage** backend:`WriteResult/EditResult.files_update=None`(已落对象存储,不进 LangGraph state)。
- 命名空间隔离:`namespace = (bot_id 或 团队, "skills")`,支持多租户。
- 以 `StoreBackend`(`backends/store.py`)为实现参考(分页、路径↔key 转换、glob/grep 语义)。
- skills 目录**只读**为主;agent 的 `write_file`/`edit_file` 临时文件可走 deepagent 默认 state backend 或 MinIO 的可写命名空间(实施时二选一,默认临时文件走 state,skills 走 MinIO 只读 —— 用 `CompositeBackend` 组合)。

## 9. Knowledge Base(双模式)

- **工具模式(默认)**:封装 `knowledge_retrieve(query: str, kb_ids: list[str] | None)` 为 langchain 工具,内部复用现有 `naive_rag` / GraphRAG 检索服务,注入 `tools`。agent 自主决定检索时机与轮数。
- **预检索模式(可选)**:保留 `naive_rag_node`,由 `LLMSkill.enable_rag` + 配置开关控制;纯 RAG 问答场景省一次 LLM 决策开销。
- 两模式可叠加(先预检索给底料,再允许 agent 补检索)。

## 10. AG-UI / A2UI 流式适配(最高优先级)

- deepagent 仍是 `CompiledStateGraph`,继续 `astream(stream_mode="messages")`,现有 `agui_stream` 事件结构基本兼容。
- **新增内部工具事件**:deepagent 会产生 `write_todos`、`read_file`/`ls`/`glob_search`/`grep_search`/`edit_file`、子 agent 调用等内部工具事件。适配层(`AGUIStreamMiddleware` 或 `agui_stream` 增强)需:
  1. 把规划(todos)、skill 读取、子 agent 进度**映射为 AG-UI/A2UI 自定义事件**(对用户有价值的进度展示),或按配置静默过滤;
  2. 文本 / 思考块(Anthropic thinking)/ 业务工具调用映射**保持不变**;
  3. 保证 token 统计、trace_id 透传不丢。
- 这是保留项里唯一需要真正动脑的适配,设为实施重点验证项。

## 11. 依赖升级矩阵(实施首阶段锁定)

| 包 | 当前 | 目标(待 `uv` 解析锁定) |
|---|---|---|
| deepagents | 0.2.5 | 0.4.12 |
| langchain | 1.0.5 | ≥1.3.11 |
| langchain-core | (间接) | ≥1.4.8 |
| langgraph / -prebuilt | 1.0.3 / 1.0.5 | 兼容版 |
| langchain-openai/-anthropic/-community/-postgres/-experimental | 见 pyproject | 兼容版 |
| langgraph-checkpoint-postgres | 3.0.1 | 兼容版 |
| langgraph-supervisor | 0.0.30 | 兼容版(若仍使用;否则下线) |
| langchain-mcp-adapters | 0.1.12 | 兼容版 |

实施第一步:在隔离 worktree 用 `uv` 解析整套兼容版本并跑通 import,再继续。

## 12. 改动幅度评估

| 区域 | 幅度 | 说明 |
|---|---|---|
| 依赖升级 | 中-高(风险集中) | langchain 1.0→1.3 跨多个小版本,178 文件潜在受影响;但隔离在 opspilot |
| 引擎统一(`build_deepagent_nodes`) | 中 | 新增统一入口,旧 `build_react_nodes`/plan/replan/LATS 节点删除 |
| 删除手写特性 | 中(净删代码) | retry/reflection/动态池/budget/compaction/approval 等手写逻辑下线 → 代码净减 |
| Skills 物化 + MinIO backend | 中 | 新增物化管线 + ~1 个 backend 适配文件 |
| KB 工具化 | 低-中 | 包装现有检索为工具 |
| AG-UI/A2UI 适配 | 中(必须做对) | 事件映射,最高优先级验证 |
| 删 LATS | 低 | 直接下线 |

**净效果**:删除大量手写循环代码,新增"统一 deepagent 入口 + MinIO backend + skills 物化 + KB 工具 + AG-UI 适配"。属于**中等偏大但收敛、且代码总量大概率净减**的重构。

## 13. 分期实施计划(供 writing-plans 细化)

1. **P0 依赖落地**:worktree 内 `uv` 锁定 deepagents 0.4.x + langchain 栈兼容版,跑通 import 与现有 opspilot 单测基线。
2. **P1 统一引擎**:实现 `build_deepagent_nodes`(tools+MCP),让 `BASIC_TOOL` 走通端到端(非流式)。
3. **P2 AG-UI/A2UI 适配**:流式事件映射,达到与旧引擎等价的前端体验(重点验证项)。
4. **P3 KB 双模式**:`knowledge_retrieve` 工具 + 保留 `naive_rag_node` 开关。
5. **P4 MinIO backend + skills 物化**:backend 适配器、SkillPackage→SKILL.md 发布管线、原生 SkillsMiddleware 接通,下线伪 skills 注入。
6. **P5 收口**:Plan-Execute 切到原生规划、删 LATS、`agent_factory` 所有分支归一,删除手写特性死代码。
7. **P6 回归**:approval(interrupt_on)、compaction(summarization)、subagents 行为验证;按需补回被舍弃特性。

## 14. 风险与缓解

- **依赖级联回归**(主要风险):langchain 1.0→1.3 API 变更影响 178 文件。缓解:worktree 隔离 + 先锁版本跑 import/单测基线 + 分期。
- **AG-UI 回归**:deepagent 内部工具事件污染前端。缓解:P2 专项适配 + 与旧引擎逐事件对比。
- **舍弃特性导致行为回归**(token 失控、工具偶发失败无重试)。缓解:P6 验证,保留快速补 middleware 的入口。
- **存量技能数据**:`LLMSkill.skill_packages` 旧格式。缓解:物化管线兼容旧 manifest,`LATS` 枚举降级为别名。
- **MinIO 一致性/延迟**:skills 读取走对象存储。缓解:启动期物化 + 进程内缓存 frontmatter,运行时 `read_file` 才回源。

## 15. 不做(YAGNI)

- 不换 agent SDK(Claude Agent SDK / pi.dev)。
- 不为 LATS 重建树搜索。
- 不在本轮恢复 verification/rollback 等冷门手写特性,除非 P6 发现明确回归。
- 不改其它 app(LangChain 不被它们使用)。
