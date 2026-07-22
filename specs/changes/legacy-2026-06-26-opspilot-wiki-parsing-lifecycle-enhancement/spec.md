# Historical Superpowers change: 2026-06-26-opspilot-wiki-parsing-lifecycle-enhancement

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-26-opspilot-wiki-parsing-lifecycle-enhancement-design.md

> 关联:[Wiki 架构现状](2026-06-26-opspilot-wiki-architecture-design.md)、[企业 Wiki 需求](2026-06-18-opspilot-enterprise-llm-wiki-design.md)。
> 工作目录:worktree `kb-remove`,分支 `claude/bold-tu-40b23d`。代码根:`server/apps/opspilot/`。
> 参考实现对比:`nashsu/llm_wiki`(MinerU 解析、LanceDB 增量索引、视觉描述、sweep 自动消解)。

## 1. 背景与目标

当前 Wiki 解析用按文件类型分派的本地 loader(pymupdf/python-docx/pandas/OCR)和手写网页解析,产出**纯文本**,且全文不落库(只存 `content_hash` + `ai_summary`);构建以**有损摘要**为输入;资料增删未联动到向量索引(索引仅手动 reindex)、删除不重建关系;图片仅传统 OCR、无视觉模型。

本设计解决四件事:
1. 资料解析统一切换到微软 **markitdown**(file/web/text 都产出 markdown),并抽象出可替换的解析器层(便于日后接 MinerU 等)。
2. 资料增/改/删 **增量、自动**联动下游:摘要、页面、关系、向量索引、检查项。
3. 图片走**多模态视觉模型**做内容识别/描述(取代传统 OCR),逐文件可选、默认关闭,并按图片 hash 缓存。
4. 构建输入从"摘要"改为**解析后的全文 markdown**(长文分块迭代)。

## 2. 范围

**纳入:** markitdown 解析器 + 抽象层;file/web/text 三类资料统一解析为 markdown;解析产物持久化;构建/更新改用全文;增量联动引擎 + 删除清理;WikiLink 关系重建与失效清理;检查项自动消解;KB 多模态模型配置 + 逐文件增强开关 + caption 缓存。

**不纳入:** 接入 MinerU/云解析(仅预留接口);浏览器渲染型网页抓取;需登录网站解析;音频/视频;向量库换 pgvector/LanceDB(仍 JSONField);旧知识库迁移。

## 3. 决策汇总(已与用户确认)

| # | 决策 |
|---|---|
| D1 | markitdown 接管 **file/web/text 全部资料解析**;删除 wiki 路径里旧 file loader、旧 web/text 解析分支的使用(metis loader 文件保留) |
| D2 | 联动 = **增量 + 自动链式**(资料摘要与受影响页索引增量更新 + 全库关系/WikiLink 重建;删除清理归档页向量) |
| D3 | 图片识别用**独立多模态模型**(KB 设置选,与主推理模型解耦) |
| D4 | 增强开关 = **逐文件**(上传时勾),**默认关闭** |
| C1 | 解析器**抽象层**(默认 markitdown,可插拔) |
| C2 | caption **按图片 hash 缓存** |
| C3 | 资料删除/页面变更后**自动消解**已不成立的检查项 |
| C4 | 构建/更新输入改用**解析后的全文 markdown**(非摘要) |
| C5 | WikiLink 语法支持 `[[title]]` / `[[title\|alias]]`;只解析当前有效版本;关系全库重建,死链生成检查项 |

## 4. 数据模型变更(`models/wiki_mgmt.py`,一条迁移)

| 模型 | 变更 |
|---|---|
| `WikiKnowledgeBase` | + `vision_model`(FK→`LLMModel`, null):图片识别多模态模型 |
| `Material` | + `ocr_enhance`(bool, default False):本资料上传时是否启用图片增强 |
| `MaterialVersion`(激活现有模型) | 每次成功解析写一条:`content_locator`=MinIO 中解析后 markdown 的对象路径,`content_hash`=md 的 SHA256。资料因此获得版本化 |
| `WikiImageCaption`(新) | `image_hash`(唯一)、`caption`、`vision_model`(FK, null)、`created_at`:图片描述缓存 |

> 摘要 `Material.ai_summary` 保留(用于资料详情展示与检索补充上下文),但**不再是构建输入**。

## 5. 组件设计

### 5.1 解析器抽象层 + markitdown(D1/C1)

