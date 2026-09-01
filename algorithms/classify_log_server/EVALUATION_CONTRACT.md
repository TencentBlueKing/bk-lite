# 日志聚类评估契约

当前正式训练契约为 `log-clustering-unsupervised-v1`。

## 正式支持范围

BK-Lite Web、Server、数据集发布包和 `UniversalTrainer` 当前只传递日志样本，不传递标签或稳定 sample ID。因此正式训练、验证调参、测试评估和 MLflow 比较只允许以下无监督指标：

- `template_quality_score`
- `coverage_rate`
- `template_diversity`
- `num_templates`

Trainer 会把 `evaluation_contract_version=log-clustering-unsupervised-v1` 写入 MLflow 参数和训练结果。不同评估契约的分数不得直接比较。

## Ground truth 边界

`LogDataLoader` 中的标签读写 helper 仅为历史实验代码兼容保留，不属于正式 Trainer 契约。显式向模型评估传入 `ground_truth` 会抛出稳定的 `supervised_evaluation_unsupported` 异常，不会静默忽略标签，也不会生成直接比较任意 cluster ID 的 GA、precision、recall 或 F1。

## 未来带标签版本

若产品正式支持带标签训练，应建立新版本 `TrainingDataset`，至少包含日志、标签、稳定 sample ID、train/val/test 切分和完整性摘要；预处理必须保持 sample ID 对齐，监督聚类指标应采用 ARI、NMI 或等价的编号置换不敏感指标，并使用新的 `evaluation_contract_version`。
