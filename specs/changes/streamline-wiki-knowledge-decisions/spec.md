# Streamline Wiki Knowledge Decisions

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/streamline-wiki-knowledge-decisions/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

OpsPilot Wiki 目前把候选采纳、重复页面、资料失效、Schema 变化和图谱维护混在同一套“接受/拒绝”检查项中，用户既难以理解决策含义，也会在相同资料重新构建或知识库重建后重复处理同一冲突。需要将人工审批收敛为真正需要业务判断的知识结果决策，并让系统安全复用已经确认过的结果。

## What Changes

- 将用户需要处理的决策收敛为两类：知识冲突决策（`cannot_merge`、`material_update`）和页面合并决策（`duplicate`、`conflict`）；数据库只允许这四种检查类型保持 `open`。
- 知识冲突提供“保留当前知识”“使用新知识”“编辑后采用”三个语义明确的结果；页面合并提供“保持独立”“确认合并”两个结果。
- 取消新知识准入审批；新知识按构建规则直接进入知识库并执行关系、图谱和索引维护。
- 资料物理删除、资料重新构建、知识库整体重建产生的确定性失效和结构维护由系统自动处理，不再生成无法改变结果的失效审批。
- 健康诊断、图谱洞察和确定性失效仍可保存为 `auto_resolved` 审计记录，但不得进入用户待决策列表，也不得携带接受、拒绝或忽略动作。
- 上线迁移自动关闭历史非决策 `open` 检查；旧 `qa_answer_candidate` 候选自动成为当前知识，落实“新知识直接准入”。
- 新增可撤销的历史决策回放能力：相同知识主题和相同资料来源版本集合再次产生冲突时，系统自动复用已确认结果，不重复创建审批项。
- 页面合并决策按稳定知识身份记录：再次发现同一页面身份组合时自动执行既有“合并”或“保持独立”结果，不依赖可能随重建变化的页面 ID。
- 决策命中、失效和自动回放必须写入构建追踪或变更记录，保证自动维护可解释、可审计。
- 仅对来源和版本上下文完整、能够生成稳定决策签名的冲突自动回放；来源不完整、来源集合发生变化或人工结果已被后续修改时重新进入人工决策。
- 用户提交决策时重新校验实时 Schema、页面版本和完整来源集合；失效检查自动关闭且不修改知识，后续构建或扫描生成新的决策上下文。相同资料内容 hash 未变时，单纯版本记录 ID 变化不使决策失效。
- 生产 API 仅保留语义化 `decide` 和规则撤销；旧通用单条及批量处理接口返回 410，检查项集合禁止人工创建、更新和删除。
- 所有 Wiki 决策、资料、页面和维护入口统一执行团队/知识库隔离。删除和重建先提交核心数据，再执行可观测、可重试的派生维护；维护失败不得回滚已提交知识或创建新审批。

## Capabilities

### New Capabilities

- `wiki-decision-governance`: 定义 OpsPilot Wiki 哪些知识变化需要用户决策、各类决策的业务动作，以及删除和重建等确定性维护的自动处理规则。
- `wiki-decision-replay`: 定义知识冲突和页面身份决策的稳定签名、持久化、自动回放、失效、撤销与可观测性行为。

### Modified Capabilities

- 无。

## Impact

- 后端：新增决策规则持久化模型、统一决策服务、实时上下文校验、团队隔离和提交后维护重试，并接入资料构建、资料更新、知识库重建、检查扫描、页面恢复及删除生命周期。
- 数据：决策匹配使用跨数据库可索引的稳定签名；`0065_close_non_decision_checks` 关闭历史非决策待办、自动准入旧 QA 候选并增加“open 仅限四类决策”的数据库约束。历史决策不做推测性规则回填。
- API：检查项处理接收明确的业务决策动作和“编辑后采用”的正文结果，并返回决策与回放信息；旧通用处理接口以 410 明确停用，跨团队访问以 403 拒绝。
- Web：将生产检查页收敛为已确认的决策中心交互，复用 Storybook 视觉方案，并补充历史决策复用和撤销提示。
- 测试：覆盖普通构建、资料更新、全库重建、并发去重、多来源、页面合并、物理删除、归档恢复、团队隔离、维护重试以及决策失效边界。
- 依赖：不引入新的外部运行时依赖；继续使用 Django ORM、现有 JSONField、构建记录和操作日志能力。

## Implementation Decisions

## Context

OpsPilot Wiki 当前使用 `CheckItem` 同时承载候选版本审批、页面重复检查、来源失效、Schema 变化和图谱健康提示。普通资料构建、资料更新、知识库重建和健康扫描分别创建检查项，只有“同一 open 检查仍存在”这一层去重；检查被处理后，同一输入再次经过其他入口仍会重新生成检查项。

现有数据也不足以直接回放历史结果：候选检查只保存新资料 ID，没有冻结当前知识的完整来源集合、资料内容版本或稳定知识标识；拒绝会删除候选版本；接受只切换 `PageVersion`，没有把新资料版本补入 `PageEvidence`。页面合并记录依赖页面 ID，而 AI 页面在重建中可能被归档并重新生成。

系统约束如下：

- 后端使用 Django ORM，必须兼容仓库支持的多种数据库，不使用原生 SQL、方言专属 JSON 索引或条件唯一约束。
- 资料和知识页面支持物理删除；页面合并使用可恢复归档。
- `CheckItem` 继续作为待办与处理流水，`BuildRecord` 和操作日志继续作为构建及用户操作审计入口。
- Storybook 已确认决策中心视觉结构，但生产 Web 仍使用通用检查表格和接受/拒绝动作。

## Goals / Non-Goals

**Goals:**

- 只让用户处理知识结果无法由系统确定的知识冲突和页面身份合并。
- 为同一知识主题、同一完整资料来源版本集合生成稳定且与“当前/新”位置无关的决策签名。
- 在普通构建、资料更新、全库重建和页面扫描中统一查询、执行或创建决策。
- 支持多来源知识、决策撤销、物理删除、归档恢复和并发任务。
- 保证自动回放不会覆盖审批后发生的人工修改，并能够说明复用了哪次决策。
- 将已确认的 Storybook 交互落到生产页面和语义化 API。
- 用数据库约束保证只有 `cannot_merge`、`material_update`、`duplicate`、`conflict` 可以保持 `open`，其余检查只能作为自动审计记录。
- 对决策、资料、页面和维护 API 统一执行团队/知识库隔离。
- 删除和重建在核心事务提交后运行派生维护，失败可观测、可选择阶段重试，且不回滚已提交知识。

