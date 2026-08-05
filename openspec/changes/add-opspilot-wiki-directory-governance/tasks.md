> 范围说明：本清单只交付目录、Structure Revision、Generation 和目录消费面。Index/Overview/查询路由转入 `add-opspilot-wiki-generation-navigation`；最小 token/调用预算和长文件处理转入 `add-opspilot-wiki-minimal-context-budget`。当前数据为本地测试数据，不再实施 backfill、legacy 双读或灰度迁移。
## 1. 隔离环境、基线与对照证据

- [x] 1.1 在 `.claude/worktrees/opspilot-wiki-hierarchy` 复核分支 `codex/opspilot-wiki-hierarchy`、被忽略的 `server/local_settings.py` 与 `server/.env`，确认默认数据库为 `opspilot`，且环境文件和密钥不会进入 Git。
- [x] 1.2 重新运行现有 Wiki 模型与重建基线测试，诊断并记录“12 个断言通过但 pytest 进程不退出”的根因与可正常终止的隔离命令；若修复属于无关基础设施，另立 change，不扩大本功能 diff。
- [x] 1.3 在 `docs/superpowers/verifications/2026-07-13-opspilot-wiki-directory-governance-verification.md` 建立 1–15 阶段对照矩阵，固定 `llm_wiki@9b71ade` 对应源码/测试或“无对应实现”，逐阶段记录借鉴点、拒绝项、OpsPilot 差异和验证证据。
- [x] 1.4 为 Wiki 测试补齐统一 factory/fixture，禁止测试继续绕过页面标题、目录和 generation 领域入口直接制造无效对象。
- [ ] 1.5 重写 Structure/Generation/Page 真相源契约测试，删除 legacy/backfilling/ready 分支并证明所有读写只使用 active Generation。
- [x] 1.6 冻结结构完整快照、generation 激活/回退、目录预览 token、导入 preflight token 的请求/响应 JSON schema，覆盖 existing node 只读 ID/key 与 new node client_ref。
- [x] 1.7 冻结 manual/classification root/type 默认/merged redirect/待归类路由矩阵，以及 `KnowledgeCandidateAdapter` 两个冲突方法；相邻 change 不可用时由本 change 提供最小实现。
- [x] 1.8 冻结 base generation CAS、staging PageVersion 所有权/引用清理、结构兼容回退和空库初始化规则。

## 2. 最终模型与空库 migration

- [ ] 2.1 以测试冻结 WikiStructureRevision、WikiDirectory、PageDirectoryChange、WikiGeneration、WikiGenerationPage、页面目录/模式和关系 generation 约束。
- [x] 2.2 确认模型只包含已批准字段，不增加页面级 confidence、suggestion 或向量字段。
- [x] 2.3 与 Generation Navigation、Minimal Context Budget 完成模型对账，确保只有一个 active Generation 指针。
- [x] 2.4 保留 0066 及以前 migration，删除其后未发布 migration，并从最终模型重新生成连续 migration。
- [x] 2.5 从空数据库执行 migrate、makemigrations --check 和 Django system check。

## 3. 空知识库初始化与约束

- [x] 3.1 在知识库创建事务中初始化系统待归类、首个 Structure Revision 和空 baseline Generation。
- [ ] 3.2 验证初始化任一步失败时知识库、目录、revision 和 generation 全部回滚。
- [x] 3.3 直接施加目录/模式非空、标题全库唯一、同库父子和 Generation 关系约束。
- [ ] 3.4 运行空库初始化、幂等读取和非法标题/目录模型测试。
- [x] 3.5 删除不再需要的 audit/backfill/readiness/legacy 写入围栏代码与测试，并确认无生产入口引用。

## 4. 结构 revision 与目录治理后端

