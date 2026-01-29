"""统一的模型加载器."""

from typing import Any
from loguru import logger

from ..config import ModelConfig
from .dummy_model import DummyModel


def load_model(config: ModelConfig) -> Any:
    """
    根据配置加载模型.

    Args:
        config: 模型配置

    Returns:
        加载的模型实例（MLflow PyFunc包装器）

    Raises:
        ValueError: 配置无效时
        RuntimeError: 模型加载失败时
    """
    logger.info(f"Loading model from source: {config.source}")

    if config.source == "mlflow":
        return _load_from_mlflow(config)
    elif config.source == "local":
        return _load_from_local(config)
    elif config.source == "dummy":
        return DummyModel()
    else:
        raise ValueError(f"Unknown model source: {config.source}")


def _load_from_mlflow(config: ModelConfig) -> Any:
    """从 MLflow Registry 加载模型."""
    if not config.mlflow_model_uri:
        raise ValueError(
            "MODEL_SOURCE is 'mlflow' but MLFLOW_MODEL_URI is not set. "
            "Example: models:/text_classifier/Production"
        )

    try:
        import mlflow

        if config.mlflow_tracking_uri:
            mlflow.set_tracking_uri(config.mlflow_tracking_uri)
            logger.info(f"MLflow tracking URI: {config.mlflow_tracking_uri}")

        logger.info(f"Loading MLflow model: {config.mlflow_model_uri}")
        model = mlflow.pyfunc.load_model(config.mlflow_model_uri)
        logger.info("MLflow model loaded successfully")
        return model

    except Exception as e:
        logger.error(f"Failed to load MLflow model: {e}", exc_info=True)
        raise RuntimeError(
            f"Failed to load model from MLflow: {config.mlflow_model_uri}"
        ) from e


def _load_from_local(config: ModelConfig) -> Any:
    """从本地路径加载 MLflow 格式模型."""
    if not config.model_path:
        raise ValueError(
            "MODEL_SOURCE is 'local' but MODEL_PATH is not set. "
            "Please set MODEL_PATH environment variable to a valid MLflow model directory."
        )

    try:
        import mlflow
        from pathlib import Path

        model_path = Path(config.model_path)
        
        # 验证路径存在
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model path does not exist: {model_path}. "
                "Ensure the path is correct and accessible."
            )
        
        # 验证是 MLflow 模型目录
        if not model_path.is_dir():
            raise ValueError(
                f"MODEL_PATH must be a directory (MLflow model format), got: {model_path}. "
                "Example: /path/to/mlruns/1/<run_id>/artifacts/model/"
            )
        
        if not (model_path / "MLmodel").exists():
            raise ValueError(
                f"Invalid MLflow model at {model_path}: MLmodel file not found. "
                "Ensure the path points to a valid MLflow model directory containing MLmodel file."
            )
        
        # 使用标准方法生成 file:// URI（跨平台兼容）
        model_uri = model_path.absolute().as_uri()
        
        logger.info(f"Loading local MLflow model from: {model_uri}")
        model = mlflow.pyfunc.load_model(model_uri)
        logger.info("Local MLflow model loaded successfully")
        
        return model
        
    except Exception as e:
        logger.error(f"Failed to load local model: {e}", exc_info=True)
        raise RuntimeError(
            f"Failed to load model from local path: {config.model_path}"
        ) from e
