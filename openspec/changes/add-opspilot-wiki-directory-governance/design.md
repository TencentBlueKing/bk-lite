## Context

OpsPilot Wiki 已有知识库、资料、页面、页面版本、证据、关系、Chunk、构建记录和检查项，但目录概念尚不存在：

- `WikiKnowledgeBase.purpose_md/schema_md` 会进入生成提示，但结构只是软约束。
- `KnowledgePage` 只有 `page_type/title/status/current_version` 等字段，没有主目录或路径。
- `PageRelation` 表示页面语义关系，`PageChunk.heading_path` 表示 Markdown 内部标题路径，两者都不能承担知识目录。
- 页面 API 与 `PageTab.tsx` 是平面分页列表，图谱主要按 `page_type` 展示。
- Markdown 导出统一写入 `pages/`，导入忽略 ZIP 父目录。
- 当前全量重建先归档 AI 页面再重新生成；即使事务能够回滚数据库异常，也没有独立候选 generation、结构 revision 固定或显式消费面切换。

`llm_wiki` 提供了有价值但不完整的对照：它把 `schema.md` 的 page type 映射为物理 `wiki/...` 路径，要求 LLM 输出 FILE 路径，并在写文件前校验 frontmatter type 与目录一致。这证明“Schema 路由提示 + 确定性写前校验”有效；但其目录是文件系统路径、页面身份也是路径，UI 主要按 type 分组，没有目录实体、revision、manual lock、存量 reconciliation 或 generation。Schema 变化也不进入只包含资料正文 hash 的 ingest cache key，逐文件写入可能部分成功。

本设计借鉴 `llm_wiki` 的路由契约、完整来源相对路径、写前校验与历史备份，不复制路径身份、mismatch 丢页、source-only cache、直接写正式页或 type 分组伪目录。

相邻 change `streamline-wiki-knowledge-decisions` 正在把用户决策收敛为知识正文冲突和页面身份判断。本变更 MUST 与它兼容：目录低置信度、未知 key、Schema mismatch 和确定性重建不进入决策中心；只有 human/mixed 正文冲突或页面身份歧义复用其候选/决策能力。

该相邻 change 不是本变更的未声明前置依赖。先冻结 `KnowledgeCandidateAdapter.create_body_conflict/create_identity_conflict` 契约：若相邻服务已合入则适配复用，否则本 change 提供最小实现，后续合并不得改变目录/generation 语义。

工程约束：

- Django ORM 必须保持仓库当前数据库兼容性，避免方言专属 JSON 查询或条件唯一约束。
- 页面标题在单个知识库内全局唯一，目录不是页面身份。
- 结构化目录配置是机器真相；`schema_md` 是说明和生成上下文。
- 知识库构建通常由管理员发起，不增加结构审批、构建审批或目录 ACL。
- 本阶段不新增向量生成、检索、重建、权重和 UI。
- 开发在 `.claude/worktrees/opspilot-wiki-hierarchy` 的 `codex/opspilot-wiki-hierarchy` 分支进行，本地数据库默认名为 `opspilot`。

## Goals / Non-Goals

**Goals:**

- 建立可查询、可治理、可审计、可迁移的真实知识目录树。
- 让结构化配置、LLM 路由、持久化校验、页面列表和导入导出使用同一稳定目录身份。
- 保留页面稳定 ID、版本链和人工目录选择，并在结构变化后安全重归类 auto 页面。
- 使页面集合、当前版本、目录、关键词消费面和关系图谱通过 generation 一致切换。
- 提供目录 CRUD、排序、合并、退役、页面移动、待归类和恢复自动归类的完整前后端链路。
- 分阶段迁移存量知识，支持灰度、回退、浏览器真实点击验证和可观测性。

**Non-Goals:**

- 不使用目录替代 tags、WikiLink、PageRelation 或 page type。
- 不允许页面同时属于多个主目录；跨领域通过现有语义能力表达。
- 不增加目录级权限、结构草稿、人工验证、审批中心或构建批准。
- 不根据资料物理文件夹默认创建知识目录。
- 不在目录合并时调用 LLM 合并同名页面正文。
- 不新增或重建 embedding、向量索引、语义检索与混合检索。
- 不在数据库 schema migration 中调用 LLM。

