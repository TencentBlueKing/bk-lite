# -*- coding: utf-8 -*-
"""
MLflow 工具函数集合
提供纯函数式的 MLflow 操作封装，无状态设计
"""

import os
import tempfile
import zipfile
from io import BytesIO
from typing import List, Optional, Tuple
from pathlib import Path

import mlflow
import pandas as pd
import numpy as np
from mlflow.tracking import MlflowClient

from config.components.mlflow import MLFLOW_TRACKER_URL
from apps.core.logger import mlops_logger as logger


# ============ 命名构造工具 ============

def build_experiment_name(prefix: str, algorithm: str, train_job_id: int) -> str:
    """
    构造 MLflow 实验名称
    
    Args:
        prefix: 业务前缀，如 "TimeseriesPredict"
        algorithm: 算法名称
        train_job_id: 训练任务 ID
    
    Returns:
        str: 实验名称，格式为 "prefix_algorithm_id"
    """
    return f"{prefix}_{algorithm}_{train_job_id}"


def build_model_name(prefix: str, algorithm: str, train_job_id: int) -> str:
    """
    构造 MLflow 模型名称
    
    Args:
        prefix: 业务前缀，如 "TimeseriesPredict"
        algorithm: 算法名称
        train_job_id: 训练任务 ID
    
    Returns:
        str: 模型名称，格式为 "prefix_algorithm_id"
    """
    return f"{prefix}_{algorithm}_{train_job_id}"


def build_job_id(prefix: str, algorithm: str, train_job_id: int) -> str:
    """
    构造训练任务 Job ID
    
    Args:
        prefix: 业务前缀，如 "TimeseriesPredict"
        algorithm: 算法名称
        train_job_id: 训练任务 ID
    
    Returns:
        str: Job ID，格式为 "prefix_algorithm_id"
    """
    return f"{prefix}_{algorithm}_{train_job_id}"


# ============ 客户端工具 ============

