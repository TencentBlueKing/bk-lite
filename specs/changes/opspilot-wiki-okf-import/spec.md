# OpsPilot Wiki 导入 Open Knowledge Format (OKF) Bundle

Status: implemented

## Problem Statement

[Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/open-knowledge-format) v0.2 是 Google 提出的厂商中立知识格式：一个目录树里的 Markdown 文件 + YAML frontmatter，唯一必填键是 `type`，推荐 `title` / `description` / `resource` / `tags`，可选 provenance / trust / lifecycle 家族（`sources[]`、`generated{by,at}`、`verified[]`、`status`、`stale_after`）和 Attested Computation 的 `runtime` / `parameters` / `executor` / `attester`。保留文件 `index.md`（根级可带 `okf_version`）与 `log.md` 不是 concept。概念间用普通 markdown 路径链接（`[x](/tables/customers.md)`、`./other.md`、`posts_questions.md`）表达关系。Bundle 以 git repo / zip / 大仓库子目录分发，目录里常混有 `README.md`、`.py`、`.sql`、`viz.html`。

llm_wiki 现有 Markdown 导入（`server/apps/opspilot/services/wiki/markdown_import_governance_service.py`）无法消化 OKF bundle：

- frontmatter 解析器是手写的（`markdown_import_service._parse_front_matter`），只认扁平 `key: value` 与简单 `- item` 列表，解析不了 `generated: { by, at }`、`sources` 的 list-of-dict、多行 `description`；stackoverflow 样例的 `tags: a, b, c` 逗号串会被 `_coerce_tags` 丢弃。
- `index.md` / `log.md` / `README.md` 会被当作页面导入；OKF `type`（`BigQuery Table`、`Metric`）无处安放，全部落成 `concept`。
- 关系图与 wikilink 增强只识别 `[[...]]`（`relation_service.LINK_RE`），OKF 的路径链接导入后全部是孤点。
- 归档内同名标题（数据目录里「表 `revenue`」与「指标 `Revenue`」并存是常态）直接触发 `archive_title_duplicate` 整包拒绝。
- GitHub「Download ZIP」自带 `<repo>-<branch>/` 顶层目录，bundle-relative 链接 `/tables/x.md` 全部解析不到。

v1 落地后暴露的第二个问题（2026-09-08，`canway-it-support.zip` 实测）：真实 OKF bundle 的操作类知识大量用 `![](../../assets/xxx.jpg)` 引用包内图片（该包 225 篇 concept 中约 102 篇、1187 处本地图，图片约 1131 张 / 57MB）。v1 把所有非 `.md` 一律跳过，正文里的相对路径原样入库，阅读时被展示层替换为「> 图片：alt」占位。结果是导入报成功、知识却缺了截图步骤——用户无法从结果判断知识是否完整。同时 ZIP 上限 50MB 让带图的真实包根本传不上去。

## Solution

在现有「预检 → 一次性 token → 执行进 generation」管线里新增第四种 `archive_kind="okf"`，由前端「导入 OKF」按钮通过 `options.import_format="okf"` 显式触发。安全边界（ZIP 校验、token/CAS、conflict candidate、目录路由、`stage_ai_page`）零复制；OKF 分支只负责：用 PyYAML 解析 frontmatter、跳过保留文件与不合规文件、探测 bundle 根、`type` → `page_type` 映射、把 bundle 内路径链接改写为 `[[标题|文字]]`、同 bundle 内标题冲突确定性消歧、frontmatter 余项完整保留到 `PageVersion.meta_snapshot["okf"]`。

前端复用 `WikiMarkdownImportModal`，加 `importFormat` prop；OKF 模式下换文案、只收 `.zip`、默认勾选「按文件夹建目录」，预检结果多一块 OKF 摘要。

v2：将导入 concept 正文引用的包内图片视为知识的一部分。预检解析 `![alt](path)` 与引用式图片定义，逐条在 ZIP 内定位并校验为真实图片；任一缺失、逃出 bundle、假图即整包拒绝并列出「哪篇 md 缺哪条路径」。校验通过的图在执行时落盘到知识库级 `wiki/media/<kb>/pages/<sha>.<ext>`，正文引用改写为该 locator，复用现有知识页 `wiki/media` 展示签发链路。ZIP 上限提到 200MB / 解压 400MB。图片语义只挂在 `import_format="okf"`，普通 Markdown ZIP 导入不变。

