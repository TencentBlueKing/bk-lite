"""配置文件 Schema 和默认值定义"""

from typing import List

# 默认配置
DEFAULT_CONFIG = {
    "model": {
        "type": "GradientBoosting",
        "name": "timeseries_model"
    },
    
    "hyperparams": {
        "use_feature_engineering": True,
        "random_state": 42,
        "max_evals": 50,
        "metric": "rmse",
        "search_space": {
            "n_estimators": [50, 100, 200, 300],
            "learning_rate": [0.01, 0.05, 0.1, 0.2],
            "max_depth": [3, 5, 7, 10],
            "min_samples_split": [2, 5, 10],
            "min_samples_leaf": [1, 2, 4],
            "subsample": [0.7, 0.8, 0.9, 1.0],
            "lag_features": [6, 12, 24]
        }
    },
    
    "preprocessing": {
        "handle_missing": "interpolate",
        "max_missing_ratio": 0.3,
        "interpolation_limit": 3
    },
    
    "feature_engineering": {
        "lag_periods": [1, 2, 3, 7, 14],
        "rolling_windows": [7, 14, 30],
        "rolling_features": ["mean", "std", "min", "max"],
        "use_temporal_features": True,
        "use_cyclical_features": False,
        "use_diff_features": True,
        "diff_periods": [1]
    },
    
    "mlflow": {
        "experiment_name": "timeseries_training"
    }
}


# 支持的模型类型
SUPPORTED_MODELS: List[str] = [
    "GradientBoosting",
    "Sarima",
    "Prophet",
    "Xgboost",
    "Lstm"
]


# 支持的优化指标
SUPPORTED_METRICS: List[str] = [
    "rmse",
    "mae",
    "mape"
]


# 支持的缺失值处理方法
SUPPORTED_MISSING_HANDLERS: List[str] = [
    "interpolate",
    "ffill",
    "bfill",
    "drop",
    "median"
]
