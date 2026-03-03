"""训练配置加载器"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from loguru import logger

from .schema import (
    SUPPORTED_MODELS,
    SUPPORTED_METRICS,
    JIEBA_MODES,
    REQUIRED_TOP_LEVEL_KEYS,
    REQUIRED_MODEL_KEYS,
    REQUIRED_HYPERPARAMS_KEYS,
    REQUIRED_PREPROCESSING_KEYS,
    REQUIRED_FEATURE_ENGINEERING_KEYS,
    REQUIRED_MLFLOW_KEYS,
)


class ConfigError(Exception):
    """配置错误异常"""

    pass


class TrainingConfig:
    """训练配置加载器

    实现4层配置验证：
    1. Layer 1: 结构完整性验证
    2. Layer 2: 必需字段和类型验证
    3. Layer 3: 业务规则验证
    4. Layer 4: 依赖关系验证
    """

    def __init__(self, config_path: str):
        """加载并验证训练配置

        Args:
            config_path: 配置文件路径（JSON 格式）

        Raises:
            FileNotFoundError: 配置文件不存在
            ConfigError: 配置验证失败
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        logger.info(f"加载训练配置: {config_path}")

        # 加载配置文件
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 执行4层验证
        self._validate_config()

        logger.info("配置验证通过")

    def _validate_config(self):
        """执行4层配置验证"""
        self._validate_structure()  # Layer 1
        self._validate_required_fields()  # Layer 2
        self._validate_business_rules()  # Layer 3
        self._validate_dependencies()  # Layer 4

    def _validate_structure(self):
        """Layer 1: 结构完整性验证

        验证配置文件包含所有必需的顶层键。
        """
        logger.debug("执行 Layer 1: 结构完整性验证")

        missing_keys = [
            key for key in REQUIRED_TOP_LEVEL_KEYS if key not in self.config
        ]

        if missing_keys:
            raise ConfigError(f"配置文件缺少必需的顶层键: {missing_keys}")

    def _validate_required_fields(self):
        """Layer 2: 必需字段和类型验证

        验证每个部分包含必需的字段，并检查类型。
        """
        logger.debug("执行 Layer 2: 必需字段和类型验证")

        # 验证 model 部分
        model_config = self.config.get("model", {})
        missing_model_keys = [
            key for key in REQUIRED_MODEL_KEYS if key not in model_config
        ]
        if missing_model_keys:
            raise ConfigError(f"model 配置缺少必需字段: {missing_model_keys}")

        # 验证 hyperparams 部分
        hyperparams_config = self.config.get("hyperparams", {})
        missing_hyperparams_keys = [
            key for key in REQUIRED_HYPERPARAMS_KEYS if key not in hyperparams_config
        ]
        if missing_hyperparams_keys:
            raise ConfigError(
                f"hyperparams 配置缺少必需字段: {missing_hyperparams_keys}"
            )

        # 验证 preprocessing 部分
        preprocessing_config = self.config.get("preprocessing", {})
        missing_preprocessing_keys = [
            key
            for key in REQUIRED_PREPROCESSING_KEYS
            if key not in preprocessing_config
        ]
        if missing_preprocessing_keys:
            raise ConfigError(
                f"preprocessing 配置缺少必需字段: {missing_preprocessing_keys}"
            )

        # 验证 feature_engineering 部分
        feature_engineering_config = self.config.get("feature_engineering", {})
        missing_fe_keys = [
            key
            for key in REQUIRED_FEATURE_ENGINEERING_KEYS
            if key not in feature_engineering_config
        ]
        if missing_fe_keys:
            raise ConfigError(
                f"feature_engineering 配置缺少必需字段: {missing_fe_keys}"
            )

        # 验证 mlflow 部分
        mlflow_config = self.config.get("mlflow", {})
        missing_mlflow_keys = [
            key for key in REQUIRED_MLFLOW_KEYS if key not in mlflow_config
        ]
        if missing_mlflow_keys:
            raise ConfigError(f"mlflow 配置缺少必需字段: {missing_mlflow_keys}")

        # 类型验证
        if not isinstance(model_config.get("type"), str):
            raise ConfigError("model.type 必须是字符串")

        if not isinstance(hyperparams_config.get("use_feature_engineering"), bool):
            raise ConfigError("hyperparams.use_feature_engineering 必须是布尔值")

        if not isinstance(hyperparams_config.get("random_state"), int):
            raise ConfigError("hyperparams.random_state 必须是整数")

        if not isinstance(hyperparams_config.get("max_evals"), int):
            raise ConfigError("hyperparams.max_evals 必须是整数")

        if not isinstance(preprocessing_config.get("remove_stopwords"), bool):
            raise ConfigError("preprocessing.remove_stopwords 必须是布尔值")

    def _validate_business_rules(self):
        """Layer 3: 业务规则验证

        验证配置值符合业务逻辑和约束。
        """
        logger.debug("执行 Layer 3: 业务规则验证")

        # 验证模型类型
        model_type = self.config["model"]["type"]
        if model_type not in SUPPORTED_MODELS:
            raise ConfigError(
                f"不支持的模型类型: '{model_type}'. 支持的模型: {SUPPORTED_MODELS}"
            )

        # 验证优化指标
        metric = self.config["hyperparams"]["metric"]
        if metric not in SUPPORTED_METRICS:
            raise ConfigError(
                f"不支持的优化指标: '{metric}'. 支持的指标: {SUPPORTED_METRICS}"
            )

        # 验证 max_evals
        max_evals = self.config["hyperparams"]["max_evals"]
        if max_evals < 1:
            raise ConfigError(f"hyperparams.max_evals 必须 >= 1，当前: {max_evals}")

        # 验证 jieba 分词模式
        jieba_mode = self.config["preprocessing"]["jieba_mode"]
        if jieba_mode not in JIEBA_MODES:
            raise ConfigError(
                f"不支持的 jieba 分词模式: '{jieba_mode}'. 支持的模式: {JIEBA_MODES}"
            )

        # 验证特征工程配置
        use_tfidf = self.config["feature_engineering"]["use_tfidf"]
        use_statistical = self.config["feature_engineering"]["use_statistical"]
        if not use_tfidf and not use_statistical:
            raise ConfigError(
                "必须至少启用一种特征类型（use_tfidf 或 use_statistical）"
            )

        # 验证 TF-IDF 配置（如果启用）
        if use_tfidf:
            tfidf_config = self.config["feature_engineering"].get("tfidf", {})
            max_features = tfidf_config.get("max_features", 5000)
            if max_features < 100:
                raise ConfigError(
                    f"tfidf.max_features 建议 >= 100，当前: {max_features}"
                )

        # 验证搜索空间
        search_space = self.config["hyperparams"].get("search_space", {})
        if not search_space:
            logger.warning("未定义超参数搜索空间，将使用默认值")

    def _validate_dependencies(self):
        """Layer 4: 依赖关系验证

        验证配置项之间的依赖关系。
        """
        logger.debug("执行 Layer 4: 依赖关系验证")

        # 验证 use_feature_engineering
        use_fe = self.config["hyperparams"]["use_feature_engineering"]
        if not use_fe:
            # 如果禁用特征工程，警告用户可能影响性能
            logger.warning(
                "use_feature_engineering=false 将跳过TF-IDF和统计特征提取，可能影响模型性能"
            )

        # 如果启用 TF-IDF，必须提供 tfidf 配置
        use_tfidf = self.config["feature_engineering"]["use_tfidf"]
        if use_tfidf and use_fe:
            if "tfidf" not in self.config["feature_engineering"]:
                raise ConfigError("启用 use_tfidf 时必须提供 tfidf 配置")

        # 如果启用统计特征，可以提供 statistical_features 配置
        use_statistical = self.config["feature_engineering"]["use_statistical"]
        if use_statistical:
            stat_features = self.config["feature_engineering"].get(
                "statistical_features", []
            )
            if stat_features and not isinstance(stat_features, list):
                raise ConfigError("statistical_features 必须是列表")

        # 验证超参数搜索空间的值类型
        search_space = self.config["hyperparams"].get("search_space", {})
        for key, value in search_space.items():
            if not isinstance(value, list):
                raise ConfigError(
                    f"搜索空间 '{key}' 的值必须是列表，当前类型: {type(value)}"
                )
            if len(value) == 0:
                raise ConfigError(f"搜索空间 '{key}' 不能为空列表")

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项

        Args:
            key: 配置键（支持点号分隔的嵌套键，如 "model.type"）
            default: 默认值

        Returns:
            配置值
        """
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, *keys, value):
        """设置配置项（支持多级访问）

        Args:
            *keys: 配置路径，如 set("mlflow", "tracking_uri", value="http://...")
            value: 要设置的值

        Example:
            config.set("mlflow", "tracking_uri", value="http://mlflow:5000")
        """
        if len(keys) < 1:
            raise ValueError("至少需要一个键")

        target = self.config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value

    def to_dict(self) -> Dict[str, Any]:
        """导出配置为字典（浅拷贝）

        Returns:
            配置字典的浅拷贝

        Note:
            使用浅拷贝以提升性能。当前仅用于 MLflow 参数记录（只读场景）。
        """
        return self.config.copy()

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问

        Args:
            key: 配置键

        Returns:
            配置值
        """
        return self.config[key]

    def __contains__(self, key: str) -> bool:
        """支持 in 操作符

        Args:
            key: 配置键

        Returns:
            是否包含该键
        """
        return key in self.config

    @property
    def mlflow_tracking_uri(self) -> Optional[str]:
        """MLflow 跟踪服务 URI（运行时从环境变量注入）

        Returns:
            MLflow tracking URI，由 bootstrap 从环境变量动态注入
        """
        return self.config["mlflow"].get("tracking_uri")

    @property
    def mlflow_experiment_name(self) -> str:
        """MLflow 实验名称

        Returns:
            实验名称
        """
        return self.config["mlflow"]["experiment_name"]

    @property
    def mlflow_run_name(self) -> Optional[str]:
        """MLflow run 名称

        Returns:
            Run 名称，如果未配置则返回 None
        """
        return self.config["mlflow"].get("run_name")
