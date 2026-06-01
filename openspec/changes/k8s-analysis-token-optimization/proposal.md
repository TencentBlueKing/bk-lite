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