新建 `services/wiki/parsing/`:
- `base.py`:`class DocumentParser(Protocol)` 提供三类入口:
  - `parse_file(data: bytes, filename: str, *, vision_client=None) -> str`
  - `parse_text(text: str, *, filename: str = "raw.txt") -> str`
  - `parse_url(url: str, *, vision_client=None) -> str`
- `markitdown_parser.py`:默认实现。file/text 走临时文件或 markitdown 支持的输入形式 → `MarkItDown(...).convert(...).text_content`;URL 走 markitdown URL 解析入口。`vision_client` 非空时构造带视觉模型的 `MarkItDown(llm_client=..., llm_model=...)`。
- `registry.py`:`get_parser()` 返回当前解析器(配置/默认 markitdown);未来 `mineru_parser.py` 可注册。
- `material_service.extract_text` 只按 `material_type` 分派到 parser:
  - `file` → `get_parser().parse_file(data, name, vision_client=...)`
  - `web` → `get_parser().parse_url(material.url, vision_client=None)`
  - `text` → `get_parser().parse_text(material.text_content or "")`
- **删除 wiki 路径内旧解析分支的使用**:`_FILE_LOADERS`/`_OCR_DOC_EXTS`/`_build_ocr`/`_ocr_loader_class`、`_fetch_url`、`_html_to_text`、RawLoader 包装等不再参与 Wiki 解析。
- 依赖:`pyproject.toml` 的 `opspilot` extra 固定为 `markitdown[docx,outlook,pdf,pptx,xls,xlsx,youtube-transcription]==0.1.6`(Py3.12 ✓)。显式启用常见格式 extras,覆盖常见资料类型:
  - Office/PDF:`pdf`、`docx`、`pptx`、`xlsx`、`xls`、Outlook 邮件(`msg`)。
  - 基础 Web/文本/结构化能力(无需 extra):HTML/URL、TXT、Markdown、CSV、JSON、XML。
  - 基础图片/归档/电子书能力(无需 extra):JPG/JPEG、PNG、GIF、BMP、TIFF、WEBP、ZIP、EPub。
  - 媒体:YouTube 转写。
  - 暂不支持本地音频资料解析,避免引入 `audio-transcription` 及其 `pydub/ffmpeg` 运行时依赖。
  Azure Document Intelligence / Content Understanding 属于云增强能力,不默认启用;尤其 `az-content-understanding` 会引入 beta 依赖,若后续需要再单独评估 prerelease 策略。
  当前实现中,`web` 资料走 `MarkItDown.convert(url)` 并由 MarkItDown 按响应内容使用 HTML/URL 基础转换;`text` 资料写入临时 `raw.txt` 后 `convert()`,使用 TXT 基础转换。因此 `html`/`txt` 不出现在 extras 列表里是预期行为。
  旧解析库(pymupdf/tabula/python-docx/python-pptx)若仅 wiki 用可后续移除,本轮**保留**避免误伤 metis。
- 不保留旧 web/text fallback:markitdown 对 URL/文本解析失败时进入 `failed` 或记录精准失败原因,避免双解析路径长期并存。

### 5.2 解析产物持久化(C4 前置)

`ingest_material` 对 file/web/text 都解析得到 markdown 后:
1. 计算 `content_hash = sha256(md)`;该 hash 明确代表**解析后 markdown hash**。若与上一版本一致则跳过摘要、页面、索引、关系等后续联动(幂等)。
2. 把 markdown 上传 MinIO(`munchkin-private`,路径如 `wiki/parsed/<kb>/<material>/<hash>.md`)。
3. 建 `MaterialVersion(content_locator=对象路径, content_hash=hash)`。
4. 生成 `ai_summary`(仍保留,展示/检索用)。
5. `status=done`。
- 提供 `material_service.load_parsed_markdown(material)`:读最新 `MaterialVersion` 的 MinIO 内容(构建期调用)。

### 5.3 构建/更新改用全文(C4)

- `build_service.build_from_material`:`text` 来源由 `ai_summary` 改为 `load_parsed_markdown(material)`(回退 `text_content`)。
- **长文分块迭代**(map-reduce):正文超过 token 预算时,按 markdown 标题切块 → 逐块 `_llm_extract_facts` → 合并去重 → `_llm_generate_pages`。短文走单次(现状)。
- `update_service._default_generator`:重写页面正文时同样用全文 markdown(非摘要)。
- 兼容:解析产物缺失(旧数据)时回退 `ai_summary`,不报错。

### 5.4 多模态视觉 + caption 缓存 + 逐文件开关(D3/D4/C2)

