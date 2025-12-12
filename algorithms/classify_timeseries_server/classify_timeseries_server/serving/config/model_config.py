"""模型加载配置."""
from loguru import logger
import os
from typing import Literal
from dotenv import load_dotenv

from pydantic import BaseModel, Field
load_dotenv()
logger.debug("Loaded environment variables from .env")


class ModelConfig(BaseModel):
    """模型配置.
    
    支持三种模型来源：
    1. local: 从本地文件系统加载 MLflow 格式模型
    2. mlflow: 从 MLflow Model Registry 加载已注册模型
    3. dummy: 使用模拟模型（用于测试）
    """

    source: Literal["local", "mlflow", "dummy"] = Field(
        default="dummy",
        description="模型来源: local（本地MLflow模型）, mlflow（Registry）, dummy（测试）",
    )
    model_path: str | None = Field(
        default=None,
        description=(
            "本地模型路径（仅当 source='local' 时使用）。"
            "必须指向包含 MLmodel 文件的 MLflow 模型目录。"
            "示例: /path/to/mlruns/1/<run_id>/artifacts/model/ 或 D:/models/my_model/"
        ),
    )
    mlflow_tracking_uri: str | None = Field(
        default=None,
        description=(
            "MLflow tracking server URI（仅当 source='mlflow' 时使用）。"
            "示例: http://mlflow-server:15000"
        ),
    )
    mlflow_model_uri: str | None = Field(
        default=None,
        description=(
            "MLflow 模型 URI（仅当 source='mlflow' 时使用）。"
            "格式: models:/<model_name>/<version> 或 models:/<model_name>/<stage>。"
            "示例: models:/timeseries_gb_model/28 或 models:/timeseries_gb_model/Production"
        ),
    )


def get_model_config() -> ModelConfig:
    """从环境变量加载模型配置."""
    return ModelConfig(
        source=os.getenv("MODEL_SOURCE", "mlflow"),
        model_path=os.getenv("MODEL_PATH"),
        mlflow_tracking_uri=os.getenv("MLFLOW_TRACKING_URI"),
        mlflow_model_uri=os.getenv("MLFLOW_MODEL_URI"),
    )