## User Stories

1. As a 知识库管理员, I want 把一个 OKF bundle 的 ZIP（含 GitHub 下载 zip）直接导入知识库, so that 不必手工改写 frontmatter 或整理目录层级。
2. As a 知识库管理员, I want OKF 的子目录（`tables/`、`metrics/`、`references/joins/`）默认成为知识库目录, so that bundle 作者刻意组织的层级得以保留；也能关掉它改走自动/分类路由。
3. As a 知识库使用者, I want 导入后的概念在关系图上互相连通, so that OKF「graph-shaped」的价值不丢。
4. As a 知识库管理员, I want 预检时看清哪些文件会被跳过（及原因）、`type` 如何映射到页面类型、哪些标题被消歧重命名、多少链接被改写或解析不到, so that 执行前能判断结果是否符合预期。
5. As a 知识库管理员, I want 同一 bundle 更新后重导入是低摩擦的覆盖, so that agent 持续重写的 bundle 不会每次都把所有页面推进决策中心。
6. As a 平台维护者, I want OKF 的 `sources` / `generated` / `verified` / `status` / `stale_after` 与任何未知键都原样保留, so that 以后做 OKF 导出或信任分级时数据不丢。
7. As a 知识库管理员, I want 正文引用的包内截图随 bundle 一起进入知识库、阅读时能看到, so that 操作指南不会缺步骤。
8. As a 知识库管理员, I want 包里缺图时预检直接拒绝并告诉我哪篇 md 缺哪张图, so that 我不会把残缺的知识当完整知识导进去，也能据此补图或删引用后重试。

## Implementation Decisions

### 触发与契约

- 复用 `import_markdown_preflight` / `import_markdown_execute` 两个端点（`server/apps/opspilot/viewsets/wiki_kb_view.py:329,364`），不新增端点。前端在 `options.import_format = "okf"` 显式声明；`inspect_markdown_archive(content, filename, import_format=...)` 收到 `okf` 时走 OKF 解析并返回 `archive_kind="okf"`；不传则完全走现有嗅探逻辑，现有 `markdown` / `third_party` / `native` 行为不变。
- `import_format` 随 `options` 存进 `WikiImportPreflight.options`，execute 时从记录读回，天然参与现有 preview fingerprint 校验；不改 token 绑定逻辑。`WikiImportPreflight.archive_kind`（`max_length=20`）直接写 `okf`。
- 只接受 ZIP 上传。不做 git URL 拉取（出网、凭据、超时、资源边界一整套新问题与本变更「复用逻辑」目标冲突）。
- 声明了 `okf` 但 ZIP 里一个合规 concept 都没有，整包拒绝，错误码 `okf_no_concepts`（复用 `archive_has_no_markdown` 的语义）。

### Bundle 根探测

- 预检时自动探测 bundle 根：若 ZIP 所有条目共享唯一顶层目录，且该目录下（任意深度）存在 `.md` 文件，则以该目录为根；否则根为 ZIP 根。只下钻一层，不做手动选择子目录 UI。
- 探测结果 `bundle_root` 回显到预检 `preview.okf`。后续的 bundle-relative 链接解析、文件夹目录建立、`concept_id` 计算均以此根为基准（`archive_path` 去掉根前缀）。

### frontmatter 解析（仅 OKF 分支）

- 新增 `server/apps/opspilot/services/wiki/okf_import_service.py`，提供 `parse_okf_document(path, text)`；共享 `markdown_import_service._split_front_matter` 的 `---` 分界逻辑，块内用 `yaml.safe_load` 解析（PyYAML 已在 server 其他 app 使用，见 `apps/core/utils/loader.py`）。现有 `parse_markdown_document` 与三个已有分支不动。
- OKF 宽容处理：`tags` 若是字符串则按逗号拆分；`verified` 若是裸 mapping 视为单元素列表（OKF §5.2 MUST）；`title` 缺省时按文件名派生，规则与 `_title_from_filename` 一致。
- YAML 非 mapping、解析异常、`type` 缺失或空、非 UTF-8 三类情况视为不合规。

### 保留文件与不合规文件

