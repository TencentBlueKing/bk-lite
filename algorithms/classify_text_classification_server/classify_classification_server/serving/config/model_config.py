"""模型加载配置."""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from loguru import logger

# 在模块加载时自动加载.env文件
# 查找项目根目录的.env文件（向上4级：config -> serving -> classify_classification_server -> project_root）
_current_file = Path(__file__)
_project_root = _current_file.parent.parent.parent.parent
_env_path = _project_root / ".env"

if _env_path.exists():
    load_dotenv(_env_path)
    logger.debug(f"Loaded .env from: {_env_path}")
else:
    # 尝试从当前工作目录加载
    load_dotenv()
    logger.debug("Loaded .env from current working directory")


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
        description="MLflow 模型 URI, 例如: models:/my-model/production",
    )


def get_model_config() -> ModelConfig:
    """从环境变量加载模型配置."""
    return ModelConfig(
        source=os.getenv("MODEL_SOURCE", "dummy"),
        model_path=os.getenv("MODEL_PATH"),
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI"),
        mlflow_model_uri=os.getenv("MLFLOW_MODEL_URI"),
    )
