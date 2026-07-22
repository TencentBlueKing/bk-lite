# Historical Superpowers change: 2026-07-03-opspilot-wiki-commit

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-07-03-opspilot-wiki-commit-plan.md

> 状态:**仅 plan,未 commit**。按 auto-sync 记忆,worktree 不主动 commit/push,等用户下令。
> 评估日期:2026-07-03

## 拆分原则

按功能领域拆分,每个 commit 自带门禁(对应测试/脚本可在拆分前单跑通过)。

10 个 commit,顺序按依赖关系:**先迁移/后端模型 → 后端服务 → 后端视图/任务 → 后端测试 → 前端 → 文档**。

---

## Commit 1:chore(wiki) 迁移重排

**文件**:
- `D server/apps/opspilot/migrations/0061_buildrecord_checkitem_knowledgepage_material_and_more.py`
- `D server/apps/opspilot/migrations/0062_material_sync_policy.py`
- `A server/apps/opspilot/migrations/0062_buildrecord_checkitem_knowledgepage_material_and_more.py`
- `A server/apps/opspilot/migrations/0063_buildrecord_maintenance.py`
- `A server/apps/opspilot/migrations/0064_checkitem_assignee_due_at_action_type.py`

**说明**:
- 0061/0062 是旧 wiki 迁移,与 master 演进冲突,删除。
- 0062/0063 重建 wiki 核心数据模型(BuildRecord/CheckItem/KnowledgePage/Material/PageEvidence/PageRelation/PageChunk 等)+ BuildRecord.maintenance 字段。
- 0064 本轮新增,扩 CheckItem 为可操作任务队列(assignee/due_at/action_type)。

**Commit message**:
```
chore(opspilot): 重排 wiki 迁移 + CheckItem 任务队列字段

- 删除 wiki 旧迁移 0061/0062(与 master 演进冲突)
- 新增 0062/0063 重建 wiki 核心数据模型,合并 0064(本轮新增 CheckItem 任务队列字段)
- 0063: BuildRecord.maintenance 落库级联维护结果
- 0064: CheckItem.assignee / due_at / action_type
```

---

## Commit 2:feat(wiki) 解析/存储/构建服务

**文件**:
- `A server/apps/opspilot/services/wiki/parsing/__init__.py`
- `A server/apps/opspilot/services/wiki/parsing/base.py`
- `A server/apps/opspilot/services/wiki/parsing/markitdown_parser.py`
- `A server/apps/opspilot/services/wiki/parsing/registry.py`
- `A server/apps/opspilot/services/wiki/parsed_storage_service.py`
- `A server/apps/opspilot/services/wiki/text_utils.py`
- `A server/apps/opspilot/services/wiki/wikilink_enrichment_service.py`
- `M server/apps/opspilot/services/wiki/build_service.py`(适配 MarkItDown parser)
- `M server/apps/opspilot/services/wiki/material_service.py`(适配 parser + 落盘)
- `M server/apps/opspilot/services/wiki/embedding_service.py`
- `M server/apps/opspilot/services/wiki/update_service.py`
- `M server/apps/opspilot/services/wiki/rebuild_service.py`
- `M server/apps/opspilot/services/wiki/relation_service.py`
- `M server/apps/opspilot/services/wiki/retrieval_service.py`
- `M server/apps/opspilot/services/wiki/overview_service.py`
- `M server/apps/opspilot/services/wiki/wiki_context_service.py`
- `M server/apps/opspilot/services/wiki/page_service.py`
- `M server/apps/opspilot/services/wiki/check_service.py`
- `M server/apps/opspilot/services/wiki/graph_service.py`
- `M server/apps/opspilot/services/chat_service.py`(适配 save_answer_candidate)

**说明**:
- 重组解析子模块,统一 `base`/`markitdown_parser`/`registry` 接口
- 解析产物统一落盘到 `wiki/parsed/<kb>/<material>/<hash>.md`
- wikilink 自动包裹(只在首次出现处包)

**Commit message**:
```
feat(wiki): 解析子模块重组 + 产物落盘 + wikilink 自动包裹

- 解析子模块 parsing/{base,markitdown_parser,registry} 统一 loader 接口
- 解析产物 parsed_storage_service 落盘到 wiki/parsed/<kb>/<material>/<hash>.md
- wikilink_enrichment_service: 自动包裹首次出现的 [[title]]
- build/material/page/check/graph 等服务适配新解析链
```

---

## Commit 3:feat(wiki) 索引/级联可观测