**Non-Goals:**

- 本变更不新增向量召回或通用语义相似度服务；AI 资料之间的事实冲突仅在现有 Stage2 页面生成链路中识别。
- 本变更不对来源不完整的历史 `CheckItem` 做推测性决策回填。
- 本变更不建设独立的规则管理后台；撤销入口放在已处理决策或变更记录中。
- 除为 Stage2 增加现有页面候选清单与事实冲突判定外，本变更不改变资料解析、向量索引或图谱分析算法。

## Decisions

### 1. 将待办流水与可执行决策规则分离

新增 `WikiDecisionRule`，用于保存当前有效、可以自动执行的业务规则；`CheckItem` 继续保存一次人工决策的输入、状态和处理流水。规则至少包含：

- `knowledge_base`
- `decision_type`: `knowledge_conflict` 或 `page_identity`
- `decision_key`: 规范化匹配上下文的 SHA-256
- `subject_key`: 可诊断的稳定知识标识
- `action`: `keep_current`、`use_new`、`edit_accept`、`merge` 或 `keep_separate`
- `match_snapshot`: 来源集合、Schema 指纹、页面身份和输入指纹
- `result_snapshot`: 胜出来源、最终正文指纹、合并目标及被归档身份
- `source_check`、`result_page`、`result_version`
- `status`: `active` 或 `revoked`
- `replay_count`、`last_replayed_at` 和维护者时间字段

`knowledge_base + decision_type + decision_key` 使用普通唯一约束。相同签名重新决策时更新同一规则，审批历史仍由多个 `CheckItem` 和操作日志保留。

同时给决策型 `CheckItem` 保存可索引的 `decision_key` 与完整 `decision_context`。创建候选时先锁定目标页面并检查同签名 open 项，避免 Celery 重复投递生成多条待决策。

`CheckItem.status="open"` 是受数据库保护的业务不变量：知识冲突映射 `cannot_merge/material_update`，页面身份映射 `duplicate/conflict`。诊断与确定性失效统一保存为 `auto_resolved`，不提供人工动作。
`0065_close_non_decision_checks` 先关闭历史非决策待办并自动准入旧 `qa_answer_candidate`，再增加约束，避免部署窗口继续产生模糊审批。

**替代方案：复用 `CheckItem.related`。** 不采用，因为 `related.pages` 会在页面删除清扫时被改写，拒绝会删除候选版本，且 JSON 查询无法提供稳定的跨数据库唯一约束。检查流水也不应直接成为长期自动执行规则。

### 2. 知识冲突签名使用完整来源集合而不是固定资料对

知识冲突匹配上下文规范化为：

```text
policy_version
+ knowledge_base_id
+ decision_type
+ subject_key(canonical title key + page type)
+ schema_fingerprint(schema_md + generation_rules)
+ sorted distinct participants[
     material_id + material_content_hash
   ]
```

当前页面的全部 `PageEvidence` 与本次传入资料共同组成参与者集合；同一资料重复出现时去重。`MaterialVersion.id`、locator 和候选正文指纹保存在快照中用于审计，但不作为主匹配键：相同资料可能产生新的版本记录 ID，LLM 也可能产生非确定性的措辞变化。

用户结果不保存成相对位置含义。规则必须保存胜出资料身份和最终 `PageVersion`/正文指纹，从而在 A、B 的“当前/新”角色反转后仍执行同一个业务结果。

来源为空、资料 `content_hash` 为空或上下文无法完整冻结时，不创建可回放规则；检查项仍可人工处理，但后续同类输入继续人工决策。

提交人工决策时重新锁定并校验页面当前版本、候选正文、Schema 和实时参与者集合。参与者有效身份只比较 `material_id + content_hash`；相同 hash 的新版本记录 ID 不使检查失效。真正变化时系统自动关闭旧检查、保持知识不变，并由后续构建或扫描生成新上下文。

### 3. 回放保留已审批结果，不重新采纳波动的候选正文

统一决策服务返回三种结果：

- `replayed`: 命中有效规则且当前页面仍满足结果前置条件；保持或恢复已审批结果，不创建 `CheckItem`。
- `pending`: 未命中、规则已失效或当前结果被后续修改；创建一条语义化待决策。
- `unchanged`: 候选正文与当前正文相同，无需决策也无需规则。

知识冲突回放除签名相同外，还必须验证当前页面正文指纹与规则保存的最终结果一致。若审批后发生人工编辑、版本恢复或新的来源合入，系统不得用旧规则覆盖当前内容，而是重新进入人工决策。

“使用新知识”或“编辑后采用”完成时，系统必须把新资料及其当前版本写入 `PageEvidence`；“保留当前知识”不把被拒绝资料标记为当前知识来源。这样下一次构建能够从真实证据重建相同参与者集合。

### 4. 页面合并使用稳定页面身份对

页面身份由规范标题 key、原始紧凑标题 key 和页面类型组成；页面身份对排序后生成 `page_identity` 决策签名。页面 ID 仅作为审计引用，不参与主匹配。

- `keep_separate` 命中时，健康扫描不再创建重复页面待决策。
- `merge` 命中且两个身份再次同时有效时，系统按规则保存的目标身份自动合并、迁移证据并归档来源页面。
- 合并目标不能从数组位置推断，必须保存在 `result_snapshot` 中。

用户主动恢复被合并的归档页面，视为显式覆盖原决策：恢复事务先撤销相关 `merge` 规则，再激活页面。页面物理删除或身份字段被人工修改时，相关身份规则也必须撤销。

### 5. 所有入口使用同一个决策编排服务

新增 `decision_service.py`，负责构造上下文、计算签名、查询规则、验证结果、写入规则、回放、撤销和构建追踪。以下入口不得各自实现签名或回放逻辑：

- 普通资料构建和构建重试
- 资料重新摄取后的更新提议
- 知识库整体重建
- 健康扫描的 `conflict`/`duplicate`
- 单条语义化决策处理；旧通用单条及批量入口只保留 410 停用响应
- 资料、页面删除和归档恢复

知识库重建命中 human/mixed 页面时必须保存实际生成的候选正文与资料上下文，不能继续只调用没有候选的 `ensure_check`。重建产生的 `schema_changed`、物理删除产生的 `source_invalid` 等确定性状态不进入用户决策中心。

