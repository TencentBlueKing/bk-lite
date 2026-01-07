"""
Default configuration schema for log clustering training.
"""

from typing import List

DEFAULT_CONFIG = {
    "model": {
        "type": "spell",  # 目前只支持 spell
        "name": "spell_log_clustering",  # 模型名称
    },
    "hyperparams": {
        "use_feature_engineering": False,  # 是否启用特征工程
        "random_state": 42,  # 随机种子
        "max_evals": 0,  # 超参数搜索次数，0 表示跳过搜索
        "metric": "template_quality_score",  # 优化目标指标
        "search_space": {
            "tau": [0.5, 0.4, 0.45, 0.55, 0.6],  # LCS 相似度阈值候选值
            # 可选：聚类合并阈值（仅在超参数搜索时使用）
            # "merge_threshold": [0.8, 0.85, 0.9],
            # 可选：Token 多样性阈值（仅在超参数搜索时使用）
            # "diversity_threshold": [2, 3, 4, 5],
        },
    },
    "preprocessing": {
        "remove_digits": False,  # 是否移除数字
        "remove_special_chars": False,  # 是否移除特殊字符
        "lowercase": False,  # 是否转小写
        "custom_regex": [],  # 自定义正则表达式列表，格式: [{"pattern": "regex", "replacement": ""}]
    },
    "feature_engineering": {
        "time_features": {
            "enable": False,
            "datetime_column": "timestamp",  # 时间戳列名
            "cyclical_features": ["hour", "day_of_week"],  # 循环特征
        },
    },
    "mlflow": {
        "experiment_name": "log_clustering_spell",  # MLflow 实验名称
    },
}


# 支持的模型类型
SUPPORTED_MODELS: List[str] = [
    "spell",
    # 未来可扩展: "drain", "logram"
]


# 支持的优化指标
SUPPORTED_METRICS: List[str] = [
    "template_quality_score",
    "coverage_rate",
    "template_diversity",
    "num_templates",
]
