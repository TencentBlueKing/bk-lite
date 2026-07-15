# OpsPilot Wiki 目录治理验证记录

## 基线：现有模型与重建测试

### OpsPilot 证据

- 基线范围：`server/apps/opspilot/tests/wiki/test_models_pure.py` 的 1 项模型测试，以及 `server/apps/opspilot/tests/wiki/test_rebuild.py` 的 11 项重建测试，共 12 项。
- 默认 `server/pytest.ini` 会自动加载 pytest-cov 并对整个 `apps` 包生成覆盖率。最小模型用例已输出 `PASSED` 后，pytest-cov 的全仓覆盖率收尾在 60 秒内没有生成 coverage summary，也没有退出。
- 禁用第三方插件自动加载、只显式加载 pytest-django，并清空默认 `addopts` 后，同一模型测试正常退出；在该边界上只恢复 pytest-cov 和 `--cov=apps`，即可复现 `PASSED` 后超过 60 秒不退出。因此已定位到 pytest-cov 的全仓 coverage finalization 超时，而不是 Wiki 断言、pytest-django 或 Django 数据库 teardown。
- 当前证据不能区分 coverage finalization 是永久死锁还是全仓汇总极慢，因此不使用“死锁”结论。该问题属于测试基础设施；如需修复，应另立 OpenSpec change 调整全局 coverage/report 门禁，不扩大本功能 diff。
- 一次人工隔离运行曾停在 `TestRebuildView::test_rebuild_endpoint_enqueues_task_and_returns_running_record` 的 setup 日志后；随后该用例单独运行以 `1 passed in 12.56s` 正常退出，前置用例与该用例组合以 `2 passed in 9.56s` 正常退出，完整 12 项又以 `12 passed in 11.17s` 正常退出。该现象未稳定复现，只记录为暂态等待，不能作为代码根因。接口请求本身观测到约 5–8 秒的 slow-request 日志。

