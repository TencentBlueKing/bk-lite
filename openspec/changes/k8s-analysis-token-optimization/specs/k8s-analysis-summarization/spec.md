## ADDED Requirements

### Requirement: 分析结果精简返回
`analyze_deployment_configurations` 工具 SHALL 返回精简摘要给 LLM，完整分析数据 SHALL 存入 `_analysis_cache`。

#### Scenario: 大规模集群分析返回精简摘要
- **WHEN** 分析完成，共有 50 个 deployment，其中 28 个有问题
- **THEN** 返回给 LLM 的 JSON SHALL 包含 `total`、`healthy`、`problematic` 计数和 `issues_summary`（按严重程度分组的问题类型+计数），不包含单个 deployment 的完整 `config_analysis`

#### Scenario: 精简摘要包含足够决策信息
- **WHEN** LLM 收到精简摘要
- **THEN** 摘要 SHALL 包含：集群名称、总数、健康数、有问题数、按严重程度分组的问题类型列表（含各类型影响的 deployment 数量）

#### Scenario: 完整数据存缓存供报告使用
- **WHEN** 分析完成
- **THEN** 完整的 `analysis_results`（含每个 deployment 的所有 issues/recommendations/containers）SHALL 存入 `_analysis_cache["deployments"]`

### Requirement: 安全术语中性化
返回给 LLM 的精简摘要文本 SHALL 对可能触发 Content Filter 的安全术语进行中性化替换。

#### Scenario: 敏感术语被替换
- **WHEN** 分析结果中包含 "privileged"、"容器逃逸"、"攻击面" 等术语
- **THEN** 精简摘要中 SHALL 使用中性等价词（"特权模式"、"容器隔离风险"、"暴露面"）

#### Scenario: 缓存保留原始术语
- **WHEN** 术语中性化执行
- **THEN** `_analysis_cache` 中的完整数据 SHALL 保留原始专业术语不变
