# OpsPilot Wiki — 实现进度(持续更新)

> 工作分支 `claude/bold-tu-40b23d`(worktree `kb-remove`)。仅在分支提交,**不合并 master、不 push**。
> 前端环境在该 worktree 跑不通(见 [[worktree-web-frontend-deps]]),前端工作需另解。
> 测试:`cd server && D:\app\venv\bkliteserver\Scripts\python.exe -m pytest apps/opspilot/tests/wiki/ -o addopts="" --create-db -p no:cacheprovider -q`(当前 24 passed)。

## 已完成(后端,均有测试 + 提交)

### P0 地基 ✅
- 9 数据模型 `models/wiki_mgmt.py` + 迁移 `0060`(WikiKnowledgeBase / Material / MaterialVersion / KnowledgePage / PageVersion / PageRelation / PageEvidence / BuildRecord / CheckItem)
- 恢复 `metis/llm/loader/`(资料解析)
- `services/wiki/purpose_schema_service.py`:5 模板 + AI 辅助生成
- 知识库 CRUD + 创建流程接口

### P1 核心(部分)✅
- `services/wiki/material_service.py`:资料摄取(文本解析 + AI 摘要)+ Material CRUD/ingest 接口
- `services/wiki/build_service.py`:构建管道(资料 → Schema 驱动生成页面 + 版本 + 证据 + 构建记录);material `build` 动作
- `services/wiki/page_service.py`:页面人工创建/编辑/删除 + 版本管理/恢复;page CRUD + `versions`/`restore`;page/build_record 浏览

### P2 安全更新 + 检查审核(部分)✅
- `services/wiki/check_service.py`:候选版本(不污染当前有效版本)+ 检查事项 + 接受/拒绝 + 系统扫描(孤立/缺来源)
- check_item 列表 + `accept`/`reject` 动作;KB `scan` 动作

### P3 检索 + 问答(核心)✅
- `services/wiki/retrieval_service.py`:关键词检索(CJK 分词)+ 问答试用(引用可追溯);KB `search`/`qa` 动作

## 待办(剩余,均较大)

- **P1 余下**:文件/网页/OCR 解析(loader 已就绪,需接 OCRProvider)、Celery 异步构建、资料更新的 **3 路合并**(保护人工)+ 关系识别(PageRelation)、资料删除影响与级联
- **P3 余下**:概览工作区(健康摘要)、pgvector 语义检索(P6 可选)
- **P4 多智能体复用**:技能/智能体选知识库 + 聊天链从 wiki 页面检索作答(接回 chat chain)
- **P5 关系图可视化**:4-signal 关联度 + Louvain + 图洞察
- **P6**:pgvector + 嵌入(复用 EmbedProvider)+ RRF、网页定时刷新、Schema 变更全量重建
- **前端**:6 个工作区(概览/资料/知识/构建记录/检查审核/设置)——该 worktree 前端环境需先解决

## 已上线 API(`/api/v1/opspilot/wiki_mgmt/`)
- `knowledge_base/`(CRUD)+ 动作 `templates` `generate_purpose_schema` `search` `qa` `scan`
- `material/`(CRUD)+ 动作 `ingest` `build`
- `page/`(CRUD)+ 动作 `versions` `restore`
- `build_record/`(只读)、`check_item/`(列表 + `accept`/`reject`)