- 任意层级的 `index.md` / `log.md` 直接跳过、不计入不合规。根级 `index.md` 若带 frontmatter，只读取 `okf_version` 回显。
- 不合规 `.md` 跳过并计入 `skipped_entries`，同时进入 `preview.okf.skipped` 清单，每项 `{path, reason}`，`reason` ∈ `yaml_invalid` / `type_missing` / `not_utf8` / `reserved`。执行时按同一规则跳过。
- 非 `.md` 文件（`.py`、`.sql`、`viz.html`）一律跳过，即使被 `computation` / `attester.resource` 引用；沿用现有 `skipped_entries` 计数。图片文件的例外见「正文图片（v2）」：**被将导入 concept 正文引用的**图片随包导入，未被任何导入页引用的图片仍按跳过处理。

### `type` → `page_type` 映射

- 大小写不敏感匹配知识库 active structure 的 `page_types`：命中则用 KB 的规范写法；未命中则 `page_type="concept"`，同时加标签 `okf:<原始type>`，原始 `type` 存 `meta_snapshot.okf.type`。
- 不把 schema 外的类型原样写入 `page_type`（类型筛选与目录规则以 schema 为准），也不做逐 type 的用户映射 UI。
- 预检 `preview.okf.type_mapping` 回显 `[{okf_type, page_type, matched: bool, count}]`。

### 链接改写

- 仅改写正文 body 中的 markdown 链接 `[text](target)`（图片语法 `![alt](target)` 不走此规则，见「正文图片（v2）」）；frontmatter 里 `resource` / `sources[].resource` / `computation` / `executor.resource` / `attester.resource` 的路径不动、原样进 meta。
- 解析规则：`/` 开头按 bundle-relative（相对探测到的根）；否则相对当前文件所在目录；`.md` 后缀可省略；`#锚点` 与 `?query` 丢弃；`http(s)://`、`mailto:` 等带 scheme 的外链不动。
- 能解析到 bundle 内 concept 的链接改写为 `[[<目标最终标题>|<原链接文字>]]`（目标标题取消歧后的标题）；解析不到的（OKF 允许 broken link）原样保留。
- 预检 `preview.okf.links` 回显 `{rewritten, unresolved}` 计数。
- 不改 `relation_service` / `generation_relation_service` 的链接提取语义。

### 标题冲突消歧（bundle 内）

- 按 `archive_path` 字典序遍历；规范化标题（`title_identity_key`）首次出现者保留原标题；后续冲突者标题改为 `「<原标题> (<父目录名>)」`，仍冲突则逐级加更长路径 `「<原标题> (a/b)」`，直至唯一。消歧只依赖路径排序，重导入同一 bundle 得到相同标题，正常走 update。
- 预检页面表行加 `renamed_from`（原标题）字段；原标题同时存 `meta_snapshot.okf.title`。
- 与知识库已有页面同名不消歧，沿用现有规则：`ai` 页 update、非 `ai` 页 candidate + conflict CheckItem。

### 元数据落点与正文

- 消费掉 `type` / `title` / `tags` 后，frontmatter 全部余项（含 `description`、`resource`、`sources`、`usage_window`、`generated`、`verified`、`status`、`stale_after`、`runtime`、`parameters`、`computation`、`executor`、`attester` 及任意未知键）原样存 `PageVersion.meta_snapshot["okf"]`，并附 `okf_version`（根 `index.md` 声明值或空）、`concept_id`（相对根路径去 `.md`）、`type`（原始值）、`title`（原始值）、`trust_tier`（`unverified` / `machine_confirmed` / `human_reviewed`，按 OKF §5.3 由 `verified[].by` 是否有 `human:` 前缀推导）。现有 `source` / `archive_path` / `archive_sha256` 键保留，`source` 值为 `okf_import`。
- `description` 非空且 body 前 200 字符不包含该句时，在 body 开头注入一行 `> <description>` 引用块，使检索与 embedding 能吃到它。
- 标签追加：`okf:<type>`（仅未命中 schema 时）、`okf:<trust_tier>`、`okf:deprecated`（`status: deprecated` 时）。
- `status: deprecated` 的 concept 正常导入，不映射到 `KnowledgePage.status=archived`（archived 会让它从 generation 消失、链接断掉，违背 OKF「保留供链接与历史」语义）。
- `# Computation` 代码块与 Attested Computation 字段只作为正文与 meta 原样保留，不执行、不 attest。

### 目录结构