**文件**:
- `A server/apps/opspilot/services/wiki/cascade_service.py`
- `A server/apps/opspilot/services/wiki/index_rebuild_service.py`
- `A server/apps/opspilot/services/wiki/index_status_service.py`
- `A server/apps/opspilot/services/wiki/sweep_service.py`
- `M server/apps/opspilot/viewsets/wiki_page_view.py`(新增 retry_maintenance / batch_retry_maintenance)
- `M server/apps/opspilot/services/wiki/relation_service.py`
- `M server/apps/opspilot/services/wiki/embedding_service.py`

**说明**:
- 5 阶段级联(relations / page_embedding / chunk_embedding / check_sweep / deleted_page_prune)
- 阶段选择 + 失败隔离
- 索引重建统一 BuildRecord 格式
- 索引状态派生 indexing 中间态
- 检查项自动清扫

**Commit message**:
```
feat(wiki): 索引/级联可观测 + 按阶段重试

- cascade_service: 5 阶段级联维护(关系/页面嵌入/分块嵌入/检查清扫/删除清理),失败隔离,支持按 stage 选择
- index_rebuild_service: 页面级+分块级索引重建,统一 BuildRecord
- index_status_service: 派生 indexing/indexed/not_indexed/skipped/failed 中间态
- sweep_service: 检查项自动清扫(deleted_page_prune、open check 失效清扫)
- wiki_page_view.retry_maintenance / batch_retry_maintenance(stage=): 按阶段重试
```

---

## Commit 4:feat(wiki) 标题/别名治理

**文件**:
- `A server/apps/opspilot/services/wiki/title_service.py`
- `M server/apps/opspilot/services/wiki/graph_service.py`(`_canonical_graph_nodes` 去重)

**说明**:
- canonical_title + 通用别名表(CMDB/作业平台/GSE 等)
- 通用变体剥离(括号、空格)
- 与 graph_service 集成:同义节点合并、aliases 收集

**Commit message**:
```
feat(wiki): 标题归一 + 通用别名表 + 图谱同义节点去重

- title_service.canonical_title / title_alias_map / title_alias_terms_for_enrichment
- 通用别名表(CMDB → 配置平台、Job → 作业平台、GSE → 管控平台 等)
- 变体剥离(全角/半角括号、空格、连字符)
- graph_service._canonical_graph_nodes: 同义节点合并,避免多孤立节点
```

---

## Commit 5:feat(wiki) Markdown 导入/导出

**文件**:
- `A server/apps/opspilot/services/wiki/markdown_export_service.py`
- `A server/apps/opspilot/services/wiki/markdown_import_service.py`
- `M server/apps/opspilot/viewsets/wiki_kb_view.py`(export_markdown / import_markdown 已存在,补 roundtrip)

**说明**:
- Markdown 单文件 + zip 导出
- Markdown 导入解析 frontmatter(同标题同类型非归档页生成新版本,不重复建页)
- 导入触发增量级联维护

**Commit message**:
```
feat(wiki): Markdown 单文件/zip 导入导出 + 增量级联

- markdown_export_service: 知识库所有非归档页 + 资料 → 单 md 或 zip
- markdown_import_service: 解析 frontmatter,同标题同类型非归档页生成新版本;触发级联维护
- 导入时调用 cascade_service 维护关系、索引、检查项
```

---

## Commit 6:feat(wiki) 检查队列分配/动作/延期

**文件**:
- `M server/apps/opspilot/models/wiki_mgmt.py`(CheckItem.assignee/due_at/action_type)
- `M server/apps/opspilot/serializers/wiki_serializers.py`(CheckItemSerializer 加字段)
- `M server/apps/opspilot/viewsets/wiki_check_view.py`(assign action + list 过滤)

**说明**:
- CheckItem 扩展为可操作任务队列
- assign 端点:assignee / due_at / action_type 独立或组合更新,空值清除
- list 过滤:assignee(支持 __mine__/__unassigned__/具体用户名)、action_type、overdue

**Commit message**:
```
feat(wiki): 检查项分配/动作/延期 + list 过滤

- CheckItem 新增 assignee / due_at / action_type 字段(由迁移 0064 提供)
- assign action: 单字段或多字段更新,空值清除
- list 过滤: assignee(支持 __mine__/__unassigned__/具体用户名)、action_type、overdue=1
- CheckItemSerializer 暴露新字段
```

---

## Commit 7:feat(wiki) 资料批量创建 + 失败汇总

**文件**:
- `M server/apps/opspilot/viewsets/wiki_material_view.py`(batch_create action)
- `M server/apps/opspilot/tasks.py`(wiki_batch_ingest_materials_task)

