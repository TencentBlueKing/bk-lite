# Historical Superpowers change: 2026-06-22-opspilot-wiki-technical-architecture

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-22-opspilot-wiki-technical-architecture-design.md

- 日期: 2026-06-22
- 工作分支/worktree: `claude/bold-tu-40b23d`(worktree `kb-remove`,已删除旧知识库 + 合入 master)
- 配套产品设计: [2026-06-18-opspilot-enterprise-llm-wiki-design.md](2026-06-18-opspilot-enterprise-llm-wiki-design.md)
- 参考实现: `nashsu/llm_wiki`(本地 `D:\app\github\llm_wiki`)+ Karpathy `llm-wiki.md` 范式
- 约束: 旧知识库已删除、旧数据不迁移不兼容;新知识库从零创建。本设计只产出**总体技术架构 + 分期路线图**,每期再单独出实现计划。

---

## 1. 背景与定位

产品设计(2026-06-18)定义了一个由 AI 持续构建/维护、供多个智能体复用的结构化知识 Wiki:原始资料是事实证据,知识页面是 AI 编译 + 人工维护的可演进知识;Schema 驱动生成,安全更新,全程可追溯,隐藏 RAG 技术细节。

本文件把该产品设计落到 bk-lite/opspilot 的具体技术架构,并基于 `llm_wiki` 源码分析校准了技术选型。

### 1.1 llm_wiki 关键结论(校准依据)
- **存储**:llm_wiki 是 Tauri 桌面应用,页面是 `wiki/*.md` 文件 + git 版本 + 可选 LanceDB。**不适合直接照搬**到 Web 平台。
- **检索**:默认是「分词关键词检索 + 图谱关联度」;向量(LanceDB)**可选**,用 **RRF** 融合;**无 reranker**。核心导航靠 `index.md` 目录 + 页面链接,"avoids the need for embedding-based RAG infrastructure"。
- **图谱**:页面"互联"是核心(`related:` 链接),但**图可视化是浏览辅助**(Karpathy 用 Obsidian 自带 graph view;nashsu 的 4-signal + Louvain 是增强项,按需从链接算)。
- **构建**:两步 CoT(分析→生成)+ 风险闸门 + 异步审核是核心机制。

### 1.2 由此确定的技术取舍
- 存储用 **Postgres**(页面/版本/关系/构建/检查)+ **MinIO**(资料文件/图片);版本用 **DB 版本表**(非 git)。
- 检索 MVP 用 **Postgres 全文检索 + 关系信号**;**pgvector + 嵌入**列为后期**可选**;**不做 rerank**。
- 关系**数据**进核心;关系**图可视化**后置为独立可选一期。
- 资料解析层(loader)从 git 恢复复用。

---

## 2. 架构总览

```
前端  web/src/app/opspilot/(pages)/knowledge/      6 个工作区(重建)
        │  /api/proxy → DRF
后端  apps/opspilot/
  ├─ models/wiki_mgmt.py            数据模型(新)
  ├─ viewsets/ serializers/         DRF 接口(按资源)
  ├─ services/wiki/                 构建管道 / 合并 / 检查 / 检索 / 问答
  ├─ metis/llm/loader/              资料解析(从 git 恢复:文件/网页/文本/PDF/Office)
  ├─ metis/llm/chain|agent|common   复用现存 LLM 调用层(Stage1/2、问答)
  ├─ tasks.py (Celery)              异步构建 / 重建 / 网页同步
  └─ 复用 LLMModel/EmbedProvider/OCRProvider 配置
存储  Postgres + MinIO
检索  Postgres 全文 + 关系信号(pgvector 后置可选,无 rerank)
```

- **模块归属**:仍在 `opspilot` Django 应用内,新建 `wiki_mgmt` 模型文件;前端复用 `(pages)/knowledge/` 路径(用户心智仍是"知识库")。
- **复用现存能力**:`LLMModel`/`EmbedProvider`/`RerankProvider`/`OCRProvider` 配置模型、`metis/llm/common/llm_client_factory`、`metis/llm/chain` 均存活,可直接复用。

---

## 3. 数据模型(核心实体)

