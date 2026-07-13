# OpsPilot Wiki(知识库)开发设计方案

> 适用分支:`claude/bold-tu-40b23d`。代码路径以 `server/apps/opspilot/` 为根。
> 一句话定位:**以"页面(Page)"为中心、由 AI 从"资料(Material)"持续构建、可被多个智能体复用的知识库**。

---

## 0. 核心问题速答:文档上传后如何变成 md?是用 markitdown 吗?

**不是 markitdown。** 整条转换链没有引入 `markitdown`(微软 MarkItDown)。`markdownify` 虽是依赖,但只用于 `metis/llm/tools/fetch/formatter.py`(LLM 的网页抓取工具),**不参与 Wiki 资料解析**。

文档转换由 `metis/llm/loader/` 下**按文件类型分派的 loader** 完成(`services/wiki/material_service.py:_extract_file_text`):

| 类型 | Loader | 底层库 | 是否需 OCR |
|---|---|---|---|
| `.txt/.text/.csv` | `TextLoader` | 标准库读文件 | 否 |
| `.md/.markdown` | `MarkdownLoader` | 直接读取(保留 markdown) | 否 |
| `.xlsx/.xls` | `ExcelLoader` | pandas/openpyxl | 否 |
| `.pdf` | `PDFLoader` | PyMuPDF(fitz)+ tabula | **可选**(loader 原生抽文本;OCR 仅增强内嵌图片) |
| `.docx` | `DocLoader` | python-docx | 可选 |
| `.pptx` | `PPTLoader` | python-pptx | 可选 |
| `.png/.jpg/.jpeg` | `ImageLoader` | RapidOCR / Tesseract / 云 OCRProvider | **必须**(无 OCR → 空 → failed) |
| `web`(URL) | `_fetch_url` + `_html_to_text` | requests + 标准库 `html.parser`(剥离 script/style) | 否 |
| `text`(纯文本) | `RawLoader` | 包装 text_content | 否 |

**关键认知:**
1. 各 loader 返回的是**纯文本**(`_docs_to_text` 把每段 `page_content` 以 `\n\n` 拼接),**并非严格的 markdown**——只有 `.md` 文件本身保留 markdown 语法,其余是"抽取出的文本"。
2. **真正的 markdown 是后面 LLM 生成的**:构建阶段 LLM 被要求输出 `{"body":"markdown"}`(见 §4),知识页面正文才是 markdown。所以"变成 md"发生在 **AI 生成知识页面**这一步,而不是文件转换这一步。
3. 抽取出的全文**不落库**:只把 `SHA256(text)` 存进 `Material.content_hash`(用于变更检测),把 LLM 摘要存进 `Material.ai_summary`(作为后续构建输入)。原始文件留在 MinIO。

> 注:`material_service.py` 顶部模块 docstring 写着"PDF/Office/网页仍待接入"——这是**过时注释**,真实 `_extract_file_text` 已接入,建议后续清理该 docstring。

---

## 1. 数据模型(`models/wiki_mgmt.py`)

```
WikiKnowledgeBase ──< Material ──< MaterialVersion
       │                  │
       │                  └──< PageEvidence >── KnowledgePage ──< PageVersion(版本/候选)
       │                                              │              └── embedding(JSON 向量)
       │                                              ├──< PageChunk(分块 + embedding)
       │                                              └──< PageRelation(页面间链接)
       ├──< BuildRecord(构建记录)
       └──< CheckItem(检查/审核事项)
```