已验证可正常终止的 PowerShell 隔离命令：

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
$env:PYTHONUTF8='1'
D:\app\venv\bkliteserver\Scripts\python.exe -X utf8 -m pytest apps/opspilot/tests/wiki/test_models_pure.py apps/opspilot/tests/wiki/test_rebuild.py -p django -o addopts= -vv -s --reuse-db
```

执行目录：`server`。最终结果：`12 passed in 11.17s`，进程退出码为 0。

### llm_wiki@9b71ade 对照

- `llm_wiki` 的 `package.json` 使用 Vitest：`test:mocks` 与 `test:llm` 均执行 `vitest run`，真实 LLM 测试额外关闭文件并行并启用 verbose reporter。
- 未发现与 Django、pytest-django 或 `--cov=apps` 等价的测试链路，因此本阶段没有可直接照搬的 pytest 隔离实现。
- 借鉴点是把快速 mock 基线与真实 LLM 基线分开；拒绝直接复制其测试命令，因为 OpsPilot 的模型、迁移和 API 合约依赖 Django 测试数据库。

## 1–15 阶段对照矩阵

以下路径均通过 `git show`、`git grep` 或 `git ls-tree` 固定到 `llm_wiki@9b71ade`，不引用其后续工作树。标为“无对应实现”表示在该提交的源码树和测试树中未找到等价的关系型实体、状态机或工作流；最接近的文件机制仍列出，避免把“没有同名文件”误写成“完全没有相关思想”。

| 阶段 | `llm_wiki@9b71ade` 对应源码/测试 | 借鉴点 | 明确拒绝项 | OpsPilot 差异 | 当前验证证据 |
| --- | --- | --- | --- | --- | --- |
| 1. 隔离环境、基线与对照 | `package.json`；Vitest 的 `src/**/*.test.ts` 与 `*.real-llm.test.ts`；集中测试辅助位于 `src/test-helpers/`；`src/lib/wiki-schema.ts`/测试把 `schema.md` Page Types 解析为 type/path；`src/lib/ingest.ts` 逐文件写入且不匹配项会被丢弃；`src/components/layout/knowledge-tree.tsx` 按 type 分组；`src/lib/wiki-page-types.ts` 由物理路径推导 type；`src-tauri/src/commands/file_history.rs` 只提供单文件历史恢复；`src/commands/fs.ts` 与 `src/types/wiki.ts` 是本地 Tauri 命令/类型；固定提交无 REST JSON Schema、CAS、operation/preflight token 或 generation rollback 契约 | mock 与真实 LLM 基线分层；测试对象通过集中 helper 构造；schema 解析采用集中、可执行的纯契约测试；借鉴显式类型与命令边界 | 直接复制 Node/Vitest 命令；用文件路径、page type 或测试专用对象替代 Django 领域入口与集合级发布真相；接受逐文件写入的部分成功语义 | Django 模型、迁移、API 依赖测试数据库；新增 Wiki-local `WikiFactory`/fixture 和 AST guard；新增不可变治理契约，固定 `legacy→backfilling→ready→enabled` 单调状态、写围栏、active revision/generation 真相、generation-aware CAS 与派生兼容镜像；冻结 16 个 Draft 2020-12 请求/响应 Schema，分离 API/结构格式版本，覆盖完整快照、existing ID/key、new client_ref、generation 激活/回退及目录/导入 token 绑定 | 基线隔离命令已 `12 passed in 11.17s` 并退出 0；Task 1.4 联合复验 `26 passed in 9.29s`；Task 1.5 状态契约与 Task 1.4 factory/source guard 联合复验 `39 passed in 3.23s`；Task 1.6 根级 API 契约/factory/source guard 联合复验 `35 passed in 5.89s` 并退出 0，规格与代码质量复审均通过；OpenSpec strict 校验通过；coverage 收尾问题已单独定界 |
| 2. Expand 模型与兼容迁移 | `src-tauri/src/commands/project.rs` 创建固定 wiki 目录并写 `schema.md/purpose.md`；`src/types/wiki.ts`、`src-tauri/src/types/wiki.rs` 仅有 Project/FileNode/Page path 类型；`src/lib/persist.ts` 写 `.llm-wiki/*.json`；无关系型 migration/revision | 项目 UUID 稳定、前后端类型显式、Markdown 可移植 | 以页面文件 path 充当稳定页面/目录身份 | 新增目录、结构 revision、generation、成员快照和 PROTECT FK，先 nullable expand | 固定提交树中没有关系型 migration/revision；OpsPilot 对应任务 2.1–2.5 待实现后追加测试结果 |
| 3. Readiness、回填与 Contract | `ingest-queue.ts`/测试会为旧队列 migrate-on-load 回填 `projectId`，`review-store.ts` 有幂等 migrate-on-load；无 KB readiness/backfill 状态机 | 小范围兼容读取、幂等迁移与回归测试 | 把客户端懒迁移或 source cache 当作生产关系库回填/contract gate | KB 级 audit、写围栏、批次可恢复 backfill、`legacy→backfilling→ready→enabled` 和后置 contract migration | 固定提交仅有本地 JSON/队列兼容迁移，无流量围栏或 readiness；OpsPilot 证据目标为 `test_directory_migrations.py` 与 management command 集成测试 |
| 4. 结构 revision 与目录治理后端 | `wiki-schema.ts`/测试从 `schema.md` 的 Page Types 表解析 type→directory 并校验路由；`file-tree.tsx`、`knowledge-tree.tsx` 展示文件/type；无目录实体/revision/CAS API | 配置作为路由输入、生成后 type/目录一致性校验、树形导航 | path 身份、只读 type 分组、隐藏空目录、无并发保护 | 稳定 key、空目录、tombstone/redirect、完整快照、dry-run token、双 CAS | `knowledge-tree.tsx` 实际把 Markdown flatten 后按 type 分组；OpsPilot 对应任务 4.1–4.6 |
| 5. 页面全局身份与目录归类 | `source-identity.ts`/测试生成 slug+hash；`wiki-page-resolver.ts`/测试对跨目录同名保留 first-match DFS；`wiki-page-types.ts`、`wiki-page-delete.ts` 及测试 | 来源身份规范化、碰撞/长度/大小写测试、集中删除引用清理 | 重复标题 first-match、path/slug 页面身份、物理删除并同步删 embedding | 单 KB 规范标题全局唯一、稳定 page ID、manual/auto 路由、逻辑归档与可回退治理 generation | 固定测试明确保留 first-match；`wiki-page-delete.ts` 明确物理级联；OpsPilot 对应任务 5.1–5.7 |
| 6. Generation 一致发布与回退 | `src-tauri/src/commands/file_history.rs` 内置 append-only 历史测试；`src-tauri/src/commands/fs.rs` 的单文件 atomic write | 写前历史、单文件原子替换、恢复也追加历史 | 把逐文件历史当作集合级发布，或复活旧快照 | 完整 generation 成员快照、base/revision CAS、短事务激活、新 `rollback_of` generation | Rust 测试只证明单文件 record/restore；无集合 generation；OpsPilot 对应任务 6.1–6.8 |
| 7. 构建、更新、重建与关系 | `src/lib/ingest.ts`、`ingest-queue.ts`、`page-merge.ts`、`enrich-wikilinks.ts` 及 scenario/race/real-LLM 测试 | 合并锁定 type/title/created、LLM 输出解析校验、来源任务身份 | 逐文件正式写入、部分成功、路径路由、审批/清理替代原子发布 | 固定 base/revision 的 staging generation，无审批直接 CAS 激活，human/mixed 保留候选 | `page-merge.ts` 有写前 sanity/fallback；`ingest-queue.ts` 有 partial-output cleanup，但无 generation CAS；对应任务 7.1–7.8 |
| 8. 非向量消费面统一切换 | `knowledge-tree.tsx`、`src/lib/wiki-graph.ts`、`graph-*.test.ts`、搜索测试 | 图谱过滤与搜索场景测试集中化 | 用 page type 分组伪装目录、各消费面分别读当前文件 | 列表、关键词、Agent、WikiLink、关系、图谱、概览、导出统一读 active generation；目录路径与 Markdown heading 分离 | `knowledge-tree.tsx` 明确 `Map<type, pages>` 分组；OpsPilot 对应任务 8.1–8.8，向量行为保持不变 |
| 9. 来源路径、导入导出与安全 | `project-file-sync.ts`、`source-lifecycle.ts`、`ingest-cache.ts` 与碰撞/路径 property 测试；`ingest.ts` 拒绝绝对/逃逸 wiki 路径；有递归目录导入但无原生项目导出 | 完整相对路径/source identity/content hash、hash 配对识别移动、路径穿越与 Windows 路径测试 | “来源文件夹即知识目录”、无 preflight/token 的直接文件写入 | provenance 与知识目录解耦；manifest/structure；preflight 单次 token、配额、zip-slip/symlink/TOCTOU 防护 | 固定源码证明来源移动/导入安全，但没有导出 manifest 与 base-generation token；OpsPilot 对应任务 9.1–9.9 |
| 10. 后端 API、权限与可观测性 | `api_server.rs` 提供 health、统一 JSON 错误、429/503、kill switch、constant-time token；`api-server.real-llm.test.ts` 有真实 HTTP 矩阵 | health、限流、fail-closed token、真实 HTTP 错误测试 | 单机全局 token 代替 KB 管理权限；`{ok,error}` 代替 revision/generation CAS、阶段可观测和审计 | DRF KB 管理员权限、409/422 结构化错误、operation/preflight token、指标与可查询审计 | 固定树未见 KB ACL/409 revision/generation 契约；对应任务 10.1–10.7 |
| 11. 前端请求契约与基础设施 | `commands/fs.ts` 的 typed `invoke` 与去重测试、`types/wiki.ts`、i18n parity 测试；API 设置源码明确尚无正式 OpenAPI，类型在前端/MCP 重复 | 集中 typed adapter、pending 去重失败清理、中英文 key 一致性 | 本地 command 字符串错误或重复手写类型充当网络契约，UI 隐藏充当授权 | request 错误保真、structure/base CAS、token 类型、URL 查询状态、前后端双层权限 | 固定提交无服务端 structure 409/code/details/latest revision；OpsPilot 对应任务 11.1–11.7 |
| 12. 真实目录树与页面治理 UI | `file-tree.tsx`、`knowledge-tree.tsx`、`file-tree-utils.test.ts` | 懒加载、展开/选择交互、文件树基础组件 | `knowledge-tree` 的 type 分组、flatten Markdown 后丢空目录、path 作为选择身份 | “全部知识”虚拟节点 + “待归类”系统节点 + 真实目录；空目录、breadcrumb、manual/auto、URL 深链 | 固定源码证明 `flattenMdFiles` 后按 type 分组，非知识目录实体树；OpsPilot 对应任务 12.1–12.9 |
| 13. 结构、资料、导入导出与图谱 UI | `sources-view.tsx`、`scheduled-import-section.tsx`、`source-watch-section.tsx`、`graph-view.tsx`、`dedup-runner.ts` 及测试 | 来源树、定时导入、图过滤、危险动作二次确认 | 用 LLM dedup/页面物理删除实现目录合并，或无绑定 token 的旧预览直接执行 | 完整结构编辑器、409 保留本地树、影响 drawer、classification root、导入 preflight、目录范围图谱 | 固定提交有来源与图谱 UI，但无 structure editor/revision/token；OpsPilot 对应任务 13.1–13.8 |
| 14. 灰度、迁移演练与运行保护 | `ingest-queue.ts`、`ingest-cache.ts`、`project-file-sync.ts`、`project-mutex.ts` 及测试；API 有 kill switch；无 KB rollout/readiness 状态机 | retry/paused queue、source hash、项目互斥、启动恢复和失败清理 | source-only cache/逐文件部分成功作为发布保障，或缺配置 fail-open 的迁移门禁 | KB 默认关闭、fence/backfill/enable gate、generation 防半发布、非破坏性兼容读 | 固定树无 expand/backfill/ready/contract 或 generation runbook；OpsPilot 对应任务 14.1–14.7 |
| 15. 自动化与真实浏览器验收 | `package.json` 的 Vitest mock/real-LLM、property/race/scenario 测试和 Rust 单测；`vite.config.ts` 使用 node 环境；CI 构建前端/Rust但不执行 `npm test`；无 Playwright/Cypress/Storybook | mock/real-LLM 分门禁、property/race/scenario 与跨平台 build matrix | Node 函数/e2e 命名或 build 成功代替真实点击、双窗口、网络/console/后端读回 | Django/Web/Storybook + migration 演练 + 浏览器真实点击和证据归档 + 独立审查 | 固定提交没有 UI 自动点击框架；OpsPilot 对应任务 15.1–15.11 |

维护规则：从任务 2 开始，每完成一个子任务，必须在对应阶段的“当前验证证据”中补充 OpsPilot 文件、测试命令和结果，并再次核对固定的 `llm_wiki@9b71ade` 结论。若实际源码推翻本矩阵，先修矩阵再继续实现。