## Decisions

### 0. 目录能力启用后的真相源与发布边界

| 关注点 | 权威真相 | 兼容/派生数据 |
| --- | --- | --- |
| 当前目录树 | `active_structure_revision.structure_snapshot`，`WikiDirectory` 是该 revision 的活动查询投影 | 展示路径缓存 |
| 当前知识集合 | `active_generation` 的完整 `WikiGenerationPage` 成员、PageVersion、目录/模式/状态/元数据快照 | `KnowledgePage.current_version/status/directory/assignment_mode` 仅为旧路径兼容镜像 |
| 正文 | 不可变 `PageVersion` | Markdown 渲染缓存 |
| WikiLink/关系/关键词/图谱 | 从 active generation 的 PageVersion 派生且按 generation 隔离的结果 | 旧无 generation 数据仅在 legacy 模式读取 |
| 历史与解释 | 不可变 structure revision、generation、BuildRecord、PageDirectoryChange | 日志/指标 |

目录能力达到 `ready` 后，任何页面、目录或结构写入都不能直接修改上述 active 快照。人工创建、改名、移动、恢复 auto、正文编辑、逻辑归档和结构保存均创建一个以当前 `active_generation` 为 base 的轻量 governance generation；结构保存同时产生新 revision。激活时在知识库行锁内执行 base generation CAS，结构写还复验 base structure revision，成功后原子切换相互兼容的 active 指针。

因此已激活 generation 和 revision 永远不可变；两个构建、人工变更与构建、结构保存与构建之间的胜负规则统一为“第一个成功 CAS 的候选获胜，其他候选 superseded/rebase”。历史 breadcrumb 由 generation 固定的 structure revision 与成员目录显示快照恢复，不依赖后来被重命名的活动投影。

legacy/ready 期间旧平面 UI 可以读取兼容镜像，但 baseline 完成后所有写入口已进入 generation-aware 服务。只有 `directory_migration_state=legacy` 且尚未开始 backfill 的知识库允许旧写路径。

### 1. 结构配置快照与规范化目录表共同组成机器真相

新增以下领域模型：

- `WikiStructureRevision`
  - `knowledge_base`
  - `revision_no`
  - `structure_snapshot`
  - `fingerprint`
  - `created_by/created_at`
- `WikiDirectory`
  - `knowledge_base`
  - `key`：知识库内唯一、不可复用的稳定 key
  - `name/description`
  - `parent`
  - `sort_order`
  - `origin`：`system|schema|manual`
  - `status`：`active|retired|merged|archived`
  - `merged_into`
- `PageDirectoryChange`
  - 页面、前后目录、前后模式、结构 revision、来源、操作者和说明
- `WikiKnowledgeBase.active_structure_revision`、`active_generation`、`directory_enabled` 与 `directory_migration_state=legacy|backfilling|ready|enabled`；API 暴露的 `structure_version` 直接取 active revision 的单调 `revision_no`，不维护第二个可写版本源

revision 的 JSON 快照用于审计、构建固定和完整恢复；`WikiDirectory` 是活动查询、FK、树读取和约束的规范化投影。两者必须在同一保存事务中一致更新。

推荐结构快照格式：

```json
{
  "format_version": 1,
  "directories": [
    {
      "key": "dir_opaque_key",
      "name": "部署与升级",
      "parent_key": "dir_product",
      "description": "安装、升级和回滚流程",
      "order": 20,
      "origin": "schema",
      "rules": {
        "allowed_page_types": ["procedure", "faq"],
        "default_for_page_types": ["procedure"]
      }
    }
  ]
}
```

已有节点由 UI 隐藏回传服务端先前提供的只读 ID/key，后端校验它们与存量节点匹配且未被替换；新节点只提交前端 `client_ref`，后端生成 ID/key 并返回映射。用户和 LLM 都不能随意声明新的稳定 key。系统待归类使用保留 key，但数据库 ID 仍由系统生成。

**替代方案：只在知识库 JSONField 保存树。** 不采用，因为页面 FK、子树查询、同库授权、父子约束、影响统计和并发治理都会依赖脆弱 JSON 扫描。