def get_mlflow_client() -> MlflowClient:
    """
    获取配置好的 MLflow 客户端
    
    Returns:
        MlflowClient: 已配置跟踪 URI 的客户端实例
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
    return mlflow.tracking.MlflowClient()


# ============ 实验查询 ============

def get_experiment_by_name(experiment_name: str) -> Optional[object]:
    """
    根据名称查找 MLflow 实验
    
    Args:
        experiment_name: 实验名称
    
    Returns:
        实验对象，未找到返回 None
    
    Raises:
        Exception: MLflow 查询失败时抛出
    """
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
        experiments = mlflow.search_experiments(
            filter_string=f"name = '{experiment_name}'"
        )
        result = experiments[0] if experiments else None
        
        if not result:
            logger.info(f"未找到实验: {experiment_name}")
        
        return result
        
    except Exception as e:
        logger.error(f"查询实验失败 [{experiment_name}]: {e}", exc_info=True)
        raise


def get_experiment_runs(experiment_id: str, order_by: str = "start_time DESC") -> pd.DataFrame:
    """
    获取实验的所有运行记录
    
    Args:
        experiment_id: 实验 ID
        order_by: 排序字段，默认按开始时间倒序
    
    Returns:
        pd.DataFrame: 运行记录 DataFrame
    
    Raises:
        Exception: MLflow 查询失败时抛出
    """
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
        runs = mlflow.search_runs(
            experiment_ids=[experiment_id],
            order_by=[order_by]
        )
        
        logger.debug(f"查询到 {len(runs)} 条运行记录 [实验ID: {experiment_id}]")
        return runs
        
    except Exception as e:
        logger.error(f"查询实验运行记录失败 [实验ID: {experiment_id}]: {e}", exc_info=True)
        raise


# ============ 运行记录查询 ============

def get_run_info(run_id: str) -> object:
    """
    获取运行基本信息
    
    Args:
        run_id: 运行 ID
    
    Returns:
        Run 对象
    
    Raises:
        Exception: MLflow 查询失败时抛出
    """
    try:
        client = get_mlflow_client()
        run = client.get_run(run_id)
        return run
        
    except Exception as e:
        logger.error(f"获取运行信息失败 [run_id: {run_id}]: {e}", exc_info=True)
        raise


def get_run_metrics(run_id: str, filter_system: bool = True) -> List[str]:
    """
    获取运行的指标列表
    
    Args:
        run_id: 运行 ID
        filter_system: 是否过滤系统指标（以 'system' 开头的指标）
    
    Returns:
        List[str]: 指标名称列表
    
    Raises:
        Exception: MLflow 查询失败时抛出
    """
    try:
        client = get_mlflow_client()
        run = client.get_run(run_id)
        metrics = list(run.data.metrics.keys())
        
        if filter_system:
            metrics = [m for m in metrics if not str(m).startswith("system")]
        
        logger.debug(f"获取到 {len(metrics)} 个指标 [run_id: {run_id}]")
        return metrics
        
    except Exception as e:
        logger.error(f"获取运行指标失败 [run_id: {run_id}]: {e}", exc_info=True)
        raise


def get_metric_history(run_id: str, metric_name: str) -> List[dict]:
    """
    获取指标历史数据（自动判断排序方式）
    
    如果所有 step 都相同（通常为 0），则按 timestamp 排序；
    否则按 step 排序。
    
    Args:
        run_id: 运行 ID
        metric_name: 指标名称
    
    Returns:
        List[dict]: 格式化的指标历史数据
            - 按 step 排序时：[{"step": int, "value": float, "timestamp": str}]
            - 按 timestamp 排序时：[{"index": int, "value": float, "timestamp": str}]
    
    Raises:
        Exception: MLflow 查询失败时抛出
    """
    try:
        client = get_mlflow_client()
        history = client.get_metric_history(run_id, metric_name)
        
        if not history:
            logger.warning(f"指标无历史数据 [run_id: {run_id}, metric: {metric_name}]")
            return []
        
        # 检查是否所有 step 都相同
        all_steps = [m.step for m in history]
        unique_steps = set(all_steps)
        
        # 决定排序方式
        if len(unique_steps) == 1:
            # 所有 step 相同，按 timestamp 排序
            sorted_history = sorted(history, key=lambda m: m.timestamp)
            result = [
                {
                    "step": idx,  # 使用索引作为 x 轴
                    "value": float(m.value) if np.isfinite(m.value) else 0,
                    "timestamp": m.timestamp
                }
                for idx, m in enumerate(sorted_history)
            ]
            logger.debug(f"按 timestamp 排序 [run_id: {run_id}, metric: {metric_name}]")
        else:
            # 按 step 排序
            sorted_history = sorted(history, key=lambda m: m.step)
            result = [
                {
                    "step": int(m.step),
                    "value": float(m.value) if np.isfinite(m.value) else 0,
                    "timestamp": m.timestamp
                }
                for m in sorted_history
            ]
            logger.debug(f"按 step 排序 [run_id: {run_id}, metric: {metric_name}]")
        
        return result
        
    except Exception as e:
        logger.error(f"获取指标历史失败 [run_id: {run_id}, metric: {metric_name}]: {e}", exc_info=True)
        raise


def get_run_params(run_id: str) -> dict:
    """
    获取运行参数
    
    Args:
        run_id: 运行 ID
    
    Returns:
        dict: 参数字典
    
    Raises:
        Exception: MLflow 查询失败时抛出
    """
    try:
        client = get_mlflow_client()
        run = client.get_run(run_id)
        params = dict(run.data.params)
        
        logger.debug(f"获取到 {len(params)} 个参数 [run_id: {run_id}]")
        return params
        
    except Exception as e:
        logger.error(f"获取运行参数失败 [run_id: {run_id}]: {e}", exc_info=True)
        raise


# ============ 模型管理 ============

def get_model_versions(model_name: str) -> List[dict]:
    """
    获取模型的所有版本
    
    Args:
        model_name: 模型名称
    
    Returns:
        List[dict]: 模型版本列表，每个元素包含：
            - version: 版本号
            - run_id: 关联的运行 ID
            - stage: 阶段（None/Staging/Production/Archived）
            - status: 状态（READY/PENDING_REGISTRATION/FAILED_REGISTRATION）
            - description: 描述信息
    
    Raises:
        Exception: MLflow 查询失败时抛出
    """
    try:
        client = get_mlflow_client()
        versions = client.search_model_versions(
            filter_string=f"name='{model_name}'"
        )
        
        result = [
            {
                "version": int(v.version),
                "run_id": v.run_id,
                "stage": v.current_stage,
                "status": v.status,
                "description": v.description or ""
            }
            for v in versions
        ]
        
        logger.debug(f"获取到 {len(result)} 个模型版本 [model: {model_name}]")
        return result
        
    except Exception as e:
        logger.error(f"获取模型版本失败 [model: {model_name}]: {e}", exc_info=True)
        raise


def resolve_model_uri(model_name: str, version: str = "latest") -> str:
    """
    解析模型 URI（处理 latest 版本逻辑）
    
    Args:
        model_name: 模型名称
        version: 版本号或 "latest"
    
    Returns:
        str: MLflow model URI，格式为 "models://{model_name}/{version}"
    
    Raises:
        ValueError: 模型不存在或无可用版本时抛出
        Exception: MLflow 查询失败时抛出
    """
    try:
        if version == "latest":
            # 查询最新版本
            client = get_mlflow_client()
            versions = client.search_model_versions(
                filter_string=f"name='{model_name}'",
                order_by=["version_number DESC"],
                max_results=1
            )
            
            if not versions:
                error_msg = f"模型不存在或无可用版本 [model: {model_name}]"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            latest_version = versions[0].version
            model_uri = f"models:/{model_name}/{latest_version}"
            logger.info(f"解析 latest 版本: {model_uri}")
        else:
            # 使用指定版本
            model_uri = f"models:/{model_name}/{version}"
            logger.info(f"使用指定版本: {model_uri}")
        
        return model_uri
        
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"解析模型 URI 失败 [model: {model_name}, version: {version}]: {e}", exc_info=True)
        raise


def download_model_artifact(run_id: str, artifact_path: str = "model") -> BytesIO:
    """
    从 MLflow 下载模型并打包为 ZIP 流
    
    Args:
        run_id: 运行 ID
        artifact_path: artifact 路径，默认 "model"
    
    Returns:
        BytesIO: ZIP 文件流
    
    Raises:
        Exception: 下载或打包失败时抛出
    """
    try:
        client = get_mlflow_client()
        
        # 下载 artifact 到临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"开始下载模型 [run_id: {run_id}, artifact: {artifact_path}]")
            local_path = client.download_artifacts(run_id, artifact_path, dst_path=temp_dir)
            model_dir = Path(local_path)
            
            if not model_dir.exists():
                error_msg = f"模型文件不存在 [path: {local_path}]"
                logger.error(error_msg)
                raise FileNotFoundError(error_msg)
            
            # 打包为 ZIP
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                if model_dir.is_file():
                    # 单文件
                    zip_file.write(model_dir, model_dir.name)
                else:
                    # 目录
                    for file_path in model_dir.rglob('*'):
                        if file_path.is_file():
                            arcname = file_path.relative_to(model_dir.parent)
                            zip_file.write(file_path, arcname)
            
            zip_buffer.seek(0)
            zip_size = len(zip_buffer.getvalue())
            logger.info(f"模型打包完成 [run_id: {run_id}, size: {zip_size} bytes]")
            
            return zip_buffer
            
    except Exception as e:
        logger.error(f"下载模型失败 [run_id: {run_id}, artifact: {artifact_path}]: {e}", exc_info=True)
        raise