- [ ] 4.1 先新增 `test_structure_service.py`，覆盖 key/同级名称唯一、循环、跨库父节点、最大深度 8、唯一 page-type 默认、待归类不变量、structure version + base generation CAS、operation token 和事务全失败。
- [x] 4.2 新建 `structure_service.py`，实现 existing ID/key 校验、new client_ref 映射、完整快照规范化、fingerprint/diff；基于 active generation 构造轻量治理 generation，并原子激活相互绑定的 revision/generation。
- [x] 4.3 新建 `directory_service.py`，实现树读取、breadcrumb/子树解析、空目录归档、Schema 目录退役、非空直接删除拒绝、待归类保护和稳定 redirect/tombstone。
- [x] 4.4 为合并/退役实现 dry-run 与单次 operation token，绑定 KB/structure/base generation/参数/影响 hash；执行时重算，状态变化或子目录冲突整体中止，且不调用 LLM 合并正文。
- [x] 4.5 新增结构/目录 serializer、`wiki_directory_view.py` 和 URL，结构保存接收 structure version + base generation，并在 CAS 冲突时返回 409 最新 revision/generation/diff。
- [x] 4.6 对照 `llm_wiki/src/components/layout/file-tree.tsx` 与 `knowledge-tree.tsx` 验证 OpsPilot 新增了其缺失的 CRUD、空目录、稳定身份、影响预览、事务和并发保护，并更新阶段证据。

## 5. 页面全局身份与目录归类

- [ ] 5.1 先新增 `test_directory_assignment.py`，覆盖 NFKC/空白/casefold 标题等价、KB 行锁并发、归档恢复 ID、manual lock、classification root、唯一类型默认、merged redirect 与待归类 fallback。
- [x] 5.2 统一标题服务使用 NFKC、trim、Unicode 空白折叠与 casefold，并让创建、改名、导入、构建和重建在 KB 行锁内复用。
- [x] 5.3 新建 `directory_routing_service.py`，按 manual → 固定 revision/root 内合法 key → 范围内唯一 type 默认 → root → 待归类路由；LLM merged key fallback，原生/历史可跟 redirect，并记录完整事件。
- [x] 5.4 实现单页/批量移动与恢复 auto：从 active generation 派生轻量 governance generation，写 `PageDirectoryChange` 并 CAS 激活；不得原地改 active 快照。
- [x] 5.5 实现 `KnowledgeCandidateAdapter.create_body_conflict/create_identity_conflict`；相邻 change 可用时适配，否则提供最小实现，目录低置信度/未知 key/Schema mismatch 只写 BuildRecord。
- [x] 5.6 把页面删除改为轻量 governance generation 逻辑归档，同步移除新快照中的关系/反向链接/计数/关键词可见性；任何 retained/staging/candidate 引用存在时禁止物理删除。
- [x] 5.7 对照 `llm_wiki/src/lib/wiki-page-delete.ts` 的物理级联删除和路径身份，验证 OpsPilot 的全局标题身份、可回退逻辑删除与结构/正文边界，并更新阶段证据。

## 6. Generation 一致发布与回退

- [ ] 6.1 先新增 `test_generation_service.py`，覆盖状态机、完整成员/目录显示快照、base CAS、候选竞争、人工/结构变更抢先、WikiLink 隔离、staging 引用清理、结构兼容 rollback_of 与失败不污染。
- [x] 6.2 新建 `generation_service.py`，实现完整候选克隆、固定 base/structure/fingerprint/pipeline/source 身份、共享 staging page identity + 独立 PageVersion/成员所有权和引用安全清理。
- [x] 6.3 实现 KB 行锁内 base generation + structure revision CAS、完整校验和短事务切换 active 指针/兼容镜像；CAS 失败 superseded/rebase，数据失败保持旧 active 不变。
- [x] 6.4 新建统一 active-generation query service，用契约/守卫测试强制页面、关键词、Agent、WikiLink/反向链接、关系、图谱、概览和导出读取同一 generation，禁止遗留 current/status 直读。
- [x] 6.5 为创建/改名/编辑/移动/恢复/归档/结构保存实现不可变轻量 governance generation；正文变化先准备 WikiLink、关键词和关系，目录-only 变化可复用版本。
- [x] 6.6 实现保留、引用计数清理、回退预览和新 `rollback_of` generation；结构不兼容时只允许通过 structure version + base generation 双 CAS 联动创建递增 revision，任一冲突回滚全部联动写入并返回 409，否则阻止；不得复活旧 generation/revision 行。
- [ ] 6.7 增加确定性并发测试：结构/移动/编辑/归档与构建竞争、两个同 base 构建、staging 同标题共享、旧任务缺少 base/revision 时拒绝激活。
- [x] 6.8 对照 `llm_wiki` 的逐文件正式写入和 `src-tauri/src/commands/file_history.rs` 文件历史，验证 OpsPilot 提供集合级原子发布、完整前态和真正可执行的回退，并更新阶段证据。

