## ADDED Requirements

### Requirement: Generation 必须原子发布导航产物

系统 MUST 将页面成员、关系、结构化 Index Entry 和确定性根/目录 Overview 绑定到同一个 Generation，并在一致性校验通过后通过现有 Generation CAS 一起激活；系统 MUST NOT 新增独立 active manifest 或第二套知识内容活动指针。`active_structure_revision` 继续作为结构配置指针；结构变更 MUST 在同一事务中激活相互兼容的 Structure Revision 与 Generation。

#### Scenario: 新 Generation 导航产物完整
- **WHEN** staging Generation 的页面、关系、Index 和确定性 Overview 均构建成功且 active base 未变化
- **THEN** 系统 MUST 原子激活该 Generation
- **AND** 后续查询 MUST 只读取该 Generation 的页面与导航产物

#### Scenario: Index 或确定性 Overview 构建失败
- **WHEN** staging Generation 缺少任一活动页面的 Index Entry 或必需 Overview
- **THEN** 系统 MUST 拒绝激活
- **AND** 当前 active Generation MUST 保持不变

### Requirement: Index 必须逐页面结构化并可确定性渲染

每个活动页面版本 MUST 具有一个同代 Index Entry，至少包含页面/版本身份、标题及规范标题、别名、类型、标签、目录身份及面包屑、标题层级、关键词、摘要和内容指纹。系统 MUST 从这些条目稳定渲染 `index.md`，不得以单个大 JSON 或磁盘 Markdown 作为运行时查询真相。

#### Scenario: 重复构建相同页面集合
- **WHEN** 页面版本、目录和渲染算法均未变化
- **THEN** 系统 MUST 生成相同排序、相同条目指纹和相同 `index.md`

#### Scenario: LLM 摘要字段非法
- **WHEN** 页面生成结果缺少或返回超限 summary、keywords 或 entities
- **THEN** 系统 MUST 使用标题、标签、标题层级和首个有效段落确定性降级
- **AND** Generation MUST NOT 因可降级字段失败而丢失页面

### Requirement: Overview 必须同时提供确定性保底和受控语义增强

系统 MUST 为根和每个活动目录生成确定性 Overview。系统 MAY 使用最多一次 LLM 调用生成绑定 Generation 与内容指纹的语义增强 Overview，但该结果 MUST 经过同代目录/页面引用校验，且失败不得阻止 Generation 激活。

#### Scenario: 语义 Overview 尚未完成
- **WHEN** Generation 已激活但语义增强仍在运行
- **THEN** 查询 MUST 使用确定性 Overview
- **AND** 页面、Index 与关系 MUST 正常可用

#### Scenario: 语义 Overview 引用未知页面
- **WHEN** LLM 输出的页面或目录不能在目标 Generation 中解析
- **THEN** 系统 MUST 丢弃该语义结果并记录 degraded
- **AND** 查询 MUST 继续使用确定性 Overview

### Requirement: 问答必须使用有界查询级联

系统 MUST 先执行标题/别名精确匹配和 Index 评分。高置信度结果 MUST 直接加载真实证据；只有低置信度或跨目录问题才能调用一次 Overview 路由。最终回答 MUST 读取真实 PageVersion/Evidence，且路由失败不得触发第三次 LLM 调用。 Generation truth 知识库不得读取未按 Generation 隔离的 PageChunk/向量结果；调用方请求该模式时 MUST fail closed 并返回明确的受控错误。

#### Scenario: 精确标题命中
- **WHEN** 当前 active Generation 存在唯一标题或别名精确命中
- **THEN** 系统 MUST 不调用 Overview 路由 LLM
- **AND** 必须直接加载该页面真实证据供回答

#### Scenario: 跨目录低置信度问题
- **WHEN** Index 无高置信度结果且问题涉及多个目录
- **THEN** 系统 MAY 调用一次 Overview 路由
- **AND** 路由失败 MUST 回退全库 Index，而不是再次调用路由模型

### Requirement: 查询片段和引用必须来自真实命中证据

系统 MUST 围绕实际命中位置生成有界 snippet，并分别返回目录 breadcrumb 与正文 heading path。Index 和 Overview 只能解释路由，不能作为最终事实引用。

#### Scenario: 命中发生在正文后半部分
- **WHEN** 查询词只出现在页面后半部分
- **THEN** 返回 snippet MUST 覆盖该命中位置
- **AND** 系统 MUST NOT 固定返回正文开头片段

#### Scenario: 回答产生引用
- **WHEN** LLM 使用检索知识回答
- **THEN** 引用 MUST 指向同代 PageVersion 或来源 Evidence
- **AND** MUST NOT 只引用 Index 或 Overview

### Requirement: 导航缓存不得跨 Generation 命中

Index 路由、Overview 路由和证据装配缓存 MUST 包含 Generation、目录范围、规范化查询、候选版本和算法版本；Generation 切换后旧缓存 MUST 不再服务新查询。

#### Scenario: 查询期间 Generation 切换
- **WHEN** 查询候选基于旧 Generation 生成而激活指针已变化
- **THEN** 系统 MUST 放弃旧候选或以新 Generation 重试
- **AND** 响应 MUST NOT 混合两代页面、Overview 或关系

### Requirement: 原生导出必须包含导航 Markdown

系统 MUST 从目标 Generation 的结构化数据渲染根 `index.md`、根 `overview.md` 和目录 Overview，并与 manifest、structure 和页面一起导出。运行时查询 MUST NOT 依赖这些磁盘文件。

#### Scenario: 导出活动 Generation
- **WHEN** 管理员导出知识库
- **THEN** 所有导航文件与页面 MUST 来自同一 Generation
- **AND** manifest MUST 记录 Generation、结构 revision 和内容 hash
### Requirement: Index 路由和上下文装配必须满足性能门禁

系统 MUST 在固定 1,000 个活动页面的标注基准库上满足：Index 路由 P95 不超过 500ms，非 LLM 检索与上下文装配端到端 P95 不超过 1s。基准 MUST 使用真实数据库查询、预热后的应用进程、固定算法版本和至少 30 个查询样本，并记录每次耗时与 P95。

#### Scenario: 运行 1,000 页面性能基准
- **WHEN** 使用固定 Generation、固定目录结构和至少 30 个基准问题执行查询
- **THEN** Index 路由 P95 MUST 小于或等于 500ms
- **AND** 非 LLM 检索与上下文装配 P95 MUST 小于或等于 1s
- **AND** 旧知识页面总数增加时 LLM 调用次数 MUST NOT 线性增长

### Requirement: 导航召回和证据引用必须满足质量门禁

系统 MUST 使用固定、版本化、带人工标签的问答与冲突候选数据集评测导航质量。正常问答 Recall@5 MUST 不低于 90%，冲突候选 Recall@20 MUST 不低于 97%，最终引用证据正确率 MUST 不低于 95%。评测 MUST 固定 Generation、检索算法版本、随机种子和期望页面/证据标签，并作为发布门禁保存结果。

#### Scenario: 运行版本化质量评测
- **WHEN** 对固定标注数据集执行正常问答召回、冲突候选召回和引用核验
- **THEN** 正常问答 Recall@5 MUST 大于或等于 90%
- **AND** 冲突候选 Recall@20 MUST 大于或等于 97%
- **AND** 引用证据正确率 MUST 大于或等于 95%
- **AND** 页面、Index、Overview、关系和引用的跨 Generation 混读次数 MUST 为 0
