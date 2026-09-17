# OpsPilot Wiki 导出 Open Knowledge Format (OKF) Bundle

Status: implemented

## Problem Statement

知识库已经能消费 OKF（ZIP 导入、frontmatter 进 `meta_snapshot.okf`、正文图片落盘），但不能生产合规 OKF 包。现有「导出 Markdown」产出的是内部 native 格式，外部 Markdown / OKF 工具打不开链接、也带不出图。导入时特意保留的 provenance / trust 字段没有反向出口，round-trip 断裂。管理员无法把当前可读知识完整交给合作方或再导回本系统。

## Solution

在「导出 Markdown」旁增加「导出 OKF」：一键下载当前 active generation 可读范围内的 active 页面，打成 OKF v0.2 ZIP。曾经 OKF 导入的页按保存的 `concept_id` 与 frontmatter 还原；自产页合成最小合规 concept。正文里的 `[[wikilink]]` 改回 bundle 路径链；知识库里能显示的 `wiki/media` 图片随包放到 `assets/`，导出后用普通编辑器打开 md 必须能见图。导入时就已经裂的图，导出可以继续裂，不因此整包失败。不替换现有 native 导出，不改运行时与检索。

## User Stories

1. As a 知识库管理员, I want 从知识库菜单导出 OKF ZIP, so that 可以交给不使用 OpsPilot 的系统或合作方。
2. As a 知识库管理员, I want 曾 OKF 导入且图片能显示的知识再导出后打开 md 仍能见图、再导入预检能过, so that 外部维护与内部编辑可以交替。
3. As a 知识库使用者, I want 解开 ZIP 用普通 Markdown 阅读器打开单篇就能看正文和截图, so that 不依赖 OpsPilot UI。
4. As a 平台维护者, I want 根 `index.md` 声明 `okf_version: "0.2"` 且每篇 concept 有 `type`, so that 包符合 OKF 符合性要求。
5. As a 知识库管理员, I want 导出失败时看到接口返回的原因（例如超出体积、没有可读 generation）, so that 知道下一步改什么而不是只看到「导出失败」。
6. As a 安全/运维, I want 导出有页数和体积上限并记审计, so that 大库不会拖垮服务。

## Implementation Decisions

### 成功标准与范围

- P0 成功标准是**可再导入的完整交换包**，不是「给人逛的干净文件树」。验收以导入 → 导出 → 再预检为准：concept 数、主要 `type`、能显示的图片可对上。
- 路径只实现 `stable`。不提供 `title_slug`、不带图、缺图整包失败等 query 开关。
- 只导出 active generation 可读范围内的 **active** 页面。归档页不导出，与现网 Markdown 导出一致。
- 不把运行时改成文件系统 OKF 仓库；不执行 Attested Computation（字段仅透传）；不导出 git 历史。

### API 与权限

- 新增独立 `GET .../export_okf/`，与 `export_markdown` 并列，不用同一个 action 加 query 切换，以免破坏现有 native ZIP 客户端。
- 权限与 Markdown 导出相同（知识库列表查看）。
- 无 query 参数。固定：打包可读图片、写根 `log.md`、`stable` 路径。
- 成功：`200`，`application/zip`，`Content-Disposition` 附件，文件名 `wiki-kb-{id}-okf.zip`。
- 无 active generation / 读范围失效：`409`，复用现有 active-generation 读错误形态。
- 超页数：`400`，`code=max_pages`。超体积：`400`，`code=max_bytes`。
- 不把本端点作为新的对外 OpenAPI 网关能力；暴露方式与现有 Markdown 导出一致（产品内下载）。
- 审计记录知识库名、页数、字节、图片数。

### 配额

- 页数上限与 Markdown 导出相同：2000。
- OKF 导出 ZIP 上限 **200MB**（与 OKF 导入对齐），不抬高 native 导出的 50MB。
- 先组包再检查 ZIP 字节；超过则失败，不静默截断。按目录导出留到后续变更。

### Bundle 布局

- ZIP 内唯一顶层目录 `{安全化知识库名}-okf/`，以便导入侧「唯一顶层目录即 bundle 根」探测能剥掉。
- 根 `index.md`：frontmatter 仅 `okf_version: "0.2"`，正文含知识库名、可选用途摘要、目录列表、导出时间 / generation / 概念数。
- 根 `log.md`：本次导出一条摘要。导入会跳过它，不影响 round-trip。
- **不**生成各层子目录 `index.md`（导入本就会跳过；对再导入和「打开单篇见图」无帮助）。
- 不写 native 的 `manifest.json` / `structure.json`。
- ZIP 成员名使用 UTF-8 并带 UTF-8 标志，避免中文目录/标题在 Windows 下再出现乱码路径。

