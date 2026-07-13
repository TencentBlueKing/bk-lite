## 1. 隔离环境、基线与对照证据

- [ ] 1.1 在 `.claude/worktrees/opspilot-wiki-hierarchy` 复核分支 `codex/opspilot-wiki-hierarchy`、被忽略的 `server/local_settings.py` 与 `server/.env`，确认默认数据库为 `munchkin`，且环境文件和密钥不会进入 Git。
- [ ] 1.2 重新运行现有 Wiki 模型与重建基线测试，诊断并记录“12 个断言通过但 pytest 进程不退出”的根因与可正常终止的隔离命令；若修复属于无关基础设施，另立 change，不扩大本功能 diff。
- [ ] 1.3 在 `docs/superpowers/verifications/2026-07-13-opspilot-wiki-directory-governance-verification.md` 建立 1–15 阶段对照矩阵，固定 `llm_wiki@9b71ade` 对应源码/测试或“无对应实现”，逐阶段记录借鉴点、拒绝项、OpsPilot 差异和验证证据。
- [ ] 1.4 为 Wiki 测试补齐统一 factory/fixture，禁止测试继续绕过页面标题、目录和 generation 领域入口直接制造无效对象。
- [ ] 1.5 把 design 决策 0 落成可执行的 Structure/Generation/Page 真相源与状态机契约测试，明确 legacy/backfilling/ready/enabled 各阶段允许的读写路径。
- [ ] 1.6 冻结结构完整快照、generation 激活/回退、目录预览 token、导入 preflight token 的请求/响应 JSON schema，覆盖 existing node 只读 ID/key 与 new node client_ref。
- [ ] 1.7 冻结 manual/classification root/type 默认/merged redirect/待归类路由矩阵，以及 `KnowledgeCandidateAdapter` 两个冲突方法；相邻 change 不可用时由本 change 提供最小实现。
- [ ] 1.8 冻结 base generation CAS、staging PageVersion 所有权/引用清理、结构兼容回退和 backfill 写入围栏规则，再允许进入模型实现。

## 2. Expand 模型与兼容迁移

- [ ] 2.1 先新增 `server/apps/opspilot/tests/wiki/test_directory_models.py`，覆盖目录同库父子关系、稳定 key、系统待归类不变量、页面目录模式、generation base/rollback/成员显示快照、历史 FK PROTECT 和关系 generation 约束。
- [ ] 2.2 在 `server/apps/opspilot/models/wiki_mgmt.py` 增加 `WikiStructureRevision`、`WikiDirectory`、`PageDirectoryChange`、`WikiGeneration`、`WikiGenerationPage`，以及知识库 active 指针、`directory_enabled`、`directory_migration_state`；generation 包含 base/rollback_of/kind。
- [ ] 2.3 只给 `KnowledgePage` 增加 nullable `directory` 与 `directory_assignment_mode`，给 `PageRelation` 增加 nullable `generation`，给 Material 增加来源相对路径/身份字段；历史 generation/page/version/directory/relation FK 使用 PROTECT，关系唯一键按 generation expand，且不得增加页面级 confidence、suggestion 或向量字段。
- [ ] 2.4 创建 `0065_wiki_directory_generation_expand.py`，加入可跨当前支持数据库工作的索引和普通约束；迁移只建表/字段，不扫描大表、不调用 LLM、不清理 embedding。
- [ ] 2.5 运行模型与 migration state 测试，确认旧代码在 nullable 字段和功能关闭时仍可启动，并把“llm_wiki 仅有文件路径/type、没有目录实体与 revision”的对照结论写入验证报告。

## 3. Readiness、基线回填与 Contract

