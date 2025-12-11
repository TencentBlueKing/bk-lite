"""模型加载配置."""
from loguru import logger
import os
from typing import Literal
from dotenv import load_dotenv

from pydantic import BaseModel, Field
load_dotenv()
logger.debug("Loaded environment variables from .env")


class ModelConfig(BaseModel):
    """模型配置."""

    source: Literal["local", "mlflow", "dummy"] = Field(
        default="dummy",
        description="模型来源",
    )
    model_path: str | None = Field(
        default=None,
        description="本地模型路径",
    )
    mlflow_tracking_uri: str | None = Field(
        default=None,
        description="MLflow tracking server URI",
    )
    mlflow_model_uri: str | None = Field(
        default=None,
        description="MLflow 模型 URI, 例如: models:/timeseries_gb_model/28",
    )


def get_model_config() -> ModelConfig:
    """从环境变量加载模型配置."""
    return ModelConfig(
        source=os.getenv("MODEL_SOURCE", "mlflow"),
        model_path=os.getenv("MODEL_PATH"),
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI"),
        mlflow_model_uri=os.getenv("MLFLOW_MODEL_URI"),
    )
