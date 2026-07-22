# K8S Analysis Token Optimization

Status: done

## Migration Context

- Legacy source: `openspec/changes/k8s-analysis-token-optimization/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

K8s 配置检查工具 `analyze_deployment_configurations` 返回全部 Deployment 的完整分析 JSON（包括无问题的），在大规模集群中（50+ Deployments）产生 50-70KB 的 ToolMessage，导致：
1. **Token 溢出**：超出 LLM context window 或触发截断，后续推理质量下降
2. **Azure Content Filter 拦截**：分析结果中安全术语（privileged、容器逃逸）和完整 YAML 被 Azure 误判为有害内容

## What Changes

- 分析工具返回**精简摘要**给 LLM（按问题类型聚合计数 + 只列有问题的 deployment），完整数据存入 `_analysis_cache` 供报告生成使用
- `get_kubernetes_resource_yaml` 工具返回前过滤 `managedFields`、`status`、冗余 annotations，减少 YAML 体积
- 分析结果中对安全术语做中性化处理（仅限返回给 LLM 的文本，缓存保留原始表述）
- 在工具 hint 中明确禁止 LLM 额外调用 `get_kubernetes_resource_yaml` 获取完整 YAML

## Capabilities

### New Capabilities
- `k8s-analysis-summarization`: 分析工具返回精简摘要而非完整结果，降低 token 消耗
- `k8s-yaml-filtering`: YAML 工具过滤冗余字段，减少传输体积和敏感内容暴露

### Modified Capabilities
- `react-loop-control`: 工具返回的 hint 增加"禁止调用 get_kubernetes_resource_yaml"指令

## Impact

- `server/apps/opspilot/metis/llm/tools/kubernetes/analysis.py` — 返回结构变更（精简版给 LLM）
- `server/apps/opspilot/metis/llm/tools/kubernetes/resources.py` — YAML 过滤逻辑
- `server/apps/opspilot/metis/llm/chain/node.py` — `_analysis_cache` 存储策略（已有，无大改）
- 不影响已有 API 接口，不影响前端

## Implementation Decisions

## Context

K8s 配置检查流程中，`analyze_deployment_configurations` 工具返回完整的分析结果（含每个 deployment 的所有容器细节），直接作为 ToolMessage 进入 LLM context。在大规模集群中这导致 token 溢出和 Azure Content Filter 拦截。

当前数据流：
```
analyze_deployment_configurations → 50-70KB JSON → LLM context
                                                      ↓
                                    token overflow / Azure filter block
```

`_analysis_cache` 已在 `node.py` 中用于缓存分析数据供 `generate_repair_report` 使用，但工具本身返回给 LLM 的内容未做精简。

`get_kubernetes_resource_yaml` 返回完整 YAML（含 managedFields、status 等冗余字段），增加了 token 消耗和 Azure 拦截风险。

## Goals / Non-Goals

**Goals:**
- 将 `analyze_deployment_configurations` 返回给 LLM 的 token 从 50-70KB 降到 3-5KB
- 过滤 YAML 工具返回中的冗余字段，减少 60%+ 体积
- 降低 Azure Content Filter 拦截概率
- 不影响报告生成质量（报告从缓存读完整数据）

**Non-Goals:**
- 不修改 Azure 平台侧过滤设置（需要运维操作，不在代码范围）
- 不改变分析工具的检查逻辑本身
- 不引入新的工具或 API

## Decisions

### Decision 1: 分析工具返回精简摘要，完整数据仅存缓存

**选择**：工具返回按问题类型聚合的摘要 JSON（~3-5KB），完整 `analysis_results` 存入 `_analysis_cache`。

**替代方案**：
- A) 分页返回（每次10个）— 需多次调用，增加步数和 token
- B) 只返回有问题的（跳过健康的）— 仍可能很大（28个有问题 × 多容器）
- C) 精简摘要 ✅ — 一次返回，LLM 有足够决策信息，报告从缓存取完整数据

**理由**：LLM 只需要知道"有多少问题、什么类型"来决定下一步，不需要每个容器的详细 issues。

### Decision 2: YAML 过滤 managedFields 和 status

**选择**：在 `get_kubernetes_resource_yaml` 序列化后，删除 `metadata.managedFields` 和 `status` 字段。

**理由**：managedFields 是 K8s 内部记录（经常占 YAML 50%+），status 是运行时状态不参与配置修复。

### Decision 3: 安全术语中性化在返回给 LLM 的文本中执行

**选择**：在精简摘要中，将敏感术语替换为中性表述。缓存中保留原始术语（报告需专业表述）。

**映射**：`privileged` → `特权模式`，`容器逃逸` → `容器隔离风险`，`攻击面` → `暴露面`

**理由**：这些术语是 Azure Content Filter 的触发源，中性化后语义不丢失但降低误判。

### Decision 4: hint 中明确禁止额外 YAML 获取

**选择**：`_next_step_hint` 追加"不要调用 get_kubernetes_resource_yaml，修复方案基于分析数据生成"。

**理由**：LLM 偶尔会调用该工具获取 before YAML 做对比，但 `generate_repair_report` 已能从分析数据生成 diff，多余调用只增加 token 和拦截风险。

## Risks / Trade-offs

- [精简过度] LLM 可能无法回答细节问题（如"哪个容器有问题"）→ 在摘要中保留 deployment name + issue 类型列表，足够定位
- [术语映射遗漏] 新的敏感词未被替换 → 采用可扩展的字典，后续按需补充
- [YAML 字段误删] 某些调试场景需要 status → 只在检查场景过滤，保留 `include_status` 参数供手动使用

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-28
```