- [ ] 3.1 先新增 `test_directory_migrations.py`，覆盖重复标题、异常状态、旧 running build、幂等重跑、中断续跑、baseline revision/generation 与现有关系回填。
- [ ] 3.2 实现 `audit_wiki_directory_readiness.py`，对所有状态页面做知识库级标题规范化冲突审计，并输出可机读报告且不改数据。
- [ ] 3.3 实现 `backfill_wiki_directory_governance.py`，按批次幂等创建待归类、baseline structure revision、baseline generation，把页面与现有 PageRelation 纳入快照，保留页面 ID、版本、证据、Chunk 和现有向量。
- [ ] 3.4 实现知识库 `legacy → backfilling → ready → enabled` 状态机：进入 backfilling 前排空旧任务并开启可重试写入围栏；ready 后旧 UI 可读兼容镜像，但所有写入必须走 generation-aware 服务；启用时在 KB 锁内复验 readiness。
- [ ] 3.5 用 management command 集成测试在空库、存量库和中断点验证 audit/backfill；大表扫描与 baseline 数据回填 MUST 留在可恢复命令中，不得放进 Django data migration。
- [ ] 3.6 待所有生产写入口收敛且 readiness 全绿后创建后续 contract migration（当前分支预计 `0066_wiki_directory_generation_contract.py`），再施加目录/模式非空和 `(knowledge_base, title)` 全状态普通唯一约束。
- [ ] 3.7 对照 `llm_wiki` 无关系型 migration/readiness/backfill 的事实，记录 OpsPilot 为何采用 KB 写入围栏、幂等命令和 contract gate，并补齐阶段 3 证据。

## 4. 结构 revision 与目录治理后端

- [ ] 4.1 先新增 `test_structure_service.py`，覆盖 key/同级名称唯一、循环、跨库父节点、最大深度 8、唯一 page-type 默认、待归类不变量、structure version + base generation CAS、operation token 和事务全失败。
- [ ] 4.2 新建 `structure_service.py`，实现 existing ID/key 校验、new client_ref 映射、完整快照规范化、fingerprint/diff；基于 active generation 构造轻量治理 generation，并原子激活相互绑定的 revision/generation。
- [ ] 4.3 新建 `directory_service.py`，实现树读取、breadcrumb/子树解析、空目录归档、Schema 目录退役、非空直接删除拒绝、待归类保护和稳定 redirect/tombstone。
- [ ] 4.4 为合并/退役实现 dry-run 与单次 operation token，绑定 KB/structure/base generation/参数/影响 hash；执行时重算，状态变化或子目录冲突整体中止，且不调用 LLM 合并正文。
- [ ] 4.5 新增结构/目录 serializer、`wiki_directory_view.py` 和 URL，结构保存接收 structure version + base generation，并在 CAS 冲突时返回 409 最新 revision/generation/diff。
- [ ] 4.6 对照 `llm_wiki/src/components/layout/file-tree.tsx` 与 `knowledge-tree.tsx` 验证 OpsPilot 新增了其缺失的 CRUD、空目录、稳定身份、影响预览、事务和并发保护，并更新阶段证据。

## 5. 页面全局身份与目录归类

- [ ] 5.1 先新增 `test_directory_assignment.py`，覆盖 NFKC/空白/casefold 标题等价、KB 行锁并发、归档恢复 ID、manual lock、classification root、唯一类型默认、merged redirect 与待归类 fallback。
- [ ] 5.2 新建统一 `title_service.py`，固定 NFKC + trim + Unicode 空白折叠 + casefold 比较，在 KB 行锁内让 readiness/创建/改名/导入/构建/重建使用同一入口；持久标题保留展示大小写。
- [ ] 5.3 新建 `directory_routing_service.py`，按 manual → 固定 revision/root 内合法 key → 范围内唯一 type 默认 → root → 待归类路由；LLM merged key fallback，原生/历史可跟 redirect，并记录完整事件。
- [ ] 5.4 实现单页/批量移动与恢复 auto：从 active generation 派生轻量 governance generation，写 `PageDirectoryChange` 并 CAS 激活；不得原地改 active 快照。
- [ ] 5.5 实现 `KnowledgeCandidateAdapter.create_body_conflict/create_identity_conflict`；相邻 change 可用时适配，否则提供最小实现，目录低置信度/未知 key/Schema mismatch 只写 BuildRecord。
- [ ] 5.6 把页面删除改为轻量 governance generation 逻辑归档，同步移除新快照中的关系/反向链接/计数/关键词可见性；任何 retained/staging/candidate 引用存在时禁止物理删除。
- [ ] 5.7 对照 `llm_wiki/src/lib/wiki-page-delete.ts` 的物理级联删除和路径身份，验证 OpsPilot 的全局标题身份、可回退逻辑删除与结构/正文边界，并更新阶段证据。

## 6. Generation 一致发布与回退