**替代方案：只保存目录表。** 不采用，因为无法可靠固定构建所使用的完整结构，也不利于 diff、审计和回退。

### 2. 结构保存自动校验，生成相互绑定的 revision/governance generation 并经双 CAS 原子激活

结构编辑器保存完整快照、客户端读取的 `structure_version` 与 `base_generation_id`。服务端按顺序执行：

1. 验证知识库权限，并在知识库锁内复验请求的 `structure_version` 与 `base_generation_id` 分别匹配当前 active structure revision 和 active generation；任一不匹配返回 409 且不写入。
2. 规范化名称、父子关系与排序。
3. 验证 key 唯一、同级名称唯一、同库父节点、无循环、最大深度 8、系统目录不变量和规则引用。
4. 计算 diff 与影响摘要。
5. 基于请求的 base generation 批量构造轻量 governance generation；在同一有界事务中创建 structure revision、governance generation、assignment/projection 与审计，并仅在 `structure_version` 与 `base_generation_id` 双 CAS 仍成功时原子切换 active structure/generation 指针。末端任一 CAS 失败 MUST 返回 409 并回滚整个事务，不得保留未激活 revision、generation、assignment/projection 或审计写入。

非法保存整体失败；不产生部分节点、不产生 revision。破坏性合并/退役需要影响预览和用户确认，但这是操作安全确认，不是审批流。

**替代方案：draft → validate → approve → publish。** 不采用；知识库构建者通常就是管理员，多级审批增加状态和过期分支，却不能提升实际判断质量。

### 3. KnowledgePage 只增加目录 FK 与归类模式

`KnowledgePage` 仅增加：

```text
directory_id -> WikiDirectory
directory_assignment_mode -> auto | manual
```

归类来源、reason、confidence、建议目录、结构 revision 和操作者分别进入 `PageDirectoryChange`、`BuildRecord`、候选或 generation 元数据，不在页面主表堆积易过期解释字段。

所有页面写入口收敛到统一身份/归类服务；直接 `KnowledgePage.objects.create()` 不再允许绕过标题、目录和 generation 约束。目录能力启用后，这两个页面字段与 current/status 都是 active generation 的兼容镜像，只能在 generation 激活事务中刷新。

**替代方案：在页面增加 assignment_source、confidence、suggested_directory、structure_revision 等字段。** 不采用，因为这些是一次决策或构建事件，不是页面当前事实。

### 4. 标题是知识库内全局页面身份，目录与 page type 不是 identity

数据库最终增加 `(knowledge_base, title)` 普通唯一约束；统一算法对输入执行 Unicode NFKC、首尾 trim、连续 Unicode 空白折叠，并用 casefold 值比较，持久化标题保留清理后的展示大小写。所有 readiness/写入口在知识库行锁内执行相同算法，数据库唯一约束作为最终并发后盾。归档、pending、source-invalid 和 staging 页面都占用标题身份。

构建、导入和人工创建按同一规则处理：

- 命中活动页面：复用 ID。
- 命中唯一归档页面：恢复并复用 ID。
- 未命中：创建 staging/新页面。
- 存量重复或身份歧义：阻止该 KB 启用或 generation 激活，不自动改名/合并。
- 与已有标题冲突的正文候选：保存到已有页面的候选 `PageVersion/CheckItem`，不创建重复页面。

`page_type` 继续影响内容规则和默认目录，但不参与全局标题唯一键，也不作为目录身份。

页面改名保留页面 ID，并通过轻量 governance generation 发布新标题及重新派生的 WikiLink/关系；v1 不保留旧标题 alias，执行前必须提示旧标题引用影响。

**替代方案：目录 + 标题唯一。** 不采用，因为移动目录会改变身份，容易复制页面、断开 WikiLink 和重建历史。

### 5. LLM 只建议稳定 key，服务端确定性落位

构建开始时把固定 structure revision 中可用目录的 key、名称、路径、说明和规则注入提示。结构化页面输出包含：