- **配置**:`设置 → 基本信息` 增「图片识别模型(多模态)」选择器 → `vision_model`(可空)。
- **上传**:资料上传弹窗每个文件一个复选框「图片增强(用视觉模型识别图片内容)」,**默认不勾**;传到上传接口 → 存 `Material.ocr_enhance`。KB 未配 `vision_model` 时该复选框**置灰**并提示"需先在设置中配置图片识别模型"。
- **解析期**:`ocr_enhance and kb.vision_model` 为真才构造 `vision_client` 传入解析器。
- **caption 缓存**:`vision_client` 用一个**缓存代理**——对每张图先按 `sha256(image_bytes)` 查 `WikiImageCaption`,命中直接回描述,未命中再调真实多模态模型并写缓存。
  > 实现期验证点:markitdown 的 `llm_client` 注入是否足以拦截每张图的视觉调用;若不可行,退化为"自行抽图 + 逐图缓存描述 + 注入 alt"(llm_wiki 同思路)。spec 以"缓存代理 client"为首选。
- 增强失败/模型非多模态 → 回退纯文本抽取 + 资料标注一条警告(不判 failed)。

### 5.5 生命周期联动引擎(D2/C4)

新建 `services/wiki/cascade_service.py`:`cascade(kb, affected_page_ids, event)` —— **尽力而为、不阻断主流程**:
1. `rebuild_relations(kb)`(关系/WikiLink 全库重建,轻量,保证删除、改名、归档后一致)。
2. 增量索引:
   - `event in {"build","accept","edit"}`:对 `affected_page_ids` 调 `index_version(current_version)` + `reindex_page_chunks`。
   - `event="delete"`:对归档/失效页调 `clear_page_vectors`(清 `PageVersion.embedding` 和 `PageChunk.embedding`)。
3. 触发 §5.7 检查项自动消解。

接入点:
- **上传/构建**:`build_from_material` 末尾 → `cascade(kb, new_page_ids, "build")`(替换裸 `rebuild_relations`)。
- **更新接受**:候选生效在 `check_service.accept_candidate` 内 → `cascade(kb, [page_id], "accept")`。`propose_update` 仅产候选**不**建索引。
- **删除**:`handle_material_deletion` 末尾 → `cascade(kb, archived_page_ids, "delete")`。
- **资料有效变更**统一语义:
  - 新增/更新资料 → 解析 markdown → hash 比较。
  - hash 未变 → 跳过摘要、页面、索引、关系联动。
  - hash 已变 → 新增 `MaterialVersion`、重建该资料 `ai_summary`、构建新页或为受影响页生成候选版本。
  - 候选被接受后才更新该页索引;未审核候选不进入检索。
  - 删除资料不重建其它资料摘要。
- **删除资料页面处理**:
  - 页面仍有其它有效 `PageEvidence` → 移除被删资料证据,页面保留;必要时生成候选更新,接受后增量 reindex。
  - 页面无其它有效来源 → 标记 `source_invalid` 或归档,并清理向量,避免被 semantic/hybrid 检索召回。
- 索引需 KB 配 `embed_provider` 才跑,否则静默跳过(与现状一致)。

### 5.6 WikiLink 与关系失效清理(C5)

参考 `llm_wiki` 的做法:WikiLink 保留在 markdown 正文中,关系表从当前有效页面版本结构化解析后重建,删除/失效时做 cleanup sweep。

- **语法**:支持 `[[title]]` 与 `[[title|alias]]`;解析时使用结构化正则,不做模糊字符串 `includes`。
- **解析范围**:只解析 `KnowledgePage.current_version.body`;候选版本不进入 `PageRelation`,避免未审核内容污染图谱/检索。
- **目标解析**:
  - 优先精确匹配页面标题。
  - 归一化匹配大小写、空格、短横线、下划线差异,例如 `KV Cache` 与 `kv-cache` 可视为同一目标。
  - 多个页面命中 → 不自动建边,生成 `CheckItem(check_type="ambiguous_link")`。
  - 无命中 → 生成 `CheckItem(check_type="broken_relation")`。
- **关系重建**:`rebuild_relations(kb)` 仍全库重建:
  - 删除旧 `reference` / `shared_source` 关系后按当前有效状态重算。
  - `reference`:由 WikiLink 生成有向边。
  - `shared_source`:由 PageEvidence 生成无向关系。
  - 可继续复用现有图谱的 community/insights 能力。