- [ ] 6.1 先新增 `test_generation_service.py`，覆盖状态机、完整成员/目录显示快照、base CAS、候选竞争、人工/结构变更抢先、WikiLink 隔离、staging 引用清理、结构兼容 rollback_of 与失败不污染。
- [ ] 6.2 新建 `generation_service.py`，实现完整候选克隆、固定 base/structure/fingerprint/pipeline/source 身份、共享 staging page identity + 独立 PageVersion/成员所有权和引用安全清理。
- [ ] 6.3 实现 KB 行锁内 base generation + structure revision CAS、完整校验和短事务切换 active 指针/兼容镜像；CAS 失败 superseded/rebase，数据失败保持旧 active 不变。
- [ ] 6.4 新建统一 active-generation query service，用契约/守卫测试强制页面、关键词、Agent、WikiLink/反向链接、关系、图谱、概览和导出读取同一 generation，禁止遗留 current/status 直读。
- [ ] 6.5 为创建/改名/编辑/移动/恢复/归档/结构保存实现不可变轻量 governance generation；正文变化先准备 WikiLink、关键词和关系，目录-only 变化可复用版本。
- [ ] 6.6 实现保留、引用计数清理、回退预览和新 `rollback_of` generation；结构不兼容时联动创建递增 revision 或阻止，不得复活旧 generation/revision 行。
- [ ] 6.7 增加确定性并发测试：结构/移动/编辑/归档与构建竞争、两个同 base 构建、staging 同标题共享、旧任务缺少 base/revision 时拒绝激活。
- [ ] 6.8 对照 `llm_wiki` 的逐文件正式写入和 `src-tauri/src/commands/file_history.rs` 文件历史，验证 OpsPilot 提供集合级原子发布、完整前态和真正可执行的回退，并更新阶段证据。

## 7. 构建、更新、重建与关系链路

- [ ] 7.1 先扩展 build/update/rebuild/async/关系测试，覆盖固定 base + revision、classification root fallback、无审批激活、human/mixed 候选、WikiLink/关系隔离、CAS superseded 和失败保持旧 generation。
- [ ] 7.2 修改 `build_service.py` 的提示/解析，只暴露固定 revision 与 classification root 内的稳定 key/路径/规则，并按 manual → 合法 key → 范围内唯一类型默认 → root → 待归类重校验。
- [ ] 7.3 扩展 BuildRecord，保存 generation/base/rollback_of、revision/fingerprint/pipeline、页面动作、目录 reason/confidence/fallback、CAS/superseded/failed 原因和关联 ID。
- [ ] 7.4 修改 `update_service.py`：确定性 AI 新增/更新直接进入 staging；human/mixed 正文冲突保持当前版本并创建非阻塞候选，不创建构建审批或目录审批。
- [ ] 7.5 重构 `rebuild_service.py` 为按全状态标题原地和解，保留 manual 目录与 human/mixed 正文，禁止在候选 generation 激活前先归档旧 AI 页面。
- [ ] 7.6 修改 `relation_service.py` 与 WikiLink/反向链接物化流程，让派生结果在 staging generation 内构建并校验，禁止先删或提前改 active 结果。
- [ ] 7.7 修改 Celery `tasks.py`，开始时固定 base generation/revision/hash/pipeline，逐阶段传播并在激活前 CAS 复验；旧版 running task 纳入 backfill 排空门禁。
- [ ] 7.8 对照 `llm_wiki/src/lib/wiki-page-types.ts` 的 FILE/type 路由和 `page-merge.ts` 的内容合并保护，记录借鉴的写前校验与未采用的路径身份、mismatch 丢页和 LLM 目录合并。

## 8. 所有非向量消费面统一切换

- [ ] 8.1 建立消费契约测试，使用正文/目录/状态/WikiLink 不同的 generation 证明每个入口只读同一 active generation，构建和轻量治理切换前后都无混读窗口。
- [ ] 8.2 将 `wiki_page_view.py` 的列表/详情/搜索和关键词检索改用统一查询服务，支持 `directory_id` 与 `include_descendants` 并在评分/top-k 前应用子树范围。
- [ ] 8.3 将 retrieval/context/Agent 工具迁移到 active generation，分别返回知识目录 breadcrumb 与 Markdown heading path，禁止把两者混为一个路径。
- [ ] 8.4 将 WikiLink/反向链接、PageRelation 查询/重建和 Graph API 迁移到 generation 范围，节点返回目录 ID/key/breadcrumb，但目录父子不得写成 PageRelation。
- [ ] 8.5 将 KB 概览、计数、导出和后台消费者迁移到统一服务，并增加源码/运行守卫阻止 enabled KB 直接按 `KnowledgePage.status/current_version/directory` 读取活动知识。
- [ ] 8.6 增加查询计划/N+1 测试和大树子树过滤基准，确保目录计数和范围解析不会逐节点查询。
- [ ] 8.7 增加回归断言：本 change 不清理、不重建、不切换 PageVersion/PageChunk embedding，也不修改语义/混合检索行为或向量 UI。
- [ ] 8.8 对照 `llm_wiki/knowledge-tree.tsx` 的 type 分组与文件树展示，验证 OpsPilot 目录过滤是独立真实层级且不会把同目录误作语义权重。

