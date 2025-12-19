"""训练配置加载器"""

from typing import Dict, Any, Optional
from pathlib import Path
import json
import copy
from loguru import logger

from .schema import (
    DEFAULT_CONFIG,
    SUPPORTED_MODELS,
    SUPPORTED_METRICS,
    SUPPORTED_MISSING_HANDLERS
)


class TrainingConfig:
    """训练配置管理器
    
    支持：
    - 从 JSON 文件加载配置
    - 与默认配置深度合并
    - 配置验证（宽松模式）
    - 便捷的多级访问接口
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """初始化配置管理器
        
        Args:
            config_path: train.json 配置文件路径
                        None 则使用默认配置
                        "./support-files/train.json" 为推荐位置
        """
        self.config_path = config_path
        self.config = self._load_config(config_path)
        self._validate_config()
        
        logger.info(f"配置加载完成 - 模型类型: {self.model_type}")
    
    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        """加载配置文件
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            配置字典
        """
        # 使用默认配置作为基础
        config = copy.deepcopy(DEFAULT_CONFIG)
        
        if config_path is None:
            logger.info("未指定配置文件，使用默认配置")
            return config
        
        config_file = Path(config_path)
        if not config_file.exists():
            logger.warning(f"配置文件不存在: {config_path}，使用默认配置")
            return config
        
        try:
            logger.info(f"加载配置文件: {config_path}")
            with open(config_file, 'r', encoding='utf-8') as f:
                custom_config = json.load(f)
            
            # 深度合并配置
            merged_config = self._deep_merge(config, custom_config)
            logger.debug(f"配置合并完成")
            
            return merged_config
            
        except json.JSONDecodeError as e:
            logger.error(f"配置文件格式错误: {e}")
            raise ValueError(f"无效的 JSON 配置文件: {config_path}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise
    
    def _deep_merge(self, base: Dict, custom: Dict) -> Dict:
        """深度合并两个字典
        
        Args:
            base: 基础配置（默认配置）
            custom: 自定义配置（用户配置）
            
        Returns:
            合并后的配置
        """
        merged = copy.deepcopy(base)
        
        for key, value in custom.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                # 递归合并嵌套字典
                merged[key] = self._deep_merge(merged[key], value)
            else:
                # 直接覆盖或添加新键
                merged[key] = value
                if key not in base:
                    logger.debug(f"配置中包含额外字段: {key}")
        
        return merged
    
    def _validate_config(self):
        """验证配置合法性（宽松模式）
        
        只验证必需字段和关键约束，允许额外字段存在
        """
        # 1. 验证模型类型
        model_type = self.get("model", "type")
        if not model_type:
            raise ValueError("配置中缺少 model.type 字段")
        
        if model_type not in SUPPORTED_MODELS:
            logger.warning(
                f"模型类型 '{model_type}' 不在支持列表中 {SUPPORTED_MODELS}，"
                f"可能需要自定义实现"
            )
        
        # 2. 验证优化指标
        metric = self.get("hyperparams", "search", "metric")
        if metric and metric not in SUPPORTED_METRICS:
            logger.warning(
                f"优化指标 '{metric}' 不在支持列表中 {SUPPORTED_METRICS}"
            )
        
        # 3. 验证缺失值处理方法
        missing_handler = self.get("preprocessing", "handle_missing")
        if missing_handler and missing_handler not in SUPPORTED_MISSING_HANDLERS:
            logger.warning(
                f"缺失值处理方法 '{missing_handler}' 不在支持列表中 "
                f"{SUPPORTED_MISSING_HANDLERS}"
            )
        
        # 4. 验证数值范围
        test_size = self.get("training", "test_size")
        if test_size and not (0 < test_size < 1):
            raise ValueError(f"test_size 必须在 (0, 1) 范围内，当前值: {test_size}")
        
        val_size = self.get("training", "validation_size")
        if val_size and not (0 <= val_size < 1):
            raise ValueError(f"validation_size 必须在 [0, 1) 范围内，当前值: {val_size}")
        
        max_missing = self.get("preprocessing", "max_missing_ratio")
        if max_missing and not (0 <= max_missing <= 1):
            raise ValueError(f"max_missing_ratio 必须在 [0, 1] 范围内，当前值: {max_missing}")
        
        logger.debug("配置验证通过")
    
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
        return self.get("model", "type", default="sarima")
    
    @property
    def model_name(self) -> str:
        """模型名称"""
        return self.get("model", "name", default="timeseries_model")
    
    @property
    def is_hyperopt_enabled(self) -> bool:
        """是否启用超参数优化"""
        return self.get("hyperparams", "search", "enabled", default=False)
    
    @property
    def hyperopt_max_evals(self) -> int:
        """超参数优化最大评估次数"""
        return self.get("hyperparams", "search", "max_evals", default=50)
    
    @property
    def hyperopt_metric(self) -> str:
        """超参数优化目标指标"""
        return self.get("hyperparams", "search", "metric", default="rmse")
    
    @property
    def test_size(self) -> float:
        """测试集划分比例（固定值，单文件模式使用）"""
        return 0.2
    
    @property
    def validation_size(self) -> float:
        """验证集划分比例（固定值，单文件模式使用）"""
        return 0.1
    
    @property
    def mlflow_tracking_uri(self) -> Optional[str]:
        """MLflow 跟踪服务 URI（运行时从环境变量注入）"""
        return self.get("mlflow", "tracking_uri")
    
    @property
    def mlflow_experiment_name(self) -> str:
        """MLflow 实验名称（配置文件中或运行时注入）"""
        value = self.get("mlflow", "experiment_name")
        if not value:
            raise ValueError(
                "未配置 mlflow.experiment_name。\n"
                "请在配置文件的 mlflow 块中添加 experiment_name 字段。"
            )
        return value
    
    @property
    def mlflow_run_name(self) -> Optional[str]:
        """MLflow 运行名称（可选，运行时注入）"""
        return self.get("mlflow", "run_name")
    
    def __repr__(self) -> str:
        return (
            f"TrainingConfig("
            f"model_type='{self.model_type}', "
            f"model_name='{self.model_name}', "
            f"config_path='{self.config_path}'"
            f")"
        )
