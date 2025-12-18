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
            minio_access_key = os.getenv("MINIO_ACCESS_KEY", "")
            minio_secret_key = os.getenv("MINIO_SECRET_KEY", "")
            
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
            logger.info(f"  'minio_access_key': '***',")
            logger.info(f"  'minio_secret_key': '***'")
            
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
                    if pd.notna(start_time) and pd.notna(end_time):
                        duration_seconds = (end_time - start_time).total_seconds()
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
            
            # 构建指标历史列表（使用字典去重，相同 step 保留最新的值）
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
            
            # 按 step 排序并移除 timestamp（仅用于去重）
            metric_history = [
                {
                    "step": item['step'],
                    "value": item['value']
                }
                for item in sorted(metric_dict.values(), key=lambda x: x['step'])
            ]
            
            logger.info(f"返回 {len(metric_history)} 条指标数据，step 范围: {metric_history[0]['step'] if metric_history else 'N/A'} - {metric_history[-1]['step'] if metric_history else 'N/A'}")
            
            return Response({
                "run_id": run_id,
                "metric_name": metric_name,
                "total_points": len(metric_history),
                "metric_history": metric_history
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

