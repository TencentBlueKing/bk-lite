"""Spell 模型的 MLflow pyfunc 封装器"""

from typing import Any, Dict, List, Union

import mlflow
import pandas as pd
from loguru import logger

from .spell_model import SpellModel


class SpellWrapper(mlflow.pyfunc.PythonModel):
    """Spell 模型的 MLflow pyfunc 封装器
    
    使 Spell 模型能够通过 MLflow 模型注册中心和 BentoML 提供服务。
    """

    def __init__(self, model: SpellModel):
        """初始化封装器

        Args:
            model: 已训练的 SpellModel 实例
        """
        self.model = model
        logger.info("SpellWrapper initialized")

    def load_context(self, context):
        """加载模型上下文（MLflow 加载模型时调用）

        Args:
            context: MLflow 模型上下文
        """
        # 模型已在__init__中加载
        logger.info("SpellWrapper context loaded")

    def predict(
        self, context, model_input: Union[pd.DataFrame, List[str], Dict[str, Any]]
    ) -> pd.DataFrame:
        """预测输入日志的聚类 ID

        Args:
            context: MLflow 模型上下文（未使用）
            model_input: 输入数据（DataFrame、字符串列表或字典）

        Returns:
            包含预测结果的 DataFrame
        """
        # 解析输入
        logs = self._parse_input(model_input)

        # 获取预测结果
        cluster_ids = self.model.predict(logs)

        # 获取每条日志的模板
        templates = [self.model.get_template_by_id(cid) for cid in cluster_ids]

        # 创建结果 DataFrame
        result_df = pd.DataFrame(
            {
                "log": logs,
                "cluster_id": cluster_ids,
                "template": templates,
            }
        )

        logger.info(f"Predicted {len(logs)} logs")
        return result_df

    def _parse_input(self, model_input: Union[pd.DataFrame, List[str], Dict[str, Any]]) -> List[str]:
        """解析各种输入格式为日志字符串列表

        Args:
            model_input: 各种格式的输入数据

        Returns:
            日志字符串列表
        """
        if isinstance(model_input, pd.DataFrame):
            # 假设第一列包含日志消息
            if "log" in model_input.columns:
                logs = model_input["log"].tolist()
            elif "content" in model_input.columns:
                logs = model_input["content"].tolist()
            elif "message" in model_input.columns:
                logs = model_input["message"].tolist()
            else:
                logs = model_input.iloc[:, 0].tolist()

        elif isinstance(model_input, list):
            # 直接的日志字符串列表
            logs = model_input

        elif isinstance(model_input, dict):
            # 包含 'logs' 或 'data' 键的字典
            if "logs" in model_input:
                logs = model_input["logs"]
            elif "data" in model_input:
                logs = model_input["data"]
            elif "log" in model_input:
                logs = [model_input["log"]]
            else:
                raise ValueError(f"Invalid dict input format: {model_input.keys()}")

        else:
            raise ValueError(f"Unsupported input type: {type(model_input)}")

        # 验证
        if not isinstance(logs, list):
            raise ValueError(f"Expected list of logs, got {type(logs)}")

        if not all(isinstance(log, str) for log in logs):
            raise ValueError("All logs must be strings")

        return logs

    def get_model_info(self) -> Dict[str, Any]:
        """获取模型信息

        Returns:
            包含模型元数据的字典
        """
        return self.model.get_model_info()

    def get_templates(self) -> List[str]:
        """获取发现的日志模板

        Returns:
            模板列表
        """
        return self.model.get_templates()


def create_spell_wrapper(model_path: str) -> SpellWrapper:
    """从保存的模型文件创建 SpellWrapper

    Args:
        model_path: 保存的 Spell 模型路径

    Returns:
        SpellWrapper 实例
    """
    model = SpellModel.load(model_path)
    wrapper = SpellWrapper(model)
    logger.info(f"Created SpellWrapper from {model_path}")
    return wrapper


def log_spell_model_to_mlflow(
    model: SpellModel,
    artifact_path: str = "model",
    registered_model_name: str = None,
    **kwargs,
):
    """将 Spell 模型作为 pyfunc 模型记录到 MLflow

    Args:
        model: 已训练的 SpellModel 实例
        artifact_path: MLflow 中的 artifact 路径
        registered_model_name: 模型注册中心的名称
        **kwargs: mlflow.pyfunc.log_model 的额外参数
    """
    wrapper = SpellWrapper(model)

    # 定义 conda 环境
    conda_env = {
        "channels": ["defaults", "conda-forge"],
        "dependencies": [
            f"python={mlflow.pyfunc.PYTHON_VERSION}",
            "pip",
            {
                "pip": [
                    f"mlflow=={mlflow.__version__}",
                    "logparser3>=1.0.4",
                    "pandas>=2.2.0",
                    "numpy>=1.26.0",
                    "loguru>=0.7.3",
                    "joblib>=1.4.0",
                ]
            },
        ],
        "name": "spell_env",
    }

    # 记录模型
    mlflow.pyfunc.log_model(
        artifact_path=artifact_path,
        python_model=wrapper,
        conda_env=conda_env,
        registered_model_name=registered_model_name,
        **kwargs,
    )

    logger.info(f"Spell model logged to MLflow: {artifact_path}")
    if registered_model_name:
        logger.info(f"Model registered as: {registered_model_name}")
