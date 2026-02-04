"""配置文件 Schema 定义"""
from typing import List

# 支持的模型类型
SUPPORTED_MODELS: List[str] = [
    "XGBoost",
]

# 支持的评估指标
SUPPORTED_METRICS: List[str] = [
    "accuracy",
    "f1_weighted",
    "f1_macro",
    "f1_micro",
    "precision_weighted",
    "recall_weighted",
]

# jieba 分词模式
JIEBA_MODES: List[str] = [
    "precise",   # 精确模式
    "full",      # 全模式
    "search",    # 搜索引擎模式
]

# 配置文件必需的顶层键
REQUIRED_TOP_LEVEL_KEYS: List[str] = [
    "model",
    "hyperparams",
    "preprocessing",
    "feature_engineering",
    "mlflow",
]

# 模型配置必需的键
REQUIRED_MODEL_KEYS: List[str] = [
    "type",
    "name",
]

# 超参数配置必需的键
REQUIRED_HYPERPARAMS_KEYS: List[str] = [
    "use_feature_engineering",
    "random_state",
    "max_evals",
    "metric",
    "search_space",
]

# 预处理配置必需的键
REQUIRED_PREPROCESSING_KEYS: List[str] = [
    "jieba_mode",
    "remove_stopwords",
    "remove_punctuation",
]

# 特征工程配置必需的键
REQUIRED_FEATURE_ENGINEERING_KEYS: List[str] = [
    "use_tfidf",
    "use_statistical",
]

# MLflow 配置必需的键
REQUIRED_MLFLOW_KEYS: List[str] = [
    "experiment_name",
]
