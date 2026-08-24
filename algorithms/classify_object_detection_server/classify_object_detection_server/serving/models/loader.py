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

        if config.mlflow_tracking_uri:
            mlflow.set_tracking_uri(config.mlflow_tracking_uri)
            logger.info(f"MLflow tracking URI: {config.mlflow_tracking_uri}")

        logger.info(f"Loading MLflow model: {config.mlflow_model_uri}")
        model = mlflow.pyfunc.load_model(config.mlflow_model_uri)
        logger.info("MLflow model loaded successfully")
        return model

    except Exception as e:
        logger.error(f"Failed to load MLflow model: {e}")
        return _fallback_or_raise("Failed to load model from MLflow", e)


def _load_from_local(config: ModelConfig) -> Any:
    """从本地路径加载 MLflow 格式模型.

    Note:
        local source 应该指向 MLflow 模型目录（包含 MLmodel 文件），
        而不是使用 joblib 加载单个模型文件。
        这样可以确保加载的是完整的 YOLOWrapper。
    """
    if not config.model_path:
        return _fallback_or_raise("Local model path not provided")

    try:
        import mlflow
        from pathlib import Path

        model_path = Path(config.model_path)
        if not model_path.exists():
            logger.error(f"Model path does not exist: {model_path}")
            raise FileNotFoundError(f"Model not found: {model_path}")

        # 检查是否为 MLflow 模型目录
        mlmodel_file = model_path / "MLmodel"
        if not mlmodel_file.exists():
            logger.warning(
                f"MLmodel file not found in {model_path}, "
                "make sure this is an MLflow model directory"
            )

        logger.info(f"Loading local MLflow model from: {model_path}")
        model = mlflow.pyfunc.load_model(str(model_path))
        logger.info("Local MLflow model loaded successfully")
        return model

    except Exception as e:
        logger.error(f"Failed to load local model: {e}")
        return _fallback_or_raise("Failed to load model from local path", e)