## 9. 来源路径、原生导入导出与安全

- [ ] 9.1 先扩展 import/export/Material 测试，覆盖相对路径、classification root、空目录、空 KB 稳定 key 恢复、保留 key 伪造、unknown/merged fallback、标题冲突、token TOCTOU/replay 和 ZIP 配额。
- [ ] 9.2 修改资料上传 API 与 `MaterialTab` 请求契约，保留 `source_relative_path/source_identity/source_folder_path/content_hash`，可选 classification root 只限制候选子树，不自动创建知识目录。
- [ ] 9.3 实现原生导出 `manifest.json + structure.json + pages/<display-path>/*.md`，manifest 保存结构 revision/hash、稳定 key、空目录、页面映射和格式版本。
- [ ] 9.4 实现共享 preflight/execute：签发短期单次 token，绑定 archive hash/KB/actor/target/revision/options/quota；execute 重新鉴权复验并拒绝 replay、zip-slip、绝对路径、symlink、保留 key 伪造和资源超限。
- [ ] 9.5 实现原生导入 key → mapping → 显式目标 → 范围内类型默认 → root → 待归类；空 KB 经确认后把归档当不可信输入校验并保留合法 manifest key，创建首个业务 revision + staging generation 原子发布。
- [ ] 9.6 实现第三方 ZIP 显式目标 → 现有路径映射 → type 默认 → 待归类；只有管理员显式开启并确认结构预览时，才从文件夹创建 manual 目录并先产生新 revision。
- [ ] 9.7 在同一 staging generation 中准备版本、目录历史、WikiLink/反向链接、关系、图谱、计数和关键词元数据后再激活，保持向量数据不变。
- [ ] 9.8 增加原生导出→新建/空 KB 确认恢复结构→再次导出的规范化往返测试，并校验空目录、顺序、稳定 key 保留与页面 ID 映射报告。
- [ ] 9.9 对照 `llm_wiki/src/lib/project-file-sync.ts` 和 `source-lifecycle.ts` 的完整来源路径/hash 移动识别，记录借鉴的 provenance 与未采用的“来源文件夹等于知识目录”。

## 10. 后端 API、权限与可观测性

- [ ] 10.1 先新增 `test_wiki_directory_views.py`，覆盖结构/base CAS、operation token、合并/退役、轻量页面治理、bootstrap/readiness/fence/enable、rollback_of + 结构联动、目录筛选与越权。
- [ ] 10.2 扩展 `wiki_kb_view.py` 提供 bootstrap/readiness/fence/enable，以及创建新 rollback generation、结构兼容 diff 和显式联动递增 revision 的回退接口。
- [ ] 10.3 扩展 `wiki_page_view.py` 提供目录/breadcrumb/assignment mode、单页和批量移动、恢复 auto、逻辑归档与 409/422 可操作错误。
- [ ] 10.4 扩展 `wiki_material_view.py` 与 import/export 端点，传递来源路径/classification root 和绑定 archive/KB/actor/target/revision/options/quota 的单次 preflight token，以及 generation/build ID。
- [ ] 10.5 所有端点复用 KB 管理员权限且不增加目录 ACL；serializer 要求 existing node 回传只读 ID/key 并校验未替换，new node 只收 client_ref，拒绝用户为新节点选择或覆盖 ID/key。
- [ ] 10.6 为 null directory、待归类比例、unknown key、generation failed/superseded、409、回退和消费面 generation mismatch 增加日志、指标或可查询审计。
- [ ] 10.7 对照 `llm_wiki` 的前端直连文件命令与无 KB 权限/REST 并发契约，记录 OpsPilot 后端授权、CAS、token、审计和统一错误响应的阶段 10 差异。

## 11. 前端请求契约与基础设施

