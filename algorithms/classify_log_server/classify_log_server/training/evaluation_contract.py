"""日志聚类正式评估契约。"""

EVALUATION_CONTRACT_VERSION = "log-clustering-unsupervised-v1"

UNSUPERVISED_METRICS = (
    "template_quality_score",
    "coverage_rate",
    "template_diversity",
    "num_templates",
)

LEGACY_GROUND_TRUTH_WARNING = " ".join(
    (
        "ground truth 标签 helper 不属于当前正式 Trainer 契约；",
        "当前产品仅支持无监督评估，带标签训练需使用未来版本化 TrainingDataset",
    )
)


class SupervisedEvaluationUnsupported(ValueError):
    """当前正式训练数据契约不支持监督评估。"""

    code = "supervised_evaluation_unsupported"


def require_unsupervised_evaluation(ground_truth) -> None:
    if ground_truth is not None:
        raise SupervisedEvaluationUnsupported(
            "当前正式训练契约仅支持无监督评估；ground truth 尚未纳入 " "Web、Server、数据集发布和稳定 sample ID 契约"
        )