- **失效清理**:
  - 页面归档/删除/来源失效后,全库关系重建会移除指向失效页面的边。
  - `sweep_open_checks` 自动消解前提已不成立的 `broken_relation`/`ambiguous_link`。
  - 本期不自动改写其它页面正文里的死链;先以检查项提示人工处理。若后续需要自动清理,应借鉴 `llm_wiki` 的结构化 `stripDeletedWikilinks`:把 `[[deleted|alias]]` 降级为 `alias`,把 `[[deleted]]` 降级为纯文本,并避免删除 `ai` 时误伤 `OpenAI`。
- **自动补链(后续可选)**:可新增 `enrich_wikilinks(page)`。LLM 只返回 `{term,target}` JSON 列表,由代码在正文中替换第一个未链接 occurrence,不允许 LLM 重写整页。

### 5.7 检查项自动消解(C3)

新建 `services/wiki/sweep_service.py`:`sweep_open_checks(kb)`——遍历 `status="open"` 的 `CheckItem`,对**前提已不成立**者置 `status="auto_resolved"`:
- `duplicate`/`conflict`:`related.pages` 里的页已不足 2 个(被删/归档)→ 消解。
- `broken_relation`:目标页已 active 或关系已不存在 → 消解。
- `ambiguous_link`:同名/归一化多命中已被改名、归档或缩减为唯一目标 → 消解。
- `no_source`/`all_sources_invalid`/`orphan`:页面现已有有效证据 → 消解。
- `material_update`(候选类):候选页已被删 → 消解。
在每次 `cascade` 末尾调用;人工仍可手动忽略。新增 `CheckItem.status` 取值 `auto_resolved`。

## 6. `llm_wiki` 参考对比

| 修改点 | BK-Lite 设计 | `llm_wiki` 对应设计 | 取舍 |
|---|---|---|---|
| 解析入口 | file/web/text 统一经 `DocumentParser` + markitdown,产物落 MinIO + `MaterialVersion` | ingest 后生成 wiki markdown 文件,项目内文件系统保存 | BK-Lite 保持服务端/MinIO/DB 架构;借鉴统一 markdown 产物 |
| 内容变更判断 | `Material.content_hash = sha256(parsed_markdown)`;hash 变才重建摘要和下游 | ingest/cache 基于源文件身份与处理状态 | BK-Lite 用 markdown hash 作为唯一有效变更门控 |
| 摘要更新 | 仅新增/更新且 hash 变的 Material 重建 `ai_summary`;删除不触发其它摘要 | 更偏向持续维护 wiki 文件,不是 DB 摘要字段 | BK-Lite 摘要是展示和检索补充,不再驱动构建 |
| 页面更新 | 资料变更生成新页或候选版本;接受后生效 | LLM 直接维护 markdown 文件,并可进入 review/sweep | BK-Lite 保留人工审核安全边界 |
| 索引更新 | 受影响 active 页面增量 reindex;归档/失效页清 embedding | 删除页面时 `removePageEmbedding`,避免 phantom search hit | 直接借鉴"删页必须清向量"原则 |
| 关系/WikiLink 重建 | `rebuild_relations(kb)` 全库重建 `reference/shared_source` | `buildWikiGraph()` 扫描所有 `.md` 重新构图 | BK-Lite 用 DB 关系表持久化结果,但重建策略相同 |
| WikiLink 语法 | `[[title]]` / `[[title\|alias]]` | `[[target]]` / `[[target\|alias]]` | 语法一致;BK-Lite 目标是页面 title |
| Link 目标匹配 | 精确标题 + 归一化大小写/空格/短横线/下划线;多命中进 `ambiguous_link` | `resolveTarget` 支持 id、大小写、空格/短横线匹配 | BK-Lite 增加多命中检查项,避免误连 |
| 死链处理 | 无目标生成 `broken_relation`;归档/删除后重建关系并 sweep 检查项 | structural lint 发现 `broken-link`;删除时结构化清理正文链接 | BK-Lite 本期先不自动改正文,以检查项驱动人工处理 |
| 删除资料 | 有其它来源则保留页面并移除证据;无来源则归档/失效并清向量 | 有其它 `sources` 则保留并改 frontmatter;无来源则删页 | 逻辑一致;BK-Lite 用 PageEvidence/status 表达 |
| 自动补链 | 后续可选:LLM 返回 `{term,target}` JSON,代码做最小替换 | `enrichWithWikilinks` 采用 JSON substitutions,避免 LLM 重写整页 | 直接采用其安全模式,但不放入本期必做 |
| 健康检查 | `CheckItem`:orphan/no_source/broken_relation/ambiguous_link/no_outlinks 可扩展 | structural lint: orphan/no-outlinks/broken-link | BK-Lite 通过检查项进入审核工作流 |