## 7. 构建、更新、重建与关系链路

- [ ] 7.1 先扩展 build/update/rebuild/async/关系测试，覆盖固定 base + revision、classification root fallback、无审批激活、human/mixed 候选、WikiLink/关系隔离、CAS superseded 和失败保持旧 generation。
- [x] 7.2 修改 `build_service.py` 的提示/解析，只暴露固定 revision 与 classification root 内的稳定 key/路径/规则，并按 manual → 合法 key → 范围内唯一类型默认 → root → 待归类重校验。
- [x] 7.3 扩展 BuildRecord，保存 generation/base/rollback_of、revision/fingerprint/pipeline、页面动作、目录 reason/confidence/fallback、CAS/superseded/failed 原因和关联 ID。
- [x] 7.4 修改 `update_service.py`：确定性 AI 新增/更新直接进入 staging；human/mixed 正文冲突保持当前版本并创建非阻塞候选，不创建构建审批或目录审批。
- [x] 7.5 重构 `rebuild_service.py` 为按全状态标题原地和解，保留 manual 目录与 human/mixed 正文，禁止在候选 generation 激活前先归档旧 AI 页面。
- [x] 7.6 修改 `relation_service.py` 与 WikiLink/反向链接物化流程，让派生结果在 staging generation 内构建并校验，禁止先删或提前改 active 结果。
- [x] 7.7 修改 Celery `tasks.py`，开始时固定 base generation/revision/hash/pipeline，逐阶段传播并在激活前 CAS 复验；缺少 base/revision 身份的旧任务拒绝激活。
- [x] 7.8 对照 `llm_wiki/src/lib/wiki-page-types.ts` 的 FILE/type 路由和 `page-merge.ts` 的内容合并保护，记录借鉴的写前校验与未采用的路径身份、mismatch 丢页和 LLM 目录合并。
- [x] 7.9 将通用结构模板调整为 entity/concept/source/query/comparison/synthesis，移除与系统派生 Overview 重复的普通 overview 类型。
- [x] 7.10 将资料名称、类型和稳定来源标题注入单资料/重建生成契约，按类型约束正文骨架，并在同一次最终请求中生成多个稳定主题页。
- [x] 7.11 通过 PageEvidence 复用每份资料唯一 source 页面；模型漏产 source 时确定性补来源导航，零有效页/空正文/无效 JSON 使该文件构建失败。
- [x] 7.12 将 source 页冲突召回限制为同类型精确标题或别名匹配，并让资料更新继续遵守原 page type 正文契约。

## 8. 所有非向量消费面统一切换

- [ ] 8.1 建立消费契约测试，使用正文/目录/状态/WikiLink 不同的 generation 证明每个入口只读同一 active generation，构建和轻量治理切换前后都无混读窗口。
- [x] 8.2 将 `wiki_page_view.py` 的列表/详情/搜索和关键词检索改用统一查询服务，支持 `directory_id` 与 `include_descendants` 并在评分/top-k 前应用子树范围。
- [x] 8.3 将 retrieval/context/Agent 工具迁移到 active generation，分别返回知识目录 breadcrumb 与 Markdown heading path，禁止把两者混为一个路径。
- [x] 8.4 将 WikiLink/反向链接、PageRelation 查询/重建和 Graph API 迁移到 generation 范围，节点返回目录 ID/key/breadcrumb，但目录父子不得写成 PageRelation。
- [x] 8.5 将 KB 概览、计数、导出和后台消费者迁移到统一服务，并增加源码/运行守卫阻止 enabled KB 直接按 `KnowledgePage.status/current_version/directory` 读取活动知识。
- [ ] 8.6 增加查询计划/N+1 测试和大树子树过滤基准，确保目录计数和范围解析不会逐节点查询。
- [x] 8.7 增加回归断言：本 change 不清理、不重建、不切换 PageVersion/PageChunk embedding，也不修改语义/混合检索行为或向量 UI。
- [x] 8.8 对照 `llm_wiki/knowledge-tree.tsx` 的 type 分组与文件树展示，验证 OpsPilot 目录过滤是独立真实层级且不会把同目录误作语义权重。

