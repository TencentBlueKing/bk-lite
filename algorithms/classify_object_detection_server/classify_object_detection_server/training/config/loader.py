"""训练配置加载器."""

from typing import Dict, Any, Optional
from pathlib import Path
import json
from loguru import logger

from .schema import SUPPORTED_MODELS, SUPPORTED_DEVICES


class ConfigError(Exception):
    """配置错误异常."""

    pass


class TrainingConfig:
    """训练配置类.

    加载和管理训练配置，支持JSON配置文件。
    """

    def __init__(self, config_path: str):
        """
        初始化配置加载器.

        Args:
            config_path: 配置文件路径（JSON格式）

        Raises:
            ConfigError: 配置文件不存在或格式错误
        """
        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise ConfigError(f"配置文件不存在: {config_path}")

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            logger.info(f"配置文件加载成功: {config_path}")
        except json.JSONDecodeError as e:
            raise ConfigError(f"配置文件JSON格式错误: {e}")
        except Exception as e:
            raise ConfigError(f"配置文件加载失败: {e}")

        # 验证配置
        self._validate()

    def _validate(self):
        """验证配置的基本结构和必需字段."""
        # 验证顶层字段
        required_sections = ["model", "hyperparams", "mlflow"]
        for section in required_sections:
            if section not in self.config:
                raise ConfigError(f"配置缺少必需的顶层字段: {section}")

        # 验证model配置
        model = self.config.get("model", {})
        if "type" not in model:
            raise ConfigError("model.type为必填项")
        if model["type"] not in SUPPORTED_MODELS:
            raise ConfigError(
                f"不支持的模型类型: {model['type']}, 支持的类型: {SUPPORTED_MODELS}"
            )
        if "name" not in model:
            raise ConfigError("model.name为必填项")

        # 验证hyperparams配置
        hp = self.config.get("hyperparams", {})
        if "model_name" not in hp:
            raise ConfigError("hyperparams.model_name为必填项（如：yolo11n.pt）")
        if "epochs" not in hp:
            raise ConfigError("hyperparams.epochs为必填项")
        if "imgsz" not in hp:
            raise ConfigError("hyperparams.imgsz为必填项")

        # 验证device配置（可选，从hyperparams中读取）
        device = hp.get("device", "auto")
        if device not in SUPPORTED_DEVICES and not self._is_valid_gpu_string(device):
            raise ConfigError(
                f"不支持的设备类型: {device}, 支持的类型: {SUPPORTED_DEVICES} 或 GPU编号（如'0'或'0,1,2,3'）"
            )

        # 验证mlflow配置
        mlflow_config = self.config.get("mlflow", {})
        if "experiment_name" not in mlflow_config:
            raise ConfigError("mlflow.experiment_name为必填项")

        logger.info("配置验证通过")

    def _is_valid_gpu_string(self, device: str) -> bool:
        """
        验证GPU设备字符串是否有效.

        Args:
            device: 设备字符串（如 '0', '0,1,2,3'）

        Returns:
            是否为有效的GPU设备字符串
        """
        if not device:
            return False
        # 检查是否为纯数字或逗号分隔的数字
        parts = device.split(",")
        return all(part.strip().isdigit() for part in parts)

    def get(self, *keys, default=None) -> Any:
        """
        获取配置值（支持嵌套键）.

        Args:
            *keys: 配置键路径
            default: 默认值

        Returns:
            配置值

        Example:
            config.get("hyperparams", "device")  # 获取 hyperparams.device
        """
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def set(self, *keys, value: Any):
        """
        设置配置值（支持嵌套键）.

        Args:
            *keys: 配置键路径
            value: 要设置的值

        Example:
            config.set("mlflow", "tracking_uri", value="http://localhost:5000")
        """
        if len(keys) == 0:
            raise ValueError("至少需要一个键")

        # 导航到目标位置
        target = self.config
        for key in keys[:-1]:
            if key not in target:
                target[key] = {}
            target = target[key]

        # 设置值
        target[keys[-1]] = value
        logger.debug(f"配置已更新: {'.'.join(keys)} = {value}")

    def get_device_config(self) -> str:
        """
        获取设备配置.

        Returns:
            设备类型: 'auto', 'cpu', 'gpu', 'gpus', 或GPU编号（如'0'或'0,1,2,3'）
        """
        return self.get("hyperparams", "device", default="auto")

    @property
    def model_type(self) -> str:
        """模型类型."""
        return self.get("model", "type")

    @property
    def model_name(self) -> str:
        """模型名称（用于MLflow注册）."""
        return self.get("model", "name")

    @property
    def mlflow_experiment_name(self) -> str:
        """MLflow实验名称."""
        exp_name = self.get("mlflow", "experiment_name")
        # 确保返回的是字符串类型
        if not isinstance(exp_name, str):
            logger.warning(
                f"experiment_name类型错误({type(exp_name).__name__})，已转换为字符串"
            )
            exp_name = str(exp_name)
        return exp_name

    @property
    def mlflow_tracking_uri(self) -> Optional[str]:
        """MLflow tracking URI."""
        return self.get("mlflow", "tracking_uri")

    @property
    def mlflow_run_name(self) -> Optional[str]:
        """MLflow run名称."""
        return self.get("mlflow", "run_name")

    @property
    def hyperparams_config(self) -> Dict[str, Any]:
        """超参数配置."""
        return self.get("hyperparams", default={})

    @property
    def preprocessing_config(self) -> Dict[str, Any]:
        """预处理配置."""
        return self.get("preprocessing", default={})

    @property
    def feature_engineering_config(self) -> Dict[str, Any]:
        """特征工程配置."""
        return self.get("feature_engineering", default={})

    @property
    def use_feature_engineering(self) -> bool:
        """是否使用特征工程."""
        return self.get("hyperparams", "use_feature_engineering", default=False)

    def __str__(self) -> str:
        """返回配置的字符串表示."""
        return (
            f"TrainingConfig(model={self.model_type}, "
            f"name={self.model_name}, "
            f"experiment={self.mlflow_experiment_name})"
        )

    def __repr__(self) -> str:
        """返回配置的详细表示."""
        return self.__str__()
