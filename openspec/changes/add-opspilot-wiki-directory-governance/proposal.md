## Why

OpsPilot Wiki 当前只把 `purpose_md` 和 `schema_md` 作为生成提示，知识页面仍以平面列表和 `page_type` 展示，无法证明页面是否按配置结构落位，也缺少稳定目录身份、空库初始化和人工治理能力。需要将“Schema 骨架 + 人工治理”升级为一等领域能力，并保证页面、关键词结果和关系图谱在构建失败或结构变化时保持一致。

## What Changes

- 将「用途与结构」中的结构化 Schema 作为唯一管理员配置入口，并由它生成不可变结构 revision 与具有稳定系统 ID/key 的目录树；`WikiDirectory` 仅作为查询、页面外键和治理所需的运行时投影，不再提供第二套独立目录配置。
- 每个页面只归属一个主目录；`KnowledgePage` 仅新增 `directory_id` 与 `directory_assignment_mode`，跨领域语义继续通过 tags、WikiLink 和 `PageRelation` 表达。
- 通用资料构建采用 entity/concept/source/query/comparison/synthesis 的稳定主题页契约；每个文件独立发布并保留唯一来源摘要，Index/Overview 继续按 Generation 派生。
- 新增不可删除的系统“待归类”目录。LLM 只输出稳定 `directory_key`，服务端按人工锁定、classification root 范围内的合法 key、同一范围内的类型默认目录、允许接收页面的 classification root、待归类的优先级确定性落位，未知 key 不自动建目录。
- 支持目录新建、重命名、移动、排序、退役和结构合并；人工移动页面形成 manual lock，恢复自动归类后才允许后续构建重新路由。
- 结构保存由后端强校验，成功后创建相互绑定的 structure revision 与 governance generation，并仅在 `structure_version`（active structure revision）与 base generation CAS 均成功时原子激活二者；不增加草稿、人工验证、构建审批或目录级 ACL。
- 新增 generation 快照和 active generation 切换：页面集合、当前版本、目录位置、关键词消费面和关系图谱完成一致性校验后统一激活，失败保持旧 generation。
- 全量重建按知识库全局标题身份复用页面 ID，恢复同名归档页，保留 manual 目录；只有 human/mixed 正文冲突或页面身份歧义产生非阻塞候选。
- 来源文件夹仅作为 provenance 与分类提示；原生导入导出使用 manifest、结构 revision 和稳定 directory key 往返，第三方 ZIP 默认不按物理路径自动建目录。
- 知识列表增加真实目录树、空目录、面包屑、直属/子树筛选和批量移动；管理员在「用途与结构」中编辑唯一结构 Schema，关键词检索与图谱支持同一目录范围过滤。
- 当前数据均为本地测试数据；模型冻结后保留 0066 及以前 migration，删除其后未发布 migration，清空数据库并从最终模型重新生成连续 migration，不实现 backfill、双读或灰度兼容。
- **BREAKING**：同一知识库内页面标题改为全局唯一（包含归档与候选状态）。并发重复标题必须被数据库与领域服务拒绝，系统不得自动改名或自动合并。
- 本变更不新增或重建向量能力，不改变现有 embedding、语义检索或混合检索实现。
- 本变更只提供目录、Structure Revision 和 Generation 基础；Index/Overview/查询路由由 `add-opspilot-wiki-generation-navigation` 负责，预算与长文件有界构建由 `add-opspilot-wiki-minimal-context-budget` 负责。

## Capabilities

### New Capabilities

- `wiki-directory-structure`: 定义结构化目录配置、稳定目录身份、不可变 revision、系统目录、结构校验以及人工目录治理规则。
- `wiki-page-directory-assignment`: 定义页面单一主目录、知识库内标题唯一、自动/人工归类、LLM 路由、待归类回退和空库初始化行为。
- `wiki-generation-consistency`: 定义构建与全量重建的 generation 快照、页面身份和解、结构 revision 绑定、原子激活、失败隔离与回退行为。
- `wiki-directory-portability`: 定义来源路径语义、原生 manifest 导入导出、第三方归档映射、预检查与安全约束。
- `wiki-directory-navigation`: 定义真实目录树 UI、页面治理交互、目录范围列表/关键词检索/图谱过滤以及浏览器端到端验收。

### Modified Capabilities

- 无。当前主规格中没有 OpsPilot Wiki 目录能力；本变更新增独立 capability，并与进行中的知识决策 change 保持兼容。

## Impact

- 后端：新增目录、结构 revision、目录变更历史和 generation 领域模型；扩展页面、关系、构建记录、构建/重建、导入导出、关键词检索和图谱服务。
- 数据：从空库创建系统待归类、首个 Structure Revision 与 baseline Generation，并增加知识库内标题唯一约束；不保留本地测试旧数据。
- API：新增目录树、结构保存/影响预览、页面移动/恢复自动归类、generation 状态和目录范围过滤契约；管理员在 `directory_enabled=false` 时可完成结构配置，但不存在旧数据迁移灰度读路径。
- Web：重构知识页面导航，新增结构编辑和治理交互，并让列表、关键词与图谱共享目录筛选状态；不增加向量 UI。
- 构建：所有任务必须绑定 `base_generation_id`、`structure_revision_id`、结构指纹与 pipeline version；缺少任一冻结身份的任务一律拒绝激活。
- 测试与交付：在独立 worktree 和空 `opspilot` 数据库中执行后端、前端、migration、并发和真实浏览器点击验收，保存 UI、网络、控制台及后端关键 ID 证据。
- 后续依赖：Generation Navigation 和 Minimal Context Budget 两个 change 必须复用本变更的 active Generation，不得引入 `active_manifest` 等第二套知识内容活动指针；`active_structure_revision` 继续作为结构配置指针。
- 依赖：不引入新的外部运行时依赖；继续使用 Django ORM、现有异步任务、React/Next.js 和 Ant Design。
