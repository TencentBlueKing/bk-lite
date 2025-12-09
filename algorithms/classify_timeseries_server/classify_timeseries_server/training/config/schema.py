"""配置文件 Schema 和默认值定义"""

from typing import List

# 默认配置
DEFAULT_CONFIG = {
    "model": {
        "type": "sarima",
        "name": "timeseries_model",
        "version": "1.0.0"
    },
    
    "hyperparams": {
        "search": {
            "enabled": False,
            "max_evals": 50,
            "metric": "rmse",
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
                    "s": [12, 24, 7]
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
    
    "training": {
        "test_size": 0.2,
        "validation_size": 0.0,
        "epochs": 100,
        "batch_size": 32,
        "early_stopping": {
            "enabled": False,
            "patience": 10,
            "min_delta": 0.001
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
        "tracking_uri": None,
        "experiment_name": "timeseries_training",
        "run_name": None,
        "log_model": True,
        "register_model": True
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
