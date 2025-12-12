"""配置文件 Schema 和默认值定义"""

from typing import List

# 默认配置
DEFAULT_CONFIG = {
    "model": {
        "type": "gradient_boosting",
        "name": "timeseries_model"
    },
    
    "hyperparams": {
        "search": {
            "enabled": False,
            "max_evals": 50,
            "metric": "rmse",
            "auto_tune": True,
            "early_stopping": {
                "enabled": True,
                "min_evals": 20,
                "min_evals_ratio": 0.2,
                "patience": 15,
                "min_improvement_pct": 1.0,
                "exploration_ratio": 0.3,
                "exploration_boost": 1.5,
                "loss_cap_multiplier": 5.0
            },
            "search_space": {
                "order": {
                    "p": [0, 1, 2],
                    "d": [0, 1, 2],
                    "q": [0, 1, 2]
                },
                "seasonal_order": {
                    "P": [0, 1, 2],
                    "D": [0, 1],
                    "Q": [0, 1, 2],
                    "s": [12]
                },
                "trend": ["n", "c", "t", "ct"]
            }
        },
        "fixed": {
            "order": [1, 1, 1],
            "seasonal_order": [1, 1, 1, 12],
            "trend": "c"
        }
    },
    
    "preprocessing": {
        "handle_missing": "interpolate",
        "max_missing_ratio": 0.3,
        "interpolation_limit": 3,
        "detect_outliers": False,
        "normalize": False
    },
    
    "feature_engineering": {
        "enabled": False,
        "lag_features": [1, 2, 3, 7, 14],
        "rolling_features": {
            "windows": [7, 14, 30],
            "functions": ["mean", "std", "min", "max"]
        },
        "time_features": ["hour", "day_of_week", "month"]
    },
    
    "mlflow": {
        "experiment_name": "timeseries_training"
    }
}


# 支持的模型类型
SUPPORTED_MODELS: List[str] = [
    "sarima",
    "prophet",
    "xgboost",
    "lstm"
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
