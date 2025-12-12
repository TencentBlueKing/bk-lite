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
        logger.warning("mlflow_model_uri not provided, falling back to dummy")
        return DummyModel()

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
        logger.warning("Falling back to dummy model")
        return DummyModel()


def _load_from_local(config: ModelConfig) -> Any:
    """从本地路径加载 MLflow 格式模型（不做 fallback，异常向上传播）."""
    if not config.model_path:
        logger.warning("Local model path not provided, falling back to dummy")
        return DummyModel()

    import mlflow
    from pathlib import Path

    model_path = Path(config.model_path)
    
    # 验证路径存在
    if not model_path.exists():
        logger.error(f"Model path does not exist: {model_path}")
        raise FileNotFoundError(f"Model not found: {model_path}")
    
    # 验证是 MLflow 模型目录
    if not (model_path / "MLmodel").exists():
        logger.error(
            f"Not a valid MLflow model directory: {model_path}. "
            "MLmodel file not found."
        )
        raise ValueError(
            f"Invalid MLflow model at {model_path}. "
            "Expected a directory containing MLmodel file. "
            f"Example: /path/to/mlruns/1/<run_id>/artifacts/model/"
        )
    
    # 使用标准方法生成 file:// URI（跨平台兼容）
    model_uri = model_path.absolute().as_uri()
    
    logger.info(f"Loading local MLflow model from: {model_uri}")
    
    # 不捕获异常，让它向上传播到调用方
    model = mlflow.pyfunc.load_model(model_uri)
    
    logger.info("Local MLflow model loaded successfully")
    return model
