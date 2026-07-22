# Historical Superpowers change: 2026-07-03-opspilot-wiki-gap-analysis-progress

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-03-opspilot-wiki-gap-analysis-progress.md

- 对应文档:`server/docs/opspilot-wiki-llm-wiki-gap-analysis.md`(2026-07-02)
- worktree:`kb-remove`(分支 `claude/bold-tu-40b23d`)
- 评估日期:2026-07-03
- 范围:对照 gap analysis 9 项总体建议,记录当前 worktree 已完成/进行中/待补的项。

## 当前完成度

| 总体建议项 | 状态 | 关键证据 |
|---|---|---|
| 1. file/text/web 生命周期闭环 + MinIO 清理 | ✅ 已完成 | 提交 `205535689`;未提交 `services/wiki/parsed_storage_service.py` + `parsing/` 子模块 |
| 2. 规范标题/别名治理 | 🟡 核心已完成,缺合并预览 UI | `title_service.py` + `SettingsTab` Form.List;`graph_service._canonical_graph_nodes` 去重 |
| 3. 片段级溯源 + 长文档断点恢复 | 🟡 溯源已完成,断点恢复未做 | `source_trace` + `PageEvidence.locator`;未提交 `test_page_sources.py` 补测试 |
| 4. 索引/级联可观测(运行中状态/按阶段重试) | ✅ 已实现,UI 串通 | `cascade_service` + `index_rebuild_service` + `index_status_service`;`BuildRecordTab` 串通 `batch_retry_maintenance` |
| 5. 可操作检查队列(分配/动作/延期) | ✅ 已完成(本轮新增) | 本轮新增:`CheckItem.assignee/due_at/action_type` 字段、迁移 0064、`assign` 端点、CheckTab 分配 Modal |
| 6. 资料批量/文件夹导入(后端批次+失败汇总) | ✅ 已完成(本轮新增) | 本轮新增:`batch_create` 端点、`batch_ingest_materials_task`、`MaterialTab` 改用 `batchCreateMaterials` + 失败汇总 toast |
| 7. 图谱洞察(知识空白/惊奇连接/生命周期) | 🟡 基础已完成,可选扩展 | `graph_service.analyze_graph` 已输出 bridge/sparse/cross_community/strongest_edges;`knowledge_gap` 走 wikilink 缺失检查;`surprise_link` 未独立命名 |
| 8. QA 沉淀回 Wiki(候选页/对话快照) | 🟡 基础已完成,可选扩展 | `page_service.save_answer_candidate_page` + `wiki_page_view.save_answer(as_candidate=true)` + `source_conversation_id` 必填 |
| 9. Markdown 导入/导出治理增强(权限/审计/配额) | 🟡 核心已完成,治理未做 | `markdown_export_service.py` + `markdown_import_service.py`;**权限/审计/配额/失败重试**未做(第三阶段) |

## 本轮新增交付(未提交,本 worktree 增量)

### 后端服务(10 个)
- `services/wiki/cascade_service.py` — 5 阶段级联(relations/page_embedding/chunk_embedding/check_sweep/deleted_page_prune)+ 失败隔离 + 阶段选择
- `services/wiki/index_rebuild_service.py` — 页面级+分块级索引重建,统一 BuildRecord
- `services/wiki/index_status_service.py` — 派生 indexing/indexed/not_indexed/skipped/failed 中间态
- `services/wiki/sweep_service.py` — 检查项自动清扫(deleted_page_prune、sweep_open_checks)
- `services/wiki/title_service.py` — canonical_title + 通用别名表 + 生成规则合并
- `services/wiki/wikilink_enrichment_service.py` — 页面 wikilink 自动包裹
- `services/wiki/markdown_export_service.py` / `markdown_import_service.py` — 知识库 Markdown 导入导出
- `services/wiki/parsed_storage_service.py` — 解析产物落盘
- `services/wiki/text_utils.py` — 文本工具
- `services/wiki/parsing/` — MarkItDown 解析子模块(base / markitdown_parser / registry)

### 后端任务
- `tasks.wiki_batch_ingest_materials_task` — 批量资料解析,逐条隔离失败

### 后端 viewset 端点
- `wiki_material_view.batch_create` — 多文件一次性创建,失败汇总
- `wiki_check_view.assign` — 分配/延期/动作类型(可单字段或多字段)

### 模型 + 迁移
- `CheckItem.assignee / due_at / action_type` 字段
- 迁移 0064

### 后端测试(13 个新文件)
- `test_cascade_observability.py` / `test_title_service.py` / `test_wikilink_enrichment.py`
- `test_markdown_export.py` / `test_markdown_import.py`
- `test_page_sources.py` / `test_page_lifecycle_incremental.py`
- `test_batch_create.py` / `test_check_assign.py`
- `core/tests/test_logging_config.py`
- 配合 `parsing/` 子模块: `test_parsing*.py`(已在原 commits 落地)