```json
{
  "title": "安装指南",
  "page_type": "procedure",
  "directory_key": "dir_install",
  "directory_reason": "描述安装步骤",
  "directory_confidence": 0.91,
  "body": "..."
}
```

服务端按严格优先级落位：

1. 现有 manual 目录，即使它位于本批 classification root 外；
2. 当前 revision 且位于 classification root 内的合法 LLM key；
3. 同一有效范围内 page type 配置的唯一默认目录；
4. 允许接收页面的 classification root；
5. 系统待归类。

结构保存校验同一有效范围内每个 page type 最多一个默认目录。classification root 只限制 auto 候选；越界默认被忽略。当前 LLM 输出 merged/retired key 视为非法建议，而原生导入、历史链接和审计读取可以跟随持久 redirect 并记录重定向。

confidence 只用于构建追踪，不是页面事实，也不触发审批。未知、退役、当前 LLM 返回的 merged、跨知识库、越过 classification root 或违反硬规则的 key 不自动建目录、不丢弃页面，继续 fallback。

**对照 `llm_wiki`：** 保留其“Schema 注入提示 + 写前确定性验证”，但把 FILE path 改为稳定 key，并把 mismatch 的结果从“丢页”改为“确定性 fallback + 追踪”。

### 6. 人工移动形成 manual lock，目录治理不修改正文

人工新建页面和单页/批量移动设置 manual，并写 `PageDirectoryChange`。普通构建、资料更新、结构 reconciliation 和重建不得覆盖 manual 目录。恢复自动归类会立刻按当前 revision 重新路由；无合法建议则进入待归类。

目录合并只移动目录、页面 FK 和子目录：

- 同名活动子目录冲突时 v1 整体中止。
- 源目录标记 merged，保存 `merged_into` 和稳定 key/path redirect。
- 页面移动保留原 `auto|manual` 模式并写结构操作来源的 `PageDirectoryChange`；Schema 退役含页面目录时必须显式提供迁移映射。
- 非空目录不能直接删除。
- 空人工目录可归档；Schema 移除目录标记 retired。
- 系统待归类不能编辑、合并、退役或删除。

目录层级不创建 PageRelation，同目录不提升语义权重。

### 7. Build generation 隔离批量生成并统一切换消费面

新增：

- `WikiGeneration`
  - knowledge base、build record、structure revision、`base_generation`、`rollback_of`、`kind=build|governance|rollback`
  - `preparing|ready|active|superseded|failed|cancelled`
- `WikiGenerationPage`
  - generation、page、page version、directory ID/key/breadcrumb snapshot、assignment mode、page status、消费所需的可变页面元数据快照
- `PageRelation.generation`
- `WikiKnowledgeBase.active_generation`

所有历史引用 FK 使用保护性删除语义：`KnowledgePage.directory` 与 generation member/version/directory、`PageRelation.generation` 不得因 CASCADE 破坏保留快照。旧 PageRelation 唯一约束先 expand 为 generation-aware 唯一键，回填 baseline 关系后再移除旧约束。

页面身份可以被多个 preparing generation 复用，但每个 generation 拥有独立 PageVersion/成员。失败清理按引用计数执行：只有 active/retained generation、其他 staging version 和候选均不引用时，才能删除纯 staging 页面身份。

普通资料构建、资料更新、导入和重建先生成 staging 页面/版本/成员与关系，不修改 active 消费面。每次 generation 固定：

- `base_generation_id`，作为激活 CAS；
- `structure_revision_id`；
- structure fingerprint；
- pipeline version；
- source/material fingerprints。

激活前验证标题、目录、成员、当前版本、WikiLink/反向链接、关键词元数据和关系；在知识库行锁内要求 active generation 仍等于 base generation，且 active structure revision 与候选预期一致。任一 CAS 或结构检查失败，generation 标记 superseded；通过后在短事务中切换 active generation、必要的 active structure revision 和兼容指针。

页面列表、关键词消费面、图谱、导出和 Agent 非向量检索必须通过统一 active-generation 查询服务读取，禁止各自继续直接查询所有 `KnowledgePage(status=active)` 或无 generation 的 `PageRelation`。

