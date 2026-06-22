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

### P4 多智能体复用 ✅(已接回聊天链)
- `services/wiki/wiki_context_service.py`:跨知识库上下文提供器 + `augment_prompt`(注入系统提示并回传引用);KB `context` 动作
- **接回聊天链**:`LLMSkill.wiki_knowledge_bases`(M2M,迁移 `0061`)+ 序列化器暴露;`get_skill_and_params` 传 `wiki_kb_ids`;`chat_service.format_chat_server_kwargs` 检索并注入系统提示、`wiki_citations` 入 extra_config(无选库/无命中零副作用)
- 回归:`test_llm_viewset_views` / `test_views_auth_entrypoints_views` / `test_chat_service_k8s_instance_selection` 共 46 passed,`manage.py check` 无问题
- 余:前端技能配置 UI 增加"选择 Wiki 知识库"(前端工作);引用在回答中的前端展示

### P5 关系图谱(装配 + 洞察 + 加权社区)✅
- `services/wiki/graph_service.py`:`build_graph`(连通分量社区 + 孤立/枢纽洞察)+ `analyze_graph`(4 信号关联度加权 + **标签传播社区**,Louvain 的无依赖替代);KB `graph`/`graph_analysis` 动作

### P6 全量重建 ✅(非向量部分)
- `services/wiki/rebuild_service.py`:Schema 变更全量重建(归档旧 AI 页 / 保留并标记人工页 schema_changed / 按新 Schema 重生成);KB `rebuild` 动作 + Celery 任务 `wiki_rebuild_kb_task`

### P1 异步 ✅
- `tasks.py`:`wiki_build_material_task` / `wiki_propose_update_task` / `wiki_rebuild_kb_task`(Celery);material `build` 支持 `async=true` 走异步

### P1 文件/网页解析 ✅(真实 MinIO 已验证)
- `material_service.extract_text` 按类型/扩展名分派:
  - **OCR-free 文件** `.txt/.md/.csv/.xlsx/.xls`(Text/Markdown/Excel loader)——**真实 MinIO 往返集成测试通过**(上传 xlsx→读回解析)
  - **文档型** `.pdf/.docx/.pptx`:loader 经 fitz/python-docx/python-pptx **原生抽取文本,无需 OCR 服务**(OCR 仅在已配置时增强内嵌图片);**真实 .docx 抽取测试通过**(ocr=None)。惰性导入 + 缺依赖优雅降级
  - **纯图片** `.png/.jpg/.jpeg`:内容仅图像,需 OCR 引擎。支持两种:云端 OCRProvider(olm/azure)**或**本机 **Tesseract**(`tesseract_ocr.py`,无需服务,装好二进制即用,无 provider 时自动回退);两者都没有时优雅返回空串
  - **网页** `web`:HTTP 抓取 + 标准库剥离 HTML 为文本(基础版,不含 JS/图片 OCR),抓取失败优雅降级
- 定时刷新:`tasks.wiki_refresh_web_materials_task`(Celery,可挂 beat)重抓 web 资料,内容变更触发安全更新

### P6 语义检索 + 持久化索引 ✅(无需 pgvector)
- `embedding_service.py`:`embed_texts`(EmbedProvider/OpenAI 兼容)+ 纯函数 `cosine`/`rrf_fuse`;**持久化索引** `index_version`(把正文嵌入存入 `PageVersion.embedding`,迁移 `0062`)、`reindex_knowledge_base`、`semantic_search`(基于已存向量余弦)
- `retrieval_service.hybrid_search`:关键词召回 → 嵌入重排 → RRF 融合;无嵌入优雅回退
- KB 接口:`hybrid_search` / `semantic_search` / `reindex`
- 说明:JSON 列存向量 + in-Python 余弦,**功能完整不依赖 pgvector**;装 pgvector 后可把存储/检索换成索引列以扩规模。嵌入端点当前 502,全链路已验证优雅降级,端点恢复即生效

### 前端图谱画布 ✅
- `components/wiki/GraphCanvas.tsx`:@antv/g6 v5 力导向画布(社区着色 + 拖拽/缩放),GraphTab 画布+数据视图并存;eslint + tsc 通过(运行时冒烟需主仓库)

> 后端测试合计 **61 passed**(`apps/opspilot/tests/wiki/`)。后端 P0–P6(除下列纯基础设施项)已完成。

### 前端 ✅(`web/src/app/opspilot`,eslint + 作用域 tsc 校验通过)
- `api/wiki.ts`(useWikiApi 全量接口)+ `types/wiki.ts`;i18n `wiki.*`(zh/en)
- `(pages)/wiki/page.tsx`:知识库列表(增删改 + AI 生成 Purpose/Schema)
- `(pages)/wiki/detail/page.tsx`:详情 7 工作区 Tabs —— 概览 / 资料(增/解析/构建/删) / 知识页面(版本+恢复) / 构建记录 / 检查审核(接受/拒绝/扫描) / 关系图谱(4 信号加权+社区) / 问答试用(引用)
- `constants/menu.json`:注册知识库入口(zh/en)
- 技能设置页:`选择 Wiki 知识库` 多选(打通 P4 端到端配置)
- 校验方式:`npx eslint <files>`(全绿)+ `npx tsc -p tsconfig.lint.json`(仅 3 个既有 env 基线错误,均非 wiki 文件);运行时冒烟需主仓库(worktree Turbopack 跑不起)

