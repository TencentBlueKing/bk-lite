## ADDED Requirements

### Requirement: 每次构建固定结构与管线身份
普通构建、资料更新、导入和全量重建 MUST 在开始时固定 `base_generation_id`、`structure_revision_id`、结构指纹和 `pipeline_version`，并在生成、目录校验、页面和解、WikiLink/关系生成与激活阶段使用同一组身份。

#### Scenario: 构建期间结构未变化
- **WHEN** 构建完成时知识库 active structure revision 仍等于构建固定的 revision
- **THEN** 系统 MUST 允许 generation 进入一致性校验与激活阶段

#### Scenario: 构建期间结构变化
- **WHEN** 构建完成前管理员激活了更新的 structure revision
- **THEN** 当前 generation MUST 标记为 `superseded` 且不得激活
- **AND** 系统 MUST 基于最新 revision 安排新的构建或给出明确重试入口

#### Scenario: 构建期间出现人工或结构变更
- **WHEN** 构建固定 base generation 后，页面移动、正文编辑、逻辑归档或结构保存激活了新的 governance generation
- **THEN** 旧候选 MUST 因 `active_generation_id != base_generation_id` 标记为 `superseded` 且不得覆盖新状态
- **AND** 重试或 rebase MUST 从最新 active generation 重新开始并保留已生效的人工变化

#### Scenario: 两个候选从同一 base generation 构建
- **WHEN** 第一个候选成功激活后第二个候选才尝试激活
- **THEN** 第二个候选 MUST 在知识库行锁内 CAS 失败并标记为 `superseded`

### Requirement: 构建结果先写入 staging generation
系统 MUST 使用 `WikiGeneration` 和完整的 `WikiGenerationPage` 成员快照保存候选页面、版本、目录、目录归类模式、页面状态、目录显示快照和消费所需的可变页面元数据，并按 generation 隔离候选 `PageRelation`。WikiLink MUST 以不可变 PageVersion 为来源，任何物化 WikiLink/反向链接索引 MUST 同样按 generation 隔离。生成期间不能逐页修改 active knowledge 消费面。

#### Scenario: 构建生成多个页面
- **WHEN** LLM 已生成部分页面但其他资料仍在处理
- **THEN** 已生成页面和关系 MUST 仅存在于 preparing generation
- **AND** 页面列表、关键词检索和图谱 MUST 继续读取当前 active generation

#### Scenario: generation 包含未变化页面
- **WHEN** 某些 manual 或 human 页面本次没有正文变化
- **THEN** 候选 generation MUST 仍包含这些页面的成员快照，以形成完整知识集合

### Requirement: generation 激活是原子一致切换
系统 MUST 在激活前验证标题、目录、页面成员、当前版本、WikiLink/引用和关系一致性，并在知识库行锁内确认 `active_generation_id == base_generation_id` 及结构 revision 未过期，再在短事务内切换 `active_generation_id` 及必要的兼容指针。页面列表、关键词消费面和关系图谱 MUST 不可观察到不同 generation 的混合状态。

#### Scenario: 激活成功
- **WHEN** ready generation 通过完整校验且结构 revision 未过期
- **THEN** 系统 MUST 原子激活新 generation、把前一 generation 标记为 superseded，并使页面、关键词与图谱同时读取新快照

#### Scenario: 激活校验失败
- **WHEN** generation 存在重复标题、未知目录、缺失当前版本、跨知识库关系或不完整页面成员
- **THEN** 系统 MUST 将 generation 标记为 failed 并保持旧 active generation 完全不变

### Requirement: 非向量消费面统一读取 active generation
页面列表与详情、关键词检索、Agent 上下文、关系查询、图谱、概览统计和导出 MUST 通过统一的 active-generation 查询服务读取页面成员、版本、目录和状态，不得混用 `KnowledgePage` 的遗留 current/status 字段与 generation 快照。

#### Scenario: active generation 已切换
- **WHEN** 任一非向量消费面在新 generation 激活后发起查询
- **THEN** 它 MUST 只返回新 active generation 中的成员与关系
- **AND** 不得返回仅存在于旧 generation 的页面或旧兼容指针数据

### Requirement: 所有已激活 generation 都是不可变快照
页面创建、改名、人工移动、恢复自动归类、正文编辑、逻辑归档和结构保存 MUST 基于当前 active generation 创建轻量 governance generation，并通过同一 CAS/校验流程激活；系统 MUST 不原地修改已激活 generation 成员或 generation 范围的关系/索引。仅目录变化 MAY 复用不可变页面版本和未受影响关系。

#### Scenario: 管理员移动当前页面
- **WHEN** 管理员把 active generation 中的页面移动到另一个目录
- **THEN** 系统 MUST 创建以当前 generation 为 base 的治理 generation，更新新成员的目录与 `manual` 模式并原子激活
- **AND** 原 active generation MUST 冻结为 superseded，后续回退仍可恢复其目录与归类模式

