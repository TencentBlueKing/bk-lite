from config.drf.viewsets import ModelViewSet
from apps.mlops.filters.timeseries_predict import *
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework import status
from rest_framework.response import Response
from django.db import transaction
from django.core.files.base import ContentFile
from django.http import FileResponse
from django_minio_backend import MinioBackend, iso_date_prefix
from apps.mlops.utils.webhook_client import WebhookClient, WebhookError, WebhookConnectionError, WebhookTimeoutError
from pathlib import Path
import requests
import os
import mlflow
import pandas as pd
import numpy as np
import tempfile
import shutil
from io import BytesIO
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
            
            logger.info(f"启动训练任务: {job_id}")
            logger.info(f"  Dataset: {train_job.dataset_version.dataset_file.name}")
            logger.info(f"  Config: {train_job.config_url.name}")
            
            # 调用 WebhookClient 启动训练
            WebhookClient.train(
                job_id=job_id,
                bucket=bucket,
                dataset=train_job.dataset_version.dataset_file.name,
                config=train_job.config_url.name,
                minio_endpoint=minio_endpoint,
                mlflow_tracking_uri=mlflow_tracking_uri,
                minio_access_key=minio_access_key,
                minio_secret_key=minio_secret_key
            )
            
            # 更新任务状态
            train_job.status = 'running'
            train_job.save(update_fields=['status'])
            
            logger.info(f"训练任务已启动: {job_id}")
            
            return Response({
                'message': '训练任务已启动',
                'job_id': job_id,
                'train_job_id': train_job.id
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"启动训练任务失败: {e}")
            return Response(
                {'error': str(e)},
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
            
            # 构建训练任务标识
            job_id = f"TimeseriesPredict_{train_job.algorithm}_{train_job.id}"
            
            logger.info(f"停止训练任务: {job_id}")
            
            # 调用 WebhookClient 停止任务（默认删除容器）
            result = WebhookClient.stop(job_id)
            
            # 更新任务状态
            train_job.status = 'pending'
            train_job.save(update_fields=['status'])
            
            logger.info(f"训练任务已停止: {job_id}")
            
            return Response({
                'message': '训练任务已停止',
                'job_id': job_id,
                'train_job_id': train_job.id,
                'webhook_response': result
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"停止训练任务失败: {e}")
            return Response(
                {'error': str(e)},
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
    
    @action(detail=False, methods=['get'], url_path='download_model/(?P<run_id>[^/]+)')
    @HasPermission("timeseries_predict_train_jobs-View")
    def download_model(self, request, run_id: str):
        """
        从 MLflow 下载模型并直接返回 ZIP 文件
        
        简化版本：直接从 MLflow 拉取 artifact → 打包 → 浏览器下载
        """
        try:
            # 1. 设置 MLflow
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            mlflow_client = mlflow.tracking.MlflowClient()
            
            # 2. 验证 run 是否存在
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
            
            # 4. 生成文件名
            run_name = run.data.tags.get('mlflow.runName', 'unknown')
            algorithm = run.data.params.get('algorithm', 'unknown')
            
            # 尝试从 Model Registry 获取模型名称和版本
            model_name = None
            model_version = None
            try:
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
            
            logger.info(f"开始下载模型: run_id={run_id}, filename={filename}")
            
            # 5. 下载模型并打包
            with tempfile.TemporaryDirectory() as tmpdir:
                try:
                    # 从 MLflow 下载 model artifact
                    logger.info(f"从 MLflow 下载模型 artifacts...")
                    local_path = mlflow.artifacts.download_artifacts(
                        run_id=run_id,
                        artifact_path="model",
                        dst_path=tmpdir
                    )
                    logger.info(f"模型下载完成: {local_path}")
                    
                    # 打包成 ZIP
                    logger.info(f"开始打包模型...")
                    zip_base = os.path.join(tmpdir, run_id)
                    shutil.make_archive(
                        zip_base,
                        'zip',
                        local_path
                    )
                    zip_path = f"{zip_base}.zip"
                    
                    # 获取文件大小
                    file_size = os.path.getsize(zip_path)
                    logger.info(f"模型打包完成: {zip_path}, 大小: {round(file_size / 1024 / 1024, 2)} MB")
                    
                    # 6. 读取文件到内存（避免 Windows 文件句柄占用问题）
                    logger.info(f"读取文件到内存...")
                    with open(zip_path, 'rb') as f:
                        file_data = f.read()
                    
                    logger.info(f"文件已读取到内存，大小: {len(file_data)} 字节")
                    
                    # 7. 使用 BytesIO 包装，文件句柄已关闭，临时目录可以正常清理
                    file_obj = BytesIO(file_data)
                    
                    response = FileResponse(
                        file_obj,
                        content_type='application/zip',
                        as_attachment=True,
                        filename=filename
                    )
                    
                    logger.info(f"模型下载请求完成: {filename}")
                    return response
                    
                except Exception as e:
                    logger.error(f"模型下载或打包失败: {e}", exc_info=True)
                    return Response(
                        {'error': f'模型处理失败: {str(e)}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
        except Exception as e:
            logger.error(f"下载模型失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'下载模型失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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
        """列表查询，实时同步容器状态"""
        response = super().list(request, *args, **kwargs)

        if isinstance(response.data, dict):
            servings = response.data.get('items', [])
        else:
            servings = response.data
        
        if not servings:
            return response
        
        serving_ids = [f"TimeseriesPredict_Serving_{s['id']}" for s in servings]
        
        try:
            # 批量查询
            result = WebhookClient.get_status(serving_ids)
            status_map = {s.get('id'): s for s in result}
            
            updates = []
            for serving_data in servings:
                serving_id = f"TimeseriesPredict_Serving_{serving_data['id']}"
                container_info = status_map.get(serving_id)
                
                if container_info:
                    # 直接使用 webhookd 响应
                    serving_data['container_info'] = container_info
                    
                    # 同步到数据库
                    serving_obj = TimeSeriesPredictServing.objects.get(id=serving_data['id'])
                    serving_obj.container_info = container_info
                    updates.append(serving_obj)
                else:
                    # webhookd 没返回这个容器的状态（不应该发生）
                    serving_data['container_info'] = {
                        "status": "error",
                        "state": "unknown",
                        "message": "webhookd 未返回此容器状态"
                    }
            
            if updates:
                TimeSeriesPredictServing.objects.bulk_update(updates, ['container_info'])
        
        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            # 降级：使用数据库中的旧值，添加错误标记
            for serving_data in servings:
                old_info = serving_data.get('container_info') or {}
                serving_data['container_info'] = {
                    **old_info,
                    "status": "error",
                    "_query_failed": True,
                    "_error": str(e)
                }
        
        return response

    @HasPermission("timeseries_predict_servings-View")
    def retrieve(self, request, *args, **kwargs):
        """详情查询，实时同步容器状态"""
        response = super().retrieve(request, *args, **kwargs)
        
        serving_id = f"TimeseriesPredict_Serving_{response.data['id']}"
        
        try:
            result = WebhookClient.get_status([serving_id])
            container_info = result[0] if result else None
            
            if container_info:
                # 直接使用 webhookd 响应
                response.data['container_info'] = container_info
                
                # 更新数据库
                TimeSeriesPredictServing.objects.filter(id=response.data['id']).update(
                    container_info=container_info
                )
            else:
                # webhookd 没返回状态
                response.data['container_info'] = {
                    "status": "error",
                    "state": "unknown",
                    "message": "webhookd 未返回容器状态"
                }
        
        except WebhookError as e:
            logger.error(f"查询容器状态失败: {e}")
            # 降级：使用数据库中的旧值，添加错误标记
            old_info = response.data.get('container_info') or {}
            response.data['container_info'] = {
                **old_info,
                "status": "error",
                "_query_failed": True,
                "_error": str(e)
            }
        
        return response

    @HasPermission("timeseries_predict_servings-Delete")
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)

    @HasPermission("timeseries_predict_servings-Add")
    def create(self, request, *args, **kwargs):
        """
        创建 serving 服务并自动启动容器
        """
        # 创建 serving 记录（初始状态为 inactive）
        response = super().create(request, *args, **kwargs)
        serving_id = response.data['id']
        
        try:
            # 获取创建的 serving 对象
            serving = TimeSeriesPredictServing.objects.get(id=serving_id)
            
            # 获取环境变量
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            if not mlflow_tracking_uri:
                logger.error("环境变量 MLFLOW_TRACKER_URL 未配置")
                serving.container_info = {
                    "status": "error",
                    "message": "环境变量 MLFLOW_TRACKER_URL 未配置"
                }
                serving.save(update_fields=['container_info'])
                response.data['container_info'] = serving.container_info
                response.data['message'] = "服务已创建但启动失败：环境变量未配置"
                return response
            
            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                logger.error(f"解析 model URI 失败: {e}")
                serving.container_info = {
                    "status": "error",
                    "message": f"解析模型 URI 失败: {str(e)}"
                }
                serving.save(update_fields=['container_info'])
                response.data['container_info'] = serving.container_info
                response.data['message'] = f"服务已创建但启动失败：{str(e)}"
                return response
            
            # 构建 serving ID
            container_id = f"TimeseriesPredict_Serving_{serving.id}"
            
            logger.info(f"自动启动 serving 服务: {container_id}, Model URI: {model_uri}, Port: {serving.port or 'auto'}")
            
            try:
                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(container_id, mlflow_tracking_uri, model_uri, port=serving.port)
                
                # 启动成功，仅更新容器信息
                serving.container_info = result
                serving.save(update_fields=['container_info'])
                
                logger.info(f"Serving 服务已自动启动: {container_id}, Port: {result.get('port')}")
                
                # 更新返回数据（status 由用户控制，不修改）
                response.data['container_info'] = result
                response.data['message'] = "服务已创建并启动"
                
            except WebhookError as e:
                error_msg = str(e)
                logger.error(f"自动启动 serving 失败: {error_msg}")
                
                # 处理容器已存在的情况（同步容器状态）
                if e.code == 'CONTAINER_ALREADY_EXISTS':
                    try:
                        result = WebhookClient.get_status([container_id])
                        container_info = result[0] if result else {
                            "status": "error",
                            "id": container_id,
                            "message": "无法查询容器状态"
                        }
                        
                        # 仅更新容器信息，不修改 status
                        serving.container_info = container_info
                        serving.save(update_fields=['container_info'])
                        
                        response.data['container_info'] = container_info
                        response.data['message'] = "服务已创建，检测到容器已存在并同步容器状态"
                        response.data['warning'] = "容器已存在，已同步容器信息"
                    except WebhookError:
                        serving.container_info = {
                            "status": "error",
                            "message": f"容器已存在但同步状态失败: {error_msg}"
                        }
                        serving.save(update_fields=['container_info'])
                        response.data['container_info'] = serving.container_info
                        response.data['message'] = "服务已创建但启动失败"
                else:
                    # 其他错误
                    serving.container_info = {
                        "status": "error",
                        "message": error_msg
                    }
                    serving.save(update_fields=['container_info'])
                    response.data['container_info'] = serving.container_info
                    response.data['message'] = f"服务已创建但启动失败: {error_msg}"
        
        except Exception as e:
            logger.error(f"自动启动 serving 异常: {str(e)}", exc_info=True)
            # 确保至少有基本的错误信息
            response.data['message'] = f"服务已创建但启动异常: {str(e)}"
        
        return response

    @HasPermission("timeseries_predict_servings-Edit")
    def update(self, request, *args, **kwargs):
        """
        更新 serving 配置，自动检测并重启容器
        
        基于实际容器运行状态决策：
        - 容器 running + 配置变更 → 自动重启
        - 容器非 running → 仅更新数据库，用户自行决定是否启动
        """
        instance = self.get_object()
        
        # 保存旧值用于判断变更
        old_port = instance.port
        old_model_version = instance.model_version
        old_train_job_id = instance.time_series_predict_train_job.id
        
        # 检测是否更新了影响容器的字段（基于请求数据与旧值对比）
        model_version_changed = (
            'model_version' in request.data and 
            str(request.data['model_version']) != str(old_model_version)
        )
        train_job_changed = (
            'time_series_predict_train_job' in request.data and 
            int(request.data['time_series_predict_train_job']) != old_train_job_id
        )
        port_changed = (
            'port' in request.data and 
            request.data.get('port') != old_port
        )
        
        container_id = f"TimeseriesPredict_Serving_{instance.id}"
        
        # 获取容器实际状态（更新前）
        container_state = instance.container_info.get('state')
        container_port = instance.container_info.get('port')
        
        # 更新数据库
        response = super().update(request, *args, **kwargs)
        instance.refresh_from_db()
        
        # 只有容器在运行时才考虑重启
        if container_state != 'running':
            return response
        
        # 决策：是否需要重启
        need_restart = False
        
        # 1. model/train_job 变更，必须重启
        if model_version_changed or train_job_changed:
            need_restart = True
        
        # 2. 仅 port 变更，检查策略
        elif port_changed:
            new_port = instance.port
            if new_port is None and old_port is not None:
                # 有值 → None：不重启（当前端口视为自动分配，下次再应用）
                need_restart = False
            elif new_port is not None and old_port is None:
                # None → 有值：需要重启（用户明确要指定端口）
                need_restart = True
            elif new_port is not None and old_port is not None:
                # 有值 → 另一个有值：检查是否与实际端口一致
                if container_port and str(new_port) != str(container_port):
                    need_restart = True
        
        # 如果需要重启，先删除旧容器
        if need_restart:
            try:
                logger.info(f"配置变更需要重启，删除旧容器: {container_id}")
                WebhookClient.remove(container_id)
                logger.info(f"旧容器已删除: {container_id}")
            except WebhookError as e:
                logger.warning(f"删除旧容器失败（可能已不存在）: {e}")
                # 继续执行，尝试启动新容器
            
            try:
                # 获取环境变量
                mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
                if not mlflow_tracking_uri:
                    raise ValueError("环境变量 MLFLOW_TRACKER_URL 未配置")
                
                # 解析新的 model_uri
                model_uri = self._resolve_model_uri(instance)
                
                logger.info(f"使用新配置启动容器: {container_id}, Model URI: {model_uri}, Port: {instance.port or 'auto'}")
                
                # 启动新容器
                result = WebhookClient.serve(container_id, mlflow_tracking_uri, model_uri, port=instance.port)
                
                # 更新容器信息（status 由用户控制，不修改）
                instance.container_info = result
                instance.save(update_fields=['container_info'])
                
                logger.info(f"新容器已启动: {container_id}, Port: {result.get('port')}")
                
                # 更新返回数据
                response.data['container_info'] = result
                response.data['message'] = "配置已更新并重启服务"
                
            except Exception as e:
                logger.error(f"自动重启失败: {str(e)}", exc_info=True)
                
                # 启动失败，仅更新容器信息
                instance.container_info = {
                    "status": "error",
                    "message": f"配置已更新但重启失败: {str(e)}"
                }
                instance.save(update_fields=['container_info'])
                
                response.data['container_info'] = instance.container_info
                response.data['message'] = f"配置已更新但重启失败: {str(e)}"
                response.data['warning'] = "请手动调用 start 接口重新启动服务"
        
        return response
    
    @action(detail=True, methods=['post'], url_path='start')
    @HasPermission("timeseries_predict_servings-Start")
    def start(self, request, *args, **kwargs):
        """
        启动 serving 服务
        """
        try:
            serving = self.get_object()
            
            # 获取环境变量
            mlflow_tracking_uri = os.getenv("MLFLOW_TRACKER_URL", "")
            if not mlflow_tracking_uri:
                return Response(
                    {'error': '环境变量 MLFLOW_TRACKER_URL 未配置'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # 解析 model_uri
            try:
                model_uri = self._resolve_model_uri(serving)
            except ValueError as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建 serving ID
            serving_id = f"TimeseriesPredict_Serving_{serving.id}"
            
            logger.info(f"启动 serving 服务: {serving_id}, Model URI: {model_uri}, Port: {serving.port or 'auto'}")
            
            try:
                # 调用 WebhookClient 启动服务
                result = WebhookClient.serve(serving_id, mlflow_tracking_uri, model_uri, port=serving.port)
                
                # 正常启动成功，仅更新容器信息
                serving.container_info = result
                serving.save(update_fields=['container_info'])
                
                logger.info(f"Serving 服务已启动: {serving_id}, Port: {result.get('port')}")
                
                return Response({
                    'message': '服务已启动',
                    'serving_id': serving_id,
                    'container_info': result
                })
                
            except WebhookError as e:
                error_msg = str(e)
                
                # 处理容器已存在的情况
                if e.code == 'CONTAINER_ALREADY_EXISTS':
                    logger.warning(f"检测到容器已存在，同步容器信息: {serving_id}")
                    try:
                        # 查询当前容器状态
                        result = WebhookClient.get_status([serving_id])
                        container_info = result[0] if result else {
                            "status": "error",
                            "id": serving_id,
                            "message": "无法查询容器状态"
                        }
                        
                        # 仅更新容器信息，不修改 status
                        serving.container_info = container_info
                        serving.save(update_fields=['container_info'])
                        
                        logger.info(f"容器信息已同步: {container_info.get('state')}")
                        
                        return Response({
                            'message': '检测到容器已存在，已同步容器信息',
                            'container_info': container_info,
                            'warning': '容器已存在'
                        })
                    except WebhookError as sync_error:
                        logger.error(f"同步容器状态失败: {sync_error}")
                        return Response(
                            {'error': f'容器已存在但同步状态失败: {sync_error}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                else:
                    # 其他错误直接返回
                    logger.error(f"启动 serving 失败: {error_msg}")
                    return Response(
                        {'error': error_msg},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"启动 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'启动服务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='stop')
    @HasPermission("timeseries_predict_servings-Stop")
    def stop(self, request, *args, **kwargs):
        """
        停止 serving 服务（停止并删除容器）
        """
        try:
            serving = self.get_object()
            
            # 构建 serving ID
            serving_id = f"TimeseriesPredict_Serving_{serving.id}"
            
            logger.info(f"停止 serving 服务: {serving_id}")
            
            # 调用 WebhookClient 停止服务（默认删除容器）
            result = WebhookClient.stop(serving_id)
            
            logger.info(f"Serving 服务已停止: {serving_id}")
            
            return Response({
                'message': '服务已停止并删除',
                'serving_id': serving_id,
                'webhook_response': result
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"停止 serving 失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"停止 serving 服务失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'停止服务失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='remove')
    @HasPermission("timeseries_predict_servings-Remove")
    def remove(self, request, *args, **kwargs):
        """
        删除 serving 容器（可处理运行中的容器）
        """
        try:
            serving = self.get_object()
            
            # 构建 serving ID
            serving_id = f"TimeseriesPredict_Serving_{serving.id}"
            
            logger.info(f"删除 serving 容器: {serving_id}")
            
            # 调用 WebhookClient 删除容器
            result = WebhookClient.remove(serving_id)
            
            # 更新容器信息（status 由用户控制，不修改）
            serving.container_info = {
                "status": "success",
                "id": serving_id,
                "state": "removed",
                "message": "容器已删除"
            }
            serving.save(update_fields=['container_info'])
            
            logger.info(f"Serving 容器已删除: {serving_id}")
            
            return Response({
                'message': '容器已删除',
                'serving_id': serving_id,
                'webhook_response': result
            })
            
        except WebhookTimeoutError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookConnectionError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except WebhookError as e:
            logger.error(f"删除容器失败: {e}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"删除 serving 容器失败: {str(e)}", exc_info=True)
            return Response(
                {'error': f'删除容器失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], url_path='predict')
    @HasPermission("timeseries_predict_servings-Predict")
    def predict(self, request, *args, **kwargs):
        """
        调用 serving 服务进行时间序列预测
        
        URL: POST /api/v1/mlops/timeseries_predict_servings/{pk}/predict/
        
        请求参数:
            url: 预测服务主机地址（如 http://192.168.1.100，不含端口）
            data: 历史时间序列数据数组 [{"timestamp": "...", "value": ...}, ...]
            steps: 预测步数（默认 10）
        
        返回格式:
            预测服务的响应（通常为 {"success": true, "history": [...], "prediction": [...], "metadata": {...}, "error": null}）
        """
        try:
            serving = self.get_object()
            
            # 获取参数
            url = request.data.get('url')
            data = request.data.get('data')
            steps = request.data.get('steps', 10)
            
            # 参数校验
            if not url:
                return Response(
                    {'error': 'url 参数不能为空'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not data:
                return Response(
                    {'error': 'data 参数不能为空'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if not isinstance(data, list):
                return Response(
                    {'error': 'data 必须是数组格式'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 获取实际运行端口
            port = serving.container_info.get('port')
            if not port:
                return Response(
                    {'error': '服务端口未配置，请确认服务已启动'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # 构建预测服务 URL
            # url: http://192.168.1.100 + port: 38291 -> http://192.168.1.100:38291/predict
            predict_url = f"{url.rstrip('/')}:{port}/predict"
            
            # 构建请求体
            payload = {
                "data": data,
                "config": {"steps": steps}
            }
            
            logger.info(f"调用预测服务: serving_id={serving.id}, url={predict_url}, steps={steps}, data_size={len(data)}")
            
            # 发起 HTTP POST 请求
            response = requests.post(
                predict_url,
                json=payload,
                timeout=60,
                headers={'Content-Type': 'application/json'}
            )
            
            # 处理响应
            if response.status_code == 200:
                result = response.json()
                # 安全获取 prediction 长度（处理 None 值）
                prediction = result.get('prediction') or []
                prediction_size = len(prediction) if isinstance(prediction, (list, tuple)) else 0
                logger.info(f"预测成功: serving_id={serving.id}, prediction_size={prediction_size}")
                return Response(result)
            else:
                error_msg = f"预测服务返回错误: HTTP {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg = f"{error_msg} - {error_detail}"
                except Exception:
                    error_msg = f"{error_msg} - {response.text[:200]}"
                
                logger.error(f"预测失败: {error_msg}")
                return Response(
                    {'error': error_msg},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        except requests.exceptions.Timeout:
            error_msg = f'预测请求超时（超过 60 秒）'
            logger.error(f"预测超时: serving_id={serving.id}, url={predict_url}")
            return Response(
                {'error': error_msg},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.ConnectionError as e:
            error_msg = f'无法连接预测服务: {str(e)}'
            logger.error(f"预测连接失败: serving_id={serving.id}, url={predict_url}, error={e}")
            return Response(
                {'error': error_msg},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except requests.exceptions.RequestException as e:
            error_msg = f'预测请求异常: {str(e)}'
            logger.error(f"预测请求异常: serving_id={serving.id}, error={e}", exc_info=True)
            return Response(
                {'error': error_msg},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            logger.error(f"预测失败: serving_id={serving.id}, error={str(e)}", exc_info=True)
            return Response(
                {'error': f'预测失败: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _resolve_model_uri(self, serving):
        """
        解析 MLflow Model URI
        
        Args:
            serving: TimeSeriesPredictServing 实例
        
        Returns:
            str: MLflow model URI，如 "models:/TimeseriesPredict_Prophet_1/28"
        
        Raises:
            ValueError: 解析失败时抛出
        """
        train_job = serving.time_series_predict_train_job
        model_name = f"TimeseriesPredict_{train_job.algorithm}_{train_job.id}"
        
        if serving.model_version == "latest":
            # 查询最新版本
            mlflow.set_tracking_uri(MLFLOW_TRACKER_URL)
            client = mlflow.tracking.MlflowClient()
            
            try:
                # 搜索模型的所有版本
                versions = client.search_model_versions(f"name='{model_name}'")
                if not versions:
                    raise ValueError(f"模型 {model_name} 没有已注册的版本")
                
                # 获取最新版本号
                latest_version = max([int(v.version) for v in versions])
                logger.info(f"解析 latest 版本: {model_name} -> {latest_version}")
                return f"models:/{model_name}/{latest_version}"
                
            except Exception as e:
                raise ValueError(f"无法解析 latest 版本: {e}")
        else:
            # 直接使用指定版本
            return f"models:/{model_name}/{serving.model_version}"


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