- 复用现有路由选项（`auto` / `target` / `classification`）与 `create_directories_from_folders`。OKF 默认勾选后者；用户可关闭改走自动/分类路由。`target` + 建目录组合（挂到某目录下再按文件夹建子目录）沿用现有实现。
- OKF 按文件夹建目录时，只把压缩包**第一层**文件夹名（大小写不敏感）对齐到知识库结构**根目录**。命中则页面进入该目录，更深子文件夹只在该目录下新建或复用，**不会**把子路径（如 `wiki/operations`）再对齐到另一个根目录 `operations`。第一层未命中时，整段路径仍在系统待归类目录（UI「未分类」）下按文件夹新建。
- 同级同名：OKF 复用已有目录，不再报 `folder_directory_name_conflict`。第三方 Markdown ZIP 仍要求显式 `path_mappings`。指定了 `target_directory_id` 时不向结构根对齐，只在目标目录下建/复用子目录。
- `_folder_structure_plan` 的 kind 白名单从 `third_party` 扩为 `{third_party, okf}`；文件夹路径以探测到的 bundle 根为基准。深度 ≤ 8 约束不变。
- `restore_structure`（原生结构恢复）对 OKF 不可用，沿用现有 `native_structure_restore_unavailable` 拒绝。

### 正文图片（v2）

成败标准：将导入的 concept 正文引用了本地图片，而图片没有进入知识库（阅读时裂图或显示占位）即视为**导入失败**，不允许作为「成功但展示降级」静默入库。

- **识别范围**：只扫 body 中的行内图片 `![alt](target)`（可带 `"title"`）与引用式图片 `![alt][ref]` + `[ref]: target`。代码围栏内的图片语法不算引用。`target` 带 scheme（`http(s)://`、`data:` 等）、已是 `wiki/media/` locator 的不算本地图。HTML `<img src>` 与普通附件链接 `[说明](foo.png)` 不纳入检查、不因此拒包；预检回显未检查的 HTML 图片数（`images.html_unchecked`）作为提示。
- **路径解析**：与概念链接同规则——`/` 开头相对探测到的 bundle 根，否则相对当前 `.md` 所在目录，允许 `../`；对 target 做 URL 解码（`%20` 等）；`#fragment` 丢弃；本地路径带 `?query` 视为缺图（文件名对不上）。解析结果必须仍在 bundle 根内，逃出根视为缺图。不允许省略后缀。
- **图片判定**：后缀 ∈ `png / jpg / jpeg / gif / webp / bmp / svg / tif / tiff`（大小写不敏感）；ZIP 内该成员必须存在、是文件而非目录、非 0 字节；光栅格式校验文件头魔数，SVG 须是 XML 且根元素为 `svg`，且不含 `<script`、`on*=` 事件属性或 `javascript:`。任一不满足视为「假图」，与「ZIP 里没有」同等处理。
- **失败粒度**：任一将导入 concept 存在缺图 / 逃出根 / 假图 → **整包预检拒绝**，错误码 `okf_images_missing`，`details.missing` 列出 `[{archive_path, image_path, reason}]`，`reason` ∈ `not_found` / `outside_bundle` / `not_image` / `invalid_query`（列表有界，超出部分回显 `truncated` 与总数）。不采用「跳过缺图页、其余照常导入」。
- **落盘位置**：图片属于知识页，不暗建资料。locator 形态 `wiki/media/<kb_id>/pages/<sha256>.<ext>`，知识库级按内容哈希存一份；同一次导入内多篇 md 引用同一张图共用同一对象。现有 `_is_safe_media_locator` / `_MEDIA_LOCATOR_RE` / 代理校验 / 前端 `wikiMediaDisplay.ts` 正则从「第四段必须为数字资料 ID」放宽为「数字资料 ID 或字面 `pages`」；`Material` 删除只清 `wiki/media/<kb>/<material_id>/`，知识库删除仍整前缀清，两者与 `pages` 段不冲突。
- **时序**：locator 由内容哈希决定，预检阶段即可计算并完成正文改写（`preview.pages[].content_sha256` 仍取原始文件字节，不受改写影响）；预检**不上传**对象。执行阶段在写页面前上传（`save_media_bytes` 同内容幂等）；任一上传失败则整次执行失败、生成代不激活，并尽力删除本次新上传（此前不存在）的对象，删不掉只记日志，不再抛出。
- **生命周期**：页面 `destroy` / `batch_delete` 是逻辑归档（`status=archived`，可恢复），归档页视为**仍在引用**，不清图。GC 只在覆盖导入时发生：对本次导入被替换的旧版本引用、而新版本不再引用的 locator，在导入持有的知识库锁内检查知识库内全部当前正文与未关闭 candidate（`CheckItem.status=open` 的 `candidate_version.body`）是否仍引用；无引用才删对象。旧 `PageVersion` 不占引用。不做全库孤儿巡检。
- **范围**：以上只对 `import_format="okf"` 生效；`markdown` / `third_party` / `native` 分支的图片处理不变（仍跳过非 `.md`，正文原样）。