任何已激活 generation 都不可变。人工创建、改名、编辑、恢复、目录移动、逻辑归档和结构保存创建轻量 governance generation；目录-only 操作可复用 PageVersion/未受影响关系，正文操作必须先准备 WikiLink/反向链接、关键词元数据与受影响关系。所有候选以当前 active generation 为 base 做 CAS，第一个成功者激活，其他候选 superseded/rebase。

只要页面仍被保留 generation 引用，删除入口只能执行逻辑归档或从当前 generation 成员集合移除，不能物理删除页面身份、版本或历史成员；否则回退无法恢复稳定页面 ID。

回退不重新激活旧行，而是以目标快照创建新的 `rollback_of` generation。预检先比较目标 generation 固定的 structure revision 与当前结构；若目标目录已 merged/retired/移动且当前结构无法完整表达，必须在显式确认后联动从旧快照创建新的递增 structure revision，未确认则阻止回退。执行请求携带 `structure_version` 与 `base_generation_id`，服务端在知识库锁内复验两个 active 指针；任一 CAS 冲突均返回 409，并在同一事务中回滚全部联动恢复写入，不得保留 structure revision、rollback generation、assignment/projection 或审计等孤儿记录；仅当 structure revision 与 base generation 双 CAS 均成功时，才允许原子切换新 revision 与 rollback generation 并完成回退。

至少保留最近两个成功 generation。失败或取消只清理其独占 staging 数据，不能通过删除所有“本次触及页面”模拟回滚。

**替代方案：沿用当前 `@transaction.atomic` 包住整个重建。** 不采用，因为 LLM 与关系生成是长任务，不能把长事务当发布机制，且消费者没有显式 generation 边界。

**替代方案：先归档旧 AI 页再生成。** 不采用，因为中途失败、缓存或并发读取会暴露缺失知识；旧 AI 页只能在新 generation 成功激活时从新成员集合移除。

### 8. 重建按稳定标题原地和解，不审批可确定结果

重建先读取全部活动/归档页面身份，再生成候选：

- AI 页面唯一命中：原 ID 上创建候选版本。
- 同标题归档页面：恢复 ID。
- manual 目录：保留。
- human/mixed 正文冲突：保留当前版本，创建非阻塞候选。
- 身份歧义：阻止激活并创建页面身份冲突。
- 未匹配旧 AI 页：只有新 generation 激活后才归档。

ready generation 自动激活，不存在构建审批。相邻知识决策 change 只接收真实正文/身份判断；目录 fallback、低置信度、schema mismatch 和确定性清理只进入 BuildRecord。

### 9. 关键词与图谱共享目录范围和 active generation

页面列表、关键词检索、上下文组装和图谱接口增加：

```text
directory_id
include_descendants
```

子树范围通过目录树查询解析，必须在关键词评分/top-k 前过滤。响应分别返回知识目录 breadcrumb 和 Markdown heading path。

图谱节点增加目录 ID/key/breadcrumb；过滤仅改变可见节点/关系集合，不生成目录父子 PageRelation，也不把同目录作为权重。关系 rebuild 先写 staging generation，不得先删除 active generation 的边。

向量服务保持原样；目录路径不写入 embedding，也不触发 vector reindex。

### 10. 原始来源路径与知识目录严格分离

Material 或其来源元数据保存：

- `source_relative_path`
- `source_identity`
- `source_folder_path`
- `content_hash`

完整相对路径解决不同文件夹下同名资料碰撞；folder context 可以帮助 LLM，但不能自动创建知识目录。上传批次可选择 `classification_root_directory` 限制候选目录子树。

**对照 `llm_wiki`：** 采用其完整来源相对路径和稳定 hash 思路；不采用其知识页面路径等于页面身份的做法。

### 11. 原生导入导出用 manifest 往返，第三方路径默认只做提示

原生 ZIP：

```text
manifest.json
structure.json
pages/<human-readable-directory-path>/<page>.md
```

manifest 保存格式版本、KB 信息、structure revision/hash、完整树、稳定 key、父子/顺序/状态、空目录、页面映射和时间。Markdown frontmatter 保存 title、page_type、directory_key、tags。展示路径可变，稳定 key 是机器身份。

