"""训练配置加载器"""

from typing import Dict, Any, Optional
from pathlib import Path
import json
from loguru import logger

from .schema import (
    SUPPORTED_MODELS,
    SUPPORTED_METRICS,
    SUPPORTED_MISSING_HANDLERS
)


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
    patience = max(10, min(30, int(max_evals * 0.25)))
    min_evals = max(10, int(max_evals * 0.2))
    
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


def validate_structure(config: Dict) -> None:
    """Layer 1: 结构完整性校验"""
    required_sections = ["model", "hyperparams", "preprocessing", "mlflow"]
    
    for section in required_sections:
        if section not in config:
            raise ConfigError(f"配置缺少必需的顶层字段: {section}")
    
    # 条件依赖
    use_fe = config.get("hyperparams", {}).get("use_feature_engineering")
    if use_fe is True:
        if "feature_engineering" not in config:
            raise ConfigError(
                "hyperparams.use_feature_engineering=true 时，"
                "必须提供 feature_engineering 配置段"
            )


def validate_required_fields(config: Dict) -> None:
    """Layer 2: 必需字段 + 基本类型校验"""
    
    # model 配置
    model = config.get("model", {})
    if "type" not in model:
        raise ConfigError("model.type 为必填项")
    if "name" not in model:
        raise ConfigError("model.name 为必填项")
    
    # hyperparams 配置
    hp = config.get("hyperparams", {})
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
    
    if hp["max_evals"] < 1:
        raise ConfigError(f"hyperparams.max_evals 必须 >= 1，当前值: {hp['max_evals']}")
    
    valid_metrics = ["rmse", "mae", "mape"]
    if hp["metric"] not in valid_metrics:
        raise ConfigError(
            f"hyperparams.metric 必须是以下之一: {valid_metrics}，"
            f"当前值: {hp['metric']}"
        )
    
    # search_space 配置
    ss = hp.get("search_space", {})
    required_params = [
        "n_estimators", "learning_rate", "max_depth",
        "min_samples_split", "min_samples_leaf", "subsample", "lag_features"
    ]
    
    for param in required_params:
        if param not in ss:
            raise ConfigError(f"hyperparams.search_space.{param} 为必填项")
        if not isinstance(ss[param], list) or len(ss[param]) == 0:
            raise ConfigError(
                f"hyperparams.search_space.{param} 必须是非空列表"
            )
    
    # feature_engineering 配置（条件依赖）
    if hp["use_feature_engineering"]:
        fe = config.get("feature_engineering", {})
        required_fe_fields = {
            "lag_periods": list,
            "rolling_windows": list,
            "rolling_features": list,
            "use_temporal_features": bool,
            "use_cyclical_features": bool,
            "use_diff_features": bool
        }
        
        for field, expected_type in required_fe_fields.items():
            if field not in fe:
                raise ConfigError(
                    f"use_feature_engineering=true 时，"
                    f"feature_engineering.{field} 为必填项"
                )
            if not isinstance(fe[field], expected_type):
                raise ConfigError(
                    f"feature_engineering.{field} 类型错误: "
                    f"期望 {expected_type.__name__}, "
                    f"实际 {type(fe[field]).__name__}"
                )
        
        if len(fe["lag_periods"]) == 0:
            raise ConfigError("feature_engineering.lag_periods 不能为空列表")
        if len(fe["rolling_windows"]) == 0:
            raise ConfigError("feature_engineering.rolling_windows 不能为空列表")
        if len(fe["rolling_features"]) == 0:
            raise ConfigError("feature_engineering.rolling_features 不能为空列表")
        
        if fe["use_diff_features"]:
            if "diff_periods" not in fe:
                raise ConfigError(
                    "use_diff_features=true 时，必须提供 diff_periods 字段"
                )
            if not isinstance(fe["diff_periods"], list) or len(fe["diff_periods"]) == 0:
                raise ConfigError("diff_periods 必须是非空列表")
    
    # preprocessing 配置
    pp = config.get("preprocessing", {})
    required_pp_fields = ["handle_missing", "max_missing_ratio", "interpolation_limit"]
    for field in required_pp_fields:
        if field not in pp:
            raise ConfigError(f"preprocessing.{field} 为必填项")
    
    valid_handlers = ["interpolate", "ffill", "bfill", "drop", "median"]
    if pp["handle_missing"] not in valid_handlers:
        raise ConfigError(
            f"preprocessing.handle_missing 必须是以下之一: {valid_handlers}，"
            f"当前值: {pp['handle_missing']}"
        )
    
    # mlflow 配置
    mlflow_cfg = config.get("mlflow", {})
    if "experiment_name" not in mlflow_cfg:
        raise ConfigError("mlflow.experiment_name 为必填项")