### 体积上限（v2，共享校验）

- `MAX_ARCHIVE_BYTES` 50MB → **200MB**，`MAX_UNCOMPRESSED_BYTES` 100MB → **400MB**；`MAX_FILE_BYTES` 10MB、`MAX_ENTRIES` 5000、压缩比 1000 不变。ZIP 校验由所有导入格式共用，因此 Markdown ZIP 上限同步提高；这是接受的副作用。
- 传输链路为浏览器 → Next `/api/proxy` → Django `upload.read()`，预检与执行各上传一次、各全量驻留内存一次。接受两次上传，不做服务端暂存 ZIP。部署侧反向代理需放行 ≥200MB 请求体（仓库内无 nginx / Next body 限制配置，部署文档补一句）。
- 前端上传区与超限错误文案同步为 200MB / 单文件 10MB。

### 贡献归属

- 全部走 `stage_ai_page`，`contribution="ai"`，与现有 Markdown 导入一致。OKF 的 `human:` 生成/验证只体现为 `trust_tier` 与 `okf:human_reviewed` 标签，不映射为 `contribution=human`。理由：OKF human-verified 是「有人确认过这份内容」，`contribution=human` 在 llm_wiki 里是「wiki 内人工维护、需保护不被 AI 覆盖」；重导入必须低摩擦覆盖。用户在 wiki 内手工编辑后自然变 `human/mixed`，之后重导入进 candidate，正是所需保护。

### 预检结果扩展

- `preview` 新增 `okf` 对象（仅 `archive_kind="okf"` 时存在）：`{okf_version, bundle_root, type_mapping[], skipped[], links{rewritten, unresolved}, renamed_count}`；页面表行新增可选 `renamed_from`。
- v2 在 `preview.okf` 追加 `images: {count, bytes, pages, html_unchecked}`——将随包导入的去重图片数、合计字节、涉及页面数、未检查的 HTML `<img>` 处数。缺图时不产生 preview，直接 `okf_images_missing` 拒绝。
- `preview_fingerprint` 覆盖整个 `preview`，`okf` 对象自动参与 CAS 校验。

### 前端

- `PageTab.tsx` 在「导入 Markdown」旁新增「导入 OKF」按钮，独立 `open` 状态，渲染第二个 `WikiMarkdownImportModal` 实例并传 `importFormat="okf"`。
- `WikiMarkdownImportModal` 新增 `importFormat?: "markdown" | "okf"`（默认 `markdown`）。`okf` 模式：标题与提示文案换 OKF；`Upload.Dragger accept=".zip"`、文件名校验只放行 `.zip`；`preflightOptions` 带 `import_format: "okf"`；`createDirectoriesFromFolders` 初始值为 `true`，选文件后的首次自动预检带 `create_directories_from_folders: true`（现有 markdown 模式仍强制 `false`，行为不变）；「按文件夹建目录」Alert 的显示条件从 `archive_kind === "third_party"` 扩为 `third_party | okf`。
- 预检结果区在 `okf` 模式下多渲染一块只读摘要：bundle 根、`okf_version`、type→page_type 映射表（命中/未命中）、跳过清单（可折叠）、链接改写/未解析计数、重命名页面数。页面表「页面」列在 `renamed_from` 存在时显示原标题。
- `archiveKindLabel` 的 Record 补 `okf`；`types/wiki.ts` 的 `WikiMarkdownImportArchiveKind` 加 `"okf"`，`WikiMarkdownImportPreflightOptions` 加 `import_format`，`WikiMarkdownImportPreview` 加 `okf?`，`WikiMarkdownImportPreviewPage` 加 `renamed_from?`。
- i18n 在 `web/src/app/opspilot/locales/{zh,en}.json` 补 `wiki.okfImport*` 键。
- v2：OKF 摘要增加「随包导入图片 N 张 / 合计大小 / 涉及页面数」，`html_unchecked > 0` 时给一条提示。`okf_images_missing` 走现有「短 toast + 弹窗 Alert」错误展示，Alert 内按 `archive_path` 分组列出缺失 `image_path` 与原因，超出上限时显示「还有 N 条」。上传区文案改为「压缩包不超过 200MB，包内单个文件不超过 10MB」。知识页阅读侧无需改动（`KnowledgePageSerializer` 已对 body 做 `rewrite_media_urls_for_display`），仅放宽 `wikiMediaDisplay.ts` 的 locator 正则。
- 布局遵守 Web UI 硬约束：Tailwind `className`、语义 token、复用 AntD `Alert` / `Table` / `Tag`。