## 9. 来源路径、原生导入导出与安全

- [ ] 9.1 先扩展 import/export/Material 测试，覆盖相对路径、classification root、空目录、空 KB 稳定 key 恢复、保留 key 伪造、unknown/merged fallback、标题冲突、token TOCTOU/replay 和 ZIP 配额。
- [x] 9.2 修改资料上传 API 与 `MaterialTab` 请求契约，保留 `source_relative_path/source_identity/source_folder_path/content_hash`，可选 classification root 只限制候选子树，不自动创建知识目录。
- [x] 9.3 实现原生导出 `manifest.json + structure.json + pages/<display-path>/*.md`，manifest 保存结构 revision/hash、稳定 key、空目录、页面映射和格式版本。
- [x] 9.4 实现共享 preflight/execute：签发短期单次 token，绑定 archive hash/KB/actor/target/structure version/base generation/options/quota；execute 重新鉴权复验并拒绝 replay、zip-slip、绝对路径、symlink、保留 key 伪造和资源超限。
- [x] 9.5 实现原生导入 key → mapping → 显式目标 → 范围内类型默认 → classification root → 待归类；空 KB 经确认后把归档当不可信输入校验并保留合法 manifest key，准备首个业务 revision 与 staging generation，并通过 base generation 和 active structure revision CAS 原子激活二者。
- [x] 9.6 实现第三方 ZIP 显式目标 → 现有路径映射 → 范围内 type 默认 → classification root → 待归类；只有管理员显式开启并确认结构预览时，才从文件夹创建 manual 目录，并通过结构治理服务的 base generation 与 active structure revision 双 CAS 原子发布新 revision 和 governance generation；发布成功后再启动页面导入。
- [x] 9.7 在同一 staging generation 中准备版本、目录历史、WikiLink/反向链接、关系、图谱、计数和关键词元数据后再激活，保持向量数据不变。
- [ ] 9.8 增加原生导出→新建/空 KB 确认恢复结构→再次导出的规范化往返测试，并校验空目录、顺序、稳定 key 保留与页面 ID 映射报告。
- [x] 9.9 对照 `llm_wiki/src/lib/project-file-sync.ts` 和 `source-lifecycle.ts` 的完整来源路径/hash 移动识别，记录借鉴的 provenance 与未采用的“来源文件夹等于知识目录”。

## 10. 后端 API、权限与可观测性

- [ ] 10.1 扩展 `test_wiki_directory_views.py`，覆盖结构/base CAS、operation token、合并/退役、轻量页面治理、空库 bootstrap/enable、rollback_of + 结构联动、目录筛选与越权。
- [x] 10.2 保留 bootstrap/enable 与 rollback generation 接口，删除仅服务存量迁移的 readiness/fence 状态机和端点。
- [x] 10.3 扩展 `wiki_page_view.py` 提供目录/breadcrumb/assignment mode、单页和批量移动、恢复 auto、逻辑归档与 409/422 可操作错误。
- [x] 10.4 扩展 `wiki_material_view.py` 与 import/export 端点，传递来源路径/classification root 和绑定 archive/KB/actor/target/structure version/base generation/options/quota 的单次 preflight token，以及 generation/build ID。
- [x] 10.5 所有端点复用 KB 管理员权限且不增加目录 ACL；serializer 要求 existing node 回传只读 ID/key 并校验未替换，new node 只收 client_ref，拒绝用户为新节点选择或覆盖 ID/key。
- [x] 10.6 为 null directory、待归类比例、unknown key、generation failed/superseded、409、回退和消费面 generation mismatch 增加日志、指标或可查询审计。
- [x] 10.7 对照 `llm_wiki` 的前端直连文件命令与无 KB 权限/REST 并发契约，记录 OpsPilot 后端授权、CAS、token、审计和统一错误响应的阶段 10 差异。