class TrainingConfig:
    """训练配置管理器
    
    支持：
    - 从 JSON 文件加载配置
    - 严格配置验证（2层校验）
    - 便捷的访问接口
    """
    
    def __init__(self, config_path: str):
        """初始化配置管理器
        
        Args:
            config_path: train.json 配置文件路径（必需）
        
        Raises:
            FileNotFoundError: 配置文件不存在
            json.JSONDecodeError: 配置文件格式错误
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self._validate()
        
        logger.info(f"✓ 配置加载并校验完成 - 模型: {self.model_type}")
    
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """加载配置文件
        
        Args:
            config_path: 配置文件路径（必需）
            
        Returns:
            配置字典
        
        Raises:
            FileNotFoundError: 配置文件不存在
            json.JSONDecodeError: 配置文件格式错误
        """
        config_file = Path(config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {config_path}\n"
                f"请提供有效的配置文件或参考 support-files/train.json.example"
            )
        
        try:
            logger.info(f"加载配置文件: {config_path}")
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            return config
            
        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(
                f"配置文件格式错误: {config_path}",
                e.doc,
                e.pos
            )
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
    
    def _validate(self):
        """执行2层配置校验"""
        validate_structure(self.config)
        validate_required_fields(self.config)
    
    def get(self, *keys, default=None) -> Any:
        """获取配置项（支持多级访问）
        
        Args:
            *keys: 配置路径，如 get("model", "type")
            default: 默认值
            
        Returns:
            配置值，如果不存在返回 default
            
        Example:
            config.get("model", "type")  # "sarima"
            config.get("hyperparams", "search", "enabled")  # True
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
            *keys: 配置路径
            value: 要设置的值
            
        Example:
            config.set("model", "type", value="xgboost")
        """
        if len(keys) == 0:
            raise ValueError("至少需要一个键")
        
        target = self.config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]
        
        target[keys[-1]] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """返回完整配置字典"""
        return copy.deepcopy(self.config)
    
    # ===== 便捷属性访问 =====
    
    @property
    def model_type(self) -> str:
        """模型类型"""
        return self.config["model"]["type"]
    
    @property
    def model_name(self) -> str:
        """模型名称"""
        return self.config["model"]["name"]
    
    @property
    def test_size(self) -> float:
        """测试集划分比例（固定值）"""
        return 0.2
    
    @property
    def validation_size(self) -> float:
        """验证集划分比例（固定值）"""
        return 0.1
    
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
        """MLflow run 名称（可选，命令行注入）"""
        return self.get("mlflow", "run_name")
    
    @property
    def use_feature_engineering(self) -> bool:
        """是否使用完整特征工程"""
        return self.config["hyperparams"]["use_feature_engineering"]
    
    @property
    def max_evals(self) -> int:
        """超参数搜索最大评估次数"""
        return self.config["hyperparams"]["max_evals"]
    
    @property
    def early_stopping_config(self) -> Dict[str, Any]:
        """自动计算的早停配置"""
        return get_early_stopping_config(self.max_evals)
    
    # ===== 配置访问方法 =====
    
    def get_model_params(self) -> Dict[str, Any]:
        """获取模型参数（非搜索参数）"""
        hp = self.config["hyperparams"]

        # 向后兼容：对于传统模型（如 GradientBoosting、RandomForest），
        # 仅返回通用标志位和 random_state
        if self.model_type not in ("Prophet",):
            return {
                "use_feature_engineering": hp["use_feature_engineering"],
                "random_state": hp["random_state"]
            }

        # 对于 Prophet（以及未来的原生时间序列模型），返回 hyperparams
        # 中的所有模型参数（排除搜索相关字段），以便调用方用配置中的
        # 默认值构建模型。search_space 仍然作为超参数搜索的唯一来源。
        exclude_keys = {"max_evals", "metric", "search_space"}

        prophet_params: Dict[str, Any] = {
            k: v for k, v in hp.items() if k not in exclude_keys
        }

        # Ensure random_state present (keeps behaviour consistent)
        if "random_state" not in prophet_params and "random_state" in hp:
            prophet_params["random_state"] = hp["random_state"]

        return prophet_params
    
    def get_search_config(self) -> Dict[str, Any]:
        """获取搜索配置"""
        hp = self.config["hyperparams"]
        return {
            "max_evals": hp["max_evals"],
            "metric": hp["metric"],
            "search_space": hp["search_space"],
            "early_stopping": self.early_stopping_config
        }
    
    def get_feature_engineering_config(self) -> Optional[Dict[str, Any]]:
        """获取特征工程配置"""
        if not self.use_feature_engineering:
            return None
        return self.config.get("feature_engineering")
    
    def get_preprocessing_config(self) -> Dict[str, Any]:
        """获取预处理配置"""
        return self.config["preprocessing"]
    
    def get_mlflow_config(self) -> Dict[str, Any]:
        """获取 MLflow 配置"""
        return self.config["mlflow"]
    
    def __repr__(self) -> str:
        return (
            f"TrainingConfig("
            f"model_type='{self.model_type}', "
            f"use_fe={self.use_feature_engineering}, "
            f"max_evals={self.max_evals})"
        )