**说明**:
- batch_create:多文件一次性提交,逐条创建 + 投递解析任务,失败文件汇总到 errors
- batch_ingest_materials_task:批量解析,逐条隔离失败
- 操作日志记录"批量新增资料:成功 X 条,失败 Y 条"

**Commit message**:
```
feat(wiki): 资料批量创建 + 失败汇总

- wiki_material_view.batch_create: 多文件 multipart 单次提交,逐条创建并投递解析任务
- 失败文件汇总到 errors 字段(单条失败不影响其他)
- 解析任务投递失败不阻塞记录创建
- wiki_batch_ingest_materials_task: 批量解析异步任务(供定时调度或外部触发)
- 操作日志: 批量新增资料: 成功 X 条, 失败 Y 条
```

---

## Commit 8:feat(wiki/web) 6 工作区对齐 spec 4

**文件**:
- `M web/src/app/opspilot/components/wiki/OverviewTab.tsx`
- `M web/src/app/opspilot/components/wiki/MaterialTab.tsx`(本轮改用 batchCreateMaterials + 失败汇总)
- `M web/src/app/opspilot/components/wiki/PageTab.tsx`
- `M web/src/app/opspilot/components/wiki/CheckTab.tsx`(本轮加分配 Modal)
- `M web/src/app/opspilot/components/wiki/BuildRecordTab.tsx`
- `M web/src/app/opspilot/components/wiki/GraphTab.tsx`
- `M web/src/app/opspilot/components/wiki/GraphExplorer.tsx`
- `M web/src/app/opspilot/components/wiki/GraphCanvas.tsx`
- `M web/src/app/opspilot/components/wiki/SettingsTab.tsx`
- `M web/src/app/opspilot/components/wiki/WikiModifyModal.tsx`
- `M web/src/app/opspilot/components/wiki/WikiQaAssistant.tsx`
- `M web/src/app/opspilot/components/custom-chat-sse/WikiCitations.tsx`
- `M web/src/app/opspilot/api/wiki.ts`(本轮加 batchCreateMaterials + assignCheck)
- `M web/src/app/opspilot/types/wiki.ts`(本轮加 MaterialBatchCreateResult + CheckItem 新字段)
- `M web/src/app/opspilot/types/global.ts`
- `M web/src/app/opspilot/locales/zh.json`(本轮加 10 个 key)
- `M web/src/app/opspilot/locales/en.json`(本轮加 10 个 key)
- `A web/src/app/opspilot/components/wiki/wikiFormat.ts`

**说明**:
- 6 个工作区(概览/资料/知识页/构建记录/检查审核/设置)对齐 spec 4
- SettingsTab 术语表 Form.List + canonical/alias 编辑
- MaterialTab 改用 batchCreateMaterials + 失败汇总
- CheckTab 分配 Modal(assignee/due_at/action_type)
- 关系图谱全幅浮层 + 强关联 + 社区着色
- 问答试用悬浮助手(WikiQaAssistant)
- WikiCitations 渲染引用 evidence

**Commit message**:
```
feat(wiki/web): 6 工作区对齐 spec 4 + 分配 Modal + 批量失败汇总

- 6 个工作区(概览/资料/知识页/构建记录/检查审核/设置)对齐 spec 4
- SettingsTab 术语表 Form.List 编辑(canonical/alias 双向)
- MaterialTab 改用 batchCreateMaterials + 失败汇总 toast
- CheckTab 分配 Modal(assignee/due_at/action_type + DatePicker + Select)
- 关系图谱全幅浮层 + G6 力导向 + 社区着色 + 拖拽缩放
- 问答试用改悬浮助手(WikiQaAssistant)
- WikiCitations 渲染引用 evidence + i18n
- 33 个 wiki 验证脚本(本轮 + 既有) + 10 个新 i18n key
```

---

## Commit 9:test(wiki) 后端测试