原生导入优先级：key → manifest mapping → 显式目标 → 范围内 type 默认 → classification root → 待归类。

目标为仅含系统待归类的新建/空知识库时，管理员可在 preflight 确认恢复原生结构；系统导入器校验后保留 manifest 稳定 key，准备新的业务 structure revision 与 staging generation，并仅在 base generation 和 active structure revision CAS 均成功时原子激活二者。非空知识库仍按上述映射和 fallback，不能因未知 key 静默扩张结构。

第三方导入优先级：显式目标 → ZIP path 映射现有目录 → 范围内 type 默认 → classification root → 待归类。只有管理员显式开启“从文件夹创建人工目录”且结构预览通过，才能通过结构治理服务的 base generation 与 active structure revision 双 CAS 原子发布新 revision 和 governance generation；发布成功后再启动页面导入。

预检查返回标题冲突、未知 key、未映射路径、非法标题、重复、深度、数量和安全限制，并签发短期单次 token，绑定 archive hash、KB、操作者、目标、`structure_version`、`base_generation_id`、选项和配额版本。execute 重新鉴权、复验全部绑定值并拒绝 replay。实现必须把所有归档视为不可信输入，防 zip-slip、绝对/驱动器路径、symlink、保留 key 伪造、Unicode 规范化碰撞、大小/数量/深度超限和越权。

导入成功后更新页面版本、目录历史、WikiLink、关系、图谱、计数和关键词消费面，不修改向量。

### 12. 前端采用真实树 + 页面列表，并把结构编辑隔离成模式

知识页面布局：

- 左侧：虚拟“全部知识”、真实“待归类”和 active structure 目录树，空目录可见。
- 右侧：breadcrumb、目录说明、直属/包含子目录切换、页面表格和治理操作。
- 默认只查直属页面，避免批量操作误伤后代；`include_descendants` 显式开启。
- URL 保存 directory、子树、分页、搜索和 page type 状态。
- 页面行展示主目录、page type、auto/manual、来源、冲突和更新时间。

日常树只导航；管理员进入结构编辑模式后才能改树。结构保存提交完整快照、`structure_version` 与 `base_generation_id`。任一结构/base generation 409 冲突时保留本地树、加载服务端最新 revision/generation 并显示差异。

目录树筛选在列表、关键词和图谱间共享。灰度期未就绪 KB 继续使用旧平面列表，不删除目录数据。

**对照 `llm_wiki`：** 借鉴轻量左侧打开体验；不复制其按 frontmatter type 分组、隐藏空目录、只读 FileTree 和物理文件删除语义。

### 13. 迁移使用 expand/backfill/reconcile/grey/contract

数据库 schema migration 只做 expand：创建新表、索引、nullable FK 和 active 指针，不调用 LLM、不一次性扫描大表。

独立可恢复任务完成：

1. 预检查所有状态的重复标题、异常页面和旧 running build。
2. 在知识库锁内排空旧构建，把 migration state 置为 `backfilling` 并开启可重试写入围栏。
3. 幂等创建待归类、baseline structure revision 和 baseline generation，分批回填页面/现有关系。
4. baseline 完成后置为 `ready`；即使仍使用旧平面 UI，全部生产写入口也已走 generation-aware 服务。
5. 由管理员查看一次结构初始化预览并保存机器真相。
6. 按固定 revision 自动归类合法结果，歧义留待归类；不逐页审批。
7. readiness 在知识库锁内复验后按 KB 开启目录 UI/新管线。
8. 全部 KB 写入口已收敛并完成回填后增加非空、枚举和 `(knowledge_base,title)` 唯一约束。

旧平面读路径保留一个灰度周期。关闭功能开关只切回旧 UI，不降级数据库。结构回滚以旧快照创建新的递增 revision；generation 回退从保留快照创建新的 rollback_of generation，必要时联动新 revision。

### 14. 浏览器真实点击与关联 ID 是发布硬门禁

完成实现后使用浏览器工具真实操作，不用直接 API 代替写动作。基线与验收覆盖：