## 11. 前端请求契约与基础设施

- [x] 11.1 先为 `web/src/utils/request.ts` 增加错误保真测试，证明 409 的 HTTP status、服务端 code/details/latest revision 不会被通用异常包装丢失。
- [x] 11.2 修改 `request.ts` 的错误类型和处理链，并让旧调用方保持兼容，为结构乐观锁和导入 preflight 提供可判定错误。
- [x] 11.3 扩展 `types/wiki.ts` 与 `api/wiki.ts`，定义 structure/base generation CAS、existing node/new client_ref、generation/rollback、operation/preflight token、移动、导入导出和筛选契约。
- [x] 11.4 新建 `useWikiDirectoryQuery.ts`，用 URL 持久化 directory、include descendants、分页、搜索和 page type，并为页面列表/图谱共享范围。
- [x] 11.5 补齐 `locales/zh.json` 与 `en.json` 的目录、待归类、全部知识、结构冲突、manual/auto、影响预览、generation 和导入安全文案。
- [x] 11.6 用现有 `PermissionWrapper` 控制结构/移动/合并入口可见性，同时增加 403 回归场景以证明前端隐藏不替代后端鉴权。
- [x] 11.7 对照 `llm_wiki` 的本地 Tauri 命令调用和无服务端 409 状态，记录 OpsPilot 请求错误保真、CAS、token 与前后端权限分层的阶段 11 证据。

## 12. 真实目录树与页面治理 UI

- [ ] 12.1 先为目录树/选择器/移动/URL 写组件测试与 Storybook，覆盖空目录、深度 8、长名称、merged 重定向、retired tombstone、刷新/前进/后退/深链和无权限。
- [x] 12.2 将约 740 行的 `PageTab.tsx` 拆成查询、树、表格、编辑/来源抽屉与治理 modal，保持现有页面编辑功能回归可测。
- [x] 12.3 新建 `WikiDirectoryTree.tsx`：展示虚拟“全部知识”、真实系统“待归类”和 active 目录树，保留空目录且日常模式只负责导航。
- [x] 12.4 页面区域展示 breadcrumb、目录说明、直属/含子目录切换、目录/page type/auto-manual/来源/冲突/更新时间列；默认直属范围并明确批量操作范围。
- [x] 12.5 新建 `WikiDirectorySelect.tsx` 与 `WikiPageMoveModal.tsx`，实现单页/批量 manual 移动、影响数量确认和恢复自动归类即时结果。
- [x] 12.6 修改 `KnowledgeTab.tsx`，让页面/图谱共享 URL 范围；刷新、前进后退、分享深链可恢复，merged 自动替换目标 URL，retired 无 redirect 时提示并回到全部知识。
- [x] 12.7 目录界面未启用时显示平面页面列表；启用前复验 active Structure/Generation/待归类，启用后不得用 page_type 分组伪装目录。
- [x] 12.8 对照 `llm_wiki/knowledge-tree.tsx` 的只读 type 分组和隐藏空目录行为，记录 OpsPilot 在真实层级、空目录、治理和 URL 状态上的差异。
- [x] 12.9 页面改名继续复用稳定 page ID，并通过轻量 governance generation 发布；UI 在确认前提示 v1 不保留旧标题 alias 及可能受影响的旧标题引用。

## 13. 结构编辑、资料、导入导出与图谱 UI

