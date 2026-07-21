# Kubernetes 配置分析与修复报告闭环设计

## 目标

在完整扫描 Deployment 的同时保留人工决策点，避免模型漏翻页、提前生成修复对比，或因逐 Deployment 查询 PDB 给 Kubernetes API Server 带来不必要压力。

## 能力边界

- 同时启用 `config_analysis_report` 与 `repair_diff_report`：展示配置分析报告后，必须先让用户选择修复展示方式，再生成修复对比。
- 仅启用 `config_analysis_report`：只展示配置分析报告，不强制询问修复方式。
- 仅启用 `repair_diff_report`：不因配置分析自动进入修复选择流程。
- 两项均未启用：保持基础 Kubernetes 检查流程。

## 扫描流程

1. 工具一次获取目标范围内的 Deployment 列表。
2. 超过 100 个且未指定工作负载时，保持现有保护，要求用户先选择 namespace。
3. 安全范围内按每批最多 50 个处理，但由后端在一次工具调用内确定性完成全部批次，不依赖模型再次传递 `offset`。
4. PDB 按 namespace 只查询一次并缓存，批次和 Deployment 之间复用。
5. 所有批次聚合完成后返回一个完整分析结果，报告只发射一次，`has_more=false`。

## 用户选择流程

当两项 capability 同时启用且分析发现问题时：

1. 发射 `config_analysis_report`。
2. 发射单选问题，选项根据结果动态生成，候选包括按问题类别聚合、按工作负载聚合、全部展示。
3. 等待用户选择。
4. 按选择调用修复报告生成逻辑并发射 `repair_diff_report`。

不得在分析报告后自动生成 summary diff；这会绕过用户选择。

## 异常与性能边界

- Deployment 或 PDB API 查询失败时返回可行动错误，不生成不完整的修复报告。
- PDB API 在某 namespace 不可用时记录告警，该 namespace 的 PDB 建议允许降级，但其他配置检查继续。
- 扫描上限仍为 100；批大小 50 只是内部执行边界，不是报告完整性边界。

## 验收

- 51–100 个 Deployment 在一次工具调用中全部进入分析结果。
- 同一 namespace 的 PDB API 只调用一次。
- 两项 capability 同时启用时先出现用户选择，选择前不发射 `repair_diff_report`。
- 仅启用其中一项时不错误触发专家修复选择。
- 超过 100 个且未限定范围时仍返回 `scope_too_large`。
