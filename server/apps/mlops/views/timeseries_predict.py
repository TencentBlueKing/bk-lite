from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.timeseries_predict import *
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response
from django.db import transaction
from django.core.files.base import ContentFile
from django_minio_backend import MinioBackend, iso_date_prefix
from apps.mlops.utils.webhook_client import WebhookClient
from pathlib import Path
import requests
import os
import mlflow
import pandas as pd
import numpy as np
import tempfile
import shutil
from datetime import datetime, timedelta
from config.components.mlflow import MLFLOW_TRACKER_URL

from apps.core.logger import opspilot_logger as logger
from apps.core.decorators.api_permission import HasPermission
from apps.mlops.models.timeseries_predict import *
from apps.mlops.serializers.timeseries_predict import *
from config.drf.pagination import CustomPageNumberPagination


class TimeSeriesPredictDatasetViewSet(ModelViewSet):
    queryset = TimeSeriesPredictDataset.objects.all()
    serializer_class = TimeSeriesPredictDatasetSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictDatasetFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_dataset"

    @HasPermission("timeseries_predict_datasets-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_datasets-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainJobViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainJob.objects.all()
    serializer_class = TimeSeriesPredictTrainJobSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainJobFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_job"

    @HasPermission("timeseries_predict_train_jobs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_jobs-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='train')
    @HasPermission("timeseries_predict_train_jobs-Train")
    def train(self, request, *args, **kwargs):
        """
        启动训练任务
        """
        try:
            train_job = self.get_object()
            
            # 检查任务状态
            if train_job.status == 'running':
                return Response(
                    {'error': '训练任务已在运行中'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建 webhook URL
            webhook_url = WebhookClient.build_url("train")
            if not webhook_url:
                return Response(
                    {'error': 'Webhook 服务未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 获取环境变量
            bucket = os.getenv("MINIO_PUBLIC_BUCKETS", "munchkin-public")
            minio_endpoint = os.getenv("MLFLOW_S3_ENDPOINT_URL", "")
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            minio_access_key = os.getenv("MINIO_ACCESS_KEY", "")
            minio_secret_key = os.getenv("MINIO_SECRET_KEY", "")

            if not minio_endpoint:
                return Response(
                    {'error': 'MinIO 访问端点未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            if not mlflow_tracking_uri:
                return Response(
                    {'error': 'MLflow 访问端点未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                ) 
            
            if not minio_access_key or not minio_secret_key:
                return Response(
                    {'error': 'MinIO 访问凭证未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 检查必要字段
            if not train_job.dataset_version or not train_job.dataset_version.dataset_file:
                return Response(
                    {'error': '数据集文件不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not train_job.config_url:
                return Response(
                    {'error': '训练配置文件不存在'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建训练任务标识
            job_id = f"TimeseriesPredict_{train_job.algorithm}_{train_job.id}"
            
            # 构建请求数据
            payload = {
                "id": job_id,
                "bucket": bucket,
                "dataset": train_job.dataset_version.dataset_file.name,
                "config": train_job.config_url.name,
                "minio_endpoint": minio_endpoint,
                "mlflow_tracking_uri": mlflow_tracking_uri,
                "minio_access_key": minio_access_key,
                "minio_secret_key": minio_secret_key
            }
            
            logger.info(f"发起训练任务: {job_id}")
            logger.info(f"Webhook URL: {webhook_url}")
            logger.info(f"Payload: ")
            logger.info(f"  'id': '{job_id}',")
            logger.info(f"  'bucket': '{bucket}',")
            logger.info(f"  'dataset': '{train_job.dataset_version.dataset_file.name}',")
            logger.info(f"  'config': '{train_job.config_url.name}',")
            logger.info(f"  'minio_endpoint': {minio_endpoint}")
            logger.info(f"  'mlflow_tracking_uri': {mlflow_tracking_uri}")
            
            # 发送请求到 webhook 服务
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=30
            )
            
            # 检查响应
            logger.info(f"Webhook 响应状态码: {response.status_code}")
            logger.info(f"Webhook 响应内容: {response.text[:500]}")
            
            if response.status_code != 200:
                error_detail = response.text if response.text else f"HTTP {response.status_code}"
                logger.error(f"Webhook 返回错误: {error_detail}")
                return Response(
                    {'error': f'训练服务返回错误: {error_detail}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            response.raise_for_status()
            
            # 更新任务状态
            train_job.status = 'running'
            train_job.save(update_fields=['status'])
            
            logger.info(f"训练任务已启动: {job_id}")
            
            # 尝试解析响应
            webhook_response = None
            try:
                webhook_response = response.json() if response.content else None
            except Exception as json_err:
                logger.warning(f"无法解析 webhook 响应为 JSON: {json_err}")
                webhook_response = {'raw_response': response.text}
            
            return Response({
                'message': '训练任务已启动',
                'job_id': job_id,
                'train_job_id': train_job.id,
                'webhook_response': webhook_response
            })
            
        except requests.exceptions.Timeout:
            logger.error(f"请求 webhook 服务超时(30秒)")
            return Response(
                {'error': '请求训练服务超时,请检查 webhookd 服务是否正常运行'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"无法连接到 webhook 服务: {str(e)}")
            return Response(
                {'error': f'无法连接到训练服务: {str(e)},请检查 WEBHOOK 环境变量配置'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 webhook 服务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'请求训练服务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'启动训练任务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='stop')
    @HasPermission("timeseries_predict_train_jobs-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止训练任务
        """
        try:
            train_job = self.get_object()
            
            # 检查任务状态
            if train_job.status != 'running':
                return Response(
                    {'error': '训练任务未在运行中'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建 webhook URL
            webhook_url = WebhookClient.build_url("stop")
            if not webhook_url:
                return Response(
                    {'error': 'Webhook 服务未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 构建训练任务标识
            job_id = f"TimeseriesPredict_{train_job.algorithm}_{train_job.id}"
            
            # 构建请求数据
            payload = {
                "id": job_id
            }
            
            logger.info(f"停止训练任务: {job_id}")
            logger.info(f"Webhook URL: {webhook_url}")
            logger.info(f"Payload: {payload}")
            
            # 发送请求到 webhook 服务
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=30
            )
            
            # 检查响应
            logger.info(f"Webhook 响应状态码: {response.status_code}")
            logger.info(f"Webhook 响应内容: {response.text[:500]}")
            
            if response.status_code != 200:
                error_detail = response.text if response.text else f"HTTP {response.status_code}"
                logger.error(f"Webhook 返回错误: {error_detail}")
                return Response(
                    {'error': f'停止服务返回错误: {error_detail}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            response.raise_for_status()
            
            # 更新任务状态
            train_job.status = 'pending'
            train_job.save(update_fields=['status'])
            
            logger.info(f"训练任务已停止: {job_id}")
            
            # 尝试解析响应
            webhook_response = None
            try:
                webhook_response = response.json() if response.content else None
            except Exception as json_err:
                logger.warning(f"无法解析 webhook 响应为 JSON: {json_err}")
                webhook_response = {'raw_response': response.text}
            
            return Response({
                'message': '训练任务已停止',
                'job_id': job_id,
                'train_job_id': train_job.id,
                'webhook_response': webhook_response
            })
            
        except requests.exceptions.Timeout:
            logger.error(f"请求 webhook 服务超时(30秒)")
            return Response(
                {'error': '请求停止服务超时,请检查 webhookd 服务是否正常运行'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"无法连接到 webhook 服务: {str(e)}")
            return Response(
                {'error': f'无法连接到停止服务: {str(e)},请检查 WEBHOOK 环境变量配置'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"请求 webhook 服务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'请求停止服务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"停止训练任务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'停止训练任务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'], url_path='runs_data_list')
    @HasPermission("timeseries_predict_train_jobs-View")
    def get_run_data_list(self, request, pk=None):
        """
        获取训练任务的所有 MLflow 运行记录
        """
        try:
            train_job = self.get_object()
            
            # 设置 MLflow 跟踪 URI
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            
            # 构造实验名称
            experiment_name = f"TimeseriesPredict_{train_job.algorithm}_{train_job.id}"
            
            # 查找实验
            experiments = mlflow.search_experiments(
                filter_string=f"name = '{experiment_name}'"
            )
            
            if not experiments:
                return Response({
                    'train_job_id': train_job.id,
                    'train_job_name': train_job.name,
                    'algorithm': train_job.algorithm,
                    'message': '未找到对应的MLflow实验',
                    'data': []
                })
            
            experiment = experiments[0]
            
            # 查找该实验中的所有运行
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                order_by=["start_time DESC"]
            )
            
            if runs.empty:
                return Response({
                    'train_job_id': train_job.id,
                    'train_job_name': train_job.name,
                    'algorithm': train_job.algorithm,
                    'message': '未找到训练运行记录',
                    'data': []
                })
            
            # 构建运行信息列表
            run_datas = []
            latest_run_status = None  # 记录最新一次运行的状态
            
            for idx, row in runs.iterrows():
                try:
                    start_time = row["start_time"]
                    end_time = row["end_time"]
                    
                    # 计算耗时
                    if pd.notna(start_time):
                        if pd.notna(end_time):
                            # 已完成：使用实际结束时间
                            duration_seconds = (end_time - start_time).total_seconds()
                        else:
                            # 运行中：使用当前时间计算已运行时长
                            current_time = pd.Timestamp.now(tz=start_time.tz)
                            duration_seconds = (current_time - start_time).total_seconds()
                        duration_minutes = duration_seconds / 60
                    else:
                        duration_minutes = 0
                    
                    # 获取 run_name
                    run_name = row.get("tags.mlflow.runName", "")
                    if pd.isna(run_name):
                        run_name = ""
                    
                    # 获取状态
                    run_status = row.get("status", "UNKNOWN")
                    
                    # 记录第一条（最新）的运行状态
                    if idx == 0:
                        latest_run_status = run_status
                    
                    run_data = {
                        "run_id": str(row["run_id"]),
                        "run_name": str(run_name),
                        "status": str(run_status),  # RUNNING/FINISHED/FAILED/KILLED
                        "start_time": start_time.isoformat() if pd.notna(start_time) else None,
                        "end_time": end_time.isoformat() if pd.notna(end_time) else None,
                        "duration_minutes": float(duration_minutes) if np.isfinite(duration_minutes) else 0
                    }
                    run_datas.append(run_data)
                    
                except Exception as e:
                    logger.warning(f"解析 run 数据失败: {e}")
                    continue
            
            # 同步最新运行状态到 TrainJob（避免状态不一致）
            if latest_run_status and train_job.status == 'running':
                status_map = {
                    'FINISHED': 'completed',
                    'FAILED': 'failed',
                    'KILLED': 'failed',
                }
                new_status = status_map.get(latest_run_status)
                
                if new_status:
                    train_job.status = new_status
                    train_job.save(update_fields=['status'])
                    logger.info(f"自动同步 TrainJob {train_job.id} 状态: running -> {new_status} (基于 MLflow: {latest_run_status})")
            
            return Response({
                'train_job_id': train_job.id,
                'train_job_name': train_job.name,
                'algorithm': train_job.algorithm,
                'job_status': train_job.status,  # 返回当前 TrainJob 状态
                'total_runs': len(run_datas),
                'data': run_datas
            })
            
        except Exception as e:
            logger.error(f"获取训练记录列表失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取训练记录失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='runs_metrics_list/(?P<run_id>.+?)')
    @HasPermission("timeseries_predict_train_jobs-View")
    def get_runs_metrics_list(self, request, run_id: str):
        """
        获取指定 run 的 Model 指标列表（过滤掉 System 指标）
        """
        try:
            # 设置 MLflow 跟踪 URI
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            
            # 创建 MLflow 客户端
            client = mlflow.tracking.MlflowClient()
            
            # 获取 run 的所有指标
            run = client.get_run(run_id)
            all_metrics = run.data.metrics.keys()
            
            # 过滤掉 system 开头的指标，只保留 Model metrics
            model_metrics = [
                metric for metric in all_metrics
                if not str(metric).startswith("system")
            ]
            
            return Response({
                'run_id': run_id,
                'metrics': model_metrics
            })
            
        except Exception as e:
            logger.error(f"获取指标列表失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取指标列表失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='runs_metrics_history/(?P<run_id>.+?)/(?P<metric_name>.+?)')
    @HasPermission("timeseries_predict_train_jobs-View")
    def get_metric_data(self, request, run_id: str, metric_name: str):
        """
        获取指定 run 的指定指标的历史数据
        """
        try:
            # 设置 MLflow 跟踪 URI
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            
            # 创建 MLflow 客户端
            client = mlflow.tracking.MlflowClient()
            
            # 获取指标历史数据
            history = client.get_metric_history(run_id, metric_name)
            
            if not history:
                return Response({
                    "run_id": run_id,
                    "metric_name": metric_name,
                    "total_points": 0,
                    "metric_history": []
                })
            
            # 检查是否所有 step 都相同（通常是 0，表示未设置 step）
            all_steps = [m.step for m in history]
            unique_steps = set(all_steps)
            
            # 如果所有 step 都相同，说明记录时未指定 step，使用 timestamp 排序
            if len(unique_steps) == 1:
                logger.info(f"指标 {metric_name} 未使用 step，按 timestamp 排序（共 {len(history)} 条）")
                metric_history = [
                    {
                        "step": idx,  # 使用序号代替 step
                        "value": m.value,
                        "timestamp": m.timestamp
                    }
                    for idx, m in enumerate(sorted(history, key=lambda x: x.timestamp))
                ]
            else:
                # 正常场景：使用 step 去重，相同 step 保留最新的值
                metric_dict = {}
                for metric in history:
                    step = metric.step
                    # 如果 step 已存在，根据 timestamp 保留最新的
                    if step in metric_dict:
                        if metric.timestamp > metric_dict[step]['timestamp']:
                            metric_dict[step] = {
                                'step': step,
                                'value': metric.value,
                                'timestamp': metric.timestamp
                            }
                    else:
                        metric_dict[step] = {
                            'step': step,
                            'value': metric.value,
                            'timestamp': metric.timestamp
                        }
                
                # 按 step 排序
                metric_history = sorted(metric_dict.values(), key=lambda x: x['step'])
            
            # 移除 timestamp（仅用于排序/去重）
            metric_history_clean = [
                {
                    "step": item['step'],
                    "value": item['value']
                }
                for item in metric_history
            ]
            
            logger.info(f"返回 {len(metric_history_clean)} 条指标数据，step 范围: {metric_history_clean[0]['step'] if metric_history_clean else 'N/A'} - {metric_history_clean[-1]['step'] if metric_history_clean else 'N/A'}")
            
            return Response({
                "run_id": run_id,
                "metric_name": metric_name,
                "total_points": len(metric_history_clean),
                "metric_history": metric_history_clean
            })
            
        except Exception as e:
            logger.error(f"获取指标历史数据失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取指标历史数据失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='run_params/(?P<run_id>.+?)')
    @HasPermission("timeseries_predict_train_jobs-View")
    def get_run_params(self, request, run_id: str):
        """
        获取指定 run 的配置参数（用于查看历史训练的配置）
        """
        try:
            # 设置 MLflow 跟踪 URI
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            
            # 创建 MLflow 客户端
            client = mlflow.tracking.MlflowClient()
            
            # 获取 run 信息
            run = client.get_run(run_id)
            
            # 获取所有参数
            params = run.data.params
            
            # 获取 run_name 和状态
            run_name = run.data.tags.get('mlflow.runName', '')
            run_status = run.info.status
            start_time = run.info.start_time
            end_time = run.info.end_time
            
            return Response({
                'run_id': run_id,
                'run_name': run_name,
                'status': run_status,
                'start_time': pd.Timestamp(start_time, unit='ms').isoformat() if start_time else None,
                'end_time': pd.Timestamp(end_time, unit='ms').isoformat() if end_time else None,
                'params': params
            })
            
        except Exception as e:
            logger.error(f"获取运行参数失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'获取运行参数失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='download_model/(?P<run_id>.+?)')
    @HasPermission("timeseries_predict_train_jobs-View")
    def download_model(self, request, run_id: str):
        """
        下载 MLflow 模型（MinIO 预签名 URL）
        
        基于 Model Registry 和 Run ID 下载模型
        返回 MinIO 预签名 URL，前端直接下载
        """
        try:
            # 1. 设置 MLflow
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            mlflow_client = mlflow.tracking.MlflowClient()
            
            # 2. 获取 run 信息
            try:
                run = mlflow_client.get_run(run_id)
            except Exception as e:
                logger.error(f"Run 不存在: {run_id} - {e}")
                return Response(
                    {'error': f'Run 不存在: {run_id}'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 3. 检查模型 artifacts 是否存在
            try:
                artifacts = mlflow_client.list_artifacts(run_id, path="model")
                if not artifacts:
                    return Response(
                        {'error': '该 Run 未保存模型，无法下载'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            except Exception as e:
                logger.error(f"获取模型 artifacts 失败: {e}")
                return Response(
                    {'error': f'获取模型 artifacts 失败: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 4. 生成文件名（基于 Model Registry）
            run_name = run.data.tags.get('mlflow.runName', 'unknown')
            algorithm = run.data.params.get('algorithm', 'unknown')
            
            # 尝试从 Model Registry 获取模型名称和版本
            model_name = None
            model_version = None
            try:
                # 检查 run 是否关联了注册模型
                model_versions = mlflow_client.search_model_versions(f"run_id='{run_id}'")
                if model_versions:
                    model_name = model_versions[0].name
                    model_version = model_versions[0].version
            except Exception as e:
                logger.warning(f"未找到注册模型信息: {e}")
            
            # 构建文件名
            if model_name and model_version:
                filename = f"{model_name}_v{model_version}.zip"
            else:
                filename = f"{algorithm}_{run_name}_{run_id[:8]}.zip"
            
            # 5. 检查 MinIO 缓存
            bucket_name = "munchkin-public"
            cache_key = f"models/cache/{run_id}.zip"
            
            minio_client = self._get_minio_client()
            
            # 尝试获取缓存的模型
            cached = False
            try:
                stat = minio_client.stat_object(bucket_name, cache_key)
                # 缓存存在，直接生成预签名 URL
                logger.info(f"模型缓存命中: {cache_key} (大小: {stat.size} 字节)")
                cached = True
                presigned_url = minio_client.presigned_get_object(
                    bucket_name,
                    cache_key,
                    expires=timedelta(hours=24)
                )
                
                return Response({
                    'status': 'success',
                    'run_id': run_id,
                    'model_info': {
                        'name': model_name or run_name,
                        'version': model_version or 'N/A',
                        'algorithm': algorithm,
                        'status': run.info.status
                    },
                    'download': {
                        'url': presigned_url,
                        'expires_at': (datetime.now() + timedelta(hours=24)).isoformat(),
                        'size_mb': round(stat.size / 1024 / 1024, 2),
                        'filename': filename,
                        'cached': True
                    }
                })
            except Exception:
                # 缓存未命中，继续打包上传流程
                logger.info(f"模型缓存未命中，开始打包: {run_id}")
            
            # 6. 下载模型到临时目录并打包
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    download_start = datetime.now()
                    logger.info(f"开始下载模型 artifacts: run_id={run_id}")
                    
                    # 优化：尝试直接从 MinIO 下载，绕过 MLflow
                    artifact_uri = run.info.artifact_uri
                    logger.info(f"Artifact URI: {artifact_uri}")
                    
                    # 解析 artifact URI 并尝试直接访问 MinIO
                    # MLflow 可能使用 mlflow-artifacts: 或 s3:// 格式
                    direct_download_success = False
                    
                    # mlflow-artifacts:/ 代理模式，使用 MLflow 下载
                    # 注: 此模式性能较慢，建议配置 MLflow --default-artifact-root s3://bucket
                    
                    if artifact_uri.startswith('s3://'):
                        # 直接是 S3 URI，可以直接解析
                        try:
                            s3_path = artifact_uri.replace('s3://', '').split('/', 1)
                            bucket = s3_path[0]
                            object_prefix = s3_path[1] if len(s3_path) > 1 else ''
                            model_prefix = f"{object_prefix}/model"
                            
                            logger.info(f"直接从 MinIO 下载: bucket={bucket}, prefix={model_prefix}")
                            
                            local_path = os.path.join(tmpdir, 'model')
                            os.makedirs(local_path, exist_ok=True)
                            
                            storage = MinioBackend(bucket_name=bucket)
                            objects = list(storage.client.list_objects(bucket, prefix=model_prefix, recursive=True))
                            
                            if objects:
                                for obj in objects:
                                    relative_path = obj.object_name[len(model_prefix):].lstrip('/')
                                    if not relative_path:
                                        continue
                                    
                                    local_file_path = os.path.join(local_path, relative_path)
                                    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
                                    storage.client.fget_object(bucket, obj.object_name, local_file_path)
                                
                                download_elapsed = (datetime.now() - download_start).total_seconds()
                                logger.info(f"模型下载完成: {local_path} (耗时: {download_elapsed:.2f}秒, 直接从MinIO)")
                                direct_download_success = True
                        except Exception as e:
                            logger.warning(f"直接从 MinIO 下载失败，降级使用 MLflow: {e}")
                    
                    # 降级：使用 MLflow 原始方法
                    if not direct_download_success:
                        logger.info(f"使用 MLflow 下载方式: {artifact_uri}")
                        local_path = mlflow.artifacts.download_artifacts(
                            run_id=run_id,
                            artifact_path="model",
                            dst_path=tmpdir
                        )
                        download_elapsed = (datetime.now() - download_start).total_seconds()
                        logger.warning(f"模型下载完成: {local_path} (耗时: {download_elapsed:.2f}秒, MLflow方式 - 较慢)")
                    
                    # 打包成 ZIP
                    zip_start = datetime.now()
                    zip_base = os.path.join(tmpdir, run_id)
                    zip_path = f"{zip_base}.zip"
                    shutil.make_archive(
                        zip_base,
                        'zip',
                        local_path
                    )
                    zip_elapsed = (datetime.now() - zip_start).total_seconds()
                    logger.info(f"模型打包完成: {zip_path} (耗时: {zip_elapsed:.2f}秒)")
                    
                    # 获取文件大小
                    file_size = os.path.getsize(zip_path)
                    logger.info(f"模型文件大小: {round(file_size / 1024 / 1024, 2)} MB")
                    
                    # 上传到 MinIO
                    upload_start = datetime.now()
                    logger.info(f"上传模型到 MinIO: {bucket_name}/{cache_key}")
                    minio_client.fput_object(
                        bucket_name,
                        cache_key,
                        zip_path,
                        content_type="application/zip"
                    )
                    upload_elapsed = (datetime.now() - upload_start).total_seconds()
                    logger.info(f"模型上传成功: {cache_key} (耗时: {upload_elapsed:.2f}秒)")
                    logger.info(f"总耗时: 下载={download_elapsed:.2f}s, 打包={zip_elapsed:.2f}s, 上传={upload_elapsed:.2f}s")
                    
                except Exception as e:
                    logger.error(f"模型打包或上传失败: {e}", exc_info=True)
                    return Response(
                        {'error': f'模型处理失败: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
            # 7. 生成预签名 URL
            presigned_url = minio_client.presigned_get_object(
                bucket_name,
                cache_key,
                expires=timedelta(hours=24)
            )
            
            # 8. 返回结果
            return Response({
                'status': 'success',
                'run_id': run_id,
                'model_info': {
                    'name': model_name or run_name,
                    'version': model_version or 'N/A',
                    'algorithm': algorithm,
                    'status': run.info.status
                },
                'download': {
                    'url': presigned_url,
                    'expires_at': (datetime.now() + timedelta(hours=24)).isoformat(),
                    'size_mb': round(file_size / 1024 / 1024, 2),
                    'filename': filename,
                    'cached': False
                },
                'instructions': '点击 URL 直接下载，链接 24 小时有效。固定版本模型会缓存，后续下载无需等待。'
            })
            
        except Exception as e:
            logger.error(f"生成模型下载链接失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'生成下载链接失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _get_minio_client(self):
        """
        获取 MinIO 客户端实例
        
        使用 MinioBackend 的内部 client 来访问原生 MinIO API
        """
        storage = MinioBackend(bucket_name="munchkin-public")
        return storage.client


class TimeSeriesPredictTrainHistoryViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainHistory.objects.all()
    serializer_class = TimeSeriesPredictTrainHistorySerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainHistoryFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_history"

    @HasPermission("timeseries_predict_train_history-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_history-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictTrainDataViewSet(ModelViewSet):
    queryset = TimeSeriesPredictTrainData.objects.all()
    serializer_class = TimeSeriesPredictTrainDataSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictTrainDataFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_train_data"

    @HasPermission("timeseries_predict_train_data-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_train_data-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='release')
    @HasPermission("timeseries_predict_train_data-Release")
    def release_file(self, request, *args, **kwargs):
        pass


class TimeSeriesPredictServingViewSet(ModelViewSet):
    queryset = TimeSeriesPredictServing.objects.all()
    serializer_class = TimeSeriesPredictServingSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictServingFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_serving"

    @HasPermission("timeseries_predict_servings-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)


class TimeSeriesPredictDatasetReleaseViewSet(ModelViewSet):
    queryset = TimeSeriesPredictDatasetRelease.objects.all()
    serializer_class = TimeSeriesPredictDatasetReleaseSerializer
    pagination_class = CustomPageNumberPagination
    filterset_class = TimeSeriesPredictDatasetReleaseFilter
    ordering = ("-id",)
    permission_key = "dataset.timeseries_predict_dataset_release"

    @HasPermission("timeseries_predict_dataset_releases-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-View")
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-Add")
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    @HasPermission("timeseries_predict_dataset_releases-Edit")
    def update(self, request, *args, **kwargs):
        return super().update(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='download')
    @HasPermission("timeseries_predict_dataset_releases-View")
    def download(self, request, *args, **kwargs):
        """
        下载数据集版本的 ZIP 文件
        """
        from django.http import FileResponse
        
        try:
            release = self.get_object()
            
            if not release.dataset_file or not release.dataset_file.name:
                return Response(
                    {'error': '数据集文件不存在'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # 获取文件
            file = release.dataset_file.open('rb')
            filename = f"{release.dataset.name}_{release.version}.zip"
            
            response = FileResponse(file, content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            logger.info(f"下载数据集版本: {release.id} - {filename}")
            
            return response
            
        except Exception as e:
            logger.error(f"下载数据集失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='archive')
    @HasPermission("timeseries_predict_dataset_releases-Edit")
    def archive(self, request, *args, **kwargs):
        """
        归档数据集版本(将状态改为 archived)
        """
        try:
            release = self.get_object()
            
            if release.status == 'archived':
                return Response(
                    {'error': '数据集版本已处于归档状态'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            release.status = 'archived'
            release.description = f"[已归档] {release.description or ''}"
            release.save(update_fields=['status', 'description'])
            
            logger.info(f"归档数据集版本: {release.id}")
            
            return Response({
                'message': '归档成功',
                'release_id': release.id
            })
            
        except Exception as e:
            logger.error(f"归档失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'归档失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'], url_path='unarchive')
    @HasPermission("timeseries_predict_dataset_releases-Edit")
    def unarchive(self, request, *args, **kwargs):
        """
        恢复已归档的数据集版本(将状态改为 published)
        """
        try:
            release = self.get_object()
            
            if release.status != 'archived':
                return Response(
                    {'error': '只能恢复已归档的数据集版本'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 移除归档标记
            original_description = release.description or ''
            if original_description.startswith('[已归档] '):
                release.description = original_description.replace('[已归档] ', '', 1)
            
            release.status = 'published'
            release.save(update_fields=['status', 'description'])
            
            logger.info(f"恢复数据集版本: {release.id} - {release.dataset.name} {release.version}")
            
            return Response({
                'message': '恢复成功',
                'release_id': release.id,
                'status': release.status
            })
            
        except Exception as e:
            logger.error(f"恢复失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'恢复失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