- [ ] 11.1 先为 `web/src/utils/request.ts` 增加错误保真测试，证明 409 的 HTTP status、服务端 code/details/latest revision 不会被通用异常包装丢失。
- [ ] 11.2 修改 `request.ts` 的错误类型和处理链，并让旧调用方保持兼容，为结构乐观锁和导入 preflight 提供可判定错误。
- [ ] 11.3 扩展 `types/wiki.ts` 与 `api/wiki.ts`，定义 structure/base generation CAS、existing node/new client_ref、generation/rollback、operation/preflight token、移动、导入导出和筛选契约。
- [ ] 11.4 新建 `useWikiDirectoryQuery.ts`，用 URL 持久化 directory、include descendants、分页、搜索和 page type，并为页面列表/图谱共享范围。
- [ ] 11.5 补齐 `locales/zh.json` 与 `en.json` 的目录、待归类、全部知识、结构冲突、manual/auto、影响预览、generation 和导入安全文案。
- [ ] 11.6 用现有 `PermissionWrapper` 控制结构/移动/合并入口可见性，同时增加 403 回归场景以证明前端隐藏不替代后端鉴权。
- [ ] 11.7 对照 `llm_wiki` 的本地 Tauri 命令调用和无服务端 409 状态，记录 OpsPilot 请求错误保真、CAS、token 与前后端权限分层的阶段 11 证据。

## 12. 真实目录树与页面治理 UI

- [ ] 12.1 先为目录树/选择器/移动/URL 写组件测试与 Storybook，覆盖空目录、深度 8、长名称、merged 重定向、retired tombstone、刷新/前进/后退/深链和无权限。
- [ ] 12.2 将约 740 行的 `PageTab.tsx` 拆成查询、树、表格、编辑/来源抽屉与治理 modal，保持现有页面编辑功能回归可测。
- [ ] 12.3 新建 `WikiDirectoryTree.tsx`：展示虚拟“全部知识”、真实系统“待归类”和 active 目录树，保留空目录且日常模式只负责导航。
- [ ] 12.4 页面区域展示 breadcrumb、目录说明、直属/含子目录切换、目录/page type/auto-manual/来源/冲突/更新时间列；默认直属范围并明确批量操作范围。
- [ ] 12.5 新建 `WikiDirectorySelect.tsx` 与 `WikiPageMoveModal.tsx`，实现单页/批量 manual 移动、影响数量确认和恢复自动归类即时结果。
- [ ] 12.6 修改 `KnowledgeTab.tsx`，让页面/图谱共享 URL 范围；刷新、前进后退、分享深链可恢复，merged 自动替换目标 URL，retired 无 redirect 时提示并回到全部知识。
- [ ] 12.7 功能未启用或 readiness 未通过的 KB 继续显示旧平面页面列表；启用后不得用 page_type 分组伪装目录。
- [ ] 12.8 对照 `llm_wiki/knowledge-tree.tsx` 的只读 type 分组和隐藏空目录行为，记录 OpsPilot 在真实层级、空目录、治理和 URL 状态上的差异。
- [ ] 12.9 页面改名继续复用稳定 page ID，并通过轻量 governance generation 发布；UI 在确认前提示 v1 不保留旧标题 alias 及可能受影响的旧标题引用。

## 13. 结构编辑、资料、导入导出与图谱 UI

- [ ] 13.1 先为结构编辑器、409 冲突、影响预览、资料 classification root、导入预检和图谱目录过滤补齐 Storybook/组件测试。
- [ ] 13.2 新建 `WikiStructureEditor.tsx` 管理完整快照：existing node 隐藏回传只读 ID/key，new node 只发 client_ref，保存携带 structure version + base generation；用户不填写原始 ID/key。
- [ ] 13.3 修改 `SettingsTab.tsx` 增加结构配置区，并继续把 `schema_md` 明确显示为描述/生成规则，不把它当作可执行目录真相。
- [ ] 13.4 structure/base generation 任一 CAS 返回 409 时保留本地树，加载最新 revision/generation，展示 diff 并允许重新应用或放弃，不静默覆盖。
- [ ] 13.5 新建 `WikiDirectoryImpactDrawer.tsx`，展示合并/退役影响并持有绑定 version/base/参数/hash 的 operation token；过期或状态变化必须重新预览，不能按旧 token 执行。
- [ ] 13.6 修改 `MaterialTab.tsx` 支持完整相对路径与 classification root；新增 `WikiMarkdownImportModal.tsx` 展示 preflight、路径映射和显式“从文件夹创建人工目录”。
- [ ] 13.7 修改 `GraphTab.tsx/GraphExplorer.tsx` 共享目录/子树筛选，节点展示 breadcrumb，且不绘制目录父子关系为语义边。
- [ ] 13.8 更新 Wiki Storybook mock、settings/graph stories，并新增目录/page/import 场景；对照 `llm_wiki/wiki-page-delete.ts` 与 `dedup-runner.ts` 记录 OpsPilot 的影响预览、无 LLM 目录合并、持久 redirect 和事务差异。

