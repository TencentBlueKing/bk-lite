"""统一的模型加载器."""

import hashlib
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
    """从本地路径加载模型."""
    if not config.model_path:
        return _fallback_or_raise("Local model path not provided")

    try:
        from pathlib import Path

        model_path = Path(config.model_path)
        if not model_path.exists():
            logger.error(f"Model path does not exist: {model_path}")
            raise FileNotFoundError(f"Model not found: {model_path}")

        logger.info(f"Loading local model from: {model_path}")

        # SHA256 完整性校验：从环境变量读取期望值，未配置时仅告警（向后兼容）
        expected_sha256 = os.getenv("MODEL_SHA256")
        if expected_sha256:
            actual_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
            if actual_sha256 != expected_sha256:
                raise ValueError(
                    f"Model checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
                )
            logger.info("Model SHA256 checksum verified successfully")
        else:
            logger.warning(
                "MODEL_SHA256 not set, skipping checksum verification "
                "(set this env var in production to guard against model file tampering)"
            )

        # Try to load as Spell model first
        try:
            from ...training.models.spell_model import SpellModel
            from ...training.models.spell_wrapper import SpellWrapper

            spell_model = SpellModel.load(str(model_path))
            wrapper = SpellWrapper(spell_model)
            logger.info("Loaded as SpellModel with wrapper")
            return wrapper
        except Exception as e:
            logger.debug(f"Not a Spell model, trying generic joblib: {e}")

        # Fallback to generic joblib loading
        import joblib

        model = joblib.load(model_path)
        logger.info("Local model loaded successfully with joblib")
        return model

    except Exception as e:
        logger.error(f"Failed to load local model: {e}")
        return _fallback_or_raise("Failed to load model from local path", e)
