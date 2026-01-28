"""训练配置加载器"""

from typing import Dict, Any, Optional
from pathlib import Path
import json
from loguru import logger

from .schema import SUPPORTED_MODELS, SUPPORTED_METRICS, SUPPORTED_MISSING_HANDLERS


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
        "loss_cap_multiplier": 5.0,
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
        "search_space": dict,
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

    if hp["metric"] not in SUPPORTED_METRICS:
        raise ConfigError(
            f"hyperparams.metric 必须是以下之一: {SUPPORTED_METRICS}，"
            f"当前值: {hp['metric']}"
        )

    # search_space 配置
    ss = hp.get("search_space", {})
    required_params = ["contamination"]

    for param in required_params:
        if param not in ss:
            raise ConfigError(f"hyperparams.search_space.{param} 为必填项")
        if not isinstance(ss[param], list) or len(ss[param]) == 0:
            raise ConfigError(f"hyperparams.search_space.{param} 必须是非空列表")

    # feature_engineering 配置（条件依赖）
    if hp["use_feature_engineering"]:
        fe = config.get("feature_engineering", {})
        required_fe_fields = {
            "lag_periods": list,
            "rolling_windows": list,
            "rolling_features": list,
            "use_temporal_features": bool,
            "use_diff_features": bool,
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

    if pp["handle_missing"] not in SUPPORTED_MISSING_HANDLERS:
        raise ConfigError(
            f"preprocessing.handle_missing 必须是以下之一: {SUPPORTED_MISSING_HANDLERS}，"
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
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            return config

        except json.JSONDecodeError as e:
            raise json.JSONDecodeError(f"配置文件格式错误: {config_path}", e.doc, e.pos)
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
            config.get("model", "type")  # "ECOD"
            config.get("hyperparams", "search_space", "contamination")  # [0.01, 0.05, ...]
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
            config.set("model", "type", value="ECOD")
        """
        if len(keys) < 1:
            raise ValueError("至少需要一个键")

        target = self.config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        target[keys[-1]] = value

    # 便捷属性访问
    @property
    def model_type(self) -> str:
        """模型类型"""
        return self.config["model"]["type"]

    @property
    def model_name(self) -> str:
        """模型名称"""
        return self.config["model"]["name"]

    @property
    def use_feature_engineering(self) -> bool:
        """是否使用特征工程"""
        return self.config["hyperparams"]["use_feature_engineering"]

    @property
    def random_state(self) -> int:
        """随机种子"""
        return self.config["hyperparams"]["random_state"]

    @property
    def max_evals(self) -> int:
        """最大评估次数"""
        return self.config["hyperparams"]["max_evals"]

    @property
    def metric(self) -> str:
        """优化指标"""
        return self.config["hyperparams"]["metric"]

    @property
    def search_space(self) -> Dict[str, Any]:
        """搜索空间"""
        return self.config["hyperparams"]["search_space"]

    @property
    def preprocessing_config(self) -> Dict[str, Any]:
        """预处理配置"""
        return self.config["preprocessing"]

    @property
    def feature_engineering_config(self) -> Dict[str, Any]:
        """特征工程配置"""
        return self.config.get("feature_engineering", {})

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
    def label_column(self) -> Optional[str]:
        """标签列名"""
        return self.config["preprocessing"].get("label_column", "label")

    @property
    def early_stopping_config(self) -> Dict[str, Any]:
        """早停配置"""
        hp = self.config.get("hyperparams", {})
        if "early_stopping" in hp:
            return hp["early_stopping"]
        # 自动生成早停配置
        return get_early_stopping_config(self.max_evals)

    # 配置获取方法（与 timeseries_server 保持一致）
    def get_search_config(self) -> Dict[str, Any]:
        """获取搜索配置

        Returns:
            包含 max_evals, metric, search_space, early_stopping 的字典
        """
        hp = self.config["hyperparams"]
        return {
            "max_evals": hp["max_evals"],
            "metric": hp["metric"],
            "search_space": hp["search_space"],
            "early_stopping": self.early_stopping_config,
        }

    def get_feature_engineering_config(self) -> Optional[Dict[str, Any]]:
        """获取特征工程配置

        Returns:
            特征工程配置字典，如果未启用则返回 None
        """
        if not self.use_feature_engineering:
            return None
        return self.config.get("feature_engineering")

    def get_preprocessing_config(self) -> Dict[str, Any]:
        """获取预处理配置

        Returns:
            预处理配置字典
        """
        return self.config["preprocessing"]

    def get_mlflow_config(self) -> Dict[str, Any]:
        """获取 MLflow 配置

        Returns:
            MLflow 配置字典
        """
        return self.config["mlflow"]

    def to_dict(self) -> Dict[str, Any]:
        """导出配置为字典（浅拷贝）

        Returns:
            配置字典的浅拷贝

        Note:
            使用浅拷贝以提升性能。当前仅用于 MLflow 参数记录（只读场景）。
        """
        return self.config.copy()

    def __repr__(self) -> str:
        """字符串表示"""
        return f"TrainingConfig(model={self.model_type}, metric={self.metric})"
