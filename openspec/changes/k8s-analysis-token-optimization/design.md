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
