## Why

OpsPilot Wiki 当前只把 `purpose_md` 和 `schema_md` 作为生成提示，知识页面仍以平面列表和 `page_type` 展示，无法证明页面是否按配置结构落位，也缺少稳定目录身份、存量重归类和人工治理能力。需要将“Schema 骨架 + 人工治理”升级为一等领域能力，并保证页面、关键词结果和关系图谱在构建失败或结构变化时保持一致。

## What Changes

- 新增机器可解析的结构化目录配置、不可变结构 revision 和具有稳定系统 ID/key 的目录树；`schema_md` 继续承载用途说明和生成规则，不再充当机器结构真相。
- 每个页面只归属一个主目录；`KnowledgePage` 仅新增 `directory_id` 与 `directory_assignment_mode`，跨领域语义继续通过 tags、WikiLink 和 `PageRelation` 表达。
- 新增不可删除的系统“待归类”目录。LLM 只输出稳定 `directory_key`，服务端按人工锁定、合法 key、类型默认目录、待归类的优先级确定性落位，未知 key 不自动建目录。
- 支持目录新建、重命名、移动、排序、退役和结构合并；人工移动页面形成 manual lock，恢复自动归类后才允许后续构建重新路由。
- 结构保存由后端强校验，成功后自动生成 revision 并立即生效；不增加草稿、人工验证、构建审批或目录级 ACL。
- 新增 generation 快照和 active generation 切换：页面集合、当前版本、目录位置、关键词消费面和关系图谱完成一致性校验后统一激活，失败保持旧 generation。
- 全量重建按知识库全局标题身份复用页面 ID，恢复同名归档页，保留 manual 目录；只有 human/mixed 正文冲突或页面身份歧义产生非阻塞候选。
- 来源文件夹仅作为 provenance 与分类提示；原生导入导出使用 manifest、结构 revision 和稳定 directory key 往返，第三方 ZIP 默认不按物理路径自动建目录。
- 知识列表增加真实目录树、空目录、面包屑、直属/子树筛选、批量移动和结构编辑模式；关键词检索与图谱支持同一目录范围过滤。
- 存量数据按 expand、backfill、reconcile、grey rollout、contract 分阶段迁移；数据库 migration 不调用 LLM，页面 ID、版本、证据、关系、Chunk 与既有向量数据保持不变。
- **BREAKING**：同一知识库内页面标题改为全局唯一（包含归档与候选状态）。已有重复标题必须在知识库启用目录能力前显式解决，系统不得自动改名或自动合并。
- 本变更不新增或重建向量能力，不改变现有 embedding、语义检索或混合检索实现。

## Capabilities

### New Capabilities

- `wiki-directory-structure`: 定义结构化目录配置、稳定目录身份、不可变 revision、系统目录、结构校验以及人工目录治理规则。
- `wiki-page-directory-assignment`: 定义页面单一主目录、知识库内标题唯一、自动/人工归类、LLM 路由、待归类回退和存量重归类行为。
- `wiki-generation-consistency`: 定义构建与全量重建的 generation 快照、页面身份和解、结构 revision 绑定、原子激活、失败隔离与回退行为。
- `wiki-directory-portability`: 定义来源路径语义、原生 manifest 导入导出、第三方归档映射、预检查与安全约束。
- `wiki-directory-navigation`: 定义真实目录树 UI、页面治理交互、目录范围列表/关键词检索/图谱过滤以及浏览器端到端验收。

### Modified Capabilities

- 无。当前主规格中没有 OpsPilot Wiki 目录能力；本变更新增独立 capability，并与进行中的知识决策 change 保持兼容。

## Impact

- 后端：新增目录、结构 revision、目录变更历史和 generation 领域模型；扩展页面、关系、构建记录、构建/重建、导入导出、关键词检索和图谱服务。
- 数据：为每个知识库创建系统待归类目录与 baseline generation，分批回填页面，增加知识库内标题唯一约束，并保留现有页面身份和版本链。
- API：新增目录树、结构保存/影响预览、页面移动/恢复自动归类、generation 状态和目录范围过滤契约；现有平面页面接口在灰度期继续可用。
- Web：重构知识页面导航，新增结构编辑和治理交互，并让列表、关键词与图谱共享目录筛选状态；不增加向量 UI。
- 构建：所有新任务绑定 `structure_revision_id`、结构指纹与 pipeline version；旧任务在知识库启用前排空或拒绝激活。
- 测试与交付：在独立 worktree 和 `munchkin` 数据库环境中执行后端、前端、迁移、并发和真实浏览器点击验收，保存 UI、网络、控制台及后端关键 ID 证据。
- 依赖：不引入新的外部运行时依赖；继续使用 Django ORM、现有异步任务、React/Next.js 和 Ant Design。
