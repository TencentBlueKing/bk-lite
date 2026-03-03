"""
算法配置服务模块 - 提供动态获取算法镜像等功能
"""

from typing import Optional

from apps.core.logger import mlops_logger as logger
from apps.mlops.models import AlgorithmConfig


# 算法类型映射表（用于将 MLFLOW_PREFIX 映射到 algorithm_type）
ALGORITHM_TYPE_MAP = {
    "AnomalyDetection": "anomaly_detection",
    "TimeseriesPredict": "timeseries_predict",
    "LogClustering": "log_clustering",
    "Classification": "classification",
    "ImageClassification": "image_classification",
    "ObjectDetection": "object_detection",
}

# 默认镜像配置（回退方案）
DEFAULT_IMAGES = {
    "anomaly_detection": "bklite/classify_anomaly_server:latest",
    "timeseries_predict": "bklite/classify_timeseries_server:latest",
    "log_clustering": "bklite/classify_log_server:latest",
    "classification": "bklite/classify_text_classification_server:latest",
    "image_classification": "bklite/classify_image_classification_server:latest",
    "object_detection": "bklite/classify_object_detection_server:latest",
}


def get_algorithm_image(
    algorithm_type: str,
    algorithm_name: str,
    fallback: bool = True,
) -> Optional[str]:
    """
    获取算法的 Docker 镜像地址

    Args:
        algorithm_type: 算法类型，如 anomaly_detection, timeseries_predict 等
        algorithm_name: 算法名称，如 ECOD, Prophet, XGBoost 等
        fallback: 是否回退到默认镜像，默认 True

    Returns:
        Docker 镜像地址，如果找不到且 fallback=False 则返回 None
    """
    try:
        config = AlgorithmConfig.objects.get(
            algorithm_type=algorithm_type,
            name=algorithm_name,
            is_active=True,
        )
        logger.debug(
            f"从数据库获取算法镜像: {algorithm_type}/{algorithm_name} -> {config.image}"
        )
        return config.image
    except AlgorithmConfig.DoesNotExist:
        logger.warning(
            f"未找到算法配置: algorithm_type={algorithm_type}, name={algorithm_name}"
        )
        if fallback:
            default_image = DEFAULT_IMAGES.get(algorithm_type)
            if default_image:
                logger.info(f"使用默认镜像回退: {algorithm_type} -> {default_image}")
                return default_image
        return None


def get_image_by_prefix(
    mlflow_prefix: str,
    algorithm_name: str,
    fallback: bool = True,
) -> Optional[str]:
    """
    根据 MLFLOW_PREFIX 获取算法镜像（用于视图中的兼容调用）

    Args:
        mlflow_prefix: MLflow 前缀，如 AnomalyDetection, TimeseriesPredict 等
        algorithm_name: 算法名称
        fallback: 是否回退到默认镜像

    Returns:
        Docker 镜像地址
    """
    algorithm_type = ALGORITHM_TYPE_MAP.get(mlflow_prefix)
    if not algorithm_type:
        logger.error(f"未知的 MLFLOW_PREFIX: {mlflow_prefix}")
        return None
    return get_algorithm_image(algorithm_type, algorithm_name, fallback)
