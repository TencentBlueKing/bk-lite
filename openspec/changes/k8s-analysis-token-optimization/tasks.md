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