### 路径（concept_id）

优先级：

1. `meta_snapshot.okf.concept_id` 非空 → 使用（posix，无 `.md`）。
2. 否则 `meta_snapshot.archive_path` 以 `.md` 结尾 → 由归档路径派生。
3. 否则合成：目录**显示名**链（posix 安全、保留中文、去掉非法文件名字符）+ `{page_id}-{slug(title)}.md`。无目录则挂根或未分类显示名。禁止把内部 `dir_<uuid>` 写进 ZIP。
4. 两页抢同一 concept_id：后分配者文件名追加 `-{page_id}`。

`title`：优先 `meta_snapshot.okf.title`（导入消歧前的原标题），否则当前页标题。导出**不再**为冲突改 title（OKF 允许同名不同 path）。

### 图片

- 扫描导出用正文（改写前）中的 Markdown 图片：`![alt](wiki/media/...)` 与引用式定义。HTML `<img>`、外链 `http(s)` / `data:` 不下载、不改写（导入时本来就不会按图入库或显示）。
- Locator 必须落在本知识库 `wiki/media` 前缀下，禁止借导出读其它库。
- 对象存得到：按内容 sha256 去重，写入 `assets/{sha256 前 16 位}{原后缀}`，正文改为相对**当前 md 文件**的相对路径，使解开 ZIP 打开该 md 能见图。
- 对象读不到：视为「导入时或当前就已经裂」，保留原文（locator 或原语法），**导出仍成功**。不提供 omit/fail 开关，也不把缺图当整包错误。
- SVG 原样导出，不做二次消毒（已在库内即信任边界内）。

### Frontmatter

- 核心写入/覆盖：`type`、`title`、`tags`；自产页另写 `generated`。
- `type`：`meta_snapshot.okf.type` → 否则 `page_type` → 否则 `concept`。
- `tags`：优先 meta 原始 tags，否则当前页 tags；去掉导入衍生的 `okf:*` 前缀标签。
- 从 `meta_snapshot.okf` 透传其余键（`description`、`sources`、`verified`、`status`、`stale_after`、computation 家族、未知键）。不写出内部衍生键：`trust_tier`、`concept_id`、`okf_version`（版本只出现在根 index）。
- 有 `meta.generated`：**原样写出**。改正文也不刷新 `generated.at` / `by`，以免盖掉原作者信号。无 `generated` 的自产页才合成 `by: process:opspilot-llm-wiki/1` 与当前版本时间。不自动写 `verified`。
- `status`：meta 有则原样；否则 tags 曾含 `okf:deprecated` 则 `deprecated`；否则省略。
- YAML 用安全 dump、保留 unicode、不按字母重排键；禁止把 JSON 字符串当 YAML。正文不额外叠一层 `# title`（body 已有一级标题时）；body 为空时可写 `# {title}`。
- 若 frontmatter 已有 `description` 且 body 首段恰好是相同内容的 `>` 引用块，剥掉该块，避免 round-trip 叠两层。

### 链接

- 只改代码围栏外的 `[[标题]]` / `[[标题|文字]]`。命中本包页面 → `[文字](/{concept_id}.md)`（bundle 根相对）。未命中 → 保留原 wikilink 并计数，不失败。
- 已是 markdown 路径链的不强制重写。`http(s):` / `mailto:` 不动。

### 前端

- 与后端同一变更。知识页工具栏「导出 Markdown」旁增加「导出 OKF」（中文）/ `Export OKF`（英文）。
- 直接 GET 下载，无预检、无选项弹窗。
- 下载方式与 Markdown 导出相同（blob）。若响应体实际是 JSON 错误，解析 `message` / `code` 做 toast，不要只显示泛化失败。

## Testing Decisions

好的测试只锁可观察契约：ZIP 成员与 frontmatter、再导入预检结果、HTTP 状态与错误码、native 导出未被改动。不锁内部函数拆分或中间 dict 形状。

优先最高缝：