普通资料构建的 Stage2 同时接收当前有效页面的 ID、标题和类型清单；模型可返回 `existing_page_id` 标记标题不同但主题相同的候选。服务端必须校验该 ID 属于当前知识库，再比较当前正文和新正文并归类为 `unchanged`、`supplement` 或 `conflict`。只有明确的 `conflict` 进入既有知识冲突编排；无变化、补充、无效候选或检测失败沿用原自动构建路径。

### 6. 使用语义化单一决策 API

生产 Web 迁移到单条语义化接口：

```json
POST /check_item/{id}/decide/
{
  "action": "keep_current | use_new | edit_accept | keep_separate | merge",
  "body": "仅 edit_accept 必填"
}
```

服务端按 `decision_type` 校验允许动作，并在同一事务内完成页面变更、规则写入、检查关闭、证据更新和级联维护。通用“接受/拒绝/忽略”不再作为生产决策中心的业务语言，生产 Web 也不再提供不看上下文的批量接受/拒绝。

检查项只能由系统流程创建；集合创建、更新和删除返回 405。旧 `accept/reject/merge/resolve/batch_*` 返回 410，客户端不得降级到旧语义。

所有列表、详情和自定义动作先按用户团队过滤知识库；跨团队真实对象返回 403，混合团队批量请求在任何写入前整体拒绝。序列化关联页、资料和候选正文时再次限定当前知识库，避免跨库引用泄漏。

撤销接口只把规则改为 `revoked`；当前已生效知识不自动回滚。下次相同冲突出现时重新创建待决策。

### 7. 自动维护与用户决策分流

新知识直接生成有效页面并自动维护关系、图谱与索引。资料或知识物理删除在用户确认影响预览后执行不可逆删除，并立即清理证据、关系、索引以及相关决策规则，不再生成失效审批。

新知识直接准入也适用于历史清理：0065 将仍为 open 的 `qa_answer_candidate` 候选提升为当前版本并记录 `automatic_admission`。

资料重新构建和知识库整体重建自动处理旧 AI 页面、失效关系及索引；只有实际产生且无法由有效历史规则解决的知识冲突或页面身份判断进入待决策。

物理删除、全库重建和页面生命周期先在事务内提交核心知识结果与 pending 维护记录，再通过 `transaction.on_commit` 执行关系、图谱和索引维护。失败阶段写入 BuildRecord 的 `partial/failed` 状态，可按阶段幂等重试；重试使用 claim 防止并发重复执行。

图谱洞察和健康诊断可以继续作为系统观测数据存在，但不得混入“待决策”计数或使用接受/拒绝动作。

诊断审计按检查类型、来源页面和目标/关系/图谱身份幂等记录；完全重复只更新同一审计记录，不同目标不得错误合并。决策中心 API 不返回诊断记录。

### 8. 回放写入现有可观测链路

自动回放不创建新的待决策 `CheckItem`。普通构建、资料更新和重建必须在 `BuildRecord.inputs.source_trace.page_actions` 中记录 `decision_reused`、规则 ID、动作和目标页面；对应计数归入 `unchanged`，避免扩大现有计数协议。

扫描期页面身份回放和规则撤销写入操作日志。已处理决策详情返回来源快照、决策结果、回放次数和最后回放时间，供生产决策中心的变更记录展示。

页面身份 `merge` 回放到重建后的新页面 ID 时，同步刷新规则的 `result_page`、`result_version` 和结果快照，保证后续审计引用当前实体。

## Risks / Trade-offs

- **[来源证据不完整导致误匹配]** → 只有参与者 material ID 与 content hash 完整时才创建规则；接受候选时补齐 `PageEvidence`，不完整上下文继续人工决策。
- **[旧决策覆盖后续人工编辑]** → 回放前校验最终正文指纹；任何不一致都使规则不适用于本次输入。
- **[多来源集合增大导致旧规则频繁失效]** → 这是保守且预期的行为；来源集合变化代表知识依据变化，应重新决策。
- **[LLM 输出轻微波动导致重复审批]** → 候选正文 hash 不进入主签名，命中时保留已审批结果而不是重新采用候选正文。
- **[并发构建生成重复检查或规则]** → 锁定目标页面、事务内二次查询，并以规则唯一约束兜底。
- **[JSONField 在不同数据库上的查询差异]** → 匹配只查询普通 `decision_key` 和枚举字段；JSON 只保存审计快照。
- **[页面合并规则长期存在后语义过期]** → 页面身份变化、物理删除或归档恢复自动撤销，用户也可从已处理记录主动撤销。
- **[生产 API 更新影响现有 Web]** → Server 与 Web 在同一变更中迁移并以契约测试约束动作集合，不保留并行的模糊业务入口。
- **[失效检查持续占用待办]** → 实时上下文变化时自动关闭旧检查并提示重新构建，不让不可提交的记录继续保持 `open`。
- **[跨团队或跨知识库数据泄漏]** → 查询集、对象动作、批量写入和序列化关联均执行同一团队/KB 边界。

## Migration Plan

1. 0064 新增 `WikiDecisionRule`、决策型 `CheckItem` 字段、索引与唯一约束；不生成历史规则。
2. 0065 自动关闭历史非决策 open 检查、自动准入旧 QA 候选，并增加“open 仅限四类决策”的数据库约束。
3. 接入普通构建、资料更新、全库重建、扫描、删除与恢复流程，再切换生产 Web 到语义化 `decide`。
4. 停用旧通用处理 API，启用团队/知识库隔离和提交后维护重试。
5. 更新生产 Web、类型、API、国际化与 Storybook，使视觉伴随直接渲染生产组件。
6. 上线后仅完整的新决策形成规则；历史语义决策仍可查看，非决策历史只作为自动审计。
7. 0065 的数据迁移反向操作为 noop：回滚代码不会恢复已关闭审批，也不会撤销已准入 QA 版本；旧页面版本仍保留可恢复。
8. 回退服务前先确认没有新代码依赖约束；规则表和自动审计记录可保留，不影响旧知识内容。

## Open Questions