## Testing Decisions

- 好测试只断言对外行为：给定 ZIP 字节 + `import_format="okf"`，预检返回的 `archive_kind` / `preview.okf` / 页面表内容；执行后 `KnowledgePage` / `PageVersion.body` / `meta_snapshot.okf` / `tags` / 关系边；不声明 `import_format` 时三个已有分支的既有测试原样通过。不绑定 `okf_import_service` 私有 helper 的调用次数。
- Fixture 用官方 `bundles/acme_retail`（含 `verified`、`status: deprecated`、`sources` 指向 bundle 内路径、Attested Computation、`attesters/*.py`、根 `log.md`）与 `bundles/stackoverflow` 的裁剪样本（`tags` 逗号串、多行 `description`、`generated` 展开写法、同目录相对链接 `posts_questions.md`），在测试内以 `zipfile` 动态打包，不提交大文件。
- 最高接缝优先：
  - 根探测：GitHub 风格 `repo-main/` 单顶层目录被下钻，`bundle_root` 回显；多顶层目录不下钻。
  - 解析：嵌套 `generated` / list-of-dict `sources` / 多行 `description` 正确落入 `meta_snapshot.okf`；`tags` 逗号串拆分；`verified` 裸 mapping 归一为列表且 `trust_tier=human_reviewed`。
  - 跳过：`index.md` / `log.md` / 无 frontmatter 的 `README.md` / 无 `type` 的 `.md` / `.py` 各自进入正确 `reason`，且不产生页面；零 concept 时 `okf_no_concepts` 拒绝。
  - 类型映射：KB `page_types=["Metric","concept"]` 时 `type: metric` 命中为 `Metric`；`type: BigQuery Table` 落 `concept` 并带 `okf:BigQuery Table` 标签。
  - 链接：`/tables/orders.md`、`./revenue.md`、`posts_questions.md`、带 `#anchor` 的链接改写为 `[[目标标题|文字]]`；解析不到的与 `https://` 外链原样；改写计数正确；执行后 `PageRelation` 中存在对应边。
  - 消歧：`metrics/revenue.md` 与 `tables/revenue.md` 同标题时第二个变 `Revenue (tables)`，`renamed_from` 回显，`meta_snapshot.okf.title` 为原标题；同一 ZIP 重导入两次第二次全部为 update、页面数不变。
  - `description` 注入：body 不含该句时首行为 `> ...`；已含时不重复注入。
  - 目录：`okf` + `create_directories_from_folders` 仅将归档第一层文件夹对齐到结构根同名目录；子目录不映射到根。未命中第一层时在待归类下建树。`restore_structure` 对 OKF 被拒。
  - 贡献归属：导入页 `contribution="ai"`；手工编辑后再导入进 candidate。
  - 回归：不带 `import_format` 的现有 `test_markdown_import.py` / `test_markdown_import_governance.py` 全部通过；带 `type` 键的普通 Markdown ZIP 在未声明 `okf` 时仍按 `third_party` 处理。
  - 图片（v2）识别与解析：行内 `![a](../assets/x.png "t")`、引用式 `![a][ref]` + `[ref]: /assets/x.png`、`%20` 编码、`#frag` 均定位到 ZIP 成员；代码围栏内、`https://`、`data:`、已有 `wiki/media/` 不计入；`<img src>` 不拒包但 `images.html_unchecked` 计数。
  - 图片（v2）拒绝：ZIP 缺该成员 / `../../` 逃出 bundle 根 / 带 `?v=1` / 0 字节 / `.png` 后缀但内容为文本 / SVG 含 `<script>` 各自触发 `okf_images_missing`，`details.missing` 含正确 `archive_path`、`image_path`、`reason`；未被任何 concept 引用的图片缺失或损坏不拒包。
  - 图片（v2）落盘与展示：执行后 `PageVersion.body` 中引用为 `wiki/media/<kb>/pages/<sha>.<ext>`，对象存在；同一 ZIP 内两篇引用同一图只产生一个对象；`KnowledgePageSerializer` 输出的 body 中该 locator 被改写为可展示 URL；`sign_media` 与代理校验接受 `pages` 段、仍拒绝跨知识库与非法段。预检阶段不产生任何对象。
  - 图片（v2）失败与 GC：模拟 `save_media_bytes` 抛错时执行整体失败、生成代未激活、本次新上传对象被删除；重导入去掉某图引用后，仅当知识库内无其他当前正文与 open candidate 引用时对象才被删，仍有引用（含同 bundle 内其他页、归档页）时保留。
  - 上限（v2）：201MB 空载荷报 `archive_size_exceeded` 且文案含 200MB；普通 Markdown ZIP 中的图片仍被跳过、正文原样。