- **HTTP**：仿现有 Markdown 导出端点测试——有权限时得到 zip 附件；无 generation 时 409；超页数/超字节时 400 且 `code` 正确。
- **Round-trip**：复用 OKF 导入夹具（或同等最小包）导入 → 导出 → 再走 OKF 预检：concept 数与主要 `type` 一致；带图页的正文相对路径能在 ZIP 内解析到 `assets/` 字节。
- **自产页**：仅有 page_type/title/body 的页，导出含 `type` 与合成 `generated`，无 `verified`；路径含目录显示名与 `page_id`，不含 `dir_<uuid>`。
- **裂图**：正文引用不存在的 locator 时导出仍 200，该引用不被改成假的 `assets/` 路径。
- **净化**：导出 tags 不含 `okf:` 衍生标签；根 index 含 `okf_version: "0.2"`；无 `manifest.json`；ZIP 内中文路径可按 UTF-8 读出。
- **回归**：`export_markdown` 仍为 native zip、文件名与入口不变。
- **前端**：导出 OKF 入口与 Markdown 并列；错误 blob 解析出 `message` 的行为用纯函数/组件测试锁住，不引入浏览器 E2E。

验证命令沿用 `DEVELOP.md`：server sqlite pytest（wiki 导出/导入相关用例）；web 相关 vitest / lint。

## Out of Scope

- `title_slug` 路径模式；`include_assets` / `missing_asset` / `path_mode` 等 query。
- 子目录 `index.md`；按目录/增量导出；导出预检 API。
- 改正文后刷新 `generated`；generation 写库时强制写 `okf` meta。
- 用导出修复导入时就未入库的 HTML `<img>` / 外链图。
- 替换或改变 native「导出 Markdown」。
- 导出后自动推 GitHub / 打开远程。
- Attested Computation 执行；`verified` 人工标记 UI。
- 将 `export_okf` 登记为新的对外 OpenAPI 网关端点（除非产品另立变更要求智能体调用）。

## Further Notes

- 对齐来源：grill-me（2026-09-11）。逐项结论：P0 以再导入完整包为准；真实存在且能显示的图必须导出且解开 md 可见；导入时已裂的图导出可继续裂、不整包失败；无残缺包开关；ZIP 200MB / 2000 页；合成路径用目录显示名禁止内部 key；P0 只写根 index/log；`generated` 有则原样不刷新；前端与后端同一变更；blob 错误展示接口原文；ZIP UTF-8 标志。
- 相关已实现：OKF 导入（`opspilot-wiki-okf-import`）。导入把路径链改成 wikilink、把相对图改成 locator，并在 meta 中保留 `concept_id` / 原始 `type` / `title` / 余项，本变更做反向。
- 规范：[OKF v0.2 SPEC](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)。根 `index.md` / `log.md` 不是 concept；符合性要求每篇非保留 md 有 `type`。
- 设计草稿曾放在 worktree `docs/okf-export.md`；以本 spec 为实现契约。

## Completion Evidence

- 后端：`GET .../knowledge_base/{id}/export_okf/`（`wiki_list-View`）+ `build_okf_export_zip`。ZIP 唯一顶层 `{kb}-okf/`，根 `index.md`（`okf_version: "0.2"`）与 `log.md`，页面按 `concept_id` / 目录显示名落盘，`wiki/media` 可读图写入 `assets/` 并改相对路径。不改 `export_markdown`。
- 前端：`PageTab`「导出 Markdown」旁「导出 OKF」；blob GET；JSON 错误 blob 解析 `message`/`code` 做 toast。
- 验证（2026-09-14，`D:\app\venv\bkliteserver`，postgres `--reuse-db`；首次需 `--create-db` 重建损坏的 test DB）：
  - `python -m pytest apps/opspilot/tests/wiki/test_okf_export.py --no-cov` → **11 passed**（HTTP 200/409/400、自产页显示名路径、裂图仍成功、round-trip 预检 concept/`type`/图片、UTF-8 标志、native 导出入口回归）
  - `python -m pytest apps/opspilot/tests/wiki/test_okf_import.py --no-cov` → **21 passed**
  - `pnpm exec vitest run src/app/opspilot/utils/__tests__/wikiExportBlobError.test.ts` → **3 passed**
  - `pnpm exec tsx scripts/wiki-markdown-export-test.ts` → passed
  - `pnpm type-check` → 0
- `test_markdown_export.py` 两条旧用例仍因 `create_manual_page` 需要 active generation、且 native ZIP 含 `directories/*.keep` 与断言不一致而失败；本变更未改 `export_markdown` 契约，回归由 `test_export_markdown_endpoint_unchanged` 锁住。未做浏览器 E2E。
