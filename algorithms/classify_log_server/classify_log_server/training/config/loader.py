"""
Configuration loader for training pipeline.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

from .schema import SUPPORTED_MODELS, SUPPORTED_METRICS


class ConfigError(Exception):
    """配置错误异常"""
    pass


def get_early_stopping_config(max_evals: int) -> Dict[str, Any]:
    """根据 max_evals 自动计算早停配置
    
    Args:
        max_evals: 最大评估次数
        
    Returns:
        完整的早停配置字典
    """
    if max_evals == 0:
        return {
            "enabled": False
        }
    
    patience = max(5, min(20, int(max_evals * 0.25)))
    min_evals = max(5, int(max_evals * 0.2))
    
    return {
        "enabled": True,
        "patience": patience,
        "min_evals": min_evals,
        "min_evals_ratio": 0.2,
        "min_improvement_pct": 1.0,
        "exploration_ratio": 0.3,
        "exploration_boost": 1.5,
        "loss_cap_multiplier": 5.0
    }


class TrainingConfig:
    """
    Training configuration loader and validator.
    
    Loads configuration from JSON file and provides validation.
    """

    def __init__(self, config_path: str):
        """
        Initialize configuration.

        Args:
            config_path: Path to JSON configuration file (required)
        
        Raises:
            FileNotFoundError: Configuration file not found
            json.JSONDecodeError: Invalid JSON format
        """
        self.config = self._load_config(config_path)
        self._validate_config()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """
        Load configuration from file.

        Args:
            config_path: Path to JSON configuration file

        Returns:
            Configuration dictionary
        
        Raises:
            FileNotFoundError: Configuration file not found
            json.JSONDecodeError: Invalid JSON format
        """
        config_path = Path(config_path)
        
        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}\n"
                f"Please provide a valid configuration file or refer to "
                f"support-files/train.json.example for template"
            )

        logger.info(f"Loading configuration from {config_path}")
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"Invalid JSON in configuration file: {config_path}",
                e.doc,
                e.pos
            )

        return config

    def _validate_config(self):
        """多层配置验证"""
        # Layer 1: 结构完整性校验
        self._validate_structure()
        
        # Layer 2: 必需字段 + 基本类型校验
        self._validate_required_fields()
        
        # Layer 3: 业务规则校验
        self._validate_business_rules()
        
        # Layer 4: 依赖关系校验
        self._validate_dependencies()
        
        logger.info("Configuration validation passed")
    
    def _validate_structure(self):
        """Layer 1: 结构完整性校验"""
        required_sections = ["model", "hyperparams", "preprocessing", "mlflow"]
        
        for section in required_sections:
            if section not in self.config:
                raise ConfigError(f"配置缺少必需的顶层字段: {section}")
        
        # 条件依赖：如果启用特征工程，必须提供 feature_engineering 配置
        use_fe = self.config.get("hyperparams", {}).get("use_feature_engineering")
        if use_fe is True:
            if "feature_engineering" not in self.config:
                raise ConfigError(
                    "hyperparams.use_feature_engineering=true 时，"
                    "必须提供 feature_engineering 配置段"
                )
    
    def _validate_required_fields(self):
        """Layer 2: 必需字段 + 基本类型校验"""
        # model 配置
        model = self.config.get("model", {})
        if "type" not in model:
            raise ConfigError("model.type 为必填项")
        if "name" not in model:
            raise ConfigError("model.name 为必填项")
        
        # hyperparams 配置
        hp = self.config.get("hyperparams", {})
        required_hp_fields = {
            "use_feature_engineering": bool,
            "random_state": int,
            "max_evals": int,
            "metric": str,
            "search_space": dict
        }
        
        for field, expected_type in required_hp_fields.items():
            if field not in hp:
                raise ConfigError(f"hyperparams.{field} 为必填项")
            if not isinstance(hp[field], expected_type):
                raise ConfigError(
                    f"hyperparams.{field} 类型错误: "
                    f"期望 {expected_type.__name__}, 实际 {type(hp[field]).__name__}"
                )
        
        if hp["max_evals"] < 0:
            raise ConfigError(f"hyperparams.max_evals 必须 >= 0，当前值: {hp['max_evals']}")
    
    def _validate_business_rules(self):
        """Layer 3: 业务规则校验"""
        # 验证模型类型
        model_type = self.config["model"]["type"]
        if model_type not in SUPPORTED_MODELS:
            raise ConfigError(
                f"不支持的模型类型: {model_type}. "
                f"支持的类型: {SUPPORTED_MODELS}"
            )
        
        # 验证优化指标
        metric = self.config["hyperparams"]["metric"]
        if metric not in SUPPORTED_METRICS:
            raise ConfigError(
                f"不支持的优化指标: {metric}. "
                f"支持的指标: {SUPPORTED_METRICS}"
            )
        
        # 验证搜索空间
        search_space = self.config["hyperparams"]["search_space"]
        if not search_space:
            raise ConfigError("hyperparams.search_space 不能为空")
        
        # 验证 tau 参数
        if "tau" in search_space:
            tau_values = search_space["tau"]
            if not isinstance(tau_values, list) or not tau_values:
                raise ConfigError("hyperparams.search_space.tau 必须是非空列表")
            
            for tau in tau_values:
                if not isinstance(tau, (int, float)) or tau <= 0 or tau > 1:
                    raise ConfigError(f"tau 值必须在 (0, 1] 范围内: {tau}")
        
        # 验证 merge_threshold 参数（可选）
        if "merge_threshold" in search_space:
            merge_values = search_space["merge_threshold"]
            if not isinstance(merge_values, list) or not merge_values:
                raise ConfigError("hyperparams.search_space.merge_threshold 必须是非空列表")
            
            for merge in merge_values:
                if not isinstance(merge, (int, float)) or merge <= 0 or merge > 1:
                    raise ConfigError(f"merge_threshold 值必须在 (0, 1] 范围内: {merge}")
        
        # 验证 diversity_threshold 参数（可选）
        if "diversity_threshold" in search_space:
            div_values = search_space["diversity_threshold"]
            if not isinstance(div_values, list) or not div_values:
                raise ConfigError("hyperparams.search_space.diversity_threshold 必须是非空列表")
            
            for div in div_values:
                if not isinstance(div, (int, float)) or div < 1:
                    raise ConfigError(f"diversity_threshold 值必须 >= 1: {div}")
    
    def _validate_dependencies(self):
        """Layer 4: 依赖关系校验"""
        # 暂无依赖校验
        
        # 验证特征工程依赖
        use_fe = self.config.get("hyperparams", {}).get("use_feature_engineering")
        if use_fe:
            fe_config = self.config.get("feature_engineering", {})
            time_features = fe_config.get("time_features", {})
            if time_features.get("enable") and not time_features.get("datetime_column"):
                raise ConfigError(
                    "feature_engineering.time_features.enable=true 时，"
                    "必须提供 datetime_column"
                )

    def get(self, *keys, default=None) -> Any:
        """获取配置项（支持多级访问）
        
        Args:
            *keys: 配置路径，如 get("model", "type")
            default: 默认值
            
        Returns:
            配置值，如果不存在返回 default
            
        Example:
            config.get("model", "type")  # "Spell"
            config.get("hyperparams", "search_space", "tau")  # [0.4, 0.45, ...]
            config.get("unknown", "key", default="fallback")  # "fallback"
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return default
            else:
                return default
        return value

    def set(self, *keys, value):
        """设置配置项（支持多级访问）
        
        Args:
            *keys: 配置路径，如 set("model", "type", value="Spell")
            value: 要设置的值
            
        Example:
            config.set("model", "type", value="Spell")
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
        """
        Get configuration as dictionary.

        Returns:
            Configuration dictionary
        """
        return self.config.copy()

    def save(self, output_path: str):
        """
        Save configuration to JSON file.

        Args:
            output_path: Output file path
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

        logger.info(f"Configuration saved to {output_path}")

    @property
    def model_type(self) -> str:
        """Get model type."""
        return self.config["model"]["type"]

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self.config["model"].get("name", "spell_log_clustering")

    @property
    def mlflow_tracking_uri(self) -> Optional[str]:
        """MLflow 跟踪服务 URI（运行时从环境变量注入）"""
        return self.get("mlflow", "tracking_uri")
    
    @property
    def mlflow_experiment_name(self) -> str:
        """MLflow 实验名称"""
        return self.config["mlflow"]["experiment_name"]
    
    @property
    def mlflow_run_name(self) -> Optional[str]:
        """MLflow run 名称"""
        return self.config["mlflow"].get("run_name")
    
    @property
    def max_evals(self) -> int:
        """Get max evaluations for hyperparameter search."""
        return self.config["hyperparams"].get("max_evals", 0)
    
    @property
    def early_stopping_config(self) -> Dict[str, Any]:
        """获取早停配置（自动计算）"""
        hp = self.config.get("hyperparams", {})
        
        # 如果用户显式配置了 early_stopping，使用用户配置
        if "early_stopping" in hp:
            return hp["early_stopping"]
        
        # 否则根据 max_evals 自动计算
        return get_early_stopping_config(self.max_evals)
    
    def get_hyperopt_config(self) -> Dict[str, Any]:
        """获取完整的超参数优化配置
        
        Returns:
            包含 max_evals, metric, search_space, early_stopping 的字典
        """
        hp = self.config.get("hyperparams", {})
        
        return {
            "max_evals": hp.get("max_evals", 0),
            "metric": hp.get("metric", "template_quality_score"),
            "search_space": hp.get("search_space", {}),
            "early_stopping": self.early_stopping_config
        }
    
    @property
    def use_feature_engineering(self) -> bool:
        """是否启用特征工程"""
        return self.config["hyperparams"]["use_feature_engineering"]
    
    @property
    def feature_engineering_config(self) -> Dict[str, Any]:
        """获取特征工程配置"""
        if not self.use_feature_engineering:
            return {}
        return self.config.get("feature_engineering", {})
