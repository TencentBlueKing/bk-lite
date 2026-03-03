"""MLflow工具类 - 图片分类."""

from typing import Any, Dict, Optional
import mlflow
import mlflow.pyfunc
from loguru import logger
import math


class MLFlowUtils:
    """MLflow工具类 - 图片分类专用."""

    @staticmethod
    def setup_experiment(tracking_uri: Optional[str], experiment_name: str):
        """
        设置MLflow实验.

        Args:
            tracking_uri: MLflow tracking服务地址，如果为None则使用本地文件系统
            experiment_name: 实验名称
        """
        # 检查 experiment_name 类型
        if not isinstance(experiment_name, str):
            logger.error(
                f"❌ experiment_name类型错误: 期望str, 实际{type(experiment_name).__name__}, 值={repr(experiment_name)}"
            )
            experiment_name = str(experiment_name)
            logger.warning(f"已强制转换为字符串: {experiment_name}")

        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
            logger.info(f"MLflow跟踪地址: {tracking_uri}")
        else:
            mlflow.set_tracking_uri("file:./mlruns")
            logger.info("MLflow跟踪地址: file:./mlruns")

        mlflow.set_experiment(experiment_name)
        logger.info(f"MLflow实验: {experiment_name}")

    @staticmethod
    def load_model(model_name: str, model_version: str = "latest"):
        """
        从MLflow加载模型.

        Args:
            model_name: 模型名称
            model_version: 模型版本，默认为"latest"

        Returns:
            加载的模型对象
        """
        model_uri = f"models:/{model_name}/{model_version}"
        logger.info(f"从以下位置加载模型: {model_uri}")
        return mlflow.pyfunc.load_model(model_uri)

    @staticmethod
    def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
        """
        递归展平嵌套字典.

        用于将多层嵌套的配置字典展平为单层字典，以便记录到 MLflow。

        Args:
            d: 待展平的字典
            parent_key: 父级键名（递归时使用）
            sep: 键名分隔符（默认为 "."）

        Returns:
            展平后的字典

        Examples:
            >>> config = {
            ...     "hyperparams": {
            ...         "search_space": {
            ...             "epochs": [50, 100, 150]
            ...         },
            ...         "max_evals": 10
            ...     }
            ... }
            >>> MLFlowUtils.flatten_dict(config)
            {
                "hyperparams.search_space.epochs": [50, 100, 150],
                "hyperparams.max_evals": 10
            }
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k

            if isinstance(v, dict):
                # 递归展平嵌套字典
                items.extend(MLFlowUtils.flatten_dict(v, new_key, sep=sep).items())
            else:
                # 叶子节点（保留原始类型：int, float, bool, str, list, tuple）
                items.append((new_key, v))

        return dict(items)

    @staticmethod
    def log_params_batch(params: Dict[str, Any]):
        """
        批量记录参数到MLflow.

        Args:
            params: 参数字典（可包含嵌套结构，建议先用 flatten_dict 展平）
        """
        if params:
            # 过滤掉不支持的参数类型
            valid_params = {}
            for k, v in params.items():
                if isinstance(v, (str, int, float, bool)):
                    valid_params[k] = v
                elif isinstance(v, (list, tuple)):
                    str_v = str(v)
                    if len(str_v) <= 500:  # MLflow 参数值长度限制
                        valid_params[k] = str_v
                    else:
                        logger.warning(
                            f"参数{k}过长({len(str_v)}字符)，已截断前500字符"
                        )
                        valid_params[k] = str_v[:497] + "..."
                elif isinstance(v, dict):
                    logger.warning(f"参数{k}是dict类型，建议先使用flatten_dict展平")
                    valid_params[k] = (
                        str(v)[:497] + "..." if len(str(v)) > 500 else str(v)
                    )
                else:
                    logger.warning(f"跳过不支持类型{type(v)}的参数{k}")

            mlflow.log_params(valid_params)
            logger.debug(f"已记录{len(valid_params)}个参数")

    @staticmethod
    def log_metrics_batch(
        metrics: Dict[str, float], prefix: str = "", step: Optional[int] = None
    ):
        """
        批量记录指标到MLflow.

        Args:
            metrics: 指标字典
            prefix: 指标名称前缀，如"train_", "val_", "test_"
            step: 记录步骤（用于时间序列指标）
        """
        if metrics:
            # 过滤有效的指标值和内部数据
            prefixed_metrics = {}
            for k, v in metrics.items():
                # 跳过以_开头的内部数据（如_confusion_matrix）
                if k.startswith("_"):
                    continue
                # 跳过非数值类型
                if isinstance(v, (int, float)) and math.isfinite(v):
                    prefixed_metrics[f"{prefix}{k}"] = v

            if step is not None:
                for key, value in prefixed_metrics.items():
                    mlflow.log_metric(key, value, step=step)
            else:
                mlflow.log_metrics(prefixed_metrics)

            logger.debug(f"已记录{len(prefixed_metrics)}个指标(前缀={prefix})")

    @staticmethod
    def log_artifact(local_path: str, artifact_path: Optional[str] = None):
        """
        记录文件到MLflow.

        Args:
            local_path: 本地文件路径
            artifact_path: MLflow中的artifact路径
        """
        mlflow.log_artifact(local_path, artifact_path)
        logger.debug(f"已记录artifact: {local_path}")

    @staticmethod
    def register_model(model_uri: str, model_name: str) -> Any:
        """
        注册模型到MLflow Model Registry.

        Args:
            model_uri: 模型URI（如 runs:/<run_id>/model）
            model_name: 注册的模型名称

        Returns:
            模型版本对象
        """
        try:
            logger.info(f"注册模型到Model Registry: {model_name}")
            model_version = mlflow.register_model(model_uri, model_name)
            logger.info(f"模型注册成功: {model_name}, 版本: {model_version.version}")
            return model_version
        except Exception as e:
            logger.warning(f"模型注册失败: {e}")
            raise
