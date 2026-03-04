"""
MLOps 配置辅助模块 - 提取通用环境变量获取和校验逻辑

将分散在各 views 文件中的重复配置获取代码集中管理，提升可维护性。
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class MLflowTrainConfig:
    """MLflow 训练任务所需的配置"""

    bucket: str
    minio_endpoint: str
    mlflow_tracking_uri: str
    minio_access_key: str
    minio_secret_key: str


class ConfigurationError(Exception):
    """配置错误异常"""

    pass


def get_mlflow_train_config() -> MLflowTrainConfig:
    """
    获取 MLflow 训练任务所需的环境变量配置

    Returns:
        MLflowTrainConfig: 包含所有必要配置的数据类

    Raises:
        ConfigurationError: 当必要的环境变量未配置时抛出
    """
    bucket = "munchkin-public"
    minio_endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL", "")
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "")

    if not minio_endpoint:
        raise ConfigurationError("MinIO endpoint not configured")

    if not mlflow_tracking_uri:
        raise ConfigurationError("MLflow tracking URI not configured")

    if not minio_access_key or not minio_secret_key:
        raise ConfigurationError("MinIO credentials not configured")

    return MLflowTrainConfig(
        bucket=bucket,
        minio_endpoint=minio_endpoint,
        mlflow_tracking_uri=mlflow_tracking_uri,
        minio_access_key=minio_access_key,
        minio_secret_key=minio_secret_key,
    )


def get_mlflow_tracking_uri() -> str:
    """
    获取 MLflow tracking URI

    用于 Serving 服务启动等场景。

    Returns:
        str: MLflow tracking URI

    Raises:
        ConfigurationError: 当环境变量未配置时抛出
    """
    mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
    if not mlflow_tracking_uri:
        raise ConfigurationError("MLflow tracking URI not configured")
    return mlflow_tracking_uri


def get_host_ip() -> str:
    """
    从 DEFAULT_ZONE_VAR_NODE_SERVER_URL 环境变量中解析宿主机 IP

    该环境变量由部署脚本注入，格式为 https://{HOST_IP}:{PORT}
    例如: https://10.10.41.149:443 -> 10.10.41.149

    Returns:
        str: 宿主机 IP 地址，未配置时返回空字符串
    """
    from urllib.parse import urlparse

    node_server_url = os.getenv("DEFAULT_ZONE_VAR_NODE_SERVER_URL", "")
    if node_server_url:
        parsed = urlparse(node_server_url)
        if parsed.hostname:
            return parsed.hostname
    return ""
