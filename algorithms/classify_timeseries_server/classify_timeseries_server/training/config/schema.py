"""配置文件 Schema 定义

定义支持的枚举值和验证规则。
配置值应存储在外部 JSON 文件中。
"""

from typing import List

# 支持的模型类型
SUPPORTED_MODELS: List[str] = [
    "GradientBoosting",
    "RandomForest",
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
