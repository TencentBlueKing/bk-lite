# -*- coding: utf-8 -*-
"""
Webhook 客户端工具类
MLOps 容器化训练模块
"""

import os
import requests
from apps.core.logger import opspilot_logger as logger


class WebhookError(Exception):
    """Webhook 请求错误基类"""
    def __init__(self, message: str, code: str = None):
        super().__init__(message)
        self.code = code  # webhookd 返回的错误码，如 'CONTAINER_ALREADY_EXISTS'


class WebhookConnectionError(WebhookError):
    """Webhook 连接错误"""
    pass


class WebhookTimeoutError(WebhookError):
    """Webhook 请求超时"""
    pass


class WebhookClient:
    """Webhook 客户端,用于构建和管理 webhook URL"""
    
    @staticmethod
    def get_base_url():
        """
        获取 webhook 基础 URL
        
        Returns:
            str: webhook 基础 URL,如果未配置则返回 None
        """
        webhook_base_url = os.getenv('WEBHOOK', None)
        
        if not webhook_base_url:
            logger.warning("环境变量 WEBHOOK 未配置")
            return None
        
        # 确保 URL 以 / 结尾
        if not webhook_base_url.endswith('/'):
            webhook_base_url += '/'
        
        return webhook_base_url
    
    
    @staticmethod
    def build_url(endpoint_name):
        """
        构建完整的 webhook URL
        
        Args:
            endpoint_name: 端点名称,如 'train', 'status', 'stop', 'logs'
            
        Returns:
            str: 完整的 webhook URL,如果配置缺失则返回 None
            
        Examples:
            >>> WebhookClient.build_url('train')
            'http://webhook-server:8080/mlops/train'
        """
        base_url = WebhookClient.get_base_url()
        
        if not base_url:
            return None
        
        full_url = f"{base_url}mlops/{endpoint_name}"
        
        logger.debug(f"构建 webhook URL: {full_url}")
        return full_url
    
    @staticmethod
    def validate_config():
        """
        验证 webhook 配置是否完整
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if not os.getenv('WEBHOOK'):
            return False, "环境变量 WEBHOOK 未配置"
        
    
    @staticmethod
    def get_all_endpoints():
        """
        获取所有可用的 webhook 端点
        
        Returns:
            dict: 端点名称到完整 URL 的映射
        """
        endpoints = ['train', 'status', 'stop', 'logs', 'serve', 'remove']
        return {name: WebhookClient.build_url(name) for name in endpoints}
    
    @staticmethod
    def _request(endpoint: str, payload: dict, timeout: int = 30) -> dict:
        """
        统一的 webhook 请求方法
        
        Args:
            endpoint: 端点名称，如 'train', 'serve', 'stop' 等
            payload: 请求数据
            timeout: 超时时间（秒）
        
        Returns:
            dict: webhook 响应数据
        
        Raises:
            WebhookError: webhookd 返回错误状态
            WebhookConnectionError: 无法连接到 webhookd
            WebhookTimeoutError: 请求超时
        """
        url = WebhookClient.build_url(endpoint)
        if not url:
            raise WebhookError("环境变量 WEBHOOK 未配置")
        
        logger.debug(f"请求 webhookd - URL: {url}, Payload: {payload}")
        
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            
            logger.debug(f"Webhookd 响应 - 状态码: {response.status_code}, 内容: {response.text[:500]}")
            
            if response.status_code != 200:
                raise WebhookError(f"Webhookd 返回错误状态码: {response.status_code}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"请求 webhookd 超时({timeout}秒) - URL: {url}")
            raise WebhookTimeoutError(f"请求 webhookd 服务超时，请检查服务是否正常运行")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"无法连接到 webhookd - URL: {url}, Error: {e}")
            raise WebhookConnectionError(f"无法连接到 webhookd 服务: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 webhookd 失败 - URL: {url}, Error: {e}", exc_info=True)
            raise WebhookError(f"请求 webhookd 失败: {e}")
    
    @staticmethod
    def serve(serving_id: str, mlflow_tracking_uri: str, mlflow_model_uri: str, port: int = None) -> dict:
        """
        启动 serving 服务
        
        Args:
            serving_id: serving ID，如 "TimeseriesPredict_Serving_1"
            mlflow_tracking_uri: MLflow tracking server URL
            mlflow_model_uri: MLflow model URI，如 "models:/model_name/version"
            port: 用户指定端口，为 None 时由 docker 自动分配
        
        Returns:
            dict: 容器状态信息，格式: {"status": "success", "id": "...", "state": "running", "port": "3042", "detail": "Up"}
        
        Raises:
            WebhookError: 启动失败
        """
        payload = {
            "id": serving_id,
            "mlflow_tracking_uri": mlflow_tracking_uri,
            "mlflow_model_uri": mlflow_model_uri
        }
        
        # 仅在用户指定端口时传递
        if port is not None:
            payload["port"] = port
        
        result = WebhookClient._request("serve", payload)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', '未知错误')
            error_code = result.get('code')
            raise WebhookError(error_msg, code=error_code)
        
        return result
    
    @staticmethod
    def train(job_id: str, bucket: str, dataset: str, config: str,
              minio_endpoint: str, mlflow_tracking_uri: str,
              minio_access_key: str, minio_secret_key: str) -> dict:
        """
        启动训练任务
        
        Args:
            job_id: 训练任务 ID
            bucket: MinIO bucket 名称
            dataset: 数据集文件路径
            config: 配置文件路径
            minio_endpoint: MinIO 端点 URL
            mlflow_tracking_uri: MLflow tracking server URL
            minio_access_key: MinIO access key
            minio_secret_key: MinIO secret key
        
        Returns:
            dict: webhook 响应数据
        
        Raises:
            WebhookError: 训练启动失败
        """
        payload = {
            "id": job_id,
            "bucket": bucket,
            "dataset": dataset,
            "config": config,
            "minio_endpoint": minio_endpoint,
            "mlflow_tracking_uri": mlflow_tracking_uri,
            "minio_access_key": minio_access_key,
            "minio_secret_key": minio_secret_key
        }
        
        result = WebhookClient._request("train", payload)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', '未知错误')
            error_code = result.get('code')
            raise WebhookError(error_msg, code=error_code)
        
        return result
    
    @staticmethod
    def stop(job_id: str) -> dict:
        """
        停止任务/服务（默认删除容器）
        
        Args:
            job_id: 任务或服务 ID
        
        Returns:
            dict: webhook 响应数据
        
        Raises:
            WebhookError: 停止失败
        """
        payload = {
            "id": job_id
        }
        
        result = WebhookClient._request("stop", payload)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', '未知错误')
            error_code = result.get('code')
            raise WebhookError(error_msg, code=error_code)
        
        return result
    
    @staticmethod
    def remove(container_id: str) -> dict:
        """
        删除容器（可处理运行中的容器）
        
        Args:
            container_id: 容器 ID
        
        Returns:
            dict: webhook 响应数据
        
        Raises:
            WebhookError: 删除失败
        """
        payload = {
            "id": container_id
        }
        
        result = WebhookClient._request("remove", payload)
        
        if result.get('status') == 'error':
            error_msg = result.get('message', '未知错误')
            error_code = result.get('code')
            raise WebhookError(error_msg, code=error_code)
        
        return result
    
    @staticmethod
    def get_status(ids: list[str]) -> list[dict]:
        """
        批量查询容器状态
        
        Args:
            ids: 容器 ID 列表，如 ["TimeseriesPredict_Serving_1", "TimeseriesPredict_Serving_2"]
        
        Returns:
            list[dict]: 容器状态列表，每个元素格式如：
                       {"status": "success", "id": "...", "state": "running", "port": "3042", ...}
                       或 {"status": "error", "id": "...", "message": "Container not found"}
        
        Raises:
            WebhookError: 查询失败
        """
        payload = {"ids": ids}
        
        result = WebhookClient._request("status", payload)
        
        # 检查整体状态
        if result.get('status') == 'error':
            error_msg = result.get('message', '未知错误')
            raise WebhookError(error_msg)
        
        # 返回 results 数组（单个容器的 error 状态不算整体失败）
        return result.get('results', [])
