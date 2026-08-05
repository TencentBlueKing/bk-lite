## ADDED Requirements

### Requirement: 旧知识候选必须由 Index 确定性召回

新文件产生知识候选后，系统 MUST 在固定的 base Generation 中按标题、别名、类型、标签、目录、关键词和摘要查询 Index，最多保留 20 个紧凑候选；候选召回 MUST 不调用 LLM，也不得注入全库页面清单。

#### Scenario: 知识库包含大量旧页面
- **WHEN** 新文件构建面对 1,000 个活动页面
- **THEN** Stage2 注入的旧候选 MUST 不超过 20 个
- **AND** LLM 调用数量 MUST 不随旧页面总数线性增长

### Requirement: 冲突比较必须先确定性过滤再单次批量判断

系统 MUST 先排除硬身份无关、完全相同，以及限定词、作用域、时间和证据语义一致的可证明结构化等价/包含候选，再按相关性最多加载 5 个旧页面、8,000 token 真实证据，并在最多一次 LLM 调用中批量判断疑似冲突。任何无法由硬规则证明的 supplement/conflict MUST 进入证据比较；系统 MUST NOT 为每个旧页面单独调用 LLM。

#### Scenario: 没有疑似冲突
- **WHEN** Index 候选均被确定性判定为硬身份无关、完全相同或可证明的结构化等价/包含
- **THEN** 系统 MUST 跳过冲突判断 LLM
- **AND** 构建记录 MUST 说明过滤结果

#### Scenario: 存在多个疑似冲突
- **WHEN** 过滤后存在不超过限制的多个候选
- **THEN** 系统 MUST 在一次请求中比较全部已装配候选
- **AND** 最终判断 MUST 引用对应 PageVersion/Evidence

### Requirement: 候选溢出必须可观测且不得隐式扩大调用

候选或证据超过装配上限时，系统 MUST 记录总候选数、入选/排除页面、评分和截断原因；系统 MUST NOT 增加第二次冲突比较或静默把未比较候选标记为无冲突。

#### Scenario: 高相关候选超过五个
- **WHEN** 确定性过滤后仍有六个以上候选
- **THEN** 系统 MUST 只装配相关性最高且证据预算可容纳的候选
- **AND** BuildRecord MUST 保存候选溢出诊断

### Requirement: 冲突候选必须固定 base Generation

候选检索、证据加载和 LLM 判断 MUST 使用构建启动时固定的 base Generation。激活前 base 已变化时，旧比较结果 MUST 不得覆盖新知识状态。

#### Scenario: 比较期间知识库推进
- **WHEN** 冲突判断完成前 active Generation 已变化
- **THEN** 当前构建 MUST 在激活 CAS 处失败或基于新 base 重新计算
- **AND** MUST NOT 混合旧 Index 与新 PageVersion

### Requirement: 候选发现不得改变既有冲突决策语义

Index 路由仅负责发现可能的旧知识。是否创建人工冲突、如何回放历史决策及如何保护 human/mixed 正文，MUST 继续遵守 `streamline-wiki-knowledge-decisions` 的正式要求。

#### Scenario: 标题相近但事实不冲突
- **WHEN** Index 找到高相关旧页面但真实证据显示内容兼容
- **THEN** 系统 MUST 不仅因高匹配分数创建人工冲突