## Capability Deltas

### k8s-analysis-summarization

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

### k8s-yaml-filtering

## ADDED Requirements

### Requirement: YAML 冗余字段过滤
`get_kubernetes_resource_yaml` 工具 SHALL 在返回 YAML 前过滤冗余字段以减少体积。

#### Scenario: 过滤 managedFields
- **WHEN** 获取任何资源的 YAML
- **THEN** 返回结果 SHALL 不包含 `metadata.managedFields` 字段

#### Scenario: 过滤 status
- **WHEN** 获取资源 YAML 且未指定 `include_status=True`
- **THEN** 返回结果 SHALL 不包含顶层 `status` 字段

#### Scenario: 过滤冗余 annotations
- **WHEN** 获取资源 YAML
- **THEN** 返回结果 SHALL 移除 `metadata.annotations` 中 `kubectl.kubernetes.io/last-applied-configuration` 字段（该字段是完整配置的重复）

#### Scenario: 保留核心配置
- **WHEN** 过滤执行后
- **THEN** `metadata`（name/namespace/labels）、`spec` SHALL 完整保留

### react-loop-control

## MODIFIED Requirements

### Requirement: prepareStep 每步前钩子
系统 SHALL 在每个 ReAct 循环步骤的 LLM 调用前执行 prepareStep 钩子，允许动态调整工具集、消息和配置。

#### Scenario: prepareStep 修改可用工具
- **WHEN** prepareStep 钩子返回新的 active_tools 列表
- **THEN** 当前步骤的 LLM 调用 SHALL 使用新的工具集

#### Scenario: prepareStep 在 compaction 之后执行
- **WHEN** 消息历史触发 compaction
- **THEN** prepareStep SHALL 在 compaction 完成后执行，能够感知压缩后的消息状态

#### Scenario: 分析完成后 hint 禁止额外 YAML 获取
- **WHEN** `analyze_deployment_configurations` 执行完成返回 `_next_step_hint`
- **THEN** hint SHALL 包含明确指令"不要调用 get_kubernetes_resource_yaml，修复方案基于分析数据直接生成"

## Work Checklist

## 1. 分析工具精简返回

- [x] 1.1 在 `analysis.py` 的 `analyze_deployment_configurations` 中，构建精简摘要结构（total/healthy/problematic/issues_summary），替换原有完整 `deployments` 列表作为返回值
- [x] 1.2 将完整 `analysis_results` 通过 `config` 的 `configurable` 存入 `_analysis_cache["deployments"]`（复用现有缓存机制）
- [x] 1.3 添加安全术语中性化映射字典，对精简摘要中的文本执行替换
- [x] 1.4 更新 `_next_step_hint`：追加"不要调用 get_kubernetes_resource_yaml，修复方案基于分析数据直接生成"

## 2. YAML 工具过滤

- [x] 2.1 在 `resources.py` 的 `get_kubernetes_resource_yaml` 中，序列化后删除 `metadata.managedFields`
- [x] 2.2 删除顶层 `status` 字段
- [x] 2.3 删除 `metadata.annotations` 中的 `kubectl.kubernetes.io/last-applied-configuration`

## 3. 验证

- [x] 3.1 确认 `generate_repair_report` 仍能从 `_analysis_cache` 读取完整数据生成报告
- [x] 3.2 确认精简摘要 JSON 体积 < 5KB（模拟 30+ deployment 场景）
