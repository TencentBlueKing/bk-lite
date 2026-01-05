"""配置文件 Schema 和默认值定义"""

from typing import List

# 默认配置
DEFAULT_CONFIG = {
    "model": {
        "type": "ECOD",
        "name": "anomaly_model"
    },
    
    "hyperparams": {
        "use_feature_engineering": True,
        "random_state": 42,
        "max_evals": 30,
        "metric": "f1",  # 异常检测优化指标：f1, precision, recall
        "search_space": {
            "contamination": [0.01, 0.05, 0.1, 0.15, 0.2, 0.25]
        }
    },
    
    "preprocessing": {
        "handle_missing": "interpolate",
        "max_missing_ratio": 0.3,
        "interpolation_limit": 3,
        "label_column": "label"  # 标签列名（可选，训练时需要）
    },
    
    "feature_engineering": {
        "lag_periods": [1, 2, 3],
        "rolling_windows": [12, 24, 48],
        "rolling_features": ["mean", "std", "min", "max"],
        "use_temporal_features": True,
        "use_diff_features": True,
        "diff_periods": [1]
    },
    
    "mlflow": {
        "experiment_name": "anomaly_detection_training"
    }
}


# 支持的模型类型
SUPPORTED_MODELS: List[str] = [
    "ECOD",
    # 未来可扩展: "IsolationForest", "LOF", "KNN"
]


# 支持的优化指标
SUPPORTED_METRICS: List[str] = [
    "f1",
    "precision",
    "recall",
    "auc"
]


# 支持的缺失值处理方法
SUPPORTED_MISSING_HANDLERS: List[str] = [
    "interpolate",
    "ffill",
    "bfill",
    "drop",
    "median"
]