#### Scenario: 管理员编辑正文
- **WHEN** 人工正文编辑会改变当前页面版本
- **THEN** 系统 MUST 在轻量 generation 中先准备新 PageVersion、WikiLink/反向链接、关键词元数据和受影响关系，再原子切换消费面
- **AND** 查询不得观察到新正文配旧关系或旧关键词的混合状态

#### Scenario: 管理员逻辑归档页面
- **WHEN** 页面从当前知识集合移除
- **THEN** 新 governance generation MUST 同时排除该成员及其 active 关系/反向链接/计数/关键词可见性，旧 generation 保持可回退

### Requirement: 页面身份按知识库全局标题原地和解
全量重建 MUST 在包括归档页在内的同知识库页面集合中按规范标题寻找身份，并在身份唯一时复用页面 ID。目录不是页面 identity，结构变化不得通过创建新路径页面替代旧页面。

#### Scenario: 更新已有 AI 页面
- **WHEN** 新结果唯一命中已有 AI 页面标题
- **THEN** 系统 MUST 为原页面创建候选版本并在 generation 中引用原页面 ID

#### Scenario: 恢复归档 AI 页面
- **WHEN** 新结果唯一命中同标题归档页面
- **THEN** 系统 MUST 在候选 generation 中恢复该页面，而不是新建同标题页面

#### Scenario: 新标题页面
- **WHEN** 新结果未命中任何现有或归档标题
- **THEN** 系统 MUST 创建 staging 页面身份，并仅在 generation 激活后进入活动消费面

#### Scenario: 身份歧义
- **WHEN** 并发异常导致同一标题无法唯一确定页面身份
- **THEN** 系统 MUST 阻止 generation 激活并创建页面身份冲突记录

### Requirement: 单资料构建生成稳定主题页
通用知识库的单资料构建 MUST 按固定 Structure Revision 生成 `entity`、`concept`、`source`、`query`、`comparison` 与 `synthesis` 类型中的有证据页面，并 MUST 将解析 Chunk 仅作为证据而非页面边界。系统 MUST NOT 生成普通 `index`、`overview` 或 `log` 页面；这些内容 MUST 由同一 Generation 的导航数据派生。

#### Scenario: 一份资料生成多个稳定主题
- **WHEN** 一份资料同时描述多个平台组件、架构关系和运维机制
- **THEN** 系统 MUST 按独立实体和可复用概念生成多页知识，并用 WikiLink、PageRelation 和 PageEvidence 建立关系与来源
- **AND** 系统 MUST NOT 按解析 Chunk 数量机械生成页面

#### Scenario: 每份资料只有一个来源摘要
- **WHEN** 固定 revision 允许 `source` 类型且当前资料产生有效主题页面
- **THEN** 系统 MUST 生成且只生成一个绑定该 Material 的来源摘要页
- **AND** 同一资料重建 MUST 通过 PageEvidence 复用既有来源页面身份；缺失模型 source 输出时 MAY 确定性生成来源导航而不得追加 LLM 调用

#### Scenario: 证据不足的可选类型
- **WHEN** 资料没有明确未解决问题、共同对比维度或跨主题综合结论
- **THEN** query、comparison 或 synthesis 目录 MAY 为空
- **AND** 系统 MUST NOT 为填满目录而编造页面

#### Scenario: 文件未生成有效知识
- **WHEN** 非空资料的最终结构化输出无有效页面、页面正文为空或 JSON 无法解析
- **THEN** 该文件的构建 MUST 失败并保留解析阶段诊断
- **AND** 其他资料的独立构建终态 MUST 不受影响

### Requirement: 重建保留人工目录和人工正文边界
全量重建 MUST 保留 manual 页面目录。AI 页面可以自动更新；human/mixed 页面正文不能被自动覆盖，只有内容冲突时创建候选。未被新 generation 匹配的旧 AI 页面只能在新 generation 成功激活时归档。

#### Scenario: 未匹配旧 AI 页面
- **WHEN** staging 生成与校验完成但尚未激活
- **THEN** 系统 MUST 保持旧 AI 页面在 active generation 中可见
- **AND** 仅在新 generation 激活事务中将其从新成员集合排除或标记归档

#### Scenario: human 页面仅目录可自动确定
- **WHEN** human 页面正文不变但 auto 目录可按新结构重新确定
- **THEN** 系统 MAY 在候选 generation 中更新目录，但 MUST 不创建新正文版本

### Requirement: 新知识与确定性更新不需要构建审批
ready generation MUST 在系统校验通过后自动激活，不得等待管理员逐页批准或构建级审批。非阻塞内容候选不得阻止其余一致页面进入新 generation。