## 7. 前端变更(`web/src/app/opspilot`)

- 设置页 [SettingsTab.tsx]:基本信息增「图片识别模型」选择器(选项来自 LLM 模型列表)。
- 资料上传组件:每文件「图片增强」复选框(默认关;无 vision_model 置灰 + 提示);提交带 `ocr_enhance`。
- 资料详情:解析告警(如"图片增强失败,已回退纯文本")展示。
- i18n:zh/en 新增对应文案。

## 8. 异常与边界

- markitdown 转换失败/缺格式依赖 → `status=failed` + 精准原因(沿用 `_ingest_failure_reason`)。
- markitdown URL 解析超时、404、登录页、反爬、动态渲染失败 → `status=failed` + 精准原因;本期不引入浏览器渲染或登录态抓取。
- 视觉增强请求但模型不可用/非多模态 → 回退纯文本 + 警告,不 failed。
- MinIO 写/读解析产物失败 → 构建回退 `ai_summary`,记录告警。
- 联动里 embedding provider 缺失/超时 → best-effort 跳过,构建仍成功(索引滞后,可手动 reindex 兜底)。
- 更新走候选:索引只在"接受"时更新,绝不给未生效内容建索引。
- caption 缓存命中跨 KB 复用(按 image hash,与 KB 无关)——同图省 token。
- 网页中的远程图片是否触发多模态识别本期不承诺;`ocr_enhance` 主要面向上传文件中的图片/PDF/Office 内图片。
- WikiLink 死链本期生成检查项,不自动改写页面正文,避免未审核内容被隐式修改。

## 9. 测试策略

- **解析**:file/text/web 三类资料都调用 parser;markitdown 解析各格式样例 → markdown(纯单测 mock markitdown;少量真实库集成 1~2 格式);web 用 mock,不依赖真实网络;抽象层可替换 parser。
- **持久化**:file/text/web ingest → MinIO 写入 + MaterialVersion 落库;`load_parsed_markdown` 回读;markdown hash 一致跳过摘要和下游联动。
- **构建用全文**:长文分块迭代生成多页;解析产物缺失回退摘要。
- **视觉**:`ocr_enhance`+vision_model → 传 vision_client;关→纯文本;caption 缓存命中不重复调用(mock 计数)。
- **联动**:上传→关系+受影响页索引更新;删除→关系重建+归档页向量清除;更新接受→该页 reindex;删除资料不重建其它资料摘要。
- **WikiLink**:`[[title]]`/`[[title|alias]]` 解析;大小写/空格/短横线/下划线归一化;多命中生成 `ambiguous_link`;无命中生成 `broken_relation`;候选版本不入关系。
- **自动消解**:删资料/删页后,duplicate/broken_relation/ambiguous_link/no_source 等 open 检查按规则置 auto_resolved。
- 遵循 `server/docs/testing-guide.md` 分层(`_pure`/`_service`/`_views`)。

## 10. 实施分期(供 writing-plans 拆解)

- **P1 解析现代化**:解析器抽象层 + markitdown + 解析产物持久化(MaterialVersion/MinIO)+ 构建/更新改用全文。
- **P2 生命周期联动**:cascade_service(增量索引 + 关系/WikiLink 全库重建 + 删除清理)+ 接三处入口 + sweep_service 自动消解。
- **P3 多模态视觉**:vision_model 配置 + 逐文件增强开关 + caption 缓存代理 + 前端。
- **P4 自动补链(可选)**:借鉴 `llm_wiki` 的 JSON substitution 模式,由 LLM 只建议 `{term,target}`,代码执行最小替换。

> 三期可顺序交付且各自可独立验证。若 writing-plans 判定 P1 单独即超一个计划,可再细分。

## 11. 实现期需验证的关键点

1. markitdown `llm_client` 注入能否拦截每张图的视觉调用以启用缓存(否则退化为自行抽图+注入 alt)。
2. markitdown 对扫描件/复杂表格的保真度(作为日后是否接 MinerU 的判据)。
3. 长文分块迭代的 token 预算与合并去重质量。
4. 旧资料(无 MaterialVersion)在构建期回退路径的正确性。
5. markitdown 的 URL 解析能力、超时配置和错误类型是否足够支撑精准失败原因。
6. WikiLink title 匹配是否需要额外字段(如 slug/display_title)来避免同名页面歧义。