| 模型 | 关键字段 | 作用 |
|---|---|---|
| **KnowledgeBase** | name, team[], `purpose_md`, `schema_md`, llm_model FK, embed_provider FK(可空,后期), 生成语言/规则, 自动/风险规则(JSON), 网页同步策略, status | 知识库本体;独立资产,多智能体复用 |
| **Material**(资料) | kb FK, type(文件/网页/文本), source_ref(MinIO path/url/text), content_hash, status(待构建/构建中/完成/部分/失败/已更新/已失效), `ai_summary`, current_version FK | 原始证据 + AI 摘要 |
| **MaterialVersion** | material FK, content_snapshot/locator, hash, captured_at | 网页快照 / 资料更新留版 |
| **KnowledgePage**(知识页面) | kb FK, type(由 schema 定), title, tags[], current_version FK, contribution(AI/人工/混合), created_by/updated_by/method, status | AI 编译 + 人工维护的可演进知识 |
| **PageVersion**(页面版本) | page FK, no, body(md), meta 快照(JSON), change_type(人工编辑/AI 创建/AI 合并/资料更新/全量重建/恢复/**候选**), build_record FK, is_current, created_by | 全量版本/diff/恢复;**风险变更=候选版本**(is_current=false) |
| **PageRelation**(关系) | from_page FK, to_page FK, type(引用/共同来源/AI 识别), weight, via_material FK | 互联**关系数据**(核心;图可视化后置) |
| **PageEvidence**(证据) | page FK, material FK, material_version FK, locator/snippet | 页面→资料可追溯 |
| **BuildRecord**(构建记录) | kb FK, trigger, operator, 输入资料+版本(JSON), stage, progress, counts(新增/更新/未变/待审 JSON), 受影响页面, errors/warnings, status | 长期"资料→知识"加工档案 |
| **CheckItem**(检查/审核) | kb FK, type(冲突/重复/过期/缺失/孤立/失效关系/缺来源/低置信/无法合并/来源全失效/不符 Schema), status, 关联页/资料(JSON), candidate_version FK, suggested_actions(JSON) | §4.5+§10.2 风险统一承载 |
| *(后期)* **PageChunk** | page FK, idx, text, heading_path, `embedding`(pgvector) | 可选语义检索,P6 |

设计要点:
- **候选版本不单独建表**:复用 `PageVersion`(change_type=候选 + is_current=false)+ `CheckItem` 关联,避免双状态。
- **Purpose/Schema 只存 Markdown**(KnowledgeBase 的 `purpose_md`/`schema_md` 文本字段),不维护表单+MD 两套状态;AI 辅助修改最终写回 MD。
- 资料文件/图片走 **MinIO**(复用 `django_minio_backend`);页面正文/版本/关系/构建/检查全部入 **Postgres**。

---

## 4. 构建管道(对标 llm_wiki 两步法)

Celery 任务编排 + `metis/llm/chain` 调 LLM,每份资料经过:

1. **解析**(loader):正文 + 可选多模态图片(PDF/Office/网页/文本)。
2. **AI 摘要 / 分析(Stage1)**:依据 `purpose_md` 识别与目标相关的信息,产出资料摘要。
3. **风险闸门**:判定普通变更 vs 风险变更。
4. **生成/更新页面(Stage2)**:依据 `schema_md` 决定页面类型/字段/结构,创建新页面或更新已有页面。
5. **3 路合并**:LLM 版 vs 人工编辑 vs 上一版本;**保护人工内容**,无法安全合并→候选版本。
6. **建关系 + 证据**:页面引用、共同来源、AI 识别关系;页面↔资料证据。
7. **检查**:冲突/重复/缺失/低置信等写入 `CheckItem`。
8. **写版本**:普通变更立即生效(新版本 is_current=true);风险变更生成候选版本,当前有效版本不动。

全过程进度/计数写入 `BuildRecord`;失败保留可恢复阶段(对标产品 §13 异常处理)。一份资料可生成/更新多篇页面。

---

## 5. 检索与问答

- **检索**:Postgres 全文检索(知识页面 + 资料摘要)+ 关系信号;多路结果用 **RRF** 融合(K=60,对标 llm_wiki);**无 rerank**;`pgvector` 语义检索为 P6 可选增强。
- **问答试用**(概览内):检索 → `metis/llm/chain` 带页面上下文作答 → 回答展示引用的知识页面 → 可追溯到资料证据;资料不足时明确说明;支持多轮/重生成。
- 问答优先用知识页面,资料摘要作补充上下文,原始资料是最终证据。

---

## 6. 前端(6 工作区,复用 `(pages)/knowledge/`)

按产品 §4:**概览 / 资料 / 知识(页面;关系图后置)/ 构建记录 / 检查与审核 / 设置**。全程不向普通用户暴露分块、召回阈值、候选数、重排数等 RAG 参数。

---

## 7. 实现策略:从 git 复用 + 转换式迁移

利用"旧代码都在 git、删除迁移尚未应用"两点:

- **从 git 恢复可复用代码作为起点**(而非从零写):
  - `metis/llm/loader/`(文件/文本/网页/PDF/Office 解析)→ 直接复用做资料解析层。
  - `metis/llm/embed/`、`metis/llm/chunk/` → 留给 P6"可选向量"复用。
  - 旧 `KnowledgeBase`/`KnowledgeDocument(File/Web/Manual)` + 摄取 tasks(上传/解析/网页同步)→ 作为新 `KnowledgeBase`/`Material` 骨架,改造为 page-centric。
  - **不恢复**:`QAPairs`/`KnowledgeGraph`/`GraphChunkMap`、`rerank`、graphiti(旧 RAG 心智)。
- **迁移**:**不应用裸删除迁移**(当前 worktree 的 `0059_remove_fileknowledge…`)。改为:恢复/新增模型后,从"当前已应用状态(旧表仍在)"重新 `makemigrations`,生成一条**转换式迁移**(删 RAG 专用表、复用/改 KB+资料表、新建 页面/版本/关系/证据/构建/检查 表)。旧数据不保留(符合产品 §1),但省去无谓 drop+recreate 且复用代码。

> 注:当前 worktree 处于 merge(未提交)状态;落地时先按本策略把"裸删除"调整为"转换式迁移"。

---

## 8. 分期路线图(依赖有序,每期独立可交付 + 单独 plan)

| 期 | 内容 | 价值 |
|---|---|---|
| **P0 地基** | 数据模型(git 复用 + 转换迁移)、KB CRUD、团队权限、Purpose/Schema(MD+模板+AI 辅助)、创建知识库流程、精简 loader、MinIO | 能建库、能定义目标 |
| **P1 摄取+构建(核心)** | 资料工作区(文件/网页/文本)、解析、AI 摘要、Stage1/2 按 Schema 生成、3 路合并保护人工、关系+证据、构建记录、页面浏览/编辑/版本 | **核心闭环:资料→互联知识页面** |
| **P2 安全更新+检查审核** | 风险闸门、候选版本、检查与审核工作区+动作、版本 diff/恢复、资料更新/删除影响与级联(归档纯 AI、保护人工) | 生产可信:不污染有效知识、保护人工 |
| **P3 概览+检索+问答试用** | 全文+关系检索(RRF)、概览健康摘要、问答(引用+追溯) | 用户可验证准确性/可追溯 |
| **P4 多智能体复用(北极星)** | 技能/智能体选知识库、聊天链从页面检索作答(把基于页面的检索接回 chat chain) | 把"知识"以新形态接回智能体 |
| **P5 关系图可视化(可选)** | 图视图、4-signal 关联度、Louvain 聚类、图洞察(孤立/桥接/缺口)→ 检查 | 知识健康洞察 |
| **P6 语义向量+网页定时+全量重建(可选)** | pgvector+嵌入(复用 EmbedProvider)RRF、chunk(git 复用)、网页定时刷新、Schema 变更全量重建 | 语义增强与长期演进 |

**P0–P4 是产品成立主线;P5/P6 可选靠后。** 每期完成后单独进入 writing-plans 出实现计划。

---

## 9. 不在本架构范围(沿用产品 §17)

- 旧知识库迁移/兼容、通用 API/DB/第三方连接器、网站递归爬取、正式评测中心、草稿/审批/发布 CMS 工作流、图上直接编辑关系、独立知识图谱训练与 GraphRAG 配置、面向普通用户的分块/召回参数、Deep Research、Chrome 剪藏扩展。
- 本设计额外明确:MVP 不引入 pgvector、嵌入与 rerank(P6 可选)。

---

## 10. 验收(技术侧,呼应产品 §15)

- 用户无需理解分块/向量/召回/重排即可构建知识库(参数不暴露)。
- 一份资料可生成并更新多篇 Schema 定义的页面;页面与资料摘要均可参与全文检索与问答。
- 每条 AI 知识可追溯至资料证据;人工内容不被 AI 静默覆盖;风险变更不污染当前有效版本。
- 资料更新/删除/全量重建均有完整构建记录;所有版本可比较与恢复。
- 知识库可被多个智能体复用(P4)。
- 关系图与语义向量为可选增强(P5/P6),缺失不影响核心闭环。
