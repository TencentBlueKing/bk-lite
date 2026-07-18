"""统一的模型加载器."""

import os
from typing import Any

from loguru import logger

from ..config import ModelConfig
from .dummy_model import DummyModel


def _fallback_or_raise(message: str, error: Exception | None = None) -> Any:
    """Use DummyModel only when the fallback is explicitly enabled."""
    if os.getenv("ALLOW_DUMMY_FALLBACK", "false").strip().lower() == "true":
        logger.warning(f"{message}; ALLOW_DUMMY_FALLBACK=true, using DummyModel")
        return DummyModel()

    if error is None:
        raise ValueError(message)
    raise RuntimeError(message) from error


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
        return _fallback_or_raise(f"Unknown model source: {config.source}")


def _load_from_mlflow(config: ModelConfig) -> Any:
    """从 MLflow 加载模型."""
    if not config.mlflow_model_uri:
        return _fallback_or_raise("MLflow model URI not provided")

    try:
        import mlflow

        # 设置 tracking URI
        tracking_uri = config.mlflow_tracking_uri or "http://localhost:15000"
        mlflow.set_tracking_uri(tracking_uri)
        logger.info(f"MLflow tracking URI: {tracking_uri}")

        logger.info(f"Loading MLflow model from: {config.mlflow_model_uri}")
        model = mlflow.pyfunc.load_model(config.mlflow_model_uri)
        logger.info("MLflow model loaded successfully")
        return model

    except Exception as e:
        logger.error(f"Failed to load MLflow model: {e}")
        return _fallback_or_raise("Failed to load model from MLflow", e)


def _load_from_local(config: ModelConfig) -> Any:
    """从本地路径加载 MLflow 格式模型."""
    if not config.model_path:
        return _fallback_or_raise("Local model path not provided")

    try:
        import mlflow
        from pathlib import Path

        model_path = Path(config.model_path)

        if not model_path.exists():
            raise FileNotFoundError(f"Model not found: {model_path}")

        if not (model_path / "MLmodel").exists():
            raise ValueError(
                f"Invalid MLflow model at {model_path}: MLmodel file not found"
            )

        model_uri = model_path.absolute().as_uri()
        logger.info(f"Loading local MLflow model from: {model_uri}")
        model = mlflow.pyfunc.load_model(model_uri)
        logger.info("Local MLflow model loaded successfully")
        return model

    except Exception as e:
        logger.error(f"Failed to load local model: {e}")
        return _fallback_or_raise("Failed to load model from local path", e)