- 前端：`WikiMarkdownImportModal` 在 `importFormat="okf"` 下的 accept / 初始预检 options / OKF 摘要渲染用组件测试或 Storybook 锁住；不引入浏览器 E2E。
- 验证命令沿用 `DEVELOP.md`：server 用 sqlite `uv run pytest server/apps/opspilot/tests/wiki/ --no-cov`；web `pnpm lint`、`pnpm type-check`。

## Out of Scope

- OKF 导出（body 已改写为 wikilink，需要单独设计反向还原与 `concept_id` 路径重建）。
- git URL / tarball 拉取；ZIP 内手动选择子目录。
- OKF 元数据的页面 UI 展示；`stale_after` 过期提醒、trust tier 降权等产品语义。
- Attested Computation 的执行与 attest；`.py` / `.sql` 等非 `.md`、非图片资源的导入。
- 普通 Markdown / 第三方 ZIP 导入的图片随包落盘与缺图校验（先只做 OKF）。
- HTML `<img>` 与附件链接 `[说明](foo.png)` 的落盘与缺失校验（只回显未检查数）。
- 知识页导出携带 `wiki/media` 对象并还原为相对路径（`export_markdown` 现只输出 locator，换库导入或离线阅读会裂图；资料生成的页面同样受影响，为既有限制，另立变更）。
- 归档页的图片回收、全库孤儿对象巡检、图片引用表模型。
- 服务端暂存 ZIP 以避免预检 / 执行两次上传；流式解压。
- 把现有 `markdown` / `third_party` / `native` 分支切换到 PyYAML。
- 靠嗅探自动识别 OKF（必须显式 `import_format`）。
- 逐 `type` 的用户映射 UI；把 schema 外类型原样写入 `page_type`。
- 修改 `relation_service` 使其识别 markdown 路径链接。
- 按 `concept_id`（路径）而非标题匹配已有页面（`concept_id` 已存 meta，为后续预留）。
- `status: deprecated` 映射为 `KnowledgePage.status=archived`。

## Further Notes