无阻塞问题。独立规则管理后台和基于向量召回的通用跨资料身份识别留作后续变更。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-07-10
```

## Capability Deltas

### wiki-decision-governance

## ADDED Requirements

### Requirement: 用户待决策范围

系统 SHALL 只把知识冲突和页面合并作为 OpsPilot Wiki 的用户待决策事项；确定性维护和系统健康诊断 MUST NOT 使用通用接受、拒绝或忽略动作进入待决策队列。

#### Scenario: 识别到知识结果冲突
- **WHEN** 构建流程确认当前知识与候选知识不能安全自动合并且没有可回放结果
- **THEN** 系统创建一条知识冲突待决策
- **AND** 待决策详情同时提供当前知识、候选知识、来源和影响范围

#### Scenario: AI 资料之间存在事实冲突
- **WHEN** 新资料生成的页面与现有页面属于同一知识主题，即使两者标题不同
- **AND** 当前正文与新正文对同一条件给出互斥的事实结论
- **THEN** 系统使用服务端校验后的页面候选创建知识冲突待决策
- **AND** 无变化或仅补充非矛盾信息时继续自动构建，不增加用户待决策数量

#### Scenario: 识别到页面身份不确定
- **WHEN** 两个有效页面可能表达同一知识对象且没有可回放的页面身份结果
- **THEN** 系统创建一条页面合并待决策
- **AND** 待决策详情同时提供两个页面的知识身份、正文和来源证据

#### Scenario: 产生图谱健康诊断
- **WHEN** 图谱分析产生孤立节点、稀疏社区或其他结构维护信息
- **THEN** 系统不得把该信息计入用户待决策数量
- **AND** 系统通过自动维护结果或独立诊断视图呈现该信息

### Requirement: 知识冲突使用语义化结果

系统 SHALL 为知识冲突提供且仅提供“保留当前知识”“使用新知识”和“编辑后采用”三个业务结果，并 MUST 在结果生效后维护版本、来源证据、关系、图谱和索引的一致性。

#### Scenario: 保留当前知识
- **WHEN** 用户对知识冲突选择“保留当前知识”
- **THEN** 当前页面版本保持有效
- **AND** 候选版本不再作为待决策内容
- **AND** 被拒绝资料不得被标记为当前知识的已采用来源

#### Scenario: 使用新知识
- **WHEN** 用户对知识冲突选择“使用新知识”
- **THEN** 候选正文成为新的当前页面版本
- **AND** 原当前版本继续作为可恢复历史版本保留
- **AND** 候选资料及其内容版本被记录为页面来源证据

#### Scenario: 编辑后采用
- **WHEN** 用户提交“编辑后采用”及非空编辑正文
- **THEN** 系统以该正文创建新的当前页面版本
- **AND** 当前知识与候选知识的来源上下文被保存在处理记录中
- **AND** 候选资料及其内容版本被记录为页面来源证据

#### Scenario: 提交不适用的知识冲突动作
- **WHEN** 用户对知识冲突提交页面合并动作或为空的编辑正文
- **THEN** 系统拒绝请求
- **AND** 页面、候选版本和决策状态均保持不变

### Requirement: 页面合并使用语义化结果

系统 SHALL 为页面合并提供且仅提供“保持独立”和“确认合并”两个业务结果，并 MUST 明确保存合并目标而不是从页面展示顺序推断目标。

#### Scenario: 保持页面独立
- **WHEN** 用户选择“保持独立”
- **THEN** 两个页面均保持有效且正文不变
- **AND** 系统记录该页面身份组合的独立结果

#### Scenario: 确认页面合并
- **WHEN** 用户选择“确认合并”
- **THEN** 系统把正文、来源证据、标签和关系合并到已确认的目标页面
- **AND** 来源页面进入可恢复归档
- **AND** 系统重建受影响的关系、图谱和索引

#### Scenario: 合并条件在提交前已失效
- **WHEN** 用户提交合并时任一相关页面已删除、已归档或不再属于同一知识库
- **THEN** 系统拒绝合并
- **AND** 不创建部分合并结果

### Requirement: 新知识直接准入

系统 SHALL 让未与现有知识形成冲突的新知识直接进入有效知识集，不得创建“新知识准入”审批。

#### Scenario: 新资料生成全新知识
- **WHEN** 资料构建生成一个不存在同主题冲突的知识页面
- **THEN** 系统直接创建有效页面和当前版本
- **AND** 系统自动创建来源证据并执行关系、图谱和索引维护
- **AND** 用户待决策数量不增加

### Requirement: 确定性删除自动维护

系统 MUST 在用户确认删除影响后自动处理资料或知识物理删除造成的证据、页面状态、关系、图谱、索引及决策规则变化，不得为已经发生且不可恢复的失效创建用户审批。

#### Scenario: 物理删除资料
- **WHEN** 用户确认资料删除影响并执行物理删除
- **THEN** 系统级联删除该资料及其版本和来源证据
- **AND** 系统自动更新失去来源的页面状态及所有派生结构
- **AND** 系统不创建 `source_invalid` 或其他失效审批

#### Scenario: 物理删除知识页面
- **WHEN** 用户确认并物理删除知识页面
- **THEN** 系统自动移除页面版本、证据、关系、图谱节点、索引和相关决策规则
- **AND** 系统不创建删除结果审批

### Requirement: 重建产生的确定性维护自动执行

系统 MUST 在资料重新构建和知识库整体重建时自动处理旧 AI 页面、来源失效、关系、图谱和索引；只有无法由系统或历史规则确定结果的知识冲突和页面身份问题可以进入用户待决策。

#### Scenario: 重新构建相同内容资料
- **WHEN** 用户重新构建内容 hash 未变化的资料
- **THEN** 系统不得仅因重新构建动作创建失效或 Schema 变化审批
- **AND** 系统按当前知识和历史规则完成维护

#### Scenario: 整体重建知识库
- **WHEN** 用户执行知识库整体重建
- **THEN** 系统自动归档或替换可确定处理的旧 AI 结果并更新派生结构
- **AND** 系统不得为确定性的 `schema_changed` 或重建失效创建用户审批
- **AND** 新产生且无法回放的知识冲突仍进入知识冲突待决策

### Requirement: 决策中心使用明确的知识语言

生产决策中心 SHALL 使用“当前知识/新知识”和“保持独立/确认合并”等业务语言呈现结果，不得把通用“接受/拒绝/忽略”作为用户的主要决策动作。

#### Scenario: 查看知识冲突详情
- **WHEN** 用户打开知识冲突待决策
- **THEN** 页面以统一的当前知识和新知识卡片展示标题、正文差异、来源版本、触发原因、影响范围和可恢复性
- **AND** 页面只展示该决策类型允许的三个动作

#### Scenario: 查看页面合并详情
- **WHEN** 用户打开页面合并待决策
- **THEN** 页面以与知识冲突一致的双侧卡片风格展示两个知识身份
- **AND** 页面只展示“保持独立”和“确认合并”

#### Scenario: 查看已处理决策
- **WHEN** 用户切换到已处理记录或打开变更记录
- **THEN** 系统展示语义化结果、操作人、处理时间、来源快照及是否已被自动回放


### Requirement: 待决策边界由存储与 API 共同保证

系统 MUST 只允许 `cannot_merge`、`material_update`、`duplicate`、`conflict` 四种检查类型保持 `open`；前两者属于知识冲突，后两者属于页面身份。其他检查 MUST 以 `auto_resolved` 保存自动审计，且建议动作必须为空。

#### Scenario: 诊断检查被系统记录
- **WHEN** 健康扫描发现孤立页、缺失链接、异常关系或图谱洞察
- **THEN** 系统按检查类型、来源页面和目标身份幂等保存自动审计
- **AND** 完全相同的诊断不重复创建，不同目标分别保存
- **AND** 记录不进入决策中心或待决策计数

#### Scenario: 上线清理历史待办
- **WHEN** 0065 迁移处理历史非决策 open 检查
- **THEN** 普通诊断变为 `auto_resolved` 并记录 `automatic_maintenance`
- **AND** 带候选版本的 `qa_answer_candidate` 自动成为当前知识并记录 `automatic_admission`
- **AND** 迁移完成后数据库拒绝新的非决策 open 检查

### Requirement: 决策 API 使用单一语义入口并执行团队隔离

系统 SHALL 只允许系统流程创建检查项；生产客户端 MUST 使用 `decide` 和规则撤销接口。所有 Wiki 资源和动作 MUST 限定在调用者可访问的团队及知识库内。

#### Scenario: 调用旧通用审批接口
- **WHEN** 客户端调用 accept、reject、merge、resolve 或任一 batch 通用处理接口
- **THEN** 系统返回 410 并提示改用 `decide`
- **AND** 检查、页面和规则均保持不变

#### Scenario: 人工修改检查项集合
- **WHEN** 客户端尝试创建、更新或删除检查项
- **THEN** 系统返回 405

#### Scenario: 跨团队访问或混合团队批量操作
- **WHEN** 用户访问不属于其团队的知识库对象或批量请求混入跨团队对象
- **THEN** 系统返回 403
- **AND** 批量请求在任何对象写入前整体失败
- **AND** 序列化结果不得解析或泄漏跨知识库的页面、资料或候选正文

### Requirement: 删除与重建维护在核心提交后可重试

系统 MUST 先提交物理删除、重建或页面生命周期的核心知识结果和维护记录，再执行关系、图谱与索引等派生维护。维护失败 MUST 可观测、可按阶段幂等重试，且不得恢复已删除对象或创建用户决策。

#### Scenario: 提交后维护失败
- **WHEN** 核心删除或重建事务已经成功，但任一派生维护阶段失败
- **THEN** BuildRecord 记录失败阶段、错误和 `partial` 或 `failed` 状态
- **AND** 已提交的知识结果保持不变
- **AND** 用户待决策数量不增加

#### Scenario: 并发重试同一维护记录
- **WHEN** 两个请求同时重试同一维护记录
- **THEN** 系统只允许一个请求取得有效 claim 并执行选定阶段
- **AND** 成功阶段不会因重试被重复应用

### wiki-decision-replay

## ADDED Requirements

### Requirement: 知识冲突生成稳定签名

系统 MUST 使用知识库、决策类型、稳定知识标识、Schema 指纹和完整且去重排序的资料来源版本集合生成知识冲突签名；签名不得依赖资料在界面中的当前或新位置。

#### Scenario: 一对一资料冲突
- **WHEN** 当前知识来源为资料 A 的内容 hash `a1` 且候选来源为资料 B 的内容 hash `b1`
- **THEN** 签名包含 A、`a1`、B、`b1` 以及稳定知识标识
- **AND** A、B 的输入顺序变化不改变签名

#### Scenario: 多来源知识冲突
- **WHEN** 当前知识来源集合为 A、C 且候选来源为 B
- **THEN** 签名使用去重排序后的完整集合 A、B、C
- **AND** 系统不得任意选择 A 或 C 与 B 组成不完整资料对

#### Scenario: 同一资料重复出现
- **WHEN** 当前来源集合已经包含本次传入的同一资料和相同内容 hash
- **THEN** 系统在参与者集合中只保留一个该资料版本身份

#### Scenario: 来源上下文不完整
- **WHEN** 任一必要资料缺少稳定 ID、内容 hash 或知识主题无法规范化
- **THEN** 系统不得创建可自动回放的知识冲突规则
- **AND** 本次冲突仍可由用户处理

### Requirement: 决策规则保存真实结果

系统 MUST 持久化决策匹配快照、语义化动作、最终页面版本或目标身份、来源检查项、操作人和处理时间；系统不得只保存“当前”或“新”这种相对位置结果。

#### Scenario: 保存胜出资料
- **WHEN** 用户选择使用资料 B 对应的新知识
- **THEN** 规则保存 B 的资料 ID、内容 hash 和最终页面版本
- **AND** 后续 B 变成当前侧时仍可识别 B 为同一胜出来源

#### Scenario: 保存编辑结果
- **WHEN** 用户编辑候选后采用
- **THEN** 规则保存最终编辑版本及正文指纹
- **AND** 原始当前正文和候选正文指纹保存在匹配或审计快照中

#### Scenario: 保存页面合并目标
- **WHEN** 用户确认页面合并
- **THEN** 规则保存目标页面的稳定身份和结果页面引用
- **AND** 目标不得由页面数组位置推断

### Requirement: 精确命中时自动回放

系统 SHALL 在构建或扫描得到与有效规则完全相同的签名且当前结果前置条件仍成立时自动执行历史结果，不创建新的用户待决策。

#### Scenario: 相同资料再次构建
- **WHEN** 相同知识主题和相同完整资料内容 hash 集合再次产生冲突
- **AND** 当前页面正文仍等于历史决策保存的最终结果
- **THEN** 系统保持历史决策结果
- **AND** 不创建新的 `CheckItem`

#### Scenario: 当前和新角色反转
- **WHEN** 相同参与者集合再次冲突但原胜出资料位于当前侧
- **THEN** 系统仍保留原胜出资料对应的结果
- **AND** 不按“使用新知识”字符串错误选择另一资料

#### Scenario: 命中编辑后采用规则
- **WHEN** 相同来源集合再次构建且当前页面仍为历史编辑后的最终正文
- **THEN** 系统保留已编辑结果
- **AND** 不使用本次 LLM 重新生成的措辞覆盖该结果

#### Scenario: 自动回放补齐构建追踪
- **WHEN** 构建流程自动回放历史规则
- **THEN** 构建记录写入规则 ID、语义化动作、目标页面和 `decision_reused` 标识
- **AND** 本次页面动作计入 `unchanged` 而非 `pending_review`

### Requirement: 上下文变化使知识规则不适用

系统 MUST 在资料内容、完整来源集合、Schema 或已审批结果发生变化时停止自动应用旧知识冲突规则，并创建新的待决策上下文。

#### Scenario: 任一资料内容变化
- **WHEN** 资料 A 的内容 hash 从 `a1` 变为 `a2`
- **THEN** 使用 `a1` 的旧规则不匹配
- **AND** 无其他规则命中时系统创建新的知识冲突待决策

#### Scenario: 来源集合变化
- **WHEN** 原决策参与者为 A、B，当前知识又加入资料 C
- **THEN** A、B 规则不匹配 A、B、C 的新上下文

#### Scenario: Schema 变化
- **WHEN** 知识库 Schema 或影响知识生成边界的规则发生变化
- **THEN** 旧 Schema 指纹的知识冲突规则不匹配

#### Scenario: 审批后发生人工修改
- **WHEN** 当前页面正文不再等于规则保存的最终正文指纹
- **THEN** 系统不得恢复或覆盖为旧结果
- **AND** 无其他规则命中时系统重新创建待决策

#### Scenario: 相同内容作为新资料重新上传
- **WHEN** 内容相同但资料 ID 与历史参与者不同
- **THEN** 历史规则不匹配
- **AND** 系统把该资料视为新的决策参与者

### Requirement: 页面身份决策不依赖页面 ID

系统 MUST 使用排序后的稳定页面身份组合生成页面合并签名，并 SHALL 在页面 ID 因重建变化后仍识别相同身份组合。

#### Scenario: 保持独立规则再次命中
- **WHEN** 健康扫描再次发现已决定保持独立的两个页面身份
- **THEN** 系统不创建页面合并待决策
- **AND** 两个页面继续保持有效

#### Scenario: 合并规则再次命中
- **WHEN** 重建或恢复流程再次产生已决定合并的两个页面身份
- **THEN** 系统自动把来源身份合并到规则保存的目标身份
- **AND** 自动迁移证据、归档来源并维护派生结构

#### Scenario: 页面 ID 在重建后变化
- **WHEN** 相同规范标题和页面类型以新的数据库页面 ID 出现
- **THEN** 系统仍可按稳定页面身份匹配历史规则

#### Scenario: 页面身份变化
- **WHEN** 页面标题或页面类型被人工修改并形成不同稳定身份
- **THEN** 原页面身份规则不适用于新的身份组合

### Requirement: 决策规则可撤销并遵循对象生命周期

系统 SHALL 允许用户撤销历史规则，并 MUST 在物理删除或显式恢复合并来源页面时撤销相关规则；撤销不得自动回滚当前知识内容。

#### Scenario: 用户主动撤销规则
- **WHEN** 用户从已处理决策或变更记录撤销一条有效规则
- **THEN** 规则状态变为 `revoked`
- **AND** 当前页面及其版本保持不变
- **AND** 下次相同冲突不再自动回放该规则

#### Scenario: 恢复被合并页面
- **WHEN** 用户主动恢复由页面合并归档的来源页面
- **THEN** 系统在激活页面前撤销对应的 `merge` 规则
- **AND** 后续扫描可以重新产生页面合并待决策

#### Scenario: 物理删除资料
- **WHEN** 某资料被物理删除
- **THEN** 系统撤销或删除所有依赖该资料身份的知识冲突规则
- **AND** 不创建规则失效审批

#### Scenario: 物理删除页面
- **WHEN** 某页面被物理删除
- **THEN** 系统撤销或删除引用该页面身份的合并规则
- **AND** 不创建规则失效审批

### Requirement: 决策创建和回放具备并发幂等性

系统 MUST 保证同一知识库、决策类型和决策签名在并发构建或重复任务投递下最多存在一条有效规则和一条 open 待决策。

#### Scenario: 并发首次检测同一冲突
- **WHEN** 两个任务同时检测到相同签名且不存在规则
- **THEN** 系统最多创建一条 open 待决策
- **AND** 两个任务不得各自创建候选版本供重复审批

#### Scenario: 并发命中同一规则
- **WHEN** 两个任务同时命中同一有效规则
- **THEN** 两个任务均得到相同业务结果
- **AND** 规则回放计数按成功回放次数原子更新

#### Scenario: 同签名重新决策
- **WHEN** 已撤销规则对应的相同签名再次被用户处理
- **THEN** 系统更新该签名对应规则为新的有效结果
- **AND** 原处理流水继续保留用于审计

### Requirement: 历史数据不做推测性回填

系统 MUST 只为能够冻结完整输入和结果的新决策创建回放规则，不得从缺失候选版本、来源版本或语义化结果的旧检查项推断规则。

#### Scenario: 部署后读取旧检查项
- **WHEN** 系统读取变更上线前已处理但缺少完整决策上下文的 `CheckItem`
- **THEN** 该检查项仍可作为历史记录查看
- **AND** 系统不把它视为可自动回放规则

### Requirement: 提交决策时校验实时上下文

系统 MUST 在执行人工知识冲突决策前重新校验页面当前版本、候选正文、Schema 和完整参与资料集合。参与资料的业务身份使用 `material_id + content_hash`；`material_version_id` 只用于审计。

#### Scenario: 资料内容、证据集合或 Schema 已变化
- **WHEN** 冻结决策后的实时 Schema 不同，或参与资料集合的 ID/content hash 增加、减少或变化
- **THEN** 系统自动关闭旧检查并记录上下文失效原因
- **AND** 页面、候选结果和决策规则均不发生业务变更
- **AND** 后续构建或扫描使用实时上下文生成新的待决策

#### Scenario: 同内容产生新的资料版本记录
- **WHEN** 同一资料的当前版本 ID 变化但 content hash 与冻结上下文一致
- **THEN** 原检查仍可提交
- **AND** 决策签名保持不变

### Requirement: 页面身份回放刷新审计引用

系统 SHALL 在页面身份合并规则回放到重建后的实体后，刷新规则的结果页面、结果版本和结果快照引用，同时保持稳定身份签名不变。

#### Scenario: 新页面 ID 命中历史合并规则
- **WHEN** 重建生成的新页面身份命中历史 merge 规则并完成自动合并
- **THEN** 规则的 `result_page`、`result_version` 和快照 ID 指向本次实际结果
- **AND** 后续撤销、删除和变更记录使用新的有效引用

## Work Checklist

## 1. 决策规则数据模型与迁移

- [x] 1.1 在 `server/apps/opspilot/tests/wiki/test_decision_replay.py` 增加失败测试：`WikiDecisionRule` 的 `knowledge_base`、`decision_type`、`decision_key`、快照、动作、结果、状态和回放计数字段可持久化。
- [x] 1.2 在同一测试文件增加失败测试：同一知识库、决策类型和 `decision_key` 不能保存两条有效规则，不同知识库或不同类型可以保存相同摘要。
- [x] 1.3 在 `server/apps/opspilot/models/wiki_mgmt.py` 新增 `WikiDecisionRule`，并给决策型 `CheckItem` 增加可索引的 `decision_key` 与冻结的 `decision_context` 字段。
- [x] 1.4 生成并检查 `server/apps/opspilot/migrations/0064_*.py`，迁移使用普通字段唯一约束和数据库无关索引，不回填历史决策。
- [x] 1.5 运行 `cd server; uv run pytest apps/opspilot/tests/wiki/test_decision_replay.py -q`，确认模型与迁移测试通过。

## 2. 稳定签名与规则服务

- [x] 2.1 在 `test_decision_replay.py` 增加失败测试：一对一来源、多来源集合、来源排序、重复来源、同资料新版本 ID、不同资料 ID、角色反转和 Schema 指纹生成确定且可区分的签名。
- [x] 2.2 在 `server/apps/opspilot/services/wiki/decision_service.py` 实现来源快照规范化、知识主题 key、页面身份 key、Schema 指纹和 SHA-256 决策签名；主签名使用 `material_id + content_hash`，版本 ID 与正文 hash 只用于审计/校验。
- [x] 2.3 增加失败测试：缺少来源 ID/content hash、无稳定知识主题、人工结果正文已变化、来源集合增加/减少时规则不可回放。
- [x] 2.4 实现规则查询、结果前置条件校验、`replayed`/`pending`/`unchanged` 结果、规则 upsert、撤销和回放计数更新。
- [x] 2.5 增加失败测试：物理删除资料或页面、恢复合并归档页面、页面身份变化时相关规则被撤销；撤销不回滚当前知识。
- [x] 2.6 实现 `revoke_rules_for_materials`、`revoke_rules_for_pages`、`revoke_rules_for_identity_change`，并为规则快照保留可审计来源而不复制全文到通用日志。

## 3. 知识冲突审批与证据一致性

- [x] 3.1 在 `server/apps/opspilot/tests/wiki/test_checks.py` 增加失败测试：知识冲突只接受 `keep_current`、`use_new`、`edit_accept`，错误动作和空编辑正文被拒绝且不改变页面。
- [x] 3.2 在 `server/apps/opspilot/services/wiki/check_service.py` 重构候选创建与决策处理：冻结完整来源上下文，统一执行三种知识结果，并在同一事务中写入 `WikiDecisionRule`。
- [x] 3.3 增加失败测试：保留当前知识不补入被拒绝资料；使用新知识和编辑后采用都补齐资料/资料版本 `PageEvidence`，旧页面版本可恢复。
- [x] 3.4 修复 `accept_candidate`、编辑后采用和拒绝流程的当前版本竞态：提交时锁定页面并重新校验候选创建时的当前版本，过期决策不得覆盖更新后的页面。
- [x] 3.5 在 `server/apps/opspilot/viewsets/wiki_check_view.py` 增加语义化 `POST /check_item/{id}/decide/` 与规则撤销接口，按 `check_type` 校验允许动作；移除生产 Web 对通用 accept/reject/batch 动作的依赖。
- [x] 3.6 在 `server/apps/opspilot/serializers/wiki_serializers.py` 暴露决策类型、冻结来源、动作、规则 ID、回放次数和未回放原因；补充接口契约测试与无权限撤销测试。

## 4. 普通构建、资料更新和全库重建接入

- [x] 4.1 在 `server/apps/opspilot/tests/wiki/test_build.py` 增加失败测试：同一资料内容再次构建、相同冲突角色反转、候选正文与当前正文相同以及多来源集合命中时不重复创建审批。
- [x] 4.2 修改 `server/apps/opspilot/services/wiki/build_service.py`：在 `_create_review_candidate` 前调用统一决策服务，回放时保持已审批结果，未命中时创建带来源快照的候选，并在 `BuildRecord.inputs.source_trace.page_actions` 写入 `decision_reused`。
- [x] 4.3 在 `server/apps/opspilot/tests/wiki/test_update.py` 增加失败测试：资料重新摄取相同 hash 命中旧规则，hash 变化或来源集合变化重新创建知识冲突；`apply_material_update` 必须携带资料上下文。
- [x] 4.4 修改 `server/apps/opspilot/services/wiki/update_service.py`，让资料更新复用普通构建的决策编排、证据补齐和规则写入，不再为同一版本重复生成候选。
- [x] 4.5 在 `server/apps/opspilot/tests/wiki/test_rebuild.py` 增加失败测试：整体重建同 Schema 命中历史决策不创建审批，Schema 变化重新决策，重建确定性维护不创建 `schema_changed` 审批。
- [x] 4.6 修改 `server/apps/opspilot/services/wiki/rebuild_service.py`，替换无候选上下文的 `ensure_check` 分支，使用统一冲突处理器并记录真实资料/正文快照。
- [x] 4.7 增加异步任务回归测试，验证 `wiki_build_material_task`、`wiki_rebuild_kb_task` 和 BuildRecord retry 与同步入口得到相同回放结果。
- [x] 4.8 补齐 AI 资料事实冲突检测：Stage2 返回经当前知识库校验的 `existing_page_id`，新旧正文仅在明确矛盾时进入现有知识冲突审批，标题漂移回归用例覆盖报销 A/B 场景。

## 5. 页面身份合并与生命周期

- [x] 5.1 在 `test_decision_replay.py` 和 `server/apps/opspilot/tests/wiki/test_checks.py` 增加失败测试：保持独立、确认合并、扫描顺序反转、重建后页面 ID 变化和来源资料变化的行为符合页面身份规则。
- [x] 5.2 在 `server/apps/opspilot/services/wiki/check_service.py` 抽出稳定页面身份签名和可复用的页面合并核心；`merge_duplicate_check` 记录目标身份与规则结果，不依赖 related 页面数组位置。
- [x] 5.3 修改 `scan_health`/`ensure_check`，先查询 `page_identity` 规则；命中 `keep_separate` 时跳过检查，命中 `merge` 时自动合并到记录的目标身份。
- [x] 5.4 在 `server/apps/opspilot/tests/wiki/test_page_lifecycle_incremental.py` 增加失败测试：恢复合并归档页面先撤销合并规则，页面重命名/类型变化和物理删除撤销相关身份规则。
- [x] 5.5 修改 `server/apps/opspilot/viewsets/wiki_page_view.py` 与 `page_service.py`，把恢复、编辑身份、物理删除接入规则撤销；保持当前页面内容，不隐式拆分已完成合并。

## 6. 删除与确定性维护自动化

- [x] 6.1 在资料删除测试中增加失败测试：删除前返回唯一来源/共享来源影响预览，取消删除不改变数据，确认删除不创建 `source_invalid` 待决策。
- [x] 6.2 修改 `server/apps/opspilot/services/wiki/update_service.py` 的删除流程，物理删除后自动清理证据、页面状态、关系、图谱、索引和相关决策规则；唯一来源与共享来源分别验证。
- [x] 6.3 在知识页面删除测试中验证物理删除自动清理关系、索引和 page identity 规则，且不增加待决策数量。
- [x] 6.4 调整 `sweep_service.py` 与构建计数，使确定性失效、结构维护和技术失败只进入构建/维护追踪，不进入用户待决策列表。
- [x] 6.5 增加级联维护失败与重试测试：核心知识结果保持已提交，失败阶段可重试，不创建新的用户决策。

## 7. 生产 API、决策中心与 Storybook

- [x] 7.1 在 `web/src/app/opspilot/types/wiki.ts` 增加决策动作、来源快照、规则回放和撤销类型；在 `web/src/app/opspilot/api/wiki.ts` 实现 `decide`、撤销和处理记录查询。
- [x] 7.2 重构 `web/src/app/opspilot/components/wiki/CheckTab.tsx` 为生产决策中心：待处理仅显示知识冲突/页面合并，使用当前知识/新知识双侧布局和语义化动作。
- [x] 7.3 实现知识冲突的“保留当前知识”“使用新知识”“编辑后采用”交互，包括正文编辑、过期决策提示、提交中状态和成功后刷新。
- [x] 7.4 实现页面合并的“保持独立”“确认合并”交互，统一左右对比图标和双侧卡片风格；移除“更多处理”、通用忽略和无上下文批量操作。
- [x] 7.5 将 `web/src/stories/wiki-decision-center.stories.tsx` 改为复用生产决策中心组件，保留知识冲突、页面合并、自动回放和失效状态 stories。
- [x] 7.6 更新 `web/src/app/opspilot/locales/zh.json`、`en.json` 及 `web/scripts/wiki-check-review-i18n-test.ts`，覆盖语义化动作、回放、撤销、自动维护和失败提示。
- [x] 7.7 更新已处理记录/变更记录展示：显示决策结果、规则状态、回放次数、失效原因和可撤销入口，不展示资料全文。

## 8. 并发、回归与质量门禁

- [x] 8.1 增加并发测试：相同签名的两个构建最多创建一条 open 决策和一条候选，两个回放任务不重复创建页面版本、证据或合并结果。
- [x] 8.2 增加回归测试：旧 `CheckItem` 无完整上下文不被回填，物理删除/归档恢复/资料 hash 回退/新资料 ID 均符合失效规则。
- [x] 8.3 运行 `cd server; uv run pytest apps/opspilot/tests/wiki/test_decision_replay.py apps/opspilot/tests/wiki/test_checks.py apps/opspilot/tests/wiki/test_build.py apps/opspilot/tests/wiki/test_update.py apps/opspilot/tests/wiki/test_rebuild.py apps/opspilot/tests/wiki/test_page_lifecycle_incremental.py -q`。
- [ ] 8.4 运行 `cd server; make test`，确认迁移检查、后端回归和覆盖率门禁通过。
- [ ] 8.5 运行 `cd web; pnpm lint; pnpm type-check; pnpm build-storybook`，确认生产决策中心与 Storybook 视觉伴随通过。
- [x] 8.6 运行 `openspec validate streamline-wiki-knowledge-decisions --strict --no-interactive`，再用 `openspec status --change streamline-wiki-knowledge-decisions` 确认四个 artifact 完成。

## 当前验证记录（2026-07-15）

| 范围 | 状态 | 证据 |
|------|------|------|
| 1-7 实现任务 | ✅ 完成 | 对应代码与测试均已落盘，并纳入受影响后端测试和前端定向检查。 |
| 8.1-8.3 并发与回归 | ✅ 完成 | 受影响后端 20 个测试文件共 356 passed，覆盖终审补充的历史上下文、重建快照、页面身份清扫与锁顺序回归。 |
| 8.4 `make test` | ⏳ 未完成 | 尚未运行 `make test`，不以局部测试替代全量后端门禁。 |
| 8.5 Web/Storybook | 🟡 部分完成 | `test:wiki-decision-center`、QA save-answer 脚本、定向 TypeScript 与 ESLint、fresh Storybook build 已通过；尚未运行全 Web 工作区 `pnpm lint` 与 `pnpm type-check`。 |
| 8.6 OpenSpec | ✅ 完成 | strict validate 通过，status 显示 `4/4 artifacts complete`。 |

补充静态检查：变更 Python 文件 Ruff 通过，`compileall` 通过，`git diff --check` 通过；`makemigrations --check --dry-run` 返回 `No changes detected`，同时出现本地非测试数据库连接 warning。