### 前端 wiki 组件(改)
- `MaterialTab.tsx` — 改用 `batchCreateMaterials` + 失败汇总 toast
- `CheckTab.tsx` — 加"分配"按钮 + Modal(assignee/due_at/action_type)
- 其他:`OverviewTab/PageTab/SettingsTab/BuildRecordTab/CheckTab/GraphTab/GraphExplorer/GraphCanvas/WikiModifyModal/WikiQaAssistant` 都有不同程度的 spec 4 工作区对齐

### 前端 API + 类型
- `wiki.ts`: `batchCreateMaterials` + `assignCheck` + `MaterialBatchCreateResult`
- `types/wiki.ts`: `MaterialBatchCreateResult` + `CheckItem.assignee/due_at/action_type`

### 前端 Storybook/测试脚本(31 个 wiki-*.ts,全部通过)
- 覆盖:批量上传、文件夹、Markdown 导入导出、保存答案、设置危险区、批量维护、图谱可操作洞察/筛选稳定性/全屏 resize、上下文选项、标题别名、关系图谱来源追溯、构建记录影响页面、Wiki 搜索结果解释、批量删除、页面来源、批量删除、页面索引状态等

### i18n
- 新增 zh/en 各 9 项:`batchAddMaterialPartial` + 分配相关(`assign/assignee/dueAt/actionType` 等)

## 验证

- **后端 wiki 测试**:`pytest apps/opspilot/tests/wiki/` → **283 passed**
- **前端 wiki 脚本**:`for f in scripts/wiki-*.ts; do tsx $f; done` → **31/31 exit 0**

## 待办(不在本轮交付范围)

按 gap analysis 第一阶段对账,这些是"可选改进",可以分批后续处理:

1. **task 2 合并预览 UI**:`SettingsTab` 加"查看合并预览"按钮 + Modal,显示按 `title_aliases` 规则会合并哪些现有页面。需要后端预览接口 `wiki_kb_view.preview_merge`。
2. **task 3 阶段重试 UI 串通**:后端 `wiki_page_view.batch_retry_maintenance(stage=...)` 已实现,前端 `BuildRecordTab` 已有 `maintenanceStageFilter` 过滤,但需验证 stage 选择 + 批量重试的端到端流。
3. **task 6 独立 `surprise_link` 洞察**:当前 `strongest_edges` 实质承担,需要单独维度定义 + UI 标记。
4. **task 7 `chat_service` 自动落候选**:现在保存 QA 走 `wiki_page_view.save_answer(as_candidate=true)` 手动入口,可在 `chat_service` 内自动触发(避免 UI 漏触发)。
5. **task 8 Markdown 治理增强**:权限/审计/配额/失败重试。第三阶段范围,需要 `OperationLog` + 配额中间件 + 失败重试队列。

## 不在本轮范围(第三阶段)

- Deep Research 整模块
- Web Clipper
- MCP / OpenAPI
- Obsidian vault 兼容

## 提交策略

按功能领域拆 commit(工作树当前 65+ 改动文件 + 33 新文件):

1. **chore: 迁移重排** — 删 0061/0062,加 0062/0063/0064
2. **feat(wiki): 解析/存储/构建服务** — `parsing/` 子模块 + `parsed_storage_service` + `text_utils` + `wikilink_enrichment` + 既有 services 改造
3. **feat(wiki): 索引/级联可观测** — `cascade_service` + `index_rebuild_service` + `index_status_service` + `sweep_service` + `BuildRecord.maintenance` + `wiki_page_view` retry
4. **feat(wiki): 标题/别名治理** — `title_service` + `SettingsTab` Form.List
5. **feat(wiki): Markdown 导入/导出** — `markdown_export_service` + `markdown_import_service` + `wiki_kb_view` 端点
6. **feat(wiki): 检查队列分配/动作** — `CheckItem` 字段 + 迁移 0064 + `wiki_check_view.assign` + `CheckTab` Modal
7. **feat(wiki): 资料批量创建** — `batch_create` 端点 + `batch_ingest_materials_task` + `MaterialTab` 改用
8. **feat(wiki/web): 6 工作区对齐 spec 4** — OverviewTab/MaterialTab/PageTab/CheckTab/BuildRecordTab/GraphTab/SettingsTab
9. **test(wiki) + test(wiki/web)** — 后端 13 个测试 + 前端 31 个脚本
10. **docs(wiki) gap analysis 推进记录** — 本文档

后续可按用户确认后同步到 master。