- 对齐来源：grill-me（2026-09-03 ～ 09-04），逐项结论：独立按钮 + 复用管线（`archive_kind="okf"`）；只收 ZIP + 自动根探测；仅 OKF 分支用 PyYAML；不合规文件跳过并列清单、零 concept 整包拒绝；`type` 大小写不敏感匹配 schema、未命中 `concept` + `okf:<type>`；bundle 内链接改写为 wikilink；frontmatter 余项存 `meta_snapshot.okf` + `description` 注入；复用目录选项、OKF 默认建目录；全部 `contribution=ai`；`options.import_format` 显式声明；复用弹窗加 `importFormat` prop；标题冲突路径序确定性消歧。
- OKF 规范原文见仓库 `SPEC.md`（v0.2）。与本变更直接相关的条款：§3.1 保留文件、§4.1 `type` 唯一必填与「消费者 SHOULD 保留未知键」、§5.2 `verified` 裸 mapping MUST 视为列表、§5.3 trust tier 推导、§6.1 链接形式与 broken link 容忍、§11 conformance「MUST NOT reject」清单、§13.1 v0.1 兼容（`timestamp` / `# Citations`，本变更不做特殊处理，原样进 meta / body）。
- `okf:` 前缀标签是本变更引入的约定，用于以后按 OKF 类型 / 信任分级筛选与导出；不与现有标签体系冲突（现有标签为自由字符串）。
- 链接改写是有损的：改写后 body 与源文件不再字节一致。后续 OKF 导出需依赖 `meta_snapshot.okf.concept_id` 与 wikilink → 路径的反向映射，届时再设计。
- v2 对齐来源：grill-me（2026-09-08），逐项结论：正文引用本地图而图未入库 → 算失败；ZIP 内有且可解析 → 落盘并改写、未引用的图继续忽略；缺图整包拒绝并列出 md + 图路径；只认 `![]()` 与引用式定义，`<img>` / 附件链接不拒包；路径规则同概念链接、须在 bundle 内、后缀白名单、带 `?query` 算缺；ZIP 200MB / 解压 400MB、单文件与条目不变；预检只验不传、执行上传、失败不激活；图挂知识页不挂资料、知识库级按哈希存一份多页共用；GC 只在覆盖导入时对释放 locator 做引用检查（当前正文 + open candidate），归档页视为仍引用；假图（空 / 魔数不符 / 含脚本 SVG）等同缺图；先只做 OKF。
- v2 的 GC 边界说明：不同导入之间不会互相引用图片；若两次导入恰有字节相同的图会落到同一 `<sha>` 对象，删除检查按知识库全部当前引用判定，因此不会误删，也不为每次导入单独开前缀（避免重导入同 bundle 时重复上传几十 MB）。
- v2 图片改写同样有损：body 中相对路径变为 locator，OKF 导出需把 `wiki/media/<kb>/pages/<sha>.<ext>` 反向导出为文件 + 相对路径，与 wikilink 反向映射一并设计。

## Completion Evidence

- 后端：`server/apps/opspilot/services/wiki/okf_import_service.py` + `markdown_import_governance_service.py` 的 `archive_kind=okf` / `options.import_format=okf` 分支。
- 前端：`PageTab` 工具栏「导入」下拉（Markdown / OKF）+ 两个 `WikiMarkdownImportModal`（`importFormat="okf"`）；跳过清单用 AntD `Collapse`。入口由并列按钮改为下拉，是实现后的工具栏收口，不改变 `options.import_format="okf"` 契约。
- 验证（2026-09-04，实现收口重跑）：
  - `uv run pytest apps/opspilot/tests/wiki/test_okf_import.py apps/opspilot/tests/wiki/test_markdown_import_governance.py --no-cov` → 15 passed（含 schema `page_types` 命中 `Metric`、跳过 `type_missing`、执行后 `PageRelation` 边）
  - `uv run pytest apps/opspilot/tests/wiki/test_markdown_import.py::test_parse_markdown_without_front_matter_uses_heading_then_filename apps/opspilot/tests/wiki/test_markdown_import.py::test_parse_markdown_tolerates_loose_front_matter_values_and_missing_boundary --no-cov` → 2 passed
  - `pnpm type-check` → 0
  - `pnpm exec vitest run src/app/opspilot/utils/__tests__/wikiMarkdownImport.test.ts` → 2 passed
  - 针对改动文件的 eslint：0 errors（既有 exhaustive-deps disable 告警 2 条）
- `test_markdown_import.py` 里 `import_markdown_archive` 导入失败与未 bootstrap KB 的 legacy 预检 422 为既有问题，本变更未改那条旧入口契约。未做浏览器 E2E。
- v2 验证（2026-09-08，实现收口）：
  - `uv run pytest apps/opspilot/tests/wiki/test_okf_import.py apps/opspilot/tests/wiki/test_markdown_import_governance.py apps/opspilot/tests/wiki/test_parsed_media.py --no-cov --nomigrations`（sqlite `:memory:`）→ **36 passed**。含缺图整包拒绝、共享图落盘、MinIO 失败回滚、覆盖导入 GC、`pages` locator 签发、201MB 文案、第三方 Markdown ZIP 仍跳过图片。
  - 不加 `--nomigrations` 时 django_db 收集阶段 ERROR：`monitor` 存在两个 `0064` 叶迁移冲突（基线问题，本变更未改 monitor 迁移）。
  - `pnpm exec vitest run src/app/opspilot/utils/__tests__/wikiMarkdownImport.test.ts src/app/opspilot/utils/__tests__/wikiMediaDisplay.test.ts` → 12 passed
  - `pnpm type-check` → 0
  - 未做浏览器 E2E；阅读侧复用既有 `rewrite_media_urls_for_display` + 放宽后的 `wikiMediaDisplay` 正则。