## 14. 灰度、迁移演练与运行保护

- [ ] 14.1 新目录 UI 默认按 KB 关闭；backfill 前排空无 base/revision 旧任务并开启写围栏，ready 后所有写入已走新管线，enable 在 KB 锁内复验 readiness/base 指针。
- [ ] 14.2 在 `munchkin` 运行 audit/backfill dry-run、围栏写请求、实际回填和幂等重跑，记录行数/耗时/锁等待，并证明无新 null directory/generation 外写入及正文/证据/Chunk/向量不变。
- [ ] 14.3 选择测试 KB 保存结构真相、自动归类存量 auto 页面并核对 manual/待归类结果，再按 KB 启用新读写路径。
- [ ] 14.4 监控并设定告警阈值：null directory、待归类率、unknown key、generation failed/superseded、消费面 mismatch、结构 409 和回退频率。
- [ ] 14.5 保留旧平面读取一个发布周期，但 ready/enabled KB 的写入永远不退回 legacy；关闭 UI 开关只切兼容读视图并保留 generation/目录数据，不做破坏性 down migration。
- [ ] 14.6 编写 runbook：结构回滚生成新递增 revision；generation 回退创建新 rollback_of；结构不兼容需显式联动新 revision；列出被覆盖的后续人工变化与 CAS 失败处理。
- [ ] 14.7 对照 `llm_wiki` source-only ingest cache 与逐文件部分成功风险，验证 OpsPilot 把 structure fingerprint 纳入任务身份并以 generation 消除半发布。

## 15. 自动化验证与真实浏览器验收

- [ ] 15.1 运行新增/受影响 Django 测试、migration checks、静态检查和全量 OpsPilot Wiki 回归，要求进程正常退出且无后台线程泄漏。
- [ ] 15.2 运行 Web 类型检查、lint、组件测试与 Storybook build，修复目录功能引入的 console warning、未翻译文案和无障碍问题。
- [ ] 15.3 在空库、存量库、规范标题冲突库和大树样例演练 expand/fence/backfill/contract、开关、结构回滚、兼容与不兼容 rollback_of，并测 contract migration 锁时。
- [ ] 15.4 用固定种子数据真实点击结构保存、空目录、页面创建、NFKC/空白/大小写等价标题拒绝、单/批量移动、manual 重建保持与恢复 auto；写动作不得用 API 代替。
- [ ] 15.5 用两个窗口验证 409 后本地树仍在且可查看最新 revision/generation diff；用确定性故障钩子触发结构/人工变更 CAS superseded 和构建 failed，核对旧消费面不变。
- [ ] 15.6 真实完成资料上传/classification root、合并/退役 token 过期重预览、原生导出→空 KB 恢复结构、第三方 ZIP 显式建目录，以及 preflight token 结构变化/replay 拒绝。
- [ ] 15.7 在列表/关键词/图谱切换同一范围，核对集合/breadcrumb/generation；再验证刷新、前进、后退、分享深链、merged URL 重定向、retired tombstone 和无目录语义边。
- [ ] 15.8 为每条路径保存按固定命名的截图、脱敏网络状态/console/后端读回和 KB/revision/build/generation ID；不得记录凭据、请求头密钥或敏感正文。
- [ ] 15.9 运行 `openspec validate add-opspilot-wiki-directory-governance --strict --no-interactive`，检查所有场景、任务 checkbox、无占位标记和 proposal/design/spec/tasks 一致性。
- [ ] 15.10 检查 Git diff 仅包含预期业务/测试/文档改动，确认 `.env`、`local_settings.py`、向量重建和无关用户文件未被提交，再请求独立代码审查并解决高优先级问题。
- [ ] 15.11 完成 1–15 阶段 `llm_wiki@9b71ade` 对照矩阵完整性检查；每阶段必须有源码/测试或“无对应实现”、借鉴、拒绝、OpsPilot 差异和验证证据，缺项阻止发布。