- [ ] 13.1 先为结构编辑器、409 冲突、影响预览、资料 classification root、导入预检和图谱目录过滤补齐 Storybook/组件测试。
- [x] 13.2 新建 `WikiStructureEditor.tsx` 管理完整快照：existing node 隐藏回传只读 ID/key，new node 只发 client_ref，保存携带 structure version + base generation；用户不填写原始 ID/key。
- [x] 13.3 修改 `SettingsTab.tsx`：只保留「用途与结构」中的结构化 Schema 编辑器，移除独立「目录结构」页签和可独立编辑的自由 Schema；目录表仅作为 Schema 的运行时投影。
- [x] 13.4 structure/base generation 任一 CAS 返回 409 时保留本地树，加载最新 revision/generation，展示 diff 并允许重新应用或放弃，不静默覆盖。
- [x] 13.5 新建 `WikiDirectoryImpactDrawer.tsx`，展示合并/退役影响并持有绑定 version/base/参数/hash 的 operation token；过期或状态变化必须重新预览，不能按旧 token 执行。
- [x] 13.6 修改 `MaterialTab.tsx` 支持完整相对路径与 classification root；新增 `WikiMarkdownImportModal.tsx` 展示 preflight、路径映射和显式“从文件夹创建人工目录”。
- [x] 13.7 修改 `GraphTab.tsx/GraphExplorer.tsx` 共享目录/子树筛选，节点展示 breadcrumb，且不绘制目录父子关系为语义边。
- [ ] 13.8 更新 Wiki Storybook mock、settings/graph stories，并新增目录/page/import 场景；对照 `llm_wiki/wiki-page-delete.ts` 与 `dedup-runner.ts` 记录 OpsPilot 的影响预览、无 LLM 目录合并、持久 redirect 和事务差异。

## 14. 空库重建与运行保护

- [x] 14.1 删除 0066 之后未发布 migration，清空本地数据库并从最终模型生成连续 migration。
- [x] 14.2 从空库执行 migrate 和 OpsPilot 初始化，验证新知识库自动具备待归类、revision 和 baseline Generation。
- [x] 14.3 验证所有生产写入口只走 Generation-aware 服务，不存在 legacy/backfilling/ready 双写分支。
- [x] 14.4 监控 generation failed/superseded、消费面 mismatch、结构 409 和回退频率。
- [x] 14.5 编写 runbook：结构回滚生成递增 revision，Generation 回退创建 rollback_of，CAS 失败不产生部分写入。

## 15. 自动化验证与真实浏览器验收

- [ ] 15.1 运行新增/受影响 Django 测试、migration checks、静态检查和全量 OpsPilot Wiki 回归，要求进程正常退出且无后台线程泄漏。
- [ ] 15.2 运行 Web 类型检查、lint、组件测试与 Storybook build，修复目录功能引入的 console warning、未翻译文案和无障碍问题。
- [ ] 15.3 在空库、规范标题冲突库和大树样例演练全量 migrate、初始化、结构回滚以及兼容与不兼容 rollback_of。
- [ ] 15.4 用固定种子数据真实点击结构保存、空目录、页面创建、NFKC/空白/大小写等价标题拒绝、单/批量移动、manual 重建保持与恢复 auto；写动作不得用 API 代替。
- [ ] 15.5 用两个窗口验证 409 后本地树仍在且可查看最新 revision/generation diff；用确定性故障钩子触发结构/人工变更 CAS superseded 和构建 failed，核对旧消费面不变。
- [ ] 15.6 真实完成资料上传/classification root、合并/退役 token 过期重预览、原生导出→空 KB 恢复结构、第三方 ZIP 显式建目录，以及 preflight token 结构变化/replay 拒绝。
- [ ] 15.7 在列表/关键词/图谱切换同一范围，核对集合/breadcrumb/generation；再验证刷新、前进、后退、分享深链、merged URL 重定向、retired tombstone 和无目录语义边。
- [ ] 15.8 为每条路径保存按固定命名的截图、脱敏网络状态/console/后端读回和 KB/revision/build/generation ID；不得记录凭据、请求头密钥或敏感正文。
- [ ] 15.9 运行 `openspec validate add-opspilot-wiki-directory-governance --strict --no-interactive`，检查所有场景、任务 checkbox、无占位标记和 proposal/design/spec/tasks 一致性。
- [ ] 15.10 检查 Git diff 仅包含预期业务/测试/文档改动，确认 `.env`、`local_settings.py`、向量重建和无关用户文件未被提交，再请求独立代码审查并解决高优先级问题。
- [ ] 15.11 完成 1–15 阶段 `llm_wiki@9b71ade` 对照矩阵完整性检查；每阶段必须有源码/测试或“无对应实现”、借鉴、拒绝、OpsPilot 差异和验证证据，缺项阻止发布。