- 保存结构与空目录显示；
- 上传资料、构建和自动归类；
- manual 移动、重建保持、恢复自动归类；
- 未知 key 进入待归类；
- 目录合并/删除影响预览；
- 双窗口 structure 409；
- 构建期间结构变化导致 superseded；
- 构建失败保持旧 generation；
- 原生导出/导入往返；
- 目录范围关键词与图谱一致。

每条路径保存截图、网络状态、控制台错误检查、后端读回和 knowledge base / structure revision / build record / active generation ID。

当前仓库没有 Playwright/Cypress E2E 框架；v1 使用浏览器工具完成真实验收，稳定路径后续可以单独 change 固化为 CI E2E。

## Risks / Trade-offs

- **[完整 generation 成员快照增加存储]** → 只保留最近成功 generation，候选失败数据及时清理；规模证据表明需要时再引入 copy-on-write，不在 v1 提前复杂化。
- **[频繁治理 generation 增加写放大与竞争]** → 使用批量成员克隆、base CAS 和 superseded/rebase；回退前展示页面/目录/结构差异并显式确认，后续再评估 copy-on-write。
- **[存量标题重复阻塞唯一约束]** → 先 dry-run 输出 KB 级冲突清单，未清理 KB 保持旧平面模式，不自动改名或合并。
- **[长时间构建期间结构变化]** → 全程固定 revision，激活前复验；过期 generation 不切换并基于最新 revision 重试。
- **[消费面遗漏 generation 过滤]** → 建立统一 active-generation query service，并以契约测试覆盖列表、检索、图谱、导出、概览和 Agent 工具。
- **[目录树循环和跨库 FK 无法只靠普通 FK 保证]** → 领域服务、事务锁和模型/接口测试共同保证；数据库约束负责可表达的唯一/非空条件。
- **[大 KB 结构保存和计数代价]** → 保存完整树但只在短事务写 diff；计数按目录/子树批量查询或异步物化，避免 N+1。
- **[导入 ZIP 引入路径与资源攻击]** → 所有路径在解压前规范化，使用大小/数量/深度配额和同库授权，预检查与执行使用同一输入 hash。
- **[现有 pytest 后台线程不退出]** → 当前基线的 12 个 Wiki 测试均显示 PASSED，但进程超时未退出；实施计划单列测试进程退出诊断，避免把断言结果与 runner 生命周期混为一谈。
- **[与知识决策 change 并行修改相同服务]** → 先以 `KnowledgeCandidateAdapter` 隔离接口；相邻 change 可用时适配，不可用时本 change 提供最小候选实现。合并时以契约测试保护“只有正文/身份歧义需要决策”。

## Migration Plan

1. 在独立 worktree 完成模型/迁移和纯领域测试，所有新字段保持 nullable/兼容读取。
2. 引入目录/结构服务、统一页面身份/归类服务和 active-generation query service；先迁移所有生产写入与消费读取路径。
3. 实现幂等 bootstrap/backfill/preflight 命令和按 KB 写入围栏，使用 `opspilot` 数据库做迁移 dry-run，确认不会修改正文、版本、证据、Chunk 或向量，也不会在 backfill 后产生新的 generation 外写入。
4. 实现普通构建、资料更新、导入和重建 staging generation；接入关系/图谱和关键词消费面后再开放 activation。
5. 实现目录 API、导入导出和 Web 目录树/结构编辑；目录功能默认关闭。
6. 选择测试 KB 完成结构初始化、存量自动归类和浏览器真实点击验收。
7. 按 KB 灰度启用，监控 null directory、待归类比例、未知 key、generation failure/superseded、409 和消费面 generation 不一致。
8. 全部 KB 通过 readiness 后增加非空与标题唯一约束；保留旧平面读取一个发布周期。
9. 回滚应用时关闭目录 UI/新任务入口并保留新表；应用回退只关闭新入口并保留数据；业务回退从上一成功快照创建新 rollback_of generation，结构按需从旧快照生成新 revision，不执行破坏性 down migration。

## Open Questions

无阻塞问题。目录级 ACL、一个页面多个主目录、从第三方 ZIP 自动推断新 Schema、copy-on-write generation、向量目录权重和自动化浏览器 CI 均留作独立后续 change。
