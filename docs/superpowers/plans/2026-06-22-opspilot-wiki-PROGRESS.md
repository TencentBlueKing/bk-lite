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

### P1 核心 ✅(确定性部分全部完成)
- `services/wiki/material_service.py`:资料摄取(文本解析 + AI 摘要)+ Material CRUD/ingest 接口
- `services/wiki/build_service.py`:构建管道(资料 → Schema 驱动生成页面 + 版本 + 证据 + 构建记录);material `build` 动作;构建后自动建关系
- `services/wiki/page_service.py`:页面人工创建/编辑/删除 + 版本管理/恢复;page CRUD + `versions`/`restore`
- `services/wiki/relation_service.py`:关系识别(共享资料 / 正文 `[[引用]]`)+ KB `rebuild_relations`/`relations` 动作
- `services/wiki/update_service.py`:资料更新 **安全合并**(AI 页直更、人工页转候选审核)+ **删除级联**(失去来源页面转待审);material `propose_update` 动作 + destroy 影响

### P2 安全更新 + 检查审核 ✅
- `services/wiki/check_service.py`:候选版本(不污染当前有效版本)+ 检查事项 + 接受/拒绝 + 系统扫描(孤立/缺来源)+ 可复用 `ensure_check`
- check_item 列表 + `accept`/`reject` 动作;KB `scan` 动作

### P3 检索 + 问答 + 概览 ✅
- `services/wiki/retrieval_service.py`:关键词检索(CJK 分词)+ 问答试用(引用可追溯);KB `search`/`qa` 动作
- `services/wiki/overview_service.py`:概览健康摘要(页面/资料/构建/检查/关系统计 + 贡献分布 + 图谱社区/枢纽);KB `overview` 动作

### P4 多智能体复用(可复用单元)✅
- `services/wiki/wiki_context_service.py`:跨知识库上下文提供器(供技能/智能体注入提示词);KB `context` 动作
- 余:把 `build_context` 接回 chat chain / 技能执行处(需探查 SSE/技能执行路径,见待办)

### P5 关系图谱(装配 + 洞察)✅
- `services/wiki/graph_service.py`:图装配 + 连通分量社区 + 孤立/枢纽洞察;KB `graph` 动作
- 余:Louvain 社区发现 + 4 信号关联度加权(需 networkx/python-louvain)

> 测试合计 44 passed(`apps/opspilot/tests/wiki/`)。

## 待办(剩余 —— 受基础设施/前端环境/需探查约束,非单会话可净完成)

- **P1 余下(需基础设施)**:文件/网页/OCR 解析(loader 已就绪,需接 OCRProvider + 从 MinIO 读取;worktree 缺 MinIO env 无法联测)、Celery 异步构建(需 broker)
- **P4 接回(需探查)**:在聊天链 / 技能执行处调用 `build_context` 注入,改动 SSE 执行路径(风险较高,需先探查)
- **P5 增强**:Louvain + 4 信号关联度(需 networkx/python-louvain 依赖)
- **P6(需基础设施)**:pgvector + 嵌入(复用 EmbedProvider)+ RRF、网页定时刷新、Schema 变更全量重建
- **前端**:6 个工作区(概览/资料/知识/构建记录/检查审核/设置)——该 worktree 前端环境跑不通,需在主仓库或修好依赖后进行

## 已上线 API(`/api/v1/opspilot/wiki_mgmt/`)
- `knowledge_base/`(CRUD)+ 动作 `templates` `generate_purpose_schema` `search` `qa` `scan` `rebuild_relations` `relations` `graph` `overview` `context`(detail=False)
- `material/`(CRUD,destroy 含删除影响)+ 动作 `ingest` `build` `propose_update`
- `page/`(CRUD)+ 动作 `versions` `restore`
- `build_record/`(只读)、`check_item/`(列表 + `accept`/`reject`)