**文件**:
- `A server/apps/opspilot/tests/wiki/test_cascade_observability.py`
- `A server/apps/opspilot/tests/wiki/test_title_service.py`
- `A server/apps/opspilot/tests/wiki/test_wikilink_enrichment.py`
- `A server/apps/opspilot/tests/wiki/test_markdown_export.py`
- `A server/apps/opspilot/tests/wiki/test_markdown_import.py`
- `A server/apps/opspilot/tests/wiki/test_page_sources.py`
- `A server/apps/opspilot/tests/wiki/test_page_lifecycle_incremental.py`
- `A server/apps/opspilot/tests/wiki/test_batch_create.py`
- `A server/apps/opspilot/tests/wiki/test_check_assign.py`
- `A server/apps/core/tests/test_logging_config.py`
- `M server/apps/opspilot/tests/wiki/test_async_tasks.py`
- `M server/apps/opspilot/tests/wiki/test_build.py`
- `M server/apps/opspilot/tests/wiki/test_chat_integration.py`
- `M server/apps/opspilot/tests/wiki/test_checks.py`
- `M server/apps/opspilot/tests/wiki/test_embedding_index.py`
- `M server/apps/opspilot/tests/wiki/test_graph.py`
- `M server/apps/opspilot/tests/wiki/test_graph_analysis.py`
- `M server/apps/opspilot/tests/wiki/test_hybrid_retrieval.py`
- `M server/apps/opspilot/tests/wiki/test_material.py`
- `M server/apps/opspilot/tests/wiki/test_material_delete.py`
- `M server/apps/opspilot/tests/wiki/test_material_file.py`
- `M server/apps/opspilot/tests/wiki/test_ocr_local.py`
- `M server/apps/opspilot/tests/wiki/test_page_chunk.py`
- `M server/apps/opspilot/tests/wiki/test_purpose_schema_service.py`
- `M server/apps/opspilot/tests/wiki/test_rebuild.py`
- `M server/apps/opspilot/tests/wiki/test_relations.py`
- `M server/apps/opspilot/tests/wiki/test_retrieval.py`
- `M server/apps/opspilot/tests/wiki/test_update.py`
- `M server/apps/opspilot/tests/wiki/test_wiki_context.py`
- `M server/apps/opspilot/tests/wiki/test_wiki_kb_views.py`
- `M server/apps/opspilot/tests/test_chat_service_llm_timeout.py`
- `M server/apps/opspilot/tests/react_agent/cases/test_anthropic_protocol.py`

**说明**:
- 9 个新测试文件覆盖本轮新增服务
- 既有测试同步适配新代码

**Commit message**:
```
test(wiki): 本轮新增服务 + 端点测试(283 个 wiki 用例)

- cascade_observability / title_service / wikilink_enrichment / markdown_export /
  markdown_import / page_sources / page_lifecycle_incremental / batch_create /
  check_assign 共 9 个新测试文件
- core/tests/test_logging_config 新增
- 既有 23 个测试同步适配新代码
```

---

## Commit 10:docs(wiki) 架构设计与进度记录

**文件**:
- `A docs/superpowers/specs/2026-06-26-opspilot-wiki-architecture-design.md`
- `A docs/superpowers/specs/2026-06-26-opspilot-wiki-parsing-lifecycle-enhancement-design.md`
- `A docs/superpowers/specs/2026-07-03-opspilot-wiki-gap-analysis-progress.md`
- `A docs/superpowers/specs/2026-07-03-opspilot-wiki-commit-plan.md`(本文档)
- `A server/docs/opspilot-wiki-llm-wiki-gap-analysis.md`(已有)
- `A server/wiki_coverage.json`
- `M server/pyproject.toml`
- `M server/config/components/log.py`
- `M server/apps/opspilot/metis/llm/common/llm_client_factory.py`
- `M server/apps/opspilot/signals/wiki_material_signal.py`
- `A web/scripts/wiki-*.ts`(31 个)

**说明**:
- 2 个 specs 文档(Wiki 架构设计 + 解析生命周期增强)
- gap analysis 推进进度记录
- 本 commit plan
- 31 个前端 wiki 验证脚本(覆盖 UI 行为/Storybook 风格)
- pyproject/log/llm_client_factory 配套调整

**Commit message**:
```
docs(wiki): 架构设计 + 推进进度 + commit plan + 31 个前端脚本

- 2 个 specs:Wiki 架构设计、解析生命周期增强
- gap analysis 推进进度(2026-07-03)
- commit plan(本文档)
- 31 个 web/scripts/wiki-*.ts 验证脚本(批量上传/文件夹/分配/图谱/搜索解释/检查过滤等)
- pyproject/log/llm_client_factory 配套调整
```

---

## 风险与回滚

- 每个 commit 单独可回滚(影响范围限于该领域)
- 迁移 0061/0062 删除是不可逆操作(已合 master 的 wiki 0.0.1 部署需评估)
- batch_create 端点新增不影响既有 create 端点
- CheckItem 新字段有默认值,既有数据兼容

## 不在本 commit plan

- Deep Research(图谱洞察的"惊喜连接"等扩展) — 第三阶段
- Web Clipper — 单独立项
- MCP / OpenAPI — 本轮不实现
- Markdown 治理增强(权限/审计/配额/失败重试) — 第三阶段
- 标题合并预览 UI — 后续小迭代