## 补齐(2026-06-22 第二轮:把"spec 简化项"补成逐字实现)
- **构建两步法**:`build_service` 改为 Stage1 抽取要点 → Stage2 依 Schema 生成页面(对标 llm_wiki)。
- **Louvain 社区发现**:`graph_service._louvain`(纯 Python 模块度贪心 + 多层聚合)替换标签传播,无依赖。
- **PageChunk 分块级嵌入**:模型 + 迁移 `0063` + 按标题切分 + 块级语义检索(`reindex_chunks`/`chunk_search`)。
- **版本 diff**:`page_service.diff_versions`(unified diff)+ `page/{id}/diff` 接口 + 前端 PageTab 版本对比视图。

## 真实 LLM 端到端验证 ✅(2026-06-22,经你授权用开发库 + 可用模型 130 跑通)
已把 wiki 迁移(0059–0063)应用到开发库(`migrate opspilot`),用可达模型 `deepseek-v4-flash1`(id=130)实跑并清理测试数据,验证 LLM 依赖功能**真实产出**:
- 资料 AI 摘要:真实生成(`### 摘要…`)
- 构建:`success {new:1}`,真实生成 `procedure` 类型页面
- 问答:真实作答 + 引用(`['Nginx…', '资料摘要: 重启指南']`)
- Purpose/Schema 生成:真实输出(purpose 325 字 / schema 347 字)
- 环境事实:**聊天 LLM 端点可用**(模型 130);**嵌入端点仍 502**(单一 EmbedProvider#36 上游不可用);**pgvector 0.8.1 服务端可用**(未启用)。

## 语义检索 + 图片 OCR 真实验证 ✅(2026-06-22,经你授权用开发库)
关键发现:**网关 `https://api.v36.cm/v1`(模型 130 的 vendor)同时提供 chat + embeddings + vision**;你的 EmbedProvider#36 / OCRProvider 指向了别处/未配,换到此网关即全部可用。已实跑验证(数据用完即删):
- **语义检索**:用 `text-embedding-3-small`(dim=1536)生成**真实向量**;`semantic_search('怎么重启 nginx')` 正确把"重启服务"页排第一(`SEM_OK=True`);`chunk_search`/`hybrid_search` 同样命中正确页。**真实向量验证通过**。
- **图片 OCR**:配 OCRProvider(vendor=网关, model=`gpt-4o`)→ 对含 "RESTART NGINX 2025" 的图片 `extract_text` **真实识别出文字**(`OCR_OK=True`),走 ImageLoader→OlmOcr(OpenAI 兼容 vision,通用模型即可)。
- 配置提示:把 EmbedProvider#36 的 vendor.api_base 改为 `https://api.v36.cm/v1`、新建一个 vendor=该网关、model=gpt-4o 的 OCRProvider,即在你环境生效。

## 待办(剩余 —— 仅 1 项:前端浏览器点击,worktree 结构性跑不起)

LLM / 语义检索 / 图片 OCR 均已**真实端到端验证**(上方);仅剩:

1. **前端浏览器点击冒烟**:worktree 前端运行时**结构性跑不起**——dev server(Turbopack/webpack)与 Storybook 三次尝试均崩在 web `node_modules`/`prepare-enterprise`(缺 `fs-extra`)。代码已全程 eslint + 作用域 tsc 校验。此为你既定流程「前端冒烟去主仓库」,需在主仓库(依赖完整)对 `/opspilot/wiki` 点验。

> 其余原"受阻"项均已**真实验证或完成**:LLM 构建/问答/摘要/Purpose 生成(模型 130)、语义检索/分块/混合(真实向量,api.v36.cm 嵌入)、图片 OCR(api.v36.cm gpt-4o vision)全部**真实端到端跑通**;beat 周期已注册;`wiki_list` 已入菜单;两步构建/Louvain/PageChunk/版本 diff 已补齐。pgvector 为多 DB 可移植性故意不作默认(JSON+余弦跨 7 种库,pgvector 仅 Postgres 专属可选)。

## 已上线 API(`/api/v1/opspilot/wiki_mgmt/`)
- `knowledge_base/`(CRUD)+ 动作 `templates` `generate_purpose_schema` `search` `qa` `scan` `rebuild_relations` `relations` `graph` `overview` `context`(detail=False)
- `material/`(CRUD,destroy 含删除影响)+ 动作 `ingest` `build` `propose_update`
- `page/`(CRUD)+ 动作 `versions` `restore`
- `build_record/`(只读)、`check_item/`(列表 + `accept`/`reject`)