#### Scenario: generation 含一个人工冲突候选
- **WHEN** 构建产生十个可确定页面和一个 human/mixed 正文冲突
- **THEN** 十个可确定页面 MUST 可随 generation 自动激活
- **AND** 冲突页面 MUST 保持当前版本并单独保存候选

### Requirement: generation 失败与回退具有完整前态
系统 MUST 保留至少最近两个成功 generation，并 MUST 能在不重新调用 LLM 的情况下基于目标快照创建新的 `rollback_of` generation；不得直接重新激活或改写已冻结 generation。回退预检 MUST 校验目标 generation 的 structure revision 与当前目录兼容性；不兼容时只能在显式确认后从旧结构快照创建新的递增 structure revision，并通过请求携带且锁内复验的 `structure_version` 与 `base_generation_id` 双 CAS 将该 revision 与 rollback generation 原子激活，否则返回 409 并回滚同一事务的全部联动恢复写入。取消或失败不能通过删除“本次触及页面”模拟回滚。

#### Scenario: 切换后业务回退
- **WHEN** 管理员触发回退到仍在保留期内且与当前结构兼容的成功 generation
- **THEN** 系统 MUST 创建并原子激活新的 rollback generation，复制目标成员、版本、目录、WikiLink/关系快照并记录 `rollback_of` 与操作审计
- **AND** 被选作来源的历史 generation MUST 保持冻结

#### Scenario: 目标 generation 使用已合并或退役目录
- **WHEN** 回退预检发现目标快照不能由当前 active structure 完整表示
- **THEN** 系统 MUST 返回结构差异并要求显式联动结构恢复，或阻止执行
- **AND** 联动恢复 MUST 从旧快照创建新的递增 revision，不能重新激活旧 revision 行
- **AND** 执行请求 MUST 携带 `structure_version` 与 `base_generation_id`，服务端 MUST 在知识库锁内复验并仅在双 CAS 成功时原子激活新 revision 与 rollback generation；任一冲突 MUST 返回 409、回滚全部联动恢复写入且不保留孤儿对象或审计

#### Scenario: preparing generation 被取消
- **WHEN** 用户取消尚未激活的 generation
- **THEN** 系统 MUST 标记其取消并清理仅由其拥有的 staging 数据
- **AND** 不能删除或覆盖 active generation 中已存在的页面

#### Scenario: 并发 generation 产生同一新标题
- **WHEN** 两个 preparing generation 通过统一身份服务命中同一 staging 页面身份
- **THEN** 每个 generation MUST 拥有独立 PageVersion/成员引用，页面身份 MAY 共享但不得提前进入 active 消费面
- **AND** 取消或清理一个 generation 时，只有在页面身份未被 active/retained generation、其他 staging 版本或候选引用时才能物理删除

#### Scenario: 页面仍被保留 generation 引用
- **WHEN** 管理员从当前 generation 删除或归档一个仍被历史保留 generation 引用的页面
- **THEN** 系统 MUST 仅执行逻辑归档或从当前成员集合移除
- **AND** 不得物理删除页面身份、版本或历史成员，使后续 generation 回退仍能恢复原页面 ID

### Requirement: BuildRecord 提供 generation 可观测性
构建记录 MUST 保存 generation ID、base generation ID、固定 structure revision、结构指纹、pipeline version、页面 create/update/restore/archive/unchanged/candidate 动作、目录 fallback 原因、CAS/superseded 原因、rollback_of 和激活结果。

#### Scenario: 查询成功重建记录
- **WHEN** 用户查看已完成的全量重建
- **THEN** API MUST 返回从输入 revision 到 active generation 的可追踪链路和各类页面计数

#### Scenario: 查询过期 generation
- **WHEN** generation 因结构 revision 变化未激活
- **THEN** 构建记录 MUST 明确返回 superseded 原因和最新 revision，而不是报告普通成功

### Requirement: 缺少 Generation 身份的任务不得激活
任何构建任务 MUST 固定 base Generation、Structure Revision 和 pipeline version。缺少任一身份或激活前身份已变化的任务 MUST 不得写入活动消费面。

#### Scenario: 无固定 base 的任务尝试激活
- **WHEN** 构建任务没有 base generation、structure revision 或 pipeline version
- **THEN** 系统 MUST 拒绝激活并记录无效任务身份
- **AND** 当前 active Generation MUST 保持不变

### Requirement: 向量能力不属于新 generation 范围
本变更 MUST 不新增、清理、重建或切换 PageVersion embedding、PageChunk embedding、语义检索、混合检索和向量 UI。既有向量字段和服务 MUST 保持当前行为，且不得成为目录功能验收门槛。

#### Scenario: 目录重建完成
- **WHEN** 页面、关键词消费面和图谱 generation 成功激活
- **THEN** 系统 MUST 不因本变更触发全量向量重建或清空现有向量存储
