## Context

`add-opspilot-wiki-directory-governance` 已将页面集合、目录与关系纳入 Generation，但目录本身还不是查询导航器。参考 `llm_wiki` 的 Index/Overview 思想时，OpsPilot 必须保留数据库 Generation 原子性，不能再增加独立 `active_manifest` 或物理文件真相。

## Goals / Non-Goals

**Goals:**

- 以紧凑 Index 限定候选，再加载真实 PageVersion/Evidence。
- 以根/目录 Overview 改善低置信度与跨目录问题的语义路由。
- 让新文件冲突候选召回不随旧页面数量线性增加 LLM 消耗。
- 保证页面、Index、Overview、关系和引用来自同一 Generation。
- 导出与 `llm_wiki` 相近的 Markdown 导航文件。

**Non-Goals:**

- 不修改向量检索、embedding 或 RRF。
- 不让 Overview 或 Index 成为事实证据。
- 不改变 `streamline-wiki-knowledge-decisions` 的真实冲突决策语义。
- 不为本地测试旧数据回填导航产物。
- 不实现预算 Profile；预算由独立 change 管理。

## Decisions

### 1. Generation 是唯一知识内容发布边界

Index、确定性 Overview 和关系必须在 staging Generation 内完成并通过一致性校验后一起激活。语义 Overview 是绑定 Generation 与内容指纹的派生缓存，不修改已激活 Generation 的正式快照。`active_structure_revision` 继续作为独立结构配置指针；结构变更必须原子切换兼容的 Structure Revision 与 Generation。“唯一”只禁止新增 `active_manifest` 等第二套知识内容活动指针。

### 2. Index 逐页面结构化存储

每条 Entry 绑定 generation/page/page_version，并保存标题、别名、类型、标签、目录、标题层级、关键词、摘要和内容指纹。数据库可以直接筛选和排序；`index.md` 仅由 Entry 确定性渲染。

### 3. Overview 使用确定性保底与语义增强

确定性根/目录 Overview 是正式 Generation 产物，生成后语义状态默认为 `skipped`，表示确定性内容已可用但没有消耗 LLM。只有资料自己的剩余预算实际执行语义增强后，状态才变为 `ready` 或 `degraded`；全量重建、人工治理、导入和结构调整不得额外创建全库预算。语义增强最多调用一次 LLM，输入 Purpose、结构和有界 Index 摘要；只生成路由背景。未知页面/目录、格式错误或 stale Generation 使语义结果失效，查询继续使用确定性版本。

### 4. 查询使用级联而非固定 LLM 路由

精确标题/别名和高置信度 Index 结果直接进入证据读取。只有低置信度或跨目录问题调用一次 Overview 路由。回答阶段始终加载真实页面证据，并围绕命中位置生成 snippet。 现有 PageChunk/向量链尚未绑定 Generation，因此 Generation truth 知识库对 `chunk` 模式必须 fail closed 并返回明确错误，不能静默读取旧 Chunk 或在召回后过滤。

### 5. 冲突候选发现与事实判断分离

Index 最多返回 20 个紧凑候选，不调用 LLM。服务端只能确定性排除硬身份无关、完全相同，或限定词、作用域、时间和证据语义一致的可证明结构化等价/包含；任何不确定的 supplement/conflict 都进入证据比较。最多加载 5 个旧页面、8,000 token 证据，并在一次 LLM 请求中批量比较。最终 conflict/supplement 仍由真实 PageVersion/Evidence 支撑。

### 6. 缓存必须 Generation scoped

缓存 key 包含 Generation、规范化查询或新知识指纹、目录范围、候选页面版本和算法版本。Generation 切换后旧缓存不再命中。最终回答默认不缓存。

### 7. Markdown 是派生视图

原生导出生成 `index.md`、`overview.md` 和目录 Overview；导入时按 manifest/key 恢复结构。运行时查询只读数据库 active Generation。

## Risks / Trade-offs

- [确定性 Overview 语义较弱] → 异步语义增强；失败时保留确定性可用性。
- [LLM Overview 可能幻觉] → 只允许引用同代目录/页面，且不得作为最终证据。
- [候选上限可能漏掉弱相关冲突] → 记录溢出诊断并以 Recall@20 评测校准 Index。
- [新增结构化表增加发布成本] → 批量生成、索引数据库字段，并将 P95 纳入门禁。
- [页面摘要不可靠] → 摘要仅用于召回，判断必须回读正文和证据。

## Migration Plan

现有数据均为本地测试数据。模型冻结后保留 0066 及以前 migration，删除其后未发布 migration，清空数据库并基于 Directory Governance、Change A、Change B 的最终模型重新生成连续 migration；不实现 backfill 或双读。

## Open Questions

无。预算数值与超限行为由 `add-opspilot-wiki-minimal-context-budget` 定义。
