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
        加载的模型实例

    Raises:
        ValueError: 配置无效时
    """
    logger.info(f"Loading model from source: {config.source}")

    if config.source == "mlflow":
        return _load_from_mlflow(config)
    elif config.source == "local":
        return _load_from_local(config)
    elif config.source == "dummy":
        return DummyModel()
    else:
        logger.warning(
            f"Unknown source '{config.source}', falling back to dummy")
        return DummyModel()


def _load_from_mlflow(config: ModelConfig) -> Any:
    """从 MLflow 加载模型."""
    if not config.mlflow_model_uri:
        logger.warning("MLflow model URI not provided, falling back to dummy")
        return DummyModel()

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
        logger.error(f"Failed to load MLflow model: {e}")
        logger.warning("Falling back to dummy model")
        return DummyModel()


def _load_from_local(config: ModelConfig) -> Any:
    """从本地路径加载模型."""
    if not config.model_path:
        logger.warning("Local model path not provided, falling back to dummy")
        return DummyModel()

    try:
        import joblib
        from pathlib import Path

        model_path = Path(config.model_path)
        if not model_path.exists():
            logger.error(f"Model path does not exist: {model_path}")
            raise FileNotFoundError(f"Model not found: {model_path}")

        logger.info(f"Loading local model from: {model_path}")
        model = joblib.load(model_path)
        logger.info("Local model loaded successfully")
        return model

    except Exception as e:
        logger.error(f"Failed to load local model: {e}")
        logger.warning("Falling back to dummy model")
        return DummyModel()