| 模型 | 关键字段 | 说明 |
|---|---|---|
| `WikiKnowledgeBase` | `llm_model`(FK)、`embed_provider`(FK)、`purpose_md`、`schema_md`、`generation_language` | 库级配置:推理模型、嵌入模型、用途、结构骨架 |
| `Material` | `material_type`(text/file/web)、`file`(MinIO)、`text_content`、`url`、`content_hash`、`ai_summary`、`status` | 资料;状态 pending→parsing→done/failed |
| `MaterialVersion` | `content_locator`、`content_hash` | 资料版本(模型已建,当前实现未主动写入) |
| `KnowledgePage` | `page_type`、`title`、`tags`、`current_version`、`contribution`(ai/human/mixed)、`status`(active/archived/source_invalid) | 知识页面 |
| `PageVersion` | `no`、`body`、`embedding`、`change_type`、`is_current`、`build_record` | 页面版本;`change_type`=ai_create/ai_merge/material_update/rebuild/restore/human_edit/**candidate** |
| `PageChunk` | `idx`、`text`、`heading_path`、`embedding` | 按标题分块,块级向量 |
| `PageRelation` | `from_page`、`to_page`、`relation_type`(reference/shared_source/ai_identified)、`weight`、`via_material` | 页面间链接 |
| `PageEvidence` | `page`、`material` | 页面 ↔ 资料 的证据/来源关联 |
| `BuildRecord` | `trigger`、`stage`、`status`、`inputs`、`counts`、`affected_pages`、`errors` | 构建记录(长期审计) |
| `CheckItem` | `check_type`、`status`、`related`、`candidate_version`、`suggested_actions` | 检查/审核事项 |

---

## 2. 端到端流水线总览

```
上传资料 ──(异步)──> 解析为文本 ──> SHA256 + AI 摘要 ──> status=done
                                                  │
              用户/规则触发构建 ──────────────────┘
                    │
   ┌── Stage1: LLM 抽取要点(facts)
   └── Stage2: LLM 依据 Purpose/Schema 生成页面(body=markdown)
                    │
        创建 KnowledgePage + PageVersion(ai_create, is_current) + PageEvidence
                    │
        rebuild_relations:建立 PageRelation(shared_source / reference)
                    │
   (可选,需手动触发)reindex:页面/分块 embedding 入库
                    │
   检索:keyword / semantic / hybrid ──> augment_prompt 注入聊天上下文(RAG + [n] 引用)
                    │
   资料更新 ──> propose_update:一律生成候选版本 + CheckItem ──> 「检查与审核」人工确认
```

异步任务(`tasks.py`):
- `wiki_ingest_material_task` → `material_service.ingest_material`(解析 + 摘要)
- `wiki_build_material_task` → `build_service.build_from_material`(构建页面)
- `wiki_propose_update_task` → `update_service.propose_update`(安全合并 → 待审)
- `wiki_rebuild_kb_task` → `rebuild_service.rebuild_knowledge_base`(Schema/Purpose 变更后整库重建)

---

## 3. 资料解析与摘要(`services/wiki/material_service.py`)

### 3.1 解析(`ingest_material` → `extract_text`)
- 按 `material_type` 分派:text→RawLoader、file→`_extract_file_text`(见 §0 表)、web→`_extract_web_text`。
- 文件流程:从 MinIO 读 bytes → 写临时文件 → loader.load() → `_docs_to_text` 拼纯文本 → 删临时文件。
- OCR:`_build_ocr` 优先用已启用的 `OCRProvider`,否则回退本机 `RapidOCR`(纯 pip)→ `TesseractOCR`;PDF/docx/pptx 无 OCR 也能取文本,图片必须 OCR。
- 失败有精准原因(`_ingest_failure_reason`):未传文件 / 需 OCR 的扫描件 / 网页不可达 / 类型不支持。

### 3.2 摘要(`_llm_summarize`)
- 用 KB 的 `llm_model` 调用 `LLMClientFactory.invoke_isolated`(OpenAI 兼容协议),`temperature=0.3`。
- Prompt:`"请用简洁中文为下面的资料生成一份摘要,保留关键事实、概念与结论,作为后续知识构建的上下文。# 资料正文 {text[:8000]}"`。
- 无模型或失败:回退为截断文本(前 500 字)。
- **摘要即后续构建的输入**(§4),因此 file/web 资料的知识构建实际基于"摘要"而非全文(取舍:省 token、但会丢细节)。

---

## 4. 知识构建(`services/wiki/build_service.py`)

### 4.1 两段式生成(`build_from_material`)
- 构建输入:`text = material.ai_summary or material.text_content`。
- **Stage1 `_llm_extract_facts`**:从资料抽取"稳定、可复用、对运维有价值的关键事实",每行一条。
- **Stage2 `_llm_generate_pages`**:依据 `purpose_md` + `schema_md`,从要点生成页面;**只输出 JSON** `{"pages":[{"page_type","title","tags","body(markdown)"}]}`;`page_type` 必须来自 Schema 定义。
- 对每个 page:建 `KnowledgePage`(contribution=ai)+ `PageVersion`(no=1, change_type=`ai_create`, is_current=True, 关联 build)+ `PageEvidence`(挂资料来源)。
- 构建末尾调用 `rebuild_relations`(§6)重建链接。

`Purpose/Schema` 的作用:`purpose_md` 指导"该建什么知识/给谁看",`schema_md` 定义"合法的 page_type 与页面骨架"。二者只在 Stage2 提示词中注入。

### 4.2 BuildRecord 生命周期
- `trigger`:material / material_update / material_delete / rebuild。
- `stage`:queued → generating → done/failed。
- `status`:running → success / partial / failed。
- `counts`:`{new, updated, unchanged, pending_review}`——初次构建 `new=新建页数`;更新 `updated/pending_review`;删除 `pending_review=被置为缺源的页数`。
- `inputs`:`{material_id}`(或 `{material_id, material_name}`、整库重建 `{schema_len}`)——前端"输入资料"即据此解析为资料名。

---

## 5. 更新与安全审核(`services/wiki/update_service.py` + `check_service.py`)

**策略:任何资料更新都不自动生效。** `propose_update` 对受影响页面(经 PageEvidence 关联到该资料的页)用 LLM 重写正文(`_default_generator`, temp=0.2),然后 `apply_material_update` → **一律 `create_candidate`**:
- 生成 `PageVersion(change_type="candidate", is_current=False)`(候选版本,不动当前有效版本);
- 生成 `CheckItem(check_type="material_update", status="open", candidate_version=候选)`,`suggested_actions=[accept,reject,edit_accept]`。

审核动作(`check_service`):
- `accept_candidate`:候选置 `is_current=True`、旧版本下线、CheckItem→resolved;若原页是 human 则升级为 mixed。
- `reject_candidate`:删候选、CheckItem→dismissed,当前版本不变。

系统检查扫描(`scan_health`):孤立 / 缺有效来源 / 来源全失效 / 过期 / 疑似重复(同标题同类型,整组进一条 `related.pages`)/ 冲突(同标题不同类型)/ 失效关系 / 低置信。这些是 scan 类检查(无候选版本,只能"忽略")。

> 概览页"风险"卡 = `CheckItem.filter(status="open")` 按 `check_type` 分组计数。

---

## 6. 建链(`services/wiki/relation_service.py`)

`rebuild_relations(kb)`(幂等:先删全量再重建,构建后自动调用,也有 API):
- **shared_source(确定信号)**:扫 `PageEvidence`,共享 ≥1 份资料的页面互链;`weight=共享资料数`,`via_material=min(共享)`;无向(强制 `from.id < to.id` 去重)。
- **reference(确定信号)**:正则 `\[\[\s*([^\[\]]+?)\s*\]\]` 解析页面正文里的 `[[标题]]`,有向(引用方→被引用方),`weight=1.0`。
- **ai_identified**:模型已留字段,**当前未实现**(P5 语义关系探测占位)。

---

## 7. 索引/嵌入(`services/wiki/embedding_service.py`)

- 向量存 `PageVersion.embedding` 与 `PageChunk.embedding`(JSONField 存 float 列表,**无需 pgvector**)。
- 嵌入模型来自 `WikiKnowledgeBase.embed_provider`(OpenAI 兼容 `client.embeddings.create`)。
- 分块:`chunk_markdown` 按 markdown 标题切,过长段(>800 字)再按 `max_chars` 切,产出 `{idx, text, heading_path}`。
- **重要:嵌入与构建解耦**——构建/解析过程**不自动**生成 embedding,需显式调用 `reindex` / `reindex_chunks` API。缺 embed_provider 时静默跳过,不影响构建。

---

## 8. 检索与 RAG(`retrieval_service.py` + `wiki_context_service.py`)

三种检索:
- **keyword(MVP 默认)**:分词(中文加 bigram)→ 打分(标题×5、正文×1、资料名×2、摘要×1)。kind=`page` / `material_summary`。
- **semantic**:查询向量 vs 存量 `PageVersion.embedding` 余弦相似(需先 reindex)。
- **hybrid**:keyword 召回 top-20 → 候选嵌入 → RRF 融合(k=60)。

`answer()`:keyword 取 top-5 上下文 → LLM 作答 → 返回 `{answer, citations, contexts}`。

**聊天 RAG(`wiki_context_service`)**:`build_context` 跨多个 KB 检索 → `augment_prompt` 把"【相关知识库信息】+ [n]《标题》(知识库:X)+ 片段"注入系统提示,并强约束"严格依据知识库、末尾 `[n]` 标注引用、未覆盖则回复『知识库中暂无相关内容』"(本会话加固的防编造);citations 结构 `{n, kb_id, kind, id, title}`,经 AGUI `wiki_citations` CUSTOM 事件透传给前端,渲染为可点击引用。

---

## 9. 关系图谱(`services/wiki/graph_service.py`)

- `build_graph`:节点=页面(含 page_type/contribution/degree/cluster),边=PageRelation;用**连通分量**做粗聚类;insights 给 node/edge/cluster 计数、孤立点、最大簇、hubs(度 top5)。
- `analyze_graph`(进阶):4 信号加权 `{shared_source:1.0, reference:0.8, shared_tags:0.6, same_type:0.3}` 计算边权 → **纯 Python Louvain/标签传播**做社区发现(无 numpy/sklearn 依赖,跨 DB 可用);insights 给 `strongest_edges` top5、社区列表。
- 前端 `GraphExplorer`/`GraphCanvas`(@antv/g6)消费上述数据,全屏 + 过滤 + 社区图例 + 悬浮 tip。

---

## 10. 现状与取舍小结

**已实现:** 解析(text/file 含 pdf/docx/pptx/xlsx + 图片 OCR + web)、摘要、两段式构建、安全合并 + 检查审核、shared_source/reference 建链、keyword/semantic/hybrid 检索、聊天 RAG + 引用、连通分量 + Louvain 图谱、人工建/改页、版本对比/恢复。

**待办 / 占位:**
- `ai_identified` 语义关系(P5)未实现。
- 嵌入需手动 reindex,未挂到构建流水线(可考虑构建后异步触发)。
- 构建以"AI 摘要"为输入而非全文,长文档会丢细节(可引入分块构建)。
- `MaterialVersion` 模型已建但未主动写入(资料版本化未启用)。
- `material_service.py` 模块 docstring 过时(称 PDF/Office 未接入),需清理。

**关键取舍:**
- 向量用 JSONField 而非 pdvector → 部署简单、跨 7 种 DB,但大规模检索性能有限。
- 图算法纯 Python → 无重依赖、可在任意 DB 环境跑,但超大图性能有限。
- 更新一律走人工审核(候选版本) → 安全、可追溯,但有人工成本。
